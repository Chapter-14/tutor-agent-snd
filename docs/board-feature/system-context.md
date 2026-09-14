# Sanad Board Feature: System Context for AI Ideation

## Purpose

Use this document as factual context when generating product, UX, architecture, or
implementation ideas for Sanad's teaching board. It describes the current system, its hard
constraints, and its known limitations.

This is not a request to redesign the tutor from first principles. Ideas should improve the
board while preserving the existing responsibility boundaries unless a proposal explicitly
explains why a boundary must change.

## Product Context

Sanad is a LiveKit-powered private voice tutor. A student selects an approved lesson, then
converses with one Tutor Agent that teaches the lesson one topic at a time. Lesson content is
authored in English; the tutor can teach in English or Arabic according to the student's session
language. In Arabic sessions, technical, scientific, accounting, and programming terms remain in
English.

The teaching board is a small visual surface beside the student's course slides. It is a concise
aid to spoken teaching, not a full whiteboard, transcript, notebook, slide replacement, or an
independent source of curriculum. It should retain the few ideas a student needs to follow the
active explanation: a title, key points, definitions, rules, equations, contrasts, or ordered
steps.

The intended student experience is one coherent tutor: the tutor speaks naturally while relevant
notes appear near the moment the matching idea is heard. The tutor must not refer to the board in
speech.

## Current System At A Glance

```text
Student voice
    |
    v
LiveKit AgentSession <--> Tutor Agent
                           |
                           | generated text, before TTS
                           v
                      BoardRuntime.tee
                       |             |
                       |             +--> TTS --> student hears speech
                       v
                 sentence windows
                       |
                       v
                Board Director LLM
                       |
                    BoardPlan
                       |
                       v
          BoardRuntime executor and BoardState
                       |
             reliable LiveKit data message
                       |
                       v
              frontend board renderer
```

There is one Tutor Agent, one `BoardRuntime`, one `BoardState`, and one `BoardDirector` per
LiveKit session. Board state is session-local and is not persisted or shared across students.

## Responsibility Boundaries

| Component | Owns | Must not own |
| --- | --- | --- |
| Tutor Agent | Conversation, teaching approach, lesson progression, assessment, spoken response, topic boundaries | Low-level board planning, board IDs, board timing, frontend rendering |
| Board Director | Selecting useful visual notes from upcoming tutor speech and authored topic context | Speaking, student interaction, lesson progression, direct frontend publication |
| BoardRuntime | Speech observation, asynchronous planning, pacing, cancellation, execution | Curriculum or pedagogical decisions |
| BoardState | Canonical backend board state, validation, IDs, limits, board payload creation | I/O, LLM calls, LiveKit dependencies |
| Frontend | Rendering, layout, typography, animation, responsive behavior, local teardown reset | Curriculum decisions or semantic validation |
| Lesson plan | Facts, teaching sequence, examples, terminology guidance, optional assessment, optional scroll location | Runtime state, board IDs, frontend messages, imperative board commands |

The governing rule is:

> The Tutor decides what to teach and say. The Board Director decides what may be useful to show. Deterministic code validates, times, and publishes every board mutation.

## Tutor And Lesson Flow

The runtime loads a chapter catalog from Bunny Storage and then loads one approved lesson JSON file
at a time. A lesson contains ordered topics. A topic is the teaching and progress boundary.

```text
student chooses approved lesson
    -> get_lesson_plan(lesson_slug)
    -> activate first topic
    -> clear and title the board deterministically
    -> tutor explains the returned topic content
    -> optional authored assessment or readiness question
    -> complete topic
    -> activate next topic and reframe board
```

The Tutor Agent currently exposes only these workflow tools:

| Tool | Use |
| --- | --- |
| `get_lesson_plan(lesson)` | Load an approved lesson slug and activate its first topic. |
| `advance_to_next_topic()` | Complete an active topic that has no assessment after the student indicates readiness. |
| `check_topic_understanding(student_understood)` | Evaluate an actual answer to the active authored assessment and progress or re-explain. |

The Tutor does not have a board tool. It is prompted to make its speech board-friendly: one idea
per sentence, approximately 10 to 25 words per sentence, explicit concept names, separate
sentences for parallel facts, and one spoken sentence per process step.

## Board Runtime Behavior

### Topic boundaries

Starting a topic is a deterministic visual boundary. Pending reactive operations are invalidated,
then the runtime clears the old board and sets the topic title. The first visible topic normally
publishes:

```text
board_clear -> board_show -> board_set_title
```

Later topics normally publish `board_clear -> board_set_title` because the board remains visible.
`board_hide` exists in the state model but production flow does not currently use it.

### Reactive planning

`Assistant.tts_node()` passes the tutor's generated text through `BoardRuntime.tee()`. The same
text continues unchanged to TTS. A copy is split into sentences using English and Arabic
punctuation (`.`, `!`, `?`, `؟`, `…`), with a 240-character fallback flush.

