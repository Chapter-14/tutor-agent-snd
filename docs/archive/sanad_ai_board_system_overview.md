# Sanad AI Board System — High-Level Technical Overview

## 1. Purpose

This document defines the high-level architecture and intended behavior of the new **AI Board System** for Sanad.

The board is a visual teaching surface that the AI tutor can use while explaining. It should allow Sanad to progressively write short notes, equations, labels, arrows, simple diagrams, highlights, and other visual elements in coordination with the spoken explanation.

The objective is to make the tutoring experience feel closer to a real private tutor using a whiteboard: the student listens while seeing the important ideas appear gradually in front of them.

This document is intentionally **not a full technical implementation plan**. It defines the system boundaries, responsibilities, data flow, and major design decisions so that a coding agent can inspect the current codebase and create the detailed implementation plan.

---

## 2. Background / Current Problem

The first board prototype gives the main tutor agent tool functions that directly modify the board.

Conceptually:

```text
Tutor Agent
   |
   +--> speak
   +--> board tool
   +--> board tool
   +--> speak
   +--> board tool
```

This works in controlled tests but is unreliable in real sessions.

The main issue is that board behavior currently depends on the conversational LLM correctly performing several reasoning/tool-call rounds inside one tutor turn.

This introduces several problems:

- The number of tool calls is unpredictable.
- The LLM may stop the turn before all desired visual actions are executed.
- The LLM may speak correctly but forget to use the board.
- The LLM may overuse or underuse the board.
- Tool-call latency can interrupt the natural speech flow.
- Board execution is tightly coupled to the tutor agent's turn lifecycle.
- Prompting the main tutor to teach, manage dialogue, control slides, and manage the board at the same time makes its responsibilities too broad.
- Student interruptions make pending board actions difficult to cancel safely.

Because the board is becoming an important part of the learning experience, it should no longer behave like an optional collection of agent tool calls.

---

## 3. Core Architectural Decision

The board should become an **independent visual-control subsystem**.

The main Tutor Agent remains responsible for:

- understanding the student,
- following the teaching plan,
- deciding what to explain,
- speaking naturally,
- answering questions,
- managing the teaching conversation.

A separate **Board Director** becomes responsible for:

- deciding what should appear visually,
- translating teaching context into structured board operations,
- tracking the semantic state of the board,
- coordinating visual changes with the tutor explanation.

A deterministic **Board Runtime / Executor** becomes responsible for:

- validating board operations,
- sequencing them,
- synchronizing them with the active explanation,
- cancelling outdated operations,
- communicating with the frontend,
- maintaining authoritative board state.

The frontend remains responsible for:

- rendering,
- positioning,
- layout,
- animation,
- visual styling.

### Main principle

> **The LLM plans board behavior. Code executes board behavior.**

The system should avoid requiring the LLM to repeatedly decide whether another tool call is needed.

---

## 4. High-Level Architecture

```text
                         Student
                            |
                            v
                   +----------------+
                   |   Tutor Agent  |
                   |   (LiveKit)    |
                   +--------+-------+
                            |
                Teaching / Speech Events
                            |
                            v
                    +---------------+
                    | Event / Sync  |
                    |     Layer     |
                    +-------+-------+
                            |
                            v
                  +-------------------+
                  |   Board Director  |
                  |   LLM / Planner   |
                  +---------+---------+
                            |
                      Structured
                       BoardPlan
                            |
                            v
                  +-------------------+
                  |   Board Runtime   |
                  |    / Executor     |
                  +---------+---------+
                            |
                  LiveKit RPC / Data
                            |
                            v
                  +-------------------+
                  | Next.js Frontend  |
                  |   Board Renderer  |
                  +-------------------+
```

The Board Director should operate as a **parallel sidecar process** during the tutoring session.

It should **not** become another conversational agent that takes control of the LiveKit conversation and hands control back to the tutor.

The Tutor Agent and Board Director have separate responsibilities and separate lifecycles.

---

## 5. Main Components

## 5.1 Tutor Agent

The existing Tutor Agent remains the owner of the teaching conversation.

Responsibilities:

- receive student voice/text input,
- follow the current teaching plan,
- explain concepts,
- answer questions,
- decide pedagogical direction,
- handle student interruptions,
- move between teaching sections/topics,
- publish teaching events that the Board System can consume.

The tutor should gradually lose direct responsibility for individual board drawing actions.

The tutor may still provide high-level hints when useful, such as:

```text
visual emphasis needed
equation being introduced
comparison being explained
example beginning
diagram would help
```

