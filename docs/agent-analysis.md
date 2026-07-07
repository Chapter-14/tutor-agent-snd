# Project Technical Analysis

This project is a Python `src/`-layout LiveKit voice tutoring agent. It joins a LiveKit room, runs a real-time speech pipeline, fetches course and topic plans from Bunny Storage, guides the learner through structured explanation sections, synchronizes frontend UI state over LiveKit data messages, and records observability/cost data in Langfuse.

## Repository Shape

```text
tutor-agent-snd/
├── src/tutor_agent_snd/
│   ├── main.py                    # LiveKit worker entrypoint and voice pipeline wiring
│   ├── __main__.py                # Enables python -m tutor_agent_snd
│   ├── domain_types.py            # Dataclasses for plans, sections, questions, UI markers
│   ├── agents/tutor_agent.py      # Assistant agent, tutoring tools, UI publishing helpers
│   └── utils/
│       ├── agent_observation.py   # Langfuse setup, custom metric spans, usage cost calculation
│       ├── bunny.py               # Bunny Storage HTTP fetch helper
│       ├── parse_dynamic_prompt.py # Runtime prompt assembly from course metadata/topic list
│       └── plan_helpers.py        # Explanation-plan parsing and section prompt formatting
├── tests/test_observations.py     # Unit tests for usage cost calculation
├── docs/                          # Architecture, data-model, and execution notes
├── pyproject.toml                 # Package metadata, dependencies, lint/test/type config
├── livekit.toml                   # LiveKit Cloud project/agent IDs
├── Dockerfile                     # Container build for LiveKit agent deployment
└── README.md                      # Setup and runtime instructions
```

The current source of truth is the code under `src/tutor_agent_snd`. Some existing docs and README sections still describe older defaults, such as OpenAI as the active LLM or `lib/` paths; the runtime currently uses the `utils/` package and Cerebras-based LLM configuration.

## Runtime Entry Point

The installed command is defined in `pyproject.toml`:

```text
tutor-agent = "tutor_agent_snd.main:main"
```

`main()` calls `agents.cli.run_app()` with `entrypoint()` from `src/tutor_agent_snd/main.py`. This means the same binary supports LiveKit Agents CLI subcommands such as `console`, `dev`, `start`, and `download-files`.

At process import time, `load_dotenv(".env")` loads local environment values. Two top-level settings are then read:

| Setting | Default | Used For |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | Provider fallback ordering, prompt label selection, and whether sessions may be recorded. |
| `MAX_SESSION_DURATION` | `1800` | Maximum session length in seconds; `0` disables the watchdog. |

## Session Lifecycle

`entrypoint(ctx)` performs the full per-room setup:

1. Records `session_start_time` for duration and cost metrics.
2. Decides whether to record the session. Recording is only considered in production, with a 30% probability.
3. Connects to the LiveKit room with `AutoSubscribe.AUDIO_ONLY`.
4. Waits for the first participant and reads these participant attributes:

| Attribute | Default | Meaning |
| --- | --- | --- |
| `course_id` | `phys_1040` | Bunny course folder. |
| `chapter_id` | `ch_1` | Bunny chapter folder. |
| `language` | `Arabic` | Output language and STT/TTS language mapping. |
| `user_name` | `undefined` | Personalization and Langfuse user metadata. |
| `user_id` | `undefined` | Langfuse user metadata suffix. |

5. Calls `parse_d_prompt()` to assemble the dynamic tutor prompt and count chapter topics.
6. Configures LLM, STT, TTS, VAD, turn handling, noise cancellation, and fallback providers.
7. Initializes Langfuse tracing and loads the `snd-agent-system-prompt` prompt from Langfuse.
8. Starts an `AgentSession` with an `Assistant` instance.
9. Starts `_session_watchdog()` when `MAX_SESSION_DURATION > 0`.

When the process shuts down, `flush_trace()` calculates total session cost, creates Langfuse scores for `total_session_cost` and `total_session_time`, and force-flushes the tracer provider.

## Voice Pipeline

The active `AgentSession` is configured as follows:

| Component | Implementation | Important Settings |
| --- | --- | --- |
| STT | `deepgram.STT` | Model `nova-3`, language mapped from `English -> en`, `Arabic -> ar`, fallback default `en`. |
| LLM | `agents.llm.FallbackAdapter` over Cerebras LLMs | Production order: `zai-glm-4.7`, then `gpt-oss-120b`; non-production order is reversed. Temperature is `0.3`; max retry per LLM is `1`. |
| TTS | `agents.tts.FallbackAdapter` over ElevenLabs and Cartesia | Production order: ElevenLabs `eleven_flash_v2_5`, then Cartesia `sonic-3.5`; non-production order is reversed. |
| VAD | `silero.VAD.load()` | `activation_threshold=0.6`, `min_speech_duration=0.3`. |
| Turn handling | LiveKit `TurnHandlingOptions` | STT turn detection, dynamic endpointing from `0.4s` to `2.5s`, adaptive interruption, preemptive generation disabled. |
| Noise cancellation | `noise_cancellation.BVC()` | Applied to room audio input. |
| Text output | Disabled | `text_output=False`; the user-facing modality is audio plus frontend data messages. |