The runtime groups up to two sentences into a FIFO planning window. For each window, the Board
Director receives:

- The upcoming tutor sentences.
- The session language.
- The active topic title.
- Up to 1,200 characters of authored topic content.
- A compact snapshot of the current board, including runtime-generated IDs.
- Title and item limits and the number of remaining content slots.

The Director returns zero to four semantic operations. Empty plans are normal. Director failure,
timeout, malformed output, or provider failure is fail-open: the Tutor's speech continues and the
board simply receives no dynamic update for that window.

### Pacing and cancellation

Generated text reaches TTS before matching audio reaches the student. To avoid immediately filling
the board, the executor estimates a release time from each sentence's word offset:

```text
release time = speech-start time + word offset / words per second
```

The default is 2.4 words per second and can be configured with `BOARD_WORDS_PER_SECOND`. LiveKit's
speaking event re-anchors the estimate closer to actual playback.

Each speech generation has an internal generation ID. Starting a new generation invalidates queued
board work. Pending work is also dropped when the speech handle is interrupted. Topic boundaries
likewise invalidate pending reactive operations before the deterministic clear/title frame.

## Current Board Command Model

The Board Director has a deliberately small semantic vocabulary:

| Director operation | Required field | Intended use |
| --- | --- | --- |
| `clear` | none | Remove title, items, and emphasis. Usually only deterministic topic code needs this. |
| `set_title` | `text` | Set or replace the one topic-level title. Usually set automatically. |
| `add_bullet` | `text` | Add one unordered key point, property, cause, or outcome. |
| `add_text` | `text` | Add one definition, rule, equation, or compact contrast. |
| `add_step` | `text` | Add one step in a genuinely ordered process. |
| `emphasize` | `target_id` | Emphasize an existing title or item. |

The Director cannot issue `show` or `hide`; visibility belongs to deterministic code. It cannot
create IDs. For `emphasize`, it may use only an exact `target_id` that appears in the current board
snapshot.

The Director emits a structured response shaped like this:

```json
{
  "operations": [
    {
      "action": "add_text",
      "text": "Revenue follows control",
      "target_id": null
    }
  ]
}
```

## Board-State Invariants

`BoardState` validates every operation before a frontend message is produced. Current rules are:

| Rule | Current behavior |
| --- | --- |
| Title | One optional title; a new title replaces it without clearing content. |
| Title length | At most 80 characters after trimming. |
| Content capacity | At most six non-title items. |
| Content length | At most 180 characters after trimming. |
| IDs | Opaque UUID-backed IDs generated by backend code only. |
| Duplicates | Exact duplicate normalized content text is rejected. |
| Emphasis | One active target at a time; it may be the title or an item. |
| Clear | Removes title, content, and emphasis but preserves visibility. |
| Show/hide | Idempotent. |
| Text normalization | Trims text and sentence-cases ordinary initial lowercase Latin text; Arabic, `pH`, and `iPhone` are preserved. |

The Director prompt requires compressed notes rather than transcripts. It must retain the Tutor's
wording, preserve English technical terms in Arabic speech, avoid trailing punctuation and Markdown,
and return no operation for greetings, questions, elaboration, narrative examples, or duplicate
ideas.

## Frontend Wire Protocol

All backend UI messages are JSON, sent reliably on the LiveKit data topic `ui-control`.

```json
{"action": "board_show"}
{"action": "board_hide"}
{"action": "board_clear"}
{"action": "board_set_title", "id": "<opaque-id>", "text": "Five-Step Model"}
{"action": "board_add_bullet", "id": "<opaque-id>", "text": "Identify the contract"}
{"action": "board_add_text", "id": "<opaque-id>", "text": "Revenue follows control"}
{"action": "board_add_step", "id": "<opaque-id>", "text": "Determine the price"}
{"action": "board_emphasize", "id": "<existing-opaque-id>"}
```

Related lesson UI events use the same channel: `set_lesson`, `set_topic`, `topic_done`, `scroll`,
and `session_ending`.

The frontend implementation is outside this repository. The backend currently does not receive
acknowledgements, send full snapshots, version messages, support replay on reconnect, or persist
board state between sessions.

## Lesson Plans As Board Context

The Board Director's only authored source is the active topic's `content` string. This string is
opaque to runtime code: it is not parsed into board instructions, facts, term lists, or teaching
beats. It can contain ordinary English prose that gives the Tutor useful guidance, including
optional board intent.

For example, a topic may say that a five-stage process should be taught as a connected sequence and
that the board can support it with one short step per stage. The Tutor decides how to speak; the
Board Director reacts to the Tutor's actual upcoming sentences. A plan cannot pre-create board item
IDs, schedule commands, or force a board operation.

See [Lesson Plan Structure](lesson-plan-structure.md) for the exact runtime content contract.

## Important Current Limitations

Treat these as real constraints when proposing near-term ideas:

- Synchronization is approximate. It uses whitespace word counts and a constant speech rate, not
  TTS word timestamps, audio playout position, or frontend render acknowledgement.
- The sentence splitter is heuristic. It can split abbreviations or decimals and may cut a long
  run-on buffer in the middle of a word.
- Board Director calls are serial and internal queues are unbounded. Sustained long generation can
  build planning lag.
- An in-flight Director response can race a new generation or topic boundary because the current
  loop does not re-check captured generation and epoch after awaiting the LLM.
- The executor can race a topic boundary between its stale check and board-state mutation.
- The normal executor and immediate topic-framing path can both mutate `BoardState`; there is no
  single serialized mutation/publish path.
- Backend state changes before frontend publication is known to succeed. A publish failure can make
  backend and frontend state diverge.
- `ops_published` records accepted operations after attempted publication, not confirmed frontend
  delivery.
- Interrupted pending operations are dropped, not resumed. Already published items remain visible.
- The protocol has no revision, acknowledgement, snapshot, replay, reconnect recovery, or session
  persistence.
- The board is reactive to what the Tutor already generated. It has no authored teaching-beat
  cursor, precompiled visual plan, cache, or prefetch.

## Idea-Generation Guardrails

When suggesting ideas, distinguish explicitly between **current capability**, **near-term
enhancement**, and **long-term redesign**. Avoid proposals that assume unimplemented capabilities
already exist.

Good ideas should:

- Preserve voice continuity: board work must not block or degrade Tutor speech.
- Keep the Tutor as the curriculum and conversation owner.
- Keep LLM output structured, bounded, and semantically small.
- Keep deterministic code as the validator, ID owner, scheduler, and publisher.
- Let the frontend own pixel layout, responsive placement, typography, and animation.
- Treat interruptions, stale plans, duplicate notes, capacity, and delivery failures as first-class
  cases.
- Use the topic's existing content as the curriculum authority rather than inventing facts.
- Work in English, Arabic, and mixed Arabic-English technical terminology.
- Be testable with deterministic state/runtime tests before requiring a real LiveKit room.

Ideas should not assume arbitrary drawing, raw pixel placement, freeform SVG/code generation,
frontend acknowledgements, persistent boards, student drawing, or a richer command DSL unless they
also describe the needed contracts and migration path.

## Useful Directions To Explore

The following are open design areas, not existing features:

- Reliability: serialized state mutation, final stale checks, publication confirmation, snapshots,
  revisions, replay, and reconnection recovery.
- Synchronization: TTS timing signals, better sentence segmentation, semantic timing anchors, or
  authored teaching beats.
- Visual vocabulary: diagrams, comparisons, equations, tables, callouts, or regions while keeping
  semantic rather than pixel-level commands.
- Pedagogy: when a visual is genuinely worth showing, how to avoid visual overload, and how plans
  can provide optional visual intent without becoming imperative scripts.
- Adaptation: board behavior for re-explanations, student questions, Arabic/mixed text, dense
  subjects, and process-oriented versus conceptual topics.
- Evaluation: quality criteria, trace review, latency measurements, test fixtures, and student
  learning signals.

## Expected Output From An Ideation Model

For each proposal, provide:

1. The student problem it solves and why the current behavior is insufficient.
2. Its classification: current-capability use, near-term enhancement, or long-term redesign.
3. The affected owner(s): Tutor, Board Director, BoardRuntime, BoardState, frontend, plan schema,
   or transport.
4. The minimum data contract and lifecycle changes required.
5. Interruption, stale-state, and delivery-failure behavior.
6. A migration path that does not block current voice tutoring.
7. Measurable success criteria and the tests needed to validate the proposal.

## Primary Source Files

Use code as the final source of truth. The most relevant current files are:

- `src/tutor_agent_snd/main.py`: session setup, models, prompt loading, runtime lifecycle, and
  speech-state clock anchor.
- `src/tutor_agent_snd/agents/tutor_agent.py`: Tutor tools, topic activation, board framing, and
  LiveKit publication callback.
- `src/tutor_agent_snd/board/models.py`: structured operation and runtime data models.
- `src/tutor_agent_snd/board/state.py`: authoritative board validation and wire-payload generation.
- `src/tutor_agent_snd/board/runtime.py`: tee, sentence queue, Director loop, pacing, cancellation,
  and execution.
- `src/tutor_agent_snd/board/director.py`: Board Director request context and failure policy.
- `prompts/snd-board-director-prompt.md`: repository artifact for Board Director behavior.
- `prompts/snd-agent-system-prompt-board-rounds.md`: repository artifact for Tutor delivery style.
- `docs/current-board-director-architecture.md`: detailed current implementation analysis.
- `docs/data-models.md`: exact lesson-plan data model.

Repository prompt files are review artifacts. Runtime fetches prompts from Langfuse by the names
`snd-agent-system-prompt` and `snd-board-director-prompt`, using `latest` outside production and
`production` in production.