However, the tutor should not be required to manually issue every visual operation.

---

## 5.2 Board Director

The Board Director is a specialized LLM-driven component dedicated to visual teaching.

It does not speak to the student.

Its input may include:

- current course,
- current chapter/topic,
- current section of the teaching plan,
- current tutor explanation,
- recent tutor transcript,
- student question,
- current board state,
- relevant existing slide/context,
- optional teaching-plan visual hints,
- current generation/turn identifiers.

Its output is a structured **BoardPlan**.

Example:

```json
{
  "generation_id": "gen_104",
  "operations": [
    {
      "type": "write_text",
      "content": "Newton's Second Law",
      "region": "top"
    },
    {
      "type": "write_equation",
      "content": "F = ma",
      "region": "center"
    },
    {
      "type": "draw_arrow",
      "from": "mass",
      "to": "force"
    }
  ]
}
```

The Board Director should use strict structured output rather than natural-language instructions.

---

## 5.3 Board Runtime / Executor

The Board Runtime is deterministic application code.

It is the authoritative controller of board execution.

Responsibilities:

- receive `BoardPlan` objects,
- validate them against a strict schema,
- reject invalid or stale plans,
- maintain board version/state,
- queue operations,
- cancel pending operations when teaching direction changes,
- deduplicate operations,
- sequence board operations,
- coordinate operation timing,
- send commands to the frontend,
- receive frontend acknowledgements/errors,
- update the authoritative board state.

The Board Runtime should contain **no teaching reasoning**.

It executes decisions already made by the Board Director.

---

## 5.4 Frontend Board Renderer

The frontend renders the visual board.

The frontend should handle:

- coordinates,
- responsive layout,
- element positioning,
- handwriting-like animation,
- line/arrow animation,
- fade/appear effects,
- typography,
- colors,
- spacing,
- collision prevention,
- board regions,
- zoom/scaling if required.

The AI should ideally work with semantic placement rather than raw pixels.

Prefer:

```json
{
  "region": "right-column"
}
```

or:

```json
{
  "position": "below:eq_1"
}
```

instead of:

```json
{
  "x": 437,
  "y": 281
}
```

This keeps layout deterministic and reduces LLM errors.

---

## 6. Board State

The system must maintain a semantic representation of what currently exists on the board.

Example:

```json
{
  "board_id": "session_123_board",
  "version": 18,
  "active_region": "center",
  "objects": [
    {
      "id": "title_1",
      "type": "text",
      "content": "Newton's Second Law",
      "region": "top"
    },
    {
      "id": "eq_1",
      "type": "equation",
      "content": "F = ma",
      "region": "center"
    }
  ]
}
```

The Board Director should receive this semantic state before generating new actions.

This allows it to:

- reference existing objects,
- avoid repeating content,
- add relationships,
- update previous explanations,
- erase only what is no longer needed,
- continue building diagrams progressively.

The Board Runtime should be the authoritative owner of the current version.

---

## 7. Board Command DSL

The first implementation should intentionally expose a **small command vocabulary**.

Recommended initial operations:

```text
write_text
write_equation
draw_line
draw_arrow
draw_box
highlight
erase
clear_region
```

Possible later operations:

```text
move
group
ungroup
replace_text
draw_simple_shape
draw_graph
show_image
show_table
```

The first version should avoid arbitrary SVG/code generation.

The Board Director should express **visual intent**, while the frontend decides exactly how that intent appears.

Example:

```json
{
  "type": "write_text",
  "content": "Mass",
  "position": "left-of:eq_1",
  "animation": "write"
}
```

The frontend translates this into actual coordinates and animation.

---

## 8. Batch Operations Instead of Repeated Tool Calls

A major design requirement is that the system should not rely on one LLM round per board action.

Instead of:

```text
LLM -> write()
LLM -> arrow()
LLM -> highlight()
LLM -> write()
```

the Board Director should produce one structured plan containing multiple operations:

```json
{
  "operations": [
    {"type": "write_text", "...": "..."},
    {"type": "write_equation", "...": "..."},
    {"type": "draw_arrow", "...": "..."},
    {"type": "highlight", "...": "..."}
  ]
}
```

The Board Runtime then executes the operations independently.

This makes the system significantly more predictable and removes dependence on repeated LLM tool-call rounds.

---

## 9. Teaching Beats

The preferred long-term synchronization model is to organize explanations into small semantic **teaching beats**.

A teaching beat represents one short piece of explanation together with its associated visual actions.

Example:

