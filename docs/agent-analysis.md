# Project Technical Analysis

## Summary

This repository is a Python `src`-layout LiveKit voice tutor. It runs a real-time speech pipeline,
loads an English chapter lesson catalog and one lesson plan at a time from Bunny Storage, guides the
student through ordered topics, synchronizes lesson, topic, scroll, and teaching-board state with a
frontend, and records telemetry and cost data in Langfuse.

The implemented tutoring model is `LessonPlan -> Topic`. Historical chapter-wide unit, segment, and
rendered-prompt artifacts are not part of the runtime content path.

## Repository Shape

```text
tutor-agent-snd/
|-- src/tutor_agent_snd/
|   |-- main.py
|   |-- __main__.py
|   |-- domain_types.py
|   |-- agents/tutor_agent.py
|   `-- utils/
|       |-- agent_observation.py
|       |-- bunny.py
|       |-- parse_dynamic_prompt.py
|       `-- plan_helpers.py
|-- prompts/snd-agent-system-prompt-v2.md
|-- contexts/handoff/CONTENT_PIPELINE_INTEGRATION_SPEC.md
|-- docs/
|-- tests/
|-- pyproject.toml
|-- livekit.toml
|-- Dockerfile
`-- README.md
```

`contexts/` contains local authoring inputs, outputs, historical handoff assets, and skills. The
current runtime consumes Bunny-hosted course metadata, `lessons_list.json`, and per-lesson JSON. It
does not load local context files directly.

## Entrypoint And Session Lifecycle

The installed command is defined by `pyproject.toml`:

```text
tutor-agent = "tutor_agent_snd.main:main"
```

`main()` calls `agents.cli.run_app()` with the `entrypoint()` function from
`src/tutor_agent_snd/main.py`. The command supports LiveKit Agents modes such as `console`, `dev`,
`start`, and `download-files`.

At module import, `load_dotenv(".env")` loads local configuration. Runtime settings include:

| Setting | Default | Purpose |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | Provider order, prompt label, and recording eligibility. |
| `MAX_SESSION_DURATION` | `1800` | Session watchdog duration in seconds; `0` disables it. |

For each room, `entrypoint(ctx)`:

1. Records session start time and decides production-only probabilistic recording.
2. Connects with `AutoSubscribe.AUDIO_ONLY` and waits for the first participant.
3. Reads participant attributes.
4. Builds the dynamic prompt and ordered lesson slug list.
5. Configures LLM, STT, TTS, VAD, turn handling, and noise cancellation.
6. Configures Langfuse tracing and retrieves the environment-selected system prompt.
7. Starts `AgentSession` with `Assistant`.
8. Starts the session watchdog when enabled.
9. Calculates costs, creates Langfuse scores, and flushes telemetry during shutdown.

Participant attributes:

| Attribute | Default | Meaning |
| --- | --- | --- |
| `course_id` | `phys_1040` | Bunny course folder. |
| `chapter_id` | `ch_1` | Bunny chapter folder. |
| `language` | `Arabic` | Student-facing language and STT/TTS language mapping. |
| `user_name` | `undefined` | Greeting and observability metadata. |
| `user_id` | `undefined` | Observability user identifier suffix. |

## Voice Pipeline

The active `AgentSession` configuration in `main.py` is:

| Component | Implementation | Current settings |
| --- | --- | --- |
| STT | `deepgram.STT` | Model `nova-3`; `English -> en`, `Arabic -> ar`. |
| LLM | `agents.llm.FallbackAdapter` over Cerebras | `gemma-4-31b` and `zai-glm-4.7`, temperature `0.3`, parallel tool calls disabled, one retry per model. |
| TTS | `agents.tts.FallbackAdapter` | ElevenLabs `eleven_flash_v2_5` and Cartesia `sonic-3.5`, one retry per TTS. |
| VAD | `silero.VAD.load()` | Activation threshold `0.6`, minimum speech duration `0.3`. |
| Turn handling | `TurnHandlingOptions` | STT detection, dynamic endpointing `0.4` to `2.5` seconds, adaptive interruptions, preemptive generation disabled. |
| Noise cancellation | `noise_cancellation.BVC()` | Applied to room audio input. |
| Tool loop | `AgentSession` | Maximum eight tool steps. |
| Text output | Disabled | Student-facing output is audio plus UI data events. |

Production LLM order is Gemma then ZAI; non-production order is reversed. Production TTS order is
ElevenLabs then Cartesia. The current non-production branch passes ElevenLabs twice rather than the
Cartesia fallback.

TTS availability changes are logged as warnings.

## Dynamic Prompt Assembly

`parse_d_prompt(user_name, course_id, chapter_id, language)` fetches:

| Bunny path | Purpose |
| --- | --- |
| `courses/{course_id}/01_Course_Knowledge_Schema.md` | Course metadata and structure. |
| `courses/{course_id}/{chapter_id}/lessons_list.json` | Chapter metadata and ordered English lesson catalog. |

The catalog shape is:

```json
{
  "chapter": "Chapter title",
  "chapter_number": 1,
  "number_of_lessons": 2,
  "lessons": [
    {
      "name": "English lesson name",
      "brief": "English lesson brief.",
      "slug": "lesson_slug"
    }
  ]
}
```

The parser requires a non-empty lesson list, count equality, non-empty `name`, `brief`, and `slug`,
and unique slugs. It returns a tuple containing the dynamic prompt and ordered lesson slugs.

The dynamic prompt includes user information, full course metadata, chapter title and number, each
lesson's name, brief, and slug, and the selected output language. The slugs are the only valid
values for `get_lesson_plan(lesson)`.

## System Prompt Deployment

The runtime retrieves:

```text
prompt name: snd-agent-system-prompt
development label: latest
production label: production
```

Final instructions are the remote system prompt followed by the dynamic prompt.

`prompts/snd-agent-system-prompt-v2.md` is a complete repository review artifact for the current
lesson/topic behavior. The runtime does not read this file. An operator must manually create the
corresponding Langfuse prompt version and promote it when approved. This repository documentation
change does not modify Langfuse.

## Assistant State And Tools

`Assistant` owns:

| State | Purpose |
| --- | --- |
| `lesson_slugs` | Ordered approved lessons from the chapter catalog. |
| `current_plan` | Active `LessonPlan` or `None`. |
| `checkpoint_answers_counter` | Failed attempts for the active authored question. |
| board visibility, title ID, content IDs, emphasis ID | Server-side semantic board state. |

On entry, the agent asks the model to greet the user by name and ask them to choose a lesson from
the on-screen list without reading examples aloud.

Model-callable tools:

| Tool | Purpose |
| --- | --- |
| `get_lesson_plan(lesson)` | Load an approved lesson, publish lesson state, and activate its first topic. |
| `advance_to_next_topic()` | Complete a questionless topic after the student is ready. |
| `check_topic_understanding(student_understood)` | Record semantic evaluation of an answer to an authored question. |
| `update_teaching_board(action, text, item_id)` | Apply a short semantic board update without changing progress. |

`_start_topic`, `_finish_current_topic`, and frontend publishing methods are internal helpers.

## Lesson Plan Model

Lesson files are fetched from:

```text
courses/{course_id}/{chapter_id}/{lesson_slug}.json
```

Top-level keys are exactly:

```text
lesson_slug, title, lesson_sequence_number, total_topics, topics
```

Every topic has exactly:

```text
id, title, sequence, requires_completion_of, action, content, question
```

`parse_plan()` rejects missing and extra keys. It also validates non-empty strings, positive counts,
topic count equality, unique topic IDs, contiguous topic sequences matching list order, and
prerequisites that reference earlier topics.

`action` is either `null` or exactly a `scroll` object with a positive integer page. `question` is
either `null` or an exact six-key object containing `id`, `type`, `question`, `expected_answer`,
`choices`, and `reexplain_guide`.

The removed topic fields `markers`, `agent_guidance`, `visual_description`, and `strategy` are
explicitly rejected. There is no `schema_version` and no compatibility conversion.

### Opaque Topic Content

`content` is one required non-empty English string containing facts and all explanation guidance.
It can use Markdown-like authoring and can describe teaching-board use or identify technical terms
in ordinary prose. It is not runtime-parsed and is not fixed spoken wording.

`format_topic_content()` returns content unchanged. For a topic with a question, it appends a fixed
private assessment packet containing the authored question, expected answer, choices, and
re-explanation guide. For a questionless topic, it returns content only.

### In-Memory State

`LessonPlan.current_topic_index` starts at `-1` and becomes `sequence - 1` on activation. Topics
track `started` and `completed`; questions track `student_responded` and `completed`. These fields
are runtime-only and are not valid JSON keys.

## Progression Behavior

### Lesson loading

`get_lesson_plan` validates the requested slug before fetching, parses the complete plan, verifies
the plan slug and catalog sequence, clears the board, sets the active plan, publishes `set_lesson`,
and starts the first topic.

### Topic activation

`_start_topic` resets retries, checks prerequisites and pending assessment state, marks the topic
started, publishes `set_topic`, performs an optional scroll, and returns model context.

### Assessed topic

The model asks the authored question after teaching and compares the response semantically with the
private expected answer. It calls `check_topic_understanding` only for an actual answer.

On success, the runtime completes the topic immediately. The first unsuccessful attempt returns the
authored re-explanation guide and keeps the topic active. The second unsuccessful attempt completes
the topic and tells the model to explain the authored correct answer before continuing with the
already-returned next state.

### Questionless topic

The model completes the explanation, asks whether the student is ready, and calls
`advance_to_next_topic` only after readiness. The assessment tool rejects questionless topics, and
the advancement tool rejects topics with questions.

### Lesson and chapter completion

Within a lesson, successful completion activates and returns the next topic. At the final topic, the
runtime returns the next lesson slug but does not load it. The next lesson requires a separate
`get_lesson_plan` call. The final topic of the final lesson returns chapter completion.

## Language Contract

All catalog and plan content is English. The participant's `language` selects English or Arabic
student-facing output.

For Arabic output, the repository prompt directs the tutor to explain in Arabic, introduce each
listed technical term once with its Arabic meaning and English form, and use only the English term
after that. For example: `التزام الأداء (performance obligation)`, followed later by
`performance obligation`. The tutor must not expose assessment packet or tool labels.

## Frontend Data Contract

All frontend messages are JSON strings published with `reliable=True` on topic `ui-control`.

| Action | Key payload fields | Trigger |
| --- | --- | --- |
| `set_lesson` | `lesson`, `number_of_topics` | Valid lesson loaded. |
| `set_topic` | `topic`, `current_topic_index`, `question`, `choices` | Topic activated. |
| `topic_done` | `topic` | Topic completed. |
| `scroll` | `page` | Topic has a scroll action. |
| `board_show` | none | Board shown. |
| `board_hide` | none | Board hidden. |
| `board_clear` | none | Board content cleared. |
| `board_set_title` | `id`, `text` | Title created or replaced. |
| `board_add_bullet` | `id`, `text` | Bullet appended. |
| `board_add_text` | `id`, `text` | Text appended. |
| `board_add_step` | `id`, `text` | Step appended. |
| `board_emphasize` | `id` | Existing item emphasized. |
| `session_ending` | `message` | Session duration watchdog expires. |

`set_topic.topic` and `topic_done.topic` contain the human-readable topic title. Board item IDs are
opaque values generated by the backend.

See `docs/explanation-plan-execution.md` for exact payload examples.

## Teaching Board Behavior

The board supports `show`, `hide`, `clear`, `set_title`, `add_bullet`, `add_text`, `add_step`, and
`emphasize` model actions. A title or content add automatically shows the board. Hiding preserves
content. Clearing preserves visibility but removes content and emphasis.

The backend permits one title, six non-title content items, 80 title characters, and 180 characters
per content item. New items receive generated IDs; only an existing generated ID can be emphasized.
Successful board updates do not advance the topic and should be followed by continued explanation.

Board publication checks `RunContext` interruption state. An interrupted update is not retried in
the same turn and must not be described as successful.

## Bunny Storage Integration

`fetch_md_from_bunny(file_path)` is the shared async storage helper. It rejects absolute paths,
parent traversal, and null bytes, then performs an HTTP GET with a 20-second timeout and calls
`raise_for_status()`.

The URL is:

```text
https://{BUNNY_STORAGE_REGION}/{BUNNY_STORAGE_ZONE}/{file_path}
```

Configuration:

| Variable | Purpose |
| --- | --- |
| `BUNNY_STORAGE_ZONE` | Storage zone path segment. |
| `BUNNY_STORAGE_API_KEY` | `AccessKey` request header. |
| `BUNNY_STORAGE_REGION` | Storage host prefix; defaults to `storage`. |

## Observability And Cost Accounting

Langfuse setup requires `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` or
`LANGFUSE_BASE_URL`. Session metadata includes room/session ID, user name and ID, and environment.
Prompt name and version are attached to LiveKit telemetry.

`collect_custom_metrics()` handles model metric events and adds custom TTS spans.
`calculate_cost()` estimates provider usage from the local pricing table. Shutdown adds base
per-minute session costs, optional recording cost, model usage, and stores total cost and duration as
Langfuse scores before flushing.

## Configuration And Deployment

The project targets Python 3.10 or later. Black and Ruff use a 100-character line length, and MyPy
targets Python 3.10 with missing imports ignored.

Important environment variables:

| Variable | Purpose |
| --- | --- |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | LiveKit room and deployment access. |
| `DEEPGRAM_API_KEY` | Active STT. |
| `CEREBRAS_API_KEY` | Active LLM providers. |
| `ELEVEN_API_KEY` | ElevenLabs TTS. |
| `CARTESIA_API_KEY` | Cartesia TTS. |
| `BUNNY_STORAGE_ZONE`, `BUNNY_STORAGE_API_KEY`, `BUNNY_STORAGE_REGION` | Content loading. |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | Tracing and prompt retrieval. |
| `ENVIRONMENT` | Provider and prompt-label selection. |
| `MAX_SESSION_DURATION` | Session watchdog. |

The Docker image installs locked dependencies, installs the package, runs as a non-root user,
downloads LiveKit model files, and starts:

```bash
uv run tutor-agent start
```

## Quality Commands

```bash
uv run black .
uv run ruff check .
uv run mypy .
uv run pytest
```

## Engineering Considerations

- Session startup depends on LiveKit, voice providers, Bunny Storage, and Langfuse.
- The deployed system prompt remains remote and can differ from the repository v2 review artifact
  until an operator manually deploys it.
- The model supplies the correctness boolean for authored questions; application code does not grade
  answers deterministically.
- Question `type` is a non-empty string but is not restricted to an enum by the parser.
- Free-form content has no runtime sub-schema, so content QA must verify factual coverage and
  guidance quality before upload.
- The frontend `ui-control` payload names are an external contract and must remain synchronized with
  the web client.
- The current non-production TTS fallback list repeats ElevenLabs rather than using Cartesia.
- No schema version or old content adapter exists; incompatible artifacts must be regenerated.

## Mental Model

Treat the repository as a thin orchestration layer around LiveKit Agents. LiveKit owns real-time
audio transport and model orchestration. The project-specific core is the deterministic lesson/topic
state machine: it validates approved Bunny content, supplies one topic to the model, distinguishes
optional assessment from readiness-based progression, sends frontend events, supports a semantic
teaching board, and records operational telemetry.