The TTS fallback emits `tts_availability_changed` events that are logged as warnings.

## Prompt Assembly

`parse_d_prompt(user_name, course_id, chapter_id, language)` builds dynamic instructions by fetching two Bunny Storage files:

| Bunny Path | Purpose |
| --- | --- |
| `courses/{course_id}/01_Course_Knowledge_Schema.md` | Course-level metadata and structure. |
| `courses/{course_id}/{chapter_id}/topics_list.json` | Current chapter title, number, topic list, topic slugs, and `number_of_topics`. |

The returned dynamic prompt includes user info, course metadata, current chapter info, an ordered list of topic names/slugs, and an instruction that all responses must be in the selected language. The topic slugs are the values the agent must pass into `get_explanation_plan(topic)`.

The base system prompt is not stored in this repository. It is fetched from Langfuse using:

```text
name: snd-agent-system-prompt
label: latest      # non-production
label: production  # production
```

The final agent instructions are `system_prompt + dynamic_prompt`.

## Assistant Agent Behavior

`Assistant` extends `livekit.agents.Agent`. It owns the room context, course/chapter IDs, total topic count, the currently loaded `ExplanationPlan`, and a retry counter for checkpoint answers.

On `on_enter()`, it asks the model to greet the learner by name and ask them to choose a topic from the on-screen list or ask another question.

The agent exposes two model-callable tools:

| Tool | Purpose |
| --- | --- |
| `get_explanation_plan(topic: str)` | Fetches a topic plan JSON from Bunny, parses it, publishes the current topic to the frontend, starts the first section, and returns instructions for the model to begin teaching. |
| `check_user_understanding(student_understood: bool)` | Must be called after every checkpoint answer. It marks sections complete, advances to the next section/topic, requests re-explanation, or ends the chapter. |

`_start_section(section_id)` is an internal helper, not currently decorated as a model-callable tool. It validates the plan and prerequisites, prevents skipping away from an incomplete current checkpoint, marks the section started, publishes section state and marker updates, performs optional scroll, and returns formatted section guidance to the LLM.

## Explanation Plan Model

Plans are JSON documents fetched from:

```text
courses/{course_id}/{chapter_id}/{topic}.json
```

`parse_plan()` validates top-level keys and required section keys, then converts the JSON into dataclasses from `domain_types.py`.

### Top-Level Plan

| Field | Type | Notes |
| --- | --- | --- |
| `topic` | `str` | Topic slug/name from the plan. |
| `title` | `str` | Human-readable plan title. |
| `topic_sequence_number` | `int` | One-based topic order within the chapter. |
| `total_sections` | `int` | Declared number of sections. |
| `sections` | `list[Section]` | Ordered content sections. |
| `current_section_index` | `int` | Runtime-only zero-based index, initially `-1`. |

`ExplanationPlan.current_section` safely returns the active section or `None`. `ExplanationPlan.is_complete` returns `True` only when every section is completed.

### Section

Required JSON keys are `id`, `title`, `sequence`, `agent_guidance`, `visual_description`, and `strategy`. Optional keys include `requires_completion_of`, `action`, `markers`, and `question`.

At runtime, each section also tracks `completed` and `started`. `sequence` is treated as one-based, and `_start_section()` maps it to `current_section_index = sequence - 1`.

`format_section_prompt()` converts a section into LLM instructions containing section title, tone, visual description, numbered strategy points, and optional checkpoint question/expected answer.

### Question

Questions include `id`, `type`, `question`, `expected_answer`, `choices`, and `reexplain_guide`, plus runtime `completed` and `student_responded` booleans. The current logic treats `check_understanding` questions specially only in the success message; other question types still complete the section when `student_understood=True`.

If the learner does not understand, the agent asks for re-explanation using `reexplain_guide`. After two failed attempts, it marks the section complete and instructs the model to explain the correct answer before continuing.

### UI Markers and Actions

Sections may define:

| Model | Fields | Runtime Effect |
| --- | --- | --- |
| `SectionAction` | `type`, optional `page` | Currently used for `scroll` actions. |
| `UpdateUIMarkers` | `add`, `remove` | Marker removals are published before additions. |
| `UIMarker` | `id`, `type`, `page`, `span_id`, `delay` | Frontend marker rendering metadata. |