```json
{
  "beat_id": "beat_3",
  "speech_context": "Force equals mass multiplied by acceleration.",
  "board_operations": [
    {
      "type": "write_equation",
      "content": "F = ma"
    }
  ]
}
```

Conceptually:

```text
Beat 1
  speech: introduce concept
  board: write title

Beat 2
  speech: introduce equation
  board: write equation

Beat 3
  speech: explain variables
  board: add labels/arrows
```

This gives the system a natural unit for synchronization without forcing the tutor to stop after every visual operation.

The initial implementation does not have to fully redesign the tutor around beats, but the architecture should not prevent this future evolution.

---

## 10. Synchronization Strategies

The detailed implementation may choose one of the following or a hybrid approach.

### Strategy A — Reactive Board Director

The Tutor Agent begins speaking normally.

The Board Director observes tutor-generated text/transcription/events and generates visual actions based on what is currently being explained.

```text
Tutor speaks
     |
     v
Tutor transcript/event
     |
     v
Board Director
     |
     v
BoardPlan
```

Advantages:

- easier to integrate with the current agent,
- minimal tutor refactor,
- board is based on what the tutor actually says.

Tradeoff:

- visual actions may lag slightly behind speech.

This is likely the best starting point.

### Strategy B — Planned Teaching Beats

Before a short section is spoken, the system creates a teaching beat containing both speech intent and visual intent.

```text
Teaching Beat
    |
    +--> Tutor speech
    |
    +--> Board operations
```

Advantages:

- stronger synchronization,
- visual preparation can begin before speech playback,
- deterministic coordination.

Tradeoff:

- more changes to the current tutor-generation pipeline.

### Recommended Direction

Start with **reactive Board Director + deterministic executor**, but design message schemas so the system can later transition toward teaching beats without rewriting the entire board architecture.

---

## 11. Session Event Layer

The Tutor Agent and Board Director should communicate through events rather than direct function coupling.

Possible internal events:

```text
session_started
topic_started
section_started
tutor_text_generated
tutor_speech_started
tutor_speech_finished
student_interrupted
student_question
reexplanation_requested
example_started
topic_completed
session_ended
```

An internal async queue or event bus can initially be used.

Example:

```text
Tutor Agent
     |
     v
asyncio.Queue
     |
     v
Board Director
```

A dedicated infrastructure product is not required for the first version.

Python `asyncio` is sufficient unless system complexity later requires a larger orchestration framework.

---

## 12. Interruption and Cancellation Model

Student interruptions are a first-class requirement.

Example:

```text
Tutor:
"The derivative becomes..."

Board:
queues equation + arrow + highlight

Student:
"Wait, why?"
```

The old queued visuals must not continue appearing after the teaching direction changes.

Each teaching generation should therefore have a unique identifier:

```text
generation_id
```

Example:

```text
gen_145
```

Every BoardPlan is associated with that generation.

When the tutor is interrupted or a new teaching generation starts:

```text
current generation changes
        |
        v
pending commands from previous generation are cancelled
```

Any delayed BoardPlan arriving with an old `generation_id` must be discarded.

This prevents stale visual operations from corrupting the current explanation.

---

## 13. Board Versioning

Board state should use optimistic versioning.

Example:

```json
{
  "board_version": 21,
  "operations": [...]
}
```

The Board Runtime knows the current board version.

If a plan is generated against version 19 but the board is already at version 21, the runtime may:

- reject the plan,
- request regeneration,
- reconcile safe operations,
- or reload current semantic board state.

The exact strategy can be decided during implementation planning.

The main requirement is that delayed model responses must not blindly mutate a newer board state.

---

## 14. Frontend Communication

The existing LiveKit connection should be reused where practical.

The recommended initial transport for structured board commands is **LiveKit RPC or structured data messages**.

Conceptually:

```text
Board Runtime
      |
      | BoardPlan / BoardOperation
      v
LiveKit
      |
      v
Next.js frontend
      |
      v
Board Renderer
```

The frontend should acknowledge important commands.

Example response:

```json
{
  "ok": true,
  "operation_id": "op_891",
  "board_version": 22
}
```

This allows the runtime to detect rendering failures and keep backend state synchronized with the browser.

---

## 15. Suggested Backend Concurrency Model

For the initial implementation, use normal Python asynchronous tasks.

Conceptually:

```python
tutor_event_queue = asyncio.Queue()
board_plan_queue = asyncio.Queue()
```

Long-running session tasks:

```text
Tutor Agent Loop
Board Director Loop
Board Executor Loop
```

