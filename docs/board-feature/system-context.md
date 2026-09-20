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
authored lesson plan
    |
    | topic.segments[].board.beats[]
    v
  BeatCursor  <---------------------------+
    |                                     |
    | pending beats (id, kind, anchor)    | "which beat has he reached?"
    v                                     |
Student voice                             |
    |                                     |
    v                                     |
LiveKit AgentSession <--> Tutor Agent     |
                           |              |
                           | generated text, before TTS
                           v              |
                      BoardRuntime.tee    |
                       |             |    |
                       |             +--> TTS --> student hears speech
                       v                  |
                 sentence windows --------+
                       |
                       v
                Board Director LLM
                       |
                DirectorPlan (beat references, not content)
                       |
                       v
       BeatCursor resolves -> BoardOp -> BoardState
                       |
             reliable LiveKit data message
                       |
                       v
              frontend board renderer
```

There is one Tutor Agent, one `BoardRuntime`, one `BoardState`, one `BeatCursor`, and one
`BoardDirector` per LiveKit session. Board state is session-local and is not persisted or shared
across students.

The defining property of v2: **the Director returns references, not text.** A `fire` operation names
an authored beat; the beat's wording comes from the plan. The only text-bearing operation the
Director can emit is `improvise`, which is capped at one per window and restricted to `bullet` and
`text` items.

## Responsibility Boundaries

| Component | Owns | Must not own |
| --- | --- | --- |
| Tutor Agent | Conversation, spoken delivery of authored segments, lesson progression, judging answers | Low-level board planning, board IDs, board timing, frontend rendering |
| Board Director | Deciding **which authored beat** the tutor has reached, and narrow off-plan improvisation | Writing the content of a planned beat, speaking, lesson progression, direct publication |
| BeatCursor | Beat ordering, the one-segment firing horizon, segment-entry effects, rung lifecycle | LLM calls, publication, curriculum authorship |
| BoardRuntime | Speech observation, asynchronous planning, reference translation, pacing, cancellation | Curriculum or pedagogical decisions |
| BoardState | Canonical board state, validation, IDs, regions, capacity, revisions, payload creation | I/O, LLM calls, LiveKit dependencies |
| Frontend | Rendering, layout, typography, animation, responsive behavior, local teardown reset | Curriculum decisions or semantic validation |
| Lesson plan | Facts, teaching sequence, verbatim wording, terms, **the board's content and when it is due**, assessment, remediation, optional scroll | Runtime state, board IDs, frontend messages, timings, positions |

The governing rule is:

> The plan decides what is taught and what is shown. The Tutor decides how it is said. The Board Director decides only when an authored note is due. Deterministic code validates, times, and publishes every board mutation.

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
| `check_topic_understanding(student_understood, chosen_option_id)` | Evaluate an actual answer. `chosen_option_id` names the authored distractor the student picked, which selects the remediation rung their specific misunderstanding earns. |

The Tutor does not have a board tool. It is prompted to make its speech bindable: deliver every
authored segment in order, one idea per sentence, approximately 10 to 25 words per sentence, and —
the load-bearing rule — **name the concept explicitly in the sentence that introduces it**, because
that is what the Director matches a beat's `anchor` against.

Segment transitions are inferred by the Director from the speech, never announced by a tool round.
The tool count stays at three.

## Board Runtime Behavior

### Topic boundaries

Starting a topic is a deterministic visual boundary. `BoardRuntime.begin_topic(topic)` invalidates
pending work, rebuilds the `BeatCursor` from the topic's segments, clears the board and sets the
title. The first visible topic normally publishes:

```text
board_clear {scope: "all"} -> board_show -> board_set_title
```

Later topics normally publish `board_clear -> board_set_title` because the board remains visible.
`board_hide` exists in the state model but production flow does not currently use it.

Segment boundaries are also deterministic, but author-driven rather than code-driven: firing the
first beat of a segment applies that segment's `on_enter` rule (`keep` or `clear_live`) and opens
its group container if it declares one.

Remediation is bracketed by code. `enter_remediation(rung)` routes the rung's beats into the
`temporary` region and makes them the only fireable beats; `exit_remediation()` clears that region
whole. No model decides a region lifecycle.

### Reactive planning

`Assistant.tts_node()` passes the tutor's generated text through `BoardRuntime.tee()`. The same
text continues unchanged to TTS. A copy is split into sentences using English and Arabic
punctuation (`.`, `!`, `?`, `؟`, `…`), with a 240-character fallback flush.

The runtime groups up to two sentences into a FIFO planning window. For each window, the Board
Director receives:

- The upcoming tutor sentences.
- The session language, topic title, knowledge type, and current segment role.
- The next three to five **pending beats**: `beat_id | stage | kind | anchor | preview`.
- A compact snapshot of the current board, including runtime-generated IDs and item state.
- Per-region capacity.

Authored prose is no longer passed to the Director. The beats are the context; the segment `content`
belongs to the tutor.

The Director returns zero to four operations, which are references rather than content. The runtime
translates each one through the `BeatCursor` before anything reaches `BoardState`; a reference the
cursor refuses (an unknown beat, an already-fired beat, a beat more than one segment ahead) simply
does not happen and is counted.

Empty plans are normal. Director failure, timeout, malformed output, or provider failure is
fail-open: the Tutor's speech continues and the board simply receives no update for that window.

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

Two vocabularies, deliberately different.

### What the Director may emit

| Director operation | Required fields | Intended use |
| --- | --- | --- |
| `fire` | `beat_id` | The tutor has reached this authored beat. |
| `reveal_next` | `target_id` | The next chunk of a `definition` already on the board. |
| `update` | `target_id`, `slot`, `text` or `state` | Fill a blank; mark an option after the answer. |
| `annotate` | `target_id`, `state` | `key`, `warning`, `correct`, `wrong`, `broken`, `dim`. |
| `remove` | `target_id` | Drop a temporary item the tutor has finished with. |
| `pin` | `target_id` | Keep an item visible while the live region turns over. |
| `recall` | `beat_id` | Re-show an item cleared earlier (spaced retrieval). |
| `improvise` | `kind`, `text` | Off-plan only. `bullet` or `text`, max one per window. |

The Director cannot issue `show`, `hide`, `clear`, `set_title` or `group`; those belong to
deterministic code. It cannot create IDs, and `fire` carries no text — any text sent with it is
discarded.

```json
{
  "operations": [
    { "action": "fire", "beat_id": "b-definition" },
    { "action": "update", "target_id": "board-options-…", "slot": "opt-cash", "state": "wrong" }
  ]
}
```

### What code applies to `BoardState`

`clear(scope)` · `set_title` · `add(region, kind, payload, group_id)` · `update` · `annotate` ·
`remove` · `reveal_next` · `pin` · `group(kind, heading)`.

A fired beat compiles into one to three of these: an optional `clear {scope: "live"}` from the
segment's `on_enter`, an optional `group` container, then the `add` carrying the authored payload.
They share one release time so a container never appears without its contents.

## Board-State Invariants

`BoardState` validates every operation before a frontend message is produced. Current rules are:

| Rule | Current behavior |
| --- | --- |
| Title | One optional title; a new title replaces it without clearing content. |
| Title length | At most 80 characters after trimming. |
| Regions | `live` (12 items), `pinned` (6), `temporary` (4). Capacity is per region. |
| Content length | At most 180 characters for any string anywhere in a payload. |
| IDs | Opaque UUID-backed IDs generated by backend code only. |
| Duplicates | An identical payload of the same kind in the same region is rejected. |
| Annotation | Typed. `key` is exclusive and clears the previous `key` in the same batch; the others coexist. |
| Slots | `options`, `blanks` and `chain` carry addressable child slots; an unknown slot is rejected. |
| Reveal | A `definition` reveals one chunk at a time and rejects a reveal past its last chunk. |
| Pin | Moves an item between `live` and `pinned`, subject to the target region's capacity. |
| Recall | Items removed or cleared stay addressable by their authored beat id. |
| Clear | `all`, `live`, or `temporary`. Preserves visibility. Archives what it removes. |
| Revision | Every accepted mutation increments `rev`, which is stamped on every published payload. |
| Show/hide | Idempotent. |
| Text normalization | Trims and sentence-cases ordinary initial lowercase Latin text; Arabic, `pH`, and `iPhone` are preserved. |

Rejections are silent and counted. No rejection is ever fed back to an LLM.

## Frontend Wire Protocol

All backend UI messages are JSON, sent reliably on the LiveKit data topic `ui-control`.

Every board message carries `rev`.

```json
{"action": "board_show", "rev": 2}
{"action": "board_hide", "rev": 41}
{"action": "board_clear", "scope": "all", "rev": 1}
{"action": "board_set_title", "id": "<opaque-id>", "text": "Five-Step Model", "rev": 3}
{"action": "board_add", "id": "<opaque-id>", "region": "live", "kind": "definition", "payload": {...}, "group_id": null, "rev": 4}
{"action": "board_update", "id": "<opaque-id>", "slot": "opt-cash", "state": "wrong", "rev": 5}
{"action": "board_annotate", "id": "<opaque-id>", "kind": "key", "rev": 6}
{"action": "board_remove", "id": "<opaque-id>", "rev": 7}
{"action": "board_reveal", "id": "<opaque-id>", "index": 1, "rev": 8}
{"action": "board_pin", "id": "<opaque-id>", "pinned": true, "region": "pinned", "rev": 9}
{"action": "board_group", "id": "<opaque-id>", "region": "live", "kind": "columns", "heading": "Signing vs satisfying", "rev": 10}
{"action": "board_snapshot", "rev": 22, "visible": true, "title": {...}, "groups": [...], "items": [...]}
```

Related lesson UI events use the same channel and are unchanged: `set_lesson`, `set_topic`,
`topic_done`, `scroll`, and `session_ending`.

The frontend implementation is outside this repository; see
[Frontend Board Spec v2](frontend-board-spec-v2.md) for rendering requirements. The backend does not
receive acknowledgements and does not persist board state between sessions. `board_snapshot` exists
and `BoardRuntime.publish_snapshot()` produces it, but **no automatic trigger is wired**: the agent
has no inbound data-channel handler, so a mid-topic reconnect still shows an empty board until the
next topic boundary.

## Lesson Plans As Board Content

This is the inversion at the centre of v2. The plan no longer *hints* at the board — it authors it.

A topic is a typed teaching unit: a `knowledge_type`, a list of `terms`, an ordered list of
`segments`, a mandatory `loses_marks` line, an optional `assessment`, and a `remediation` ladder.
Each segment carries prose `content` for the tutor and an optional `board` blueprint holding ordered
**beats**. A beat is `{id, kind, anchor, payload}`: what the note is, and the idea the tutor will be
saying when it is due.

Thirteen beat kinds exist — `heading`, `text`, `bullet`, `step`, `definition`, `term`, `equation`,
`compare`, `table`, `chain`, `blanks`, `options`, `callout` — covering the P0 elements in
`Board_Elements_Catalog_v1_EN.md` without a drawing engine.

A plan still cannot create board item IDs, schedule a command, set a position, or force an
operation. What it now owns is *what the note says and which stage it belongs to*. What it does not
own is *the moment it appears*, which only the live speech can decide.

See [Lesson Plan Structure](lesson-plan-structure.md) for the exact runtime content contract, and
`tests/fixtures/ch18_v2/` for a validated worked example.

## Important Current Limitations

Treat these as real constraints when proposing near-term ideas:

- Synchronization is approximate. It uses whitespace word counts and a constant speech rate, not
  TTS word timestamps, audio playout position, or frontend render acknowledgement.
- The sentence splitter is heuristic. It can split abbreviations or decimals and may cut a long
  run-on buffer in the middle of a word.
- Board Director calls are serial and internal queues are unbounded. Sustained long generation can
  build planning lag.
- Backend state changes before frontend publication is known to succeed. A publish failure can make
  backend and frontend state diverge, and with `update` and `remove` in the vocabulary that
  divergence corrupts rather than merely omits.
- `ops_published` records accepted operations after attempted publication, not confirmed frontend
  delivery.
- Interrupted pending operations are dropped, not resumed. Already published items remain visible.
- The protocol has a revision counter and a snapshot message, but no acknowledgement, no replay, no
  automatic resync trigger, and no session persistence.
- Beat binding quality depends on the tutor actually naming the concept in the sentence that
  introduces it. When the tutor paraphrases heavily, beats bind late or not at all; a high
  `improvise` ratio in the stats is the signal that a topic's anchors do not match real speech.
- A beat passed over is marked skipped and never returns on its own. Only `recall` brings content
  back, and only for items that were actually shown.

Fixed in v2, previously listed here: the in-flight stale-plan race (generation and epoch are now
re-checked after the await), the executor/topic-boundary race, and the two competing mutation paths
(every mutation now goes through one lock-held path, including deterministic topic framing).

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

- Reliability: publication confirmation, an automatic resync trigger for `board_snapshot`, replay,
  and reconnection recovery. (Serialized mutation, final stale checks and revisions are now shipped.)
- Synchronization: TTS word timestamps, better sentence segmentation, and whether a beat's anchor
  can carry an explicit timing hint without becoming a script.
- Binding quality: measuring how often a beat fires on the right sentence, and what to do with a
  topic whose anchors keep missing.
- Pedagogy: how many beats a topic should carry, when a visual is worth showing at all, and how to
  author the `procedure` move so worked → faded → solo genuinely lands.
- Adaptation: board behavior for student questions, dense subjects, and topics whose authored beats
  run out mid-explanation.
- Evaluation: quality criteria, trace review, latency measurements, and student learning signals.

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
- `src/tutor_agent_snd/board/models.py`: internal and Director operation models, item kinds.
- `src/tutor_agent_snd/board/state.py`: authoritative board validation, regions, revisions, payloads.
- `src/tutor_agent_snd/board/cursor.py`: beat ordering, firing horizon, segment entry, rung lifecycle.
- `src/tutor_agent_snd/board/runtime.py`: tee, sentence queue, Director loop, reference translation,
  pacing, cancellation, and the single serialized mutation path.
- `src/tutor_agent_snd/board/director.py`: Board Director request context and failure policy.
- `src/tutor_agent_snd/utils/plan_helpers.py`: the authored plan contract, enforced.
- `prompts/snd-board-director-prompt-v2.md`: repository artifact for Board Director behavior.
- `prompts/snd-agent-system-prompt-v3.md`: repository artifact for Tutor delivery.
- `docs/board-feature/lesson-plan-structure.md`: the authoring contract.
- `docs/board-feature/frontend-board-spec-v2.md`: rendering requirements per item kind.
- `docs/current-board-director-architecture.md`: analysis of the v1 implementation; its board
  sections are superseded by this document.

Repository prompt files are review artifacts. Runtime fetches prompts from Langfuse by the names
`snd-agent-system-prompt` and `snd-board-director-prompt`, using `latest` outside production and
`production` in production.