The code does not validate marker type values beyond requiring the fields to exist.

## Frontend Data Contract

All frontend control messages use LiveKit `publish_data()` with `reliable=True` and topic `ui-control`. Payloads are JSON strings with an `action` field.

Current payloads emitted by the implementation are:

### Session Ending

```json
{"action": "session_ending", "message": "Session ending due to time limit."}
```

Sent by the watchdog before `session.shutdown(drain=True)`.

### Scroll

```json
{"action": "scroll", "page": 5}
```

Sent when a section action has `type == "scroll"` and a `page` value.

### Topic Change

```json
{"action": "set_topic", "topic": "topic-slug", "number_of_sections": 4}
```

Sent after loading an explanation plan.

### Section Change

```json
{
  "action": "set_section",
  "section": "Section Title",
  "current_section_index": 1,
  "question": "Checkpoint question text",
  "choices": ["A", "B", "C", "D"]
}
```

Sent whenever a section starts. The index is one-based for frontend display.

### Section Done

```json
{"action": "section_done", "section": "Section Title"}
```

Sent when the active question/section is marked complete.

### Add Markers

```json
{
  "action": "add_markers",
  "add": {
    "m_5_123": {"type": "highlight", "page": 5, "span_id": 123, "delay": 500}
  }
}
```

### Remove Markers

```json
{"action": "remove_markers", "remove": ["m_5_123"]}
```

Existing docs mention `markers` and `set_checkpoint` payloads in places, but the current code emits `add`/`remove` and includes the checkpoint question inside `set_section`.

## Bunny Storage Integration

`fetch_md_from_bunny(file_path)` is the single storage helper. It rejects paths containing `..`, absolute paths, or null bytes, then performs an async HTTP GET:

```text
https://{BUNNY_STORAGE_REGION}/{BUNNY_STORAGE_ZONE}/{file_path}
```

The request includes the `AccessKey` header from `BUNNY_STORAGE_API_KEY`, uses a 20-second timeout, calls `raise_for_status()`, and returns response text.

Required Bunny environment variables are:

| Variable | Purpose |
| --- | --- |
| `BUNNY_STORAGE_ZONE` | Storage zone path segment. |
| `BUNNY_STORAGE_API_KEY` | Bunny Storage access key. |
| `BUNNY_STORAGE_REGION` | Host prefix, defaulting to `storage`. |

## Observability and Cost Accounting

Langfuse is required by `setup_langfuse()`. Missing `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, or `LANGFUSE_HOST`/`LANGFUSE_BASE_URL` raises a `ValueError` during session startup.

Langfuse metadata includes:

| Key | Value |
| --- | --- |
| `langfuse.session.id` | LiveKit room name. |
| `langfuse.user.name` | Participant `user_name`. |
| `langfuse.user.id` | Slugified user name plus a suffix from `user_id[20:]`. |
| `langfuse.environment` | `ENVIRONMENT`. |

The code sets LiveKit telemetry to the same tracer provider and attaches prompt name/version metadata from the Langfuse prompt object.

`collect_custom_metrics()` listens for `metrics_collected` events. It currently adds custom spans only for `TTSMetrics`, including model/provider metadata, TTFT, generation duration, character count, audio duration, and cancellation status.

`calculate_cost()` estimates model usage from a local `PRICING` dictionary for LLM, TTS, and STT usage types. It supports providers/models including ElevenLabs `eleven_flash_v2_5`, Cartesia `sonic-3`, Deepgram `nova-3`, Munsit, Cerebras-hosted models, and Groq `llama-3.3-70b-versatile`. Unknown providers/models cost `0.0`.

The shutdown callback adds base per-minute costs for session infrastructure, optional recording, and usage-derived costs, then stores totals as Langfuse scores.

## Configuration and Dependencies

The project targets Python `>=3.10`, although the Dockerfile defaults to Python `3.13`. Formatting and linting are configured with Black and Ruff at 100 columns. MyPy is configured for Python 3.10 with missing imports ignored.

Primary runtime dependencies include:

| Dependency | Purpose |
| --- | --- |
| `livekit-agents[...]` | Core realtime agent runtime, MCP extras, turn detector, provider extras. |
| `livekit-plugins-deepgram` | Active STT provider. |
| `livekit-plugins-silero` | Active VAD provider. |
| `livekit-plugins-elevenlabs` | Production-primary TTS provider. |
| `livekit-plugins-cartesia` | Fallback/non-production-primary TTS provider. |
| `livekit-plugins-noise-cancellation` | BVC audio input cleanup. |
| `langfuse`, `opentelemetry-sdk` | Tracing, prompt retrieval, metrics, and scores. |
| `httpx` | Async Bunny Storage access. |
| `python-dotenv` | Local `.env` loading. |
| `pytest`, `pytest-asyncio` | Test execution. |

`pyproject.toml` also declares OpenAI, Faseeh, Munsit, Cerebras/Groq-related extras through LiveKit dependencies, but the active code path imports and uses Deepgram, Cerebras, ElevenLabs, Cartesia, Silero, and LiveKit noise cancellation.

Important environment variables in the implemented runtime are:

| Variable | Required? | Notes |
| --- | --- | --- |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | Required for LiveKit Cloud/dev/start modes | Consumed by LiveKit CLI/runtime. |
| `DEEPGRAM_API_KEY` | Yes | Required by Deepgram STT plugin. |
| `CEREBRAS_API_KEY` | Yes for active LLMs | Not listed in `.env.example`, but required by the active Cerebras plugin usage. |
| `ELEVEN_API_KEY` or provider-specific ElevenLabs key | Yes when ElevenLabs is used | `.env.example` uses `ELEVEN_API_KEY`. |
| `CARTESIA_API_KEY` | Yes when Cartesia is used | Required by active Cartesia fallback, not listed in `.env.example`. |
| `BUNNY_STORAGE_ZONE`, `BUNNY_STORAGE_API_KEY`, `BUNNY_STORAGE_REGION` | Yes for content loading | Region defaults to `storage`. |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`/`LANGFUSE_BASE_URL` | Yes | Required during session startup. |
| `ENVIRONMENT` | No | Defaults to `development`. |
| `MAX_SESSION_DURATION` | No | Defaults to 30 minutes. |