Example:

```text
Tutor Event
    |
    v
Board Director Loop
    |
    v
BoardPlan Queue
    |
    v
Board Executor Loop
    |
    v
Frontend
```

This is intentionally simpler than introducing a full multi-agent orchestration framework immediately.

---

## 16. Relationship With Current Sanad Architecture

The Board System should integrate with the existing Sanad delivery architecture rather than replace it.

Current relevant technologies include:

- Next.js frontend,
- LiveKit React components,
- LiveKit Python SDK for the tutor agent,
- Langfuse for observability and prompt/version tracking,
- structured teaching plans,
- Bunny.net content/plan storage,
- Postgres/Supabase-style persistence where needed.

Sanad already treats the **Teaching Plan** as the important intelligence asset and the voice agent as the delivery layer. The Board System should follow the same principle: it is another delivery mechanism derived from teaching context, not a separate source of pedagogical truth.

The Board Director should therefore consume the existing teaching plan and session context whenever available rather than independently deciding what the lesson should teach.

---

## 17. Relationship With Existing Visual Actions

Sanad already supports visual actions such as slide navigation and text highlighting.

The new board should eventually become part of a unified **Visual Delivery Layer**.

Conceptually:

```text
Visual Delivery Layer

    +-- Slide navigation
    +-- Slide highlighting
    +-- Board writing
    +-- Board diagrams
    +-- Checkpoints / questions
```

The detailed implementation should inspect whether existing `visual_actions` schemas, UI-control channels, or event patterns can be extended rather than building entirely separate infrastructure.

However, board state should remain explicitly modeled because it is persistent and compositional in a way that simple slide highlights are not.

---

## 18. Observability

Board behavior should be observable through Langfuse or the existing session observability stack.

Useful events/metadata:

```text
board_plan_generated
board_plan_latency
board_operation_sent
board_operation_rendered
board_operation_failed
board_plan_cancelled
board_plan_stale
board_reset
```

Recommended metadata:

```text
session_id
course_id
topic_id
teaching_plan_version
generation_id
board_version
board_director_prompt_version
model
latency
operation_count
```

This will make it possible to evaluate whether the board improves learning and whether failures are caused by:

- Board Director reasoning,
- synchronization,
- networking,
- rendering,
- stale state,
- tutor behavior.

---

## 19. Reliability Principles

Because the board is a core feature, reliability should be prioritized over open-ended creative behavior.

### Required principles

1. **Structured outputs only** from the Board Director.
2. **Strict schema validation** before frontend execution.
3. **Small command DSL** in the first version.
4. **Batch operations** instead of repeated LLM calls.
5. **Semantic board state** instead of visual/pixel reasoning.
6. **Generation-based cancellation** for interruptions.
7. **Board versioning** for stale-response protection.
8. **Frontend owns animation and layout.**
9. **Board Runtime owns execution.**
10. **Board Director owns visual reasoning only.**
11. **Tutor Agent owns pedagogy and conversation.**

---

## 20. Performance Requirements

The system should avoid noticeably slowing down the tutor.

General goals:

- Board Director processing should run asynchronously whenever possible.
- Tutor speech should not normally wait for non-critical board rendering.
- Simple board operations should appear quickly enough to feel synchronized with speech.
- Board generation should use a fast model unless complex visual reasoning clearly requires a larger one.
- Existing board state should be summarized compactly to control token usage.
- Multiple visual operations should be generated in one model response.
- Long-running board work should be cancellable.

The detailed implementation plan should define measurable latency targets based on the current voice pipeline.

---

## 21. Model Choice

The Board Director does not necessarily need the same model used by the Tutor Agent.

Its task is narrower:

```text
teaching context
+
current board state
+
current explanation
        |
        v
structured visual plan
```

The implementation should evaluate a relatively fast and inexpensive model with strong structured-output/tool-use performance.

The architecture should keep the Board Director model configurable so that models can be benchmarked independently from the Tutor Agent.

---

## 22. Framework Guidance

### Recommended for the first implementation

- LiveKit Python SDK
- LiveKit session events
- LiveKit RPC/data transport
- Python `asyncio`
- Pydantic or equivalent strict schemas
- existing Next.js board UI
- Langfuse

### Potential future orchestration tools

A more advanced workflow framework such as LangGraph may become useful if Sanad later introduces several coordinated specialist systems, for example:

```text
Tutor Agent
Board Director
Student Model
Exercise Agent
Retrieval Agent
Planning Agent
```

For the current Board System, adding a heavy orchestration framework is not required.

The coding agent should prefer the simplest architecture that supports concurrency, cancellation, state, and observability.

---

## 23. Initial Implementation Scope

The first production-capable version should focus on the smallest useful system.

### In Scope

- Board Director as an independent LLM loop.
- Tutor-to-board event stream.
- Semantic BoardState.
- Structured BoardPlan schema.
- Batched board operations.
- Board Runtime / Executor.
- Generation-based cancellation.
- Board versioning.
- LiveKit transport to frontend.
- Frontend command acknowledgement.
- Basic operations:
  - write text,
  - write equation,
  - arrow,
  - line,
  - box,
  - highlight,
  - erase,
  - clear region.
- Basic animated rendering.
- Observability.

### Out of Scope for Initial Version

- arbitrary freehand AI drawing,
- image generation,
- complex scientific diagrams,
- graph plotting,
- collaborative student drawing,
- persistence of boards between sessions,
- multi-user boards,
- full LangGraph migration,
- advanced autonomous layout reasoning,
- board-generated assessment logic.

These can be added later if the basic architecture proves reliable.

---

## 24. Suggested Development Phases

### Phase 1 — Stabilize Current Board API

Before introducing the Board Director:

- convert the current board tool into a batched `BoardPlan` style API,
- define strict command schemas,
- move layout/animation responsibility to the frontend,
- make each command address semantic board objects by ID.

Goal:

> Remove dependence on one tool call per visual action.

---

### Phase 2 — Introduce Board Director

Create:

```text
BoardDirector
BoardState
BoardPlan
BoardRuntime
TutorEventQueue
```

The main tutor publishes teaching events.

The Board Director observes them and generates plans independently.

The tutor no longer directly manages detailed board operations.

Goal:

> Decouple visual reasoning from the tutor turn lifecycle.

---

### Phase 3 — Synchronization and Cancellation

Add:

- generation IDs,
- command cancellation,
- board versions,
- frontend acknowledgements,
- stale-plan rejection,
- latency instrumentation.

Goal:

> Make the system safe under interruptions and real-world voice interaction.

---

### Phase 4 — Teaching Beats

Gradually introduce semantic teaching beats so that speech and board actions can be prepared together.

Goal:

> Improve synchronization and make the board feel intentionally choreographed rather than reactive.

---

## 25. Success Criteria

The first version should be considered successful when:

- the Tutor Agent can teach normally without manually performing many board tool calls;
- the Board Director consistently produces useful visuals during explanations;
- one Board Director response can create several visual operations;
- board commands do not continue after a student interruption;
- stale model responses cannot overwrite newer board state;
- frontend rendering failures are observable;
- board actions do not noticeably degrade speech latency;
- board behavior is reproducible enough to test through automated scenarios;
- visual behavior can be evaluated separately from tutor quality.

---

## 26. Important Open Questions for the Implementation Planning Stage

The coding agent should inspect the current codebase and decide:

1. Where Tutor Events should be emitted in the existing LiveKit agent pipeline.
2. Whether generated LLM text can be observed before TTS playback.
3. Whether the first version should react to generated tutor text or final transcription.
4. Which existing visual-action infrastructure can be reused.
5. Whether LiveKit RPC or data messages are the better transport for each board command.
6. Where authoritative BoardState should live.
7. Whether BoardState should be persisted or remain session-local initially.
8. How frontend acknowledgements should be handled.
9. How operation timing should map to tutor speech.
10. How the existing session interruption mechanism can propagate cancellation to the Board Runtime.
11. Which model should run the Board Director.
12. How Board Director prompts and model versions should be tracked in Langfuse.
13. How to test board quality automatically.
14. How to benchmark board latency.
15. Whether teaching-plan `visual_actions` should be extended to include board hints.

---

## 27. Target End State

The desired experience is:

```text
Student asks / listens
        |
        v
Tutor naturally teaches
        |
        +------------------------------+
        |                              |
        v                              v
   Spoken explanation           Teaching context
                                       |
                                       v
                                Board Director
                                       |
                                       v
                                Board Runtime
                                       |
                                       v
                               Visual explanation
```

The student should experience this as one coherent tutor.

Internally, however, the system should have clear separation of responsibilities:

```text
Tutor        -> what should be taught and said
Board Director -> what should be shown
Board Runtime  -> when/how commands are executed safely
Frontend       -> how the visuals are rendered
```

This separation should make the board substantially more reliable, easier to test, easier to improve, and easier to evolve into a major part of Sanad's teaching experience.