## Deployment

`livekit.toml` contains the configured LiveKit Cloud subdomain and agent ID.

The Dockerfile builds from `ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim`, installs compiler/build dependencies, syncs locked dependencies with `uv`, copies the project, installs the package, switches to a non-root `appuser`, pre-downloads LiveKit model files with `uv run tutor-agent download-files`, and starts the worker with:

```bash
uv run tutor-agent start
```

The `.dockerignore` and `Dockerfile` are both ignored by `.gitignore` in this repository, so deployment config may be locally present but not intended for version control in its current state.

## Testing and Quality Commands

Configured commands from the repository guidance are:

```bash
uv run black .
uv run ruff check .
uv run mypy .
uv run pytest
```

The current test suite contains `tests/test_observations.py`, focused on `calculate_cost()`. It uses mocked usage objects to verify known and unknown provider/model behavior.

One important implementation detail: `calculate_cost()` branches on `usage.type`, but the current tests construct mocked usage objects without setting `type`. Engineers extending this area should verify the test/runtime contract before relying on the tests as full coverage for cost accounting.

## Notable Engineering Considerations

- Startup depends on external systems: LiveKit, provider credentials, Bunny Storage, and Langfuse. If Langfuse credentials or prompt retrieval fail, the session cannot start.
- The active prompt is remote in Langfuse, so behavior can change without a repository code change when prompt labels are updated.
- Content plans are remote JSON files. The local parser validates required keys but does not validate sequence uniqueness, total section count consistency, marker type enums, action type enums, or question type enums.
- `_start_section()` assumes a section question exists when building the `set_section` payload. Plans with sections that omit `question` can fail at runtime despite the dataclass allowing `question=None`.
- `check_user_understanding()` relies on the LLM to pass the correct boolean. There is no deterministic answer grading in code; grading behavior is prompt/model-driven.
- Frontend payload names in current code are `add` and `remove` for marker changes, not `markers` as described by some older docs.
- `README.md` and `.env.example` mention OpenAI defaults and omit some active provider variables such as Cerebras and Cartesia. Treat the implementation as authoritative.
- `record_this_session` is production-only and probabilistic. The cost calculation includes an additional recording/observability cost only for recorded sessions.
- The project includes MCP-related dependencies, but the current source code does not configure an MCP server or expose MCP tools directly.

## Mental Model for New Engineers

Think of the project as a thin orchestration layer around LiveKit Agents. LiveKit handles realtime audio transport, STT/LLM/TTS orchestration, VAD, interruption, and room lifecycle. The repository-specific value is the tutoring state machine: it builds a contextual prompt from Bunny-hosted course metadata, fetches structured topic plans on demand, converts each section into model guidance, enforces simple section/checkpoint progression, sends synchronized UI commands to the frontend, and records operational data in Langfuse.

When modifying the project, start by identifying whether the change belongs in one of four areas: session/pipeline setup in `main.py`, tutoring behavior in `agents/tutor_agent.py`, content-plan schema handling in `domain_types.py` and `utils/plan_helpers.py`, or external integrations in `utils/`. Keep frontend payload compatibility in mind because `publish_data()` messages are an implicit API shared with the client application.
