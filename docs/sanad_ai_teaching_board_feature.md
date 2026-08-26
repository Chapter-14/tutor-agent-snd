# Sanad AI Teaching Board — High-Level Feature Overview

## 1. Feature Summary

The **AI Teaching Board** is a lightweight visual surface inside the Sanad studying canvas that allows the AI tutor to progressively write short teaching notes while explaining a topic.

The first version is intentionally simple. It should **not** behave like a full whiteboard or drawing application. Instead, it should behave more like a PowerPoint slide being built live during the explanation:

- A title can appear.
- Bullets can appear one at a time.
- Short explanatory text can appear.
- Numbered steps can appear.
- The currently discussed point can be emphasized.
- The board can be cleared when the tutor moves to a new concept.

The goal is to make the explanation feel more like a real tutoring session without introducing the complexity of freehand drawing, canvas rendering, or collaborative whiteboard tooling.

---

## 2. Product Goal

The board should make Sanad feel more interactive by giving students a visual representation of the AI's explanation in addition to:

- voice explanation,
- the original course slides,
- slide highlighting,
- checkpoints,
- and student questions.

The intended interaction model is:

> **Slides = source material**  
> **AI Teaching Board = Sanad's explanation space**

The board should contain only the most important ideas that help the student follow the explanation. It should not become a transcript of everything the AI says.

---

## 3. Current Platform Context

The feature should be implemented using the current Sanad architecture:

### Frontend
- Next.js
- React
- Existing studying canvas
- Existing slide/PDF viewer
- Existing LiveKit React session integration

### Agent
- LiveKit Python SDK
- Existing voice AI agent
- Existing structured teaching/explanation flow
- Existing UI-control communication between the agent and the frontend

### Supporting Systems
- Langfuse for observability
- Structured teaching plans
- Bunny.net for course/plan content storage

The feature should reuse the current agent-to-frontend UI control mechanism instead of introducing a separate realtime communication system.

---

## 4. MVP Scope

The first version should support only the following board actions:

1. Open/show the board
2. Hide the board
3. Clear the board
4. Set a board title
5. Add a bullet point
6. Add normal text
7. Add a numbered step
8. Emphasize one existing board item

The board should support:

- Arabic
- English
- RTL and LTR layouts
- simple appearance animations
- responsive rendering inside the studying canvas

---

## 5. Explicit Non-Goals for V1

Do **not** build the following in the first version:

- Freehand drawing
- Student drawing
- AI-generated freehand drawing
- Dragging or resizing board elements
- Manual text editing by the student
- Shapes
- Arrows
- Diagrams
- Images
- Coordinate-based placement
- Canvas libraries
- Excalidraw or tldraw integration
- Board saving or export
- Word-by-word TTS synchronization
- A persistent notebook
- Automatic transcription of the AI speech into board content

These can be considered later after validating the basic interaction.

---

## 6. Board UI Behavior

### Recommended Layout

The board should appear beside the current slide viewer.

Default state:

- Slide viewer uses the full available content area.
- Teaching board is hidden.

When the board is activated:

- Slide viewer shrinks to roughly 65–70%.
- Teaching board occupies roughly 30–35%.
- Existing agent/session controls remain available.

Example:

```text
┌─────────────────────────────┬──────────────────┐
│                             │                  │
│                             │   Sanad Board    │
│        Course Slide         │                  │
│                             │   TCP            │
│                             │   • Reliable     │
│                             │   • Ordered      │
│                             │                  │
└─────────────────────────────┴──────────────────┘
              Session Controls
```

The exact percentage can be adjusted based on the existing studying canvas layout.

---

## 7. Board Content Model

The board should be implemented as normal React/DOM elements, not an HTML `<canvas>`.

Suggested data model:

```ts
type BoardItemType =
  | "title"
  | "bullet"
  | "text"
  | "step";

type BoardItem = {
  id: string;
  type: BoardItemType;
  text: string;
  order: number;
  emphasized?: boolean;
};

type BoardState = {
  visible: boolean;
  items: BoardItem[];
};
```

The frontend is responsible for all layout and styling.

The AI should never send coordinates such as:

```json
{
  "x": 245,
  "y": 180
}
```

Instead, the AI should send semantic instructions such as:

```json
{
  "type": "board_add_bullet",
  "text": "TCP provides reliable delivery"
}
```

This keeps the feature robust and predictable.

---

## 8. Frontend Architecture

Suggested structure:

```text
StudyCanvas
│
├── SlideViewer
├── TeachingBoard
│   ├── BoardTitle
│   ├── BoardBullet
│   ├── BoardText
│   └── BoardStep
│
└── AgentControls
```

Suggested files/modules:

```text
components/study/
├── TeachingBoard.tsx
├── BoardItem.tsx
└── StudyCanvas.tsx

lib/board/
├── boardTypes.ts
└── boardReducer.ts

hooks/
└── useUIControl.ts
```

A reducer is recommended for handling board state.

Example actions:

```ts
type BoardAction =
  | { type: "BOARD_SHOW" }
  | { type: "BOARD_HIDE" }
  | { type: "BOARD_CLEAR" }
  | { type: "BOARD_ADD_ITEM"; item: BoardItem }
  | { type: "BOARD_EMPHASIZE"; id: string };
```

---

## 9. Agent-to-Frontend Events

Reuse the current `ui-control` communication channel used for other agent-driven UI actions.

Suggested events:

### Show Board

```json
{
  "type": "board_show"
}
```

### Hide Board

```json
{
  "type": "board_hide"
}
```

### Clear Board

```json
{
  "type": "board_clear"
}
```

### Set Title

```json
{
  "type": "board_set_title",
  "id": "board-title-1",
  "text": "TCP"
}
```

### Add Bullet

```json
{
  "type": "board_add_bullet",
  "id": "bullet-1",
  "text": "Reliable delivery"
}
```

### Add Text

```json
{
  "type": "board_add_text",
  "id": "text-1",
  "text": "TCP confirms that packets arrive correctly."
}
```

### Add Step

```json
{
  "type": "board_add_step",
  "id": "step-1",
  "text": "Establish the connection"
}
```

### Emphasize Item

```json
{
  "type": "board_emphasize",
  "id": "bullet-1"
}
```

The frontend should ignore invalid or unknown actions without breaking the study session.

---

## 10. AI Tool Design

The simplest initial implementation should expose one general board tool to the agent.

Example conceptual tool:

```python
update_teaching_board(
    action: str,
    text: str | None = None,
    item_id: str | None = None
)
```

Supported actions:

```text
show
hide
clear
set_title
add_bullet
add_text
add_step
emphasize
```

The Python function should translate the tool call into a UI-control message and send it to the frontend.

Example:

```python
@function_tool()
async def update_teaching_board(
    self,
    action: str,
    text: str | None = None,
    item_id: str | None = None,
) -> str:

    await self.send_ui_control({
        "type": f"board_{action}",
        "text": text,
        "id": item_id,
    })

    return (
        "Teaching board updated successfully. "
        "Continue the current explanation."
    )
```

The exact implementation should follow the project's current LiveKit agent structure.

---

## 11. Multiple Board Calls in One Agent Turn

The agent must be able to perform several board updates during one explanation turn.

Example flow:

```text
Student finishes speaking
        ↓
AI starts explanation
        ↓
board_set_title("TCP")
        ↓
AI continues speaking
        ↓
board_add_bullet("Reliable delivery")
        ↓
AI continues speaking
        ↓
board_add_bullet("Ordered packets")
        ↓
AI continues speaking
        ↓
Final spoken explanation
        ↓
Agent turn ends
```

A board tool call should **not automatically mean the AI's teaching turn is finished**.

The session should allow several sequential tool calls before the final response.

The LiveKit agent session should therefore allow a reasonable number of tool steps per turn. A starting value around **6–8 tool steps** is sufficient for the MVP.

---

## 12. Agent Behavior Rules

Add clear instructions to the agent explaining how and when to use the board.

Recommended rules:

```text
The teaching board is a visual aid used during explanations.

Use the board only for important information that helps the student
follow the explanation.

Keep each board item short.

Do not copy full paragraphs from the slide.

A board tool call does not end the current teaching turn.

After a successful board update, continue the same explanation
unless student input is required.

You may use multiple board updates during one teaching turn.

Use one board update for each meaningful teaching beat.

Prefer 3–5 visible points at a time.

Clear the board when moving to a substantially different concept.

Do not use the board as a transcript of your speech.

Only end your teaching turn when:
1. the current teaching unit is complete,
2. you ask the student a question,
3. or student input is required.
```

---

## 13. Recommended Teaching Patterns

The board should initially support four common teaching patterns.

### 13.1 Key Points

```text
Photosynthesis

• Uses sunlight
• Consumes CO₂
• Produces glucose
```

### 13.2 Step-by-Step Process

```text
Binary → Decimal

1. Write powers of 2
2. Multiply each bit
3. Add the values
```

### 13.3 Definition

```text
Encapsulation

Bundling data and the operations
that manipulate that data.
```

### 13.4 Short Summary

```text
TCP

• Reliable
• Ordered
• Connection-oriented
```

These patterns should cover most V1 usage.

---

## 14. Animation Behavior

Animations should remain simple.

Recommended behavior:

- New board item fades or slides in.
- Newly added item receives temporary emphasis.
- Previously added items remain visible.
- Emphasized item receives a stronger accent.
- Clearing the board can use a short fade-out.

Avoid complex animation timelines.

The board should feel responsive and lightweight.

---

## 15. Timing and Synchronization

The MVP should synchronize board updates with the explanation at the **idea level**, not at the word level.

Example:

```text
Board action:
"Reliable delivery" appears

AI speech:
"The first important property of TCP is reliable delivery..."
```

The board action can happen immediately before the corresponding sentence begins.

Do not attempt to synchronize individual words with TTS output.

---

## 16. Interruption Handling

The feature must respect the existing conversational behavior.

If the student interrupts while Sanad is explaining:

- Stop generating further board actions for that teaching sequence if possible.
- Do not continue adding points that the AI has not yet explained.
- Keep already displayed board content visible.
- Continue normally when the next AI response begins.

This prevents the board from moving ahead of the actual conversation.

---

## 17. Teaching Plan Integration

The board should be compatible with Sanad's structured teaching-plan architecture.

Eventually a teaching step may contain visual actions such as:

```json
{
  "step_id": "tcp_intro",
  "objective": "Explain the key characteristics of TCP",
  "visual_actions": [
    {
      "type": "board_clear"
    },
    {
      "type": "board_set_title",
      "text": "TCP"
    },
    {
      "type": "board_add_bullet",
      "text": "Reliable delivery"
    },
    {
      "type": "board_add_bullet",
      "text": "Ordered packets"
    }
  ]
}
```

For V1, board actions may still be generated dynamically by the agent.

The implementation should avoid coupling the board so tightly to the agent that future pre-generated `visual_actions` become difficult to support.

---

## 18. Observability

Board actions should be logged when practical.

Useful events:

```text
board_opened
board_closed
board_cleared
board_item_added
board_item_emphasized
```

Useful metadata:

```text
session_id
course_id
chapter_id
topic_id
section_id
plan_version
board_action
timestamp
```

This can later help determine whether board usage improves understanding.

For example:

> Do sections that use the teaching board produce fewer re-explanation requests?

Observability should not block the initial frontend implementation.

---

## 19. Implementation Phases

### Phase 1 — Frontend Board

Build:

- `TeachingBoard`
- board state reducer
- title
- bullet
- text
- numbered step
- emphasize
- clear
- show/hide
- animations
- RTL/LTR support

Test using manually triggered frontend events.

### Phase 2 — UI-Control Integration

Extend the existing LiveKit UI-control event handler.

Support:

```text
board_show
board_hide
board_clear
board_set_title
board_add_bullet
board_add_text
board_add_step
board_emphasize
```

Test events directly without the LLM.

### Phase 3 — Agent Tool

Add the board function/tool to the LiveKit Python agent.

Confirm the agent can:

- call the board tool,
- receive a tool result,
- continue explaining,
- call the tool again,
- finish the same conversational turn.

### Phase 4 — Agent Prompting

Add board behavior instructions.

Test:

- excessive board use,
- very long text,
- unnecessary clearing,
- failure to continue after a tool call,
- too many tool calls,
- board updates unrelated to speech.

### Phase 5 — Teaching Plan Integration

Optionally support board actions coming from structured teaching plans through `visual_actions`.

This phase is not required for the first working version.

---

## 20. Acceptance Criteria

The feature is considered implemented when all of the following are true:

### Frontend

- The studying canvas can display and hide the teaching board.
- Existing slides remain usable when the board is visible.
- The board supports Arabic and English correctly.
- The board can display:
  - title,
  - bullets,
  - text,
  - numbered steps.
- Items appear with a simple animation.
- One item can be visually emphasized.
- The board can be cleared.

### Realtime Control

- The LiveKit agent can send board actions through the existing UI-control channel.
- Board events update the React UI without page reloads.
- Invalid board events do not crash the studying canvas.

### Agent

- The agent can call the board tool multiple times within one AI turn.
- A tool call does not automatically finish the teaching response.
- The AI continues explaining after a successful board update.
- The agent stops naturally after the explanation unit is complete.
- The number of board actions per turn is bounded.

### Experience

A student should be able to experience a flow similar to:

```text
Sanad:
"Let's understand TCP."

Board:
TCP

Sanad:
"The first property is that it provides reliable delivery."

Board:
TCP
• Reliable delivery

Sanad:
"It also guarantees that packets are processed in order."

Board:
TCP
• Reliable delivery
• Ordered packets

Sanad:
"So remember these two properties..."
```

without manually interacting with the board.

---

## 21. Future Expansion

After validating V1, the board can gradually support:

### V1.5

- two-column comparisons,
- equations,
- code blocks,
- simple tables,
- callout boxes.

### V2

- SVG arrows,
- rectangles,
- circles,
- labels,
- simple AI-generated diagrams.

### V3

- AI drawing,
- student drawing,
- collaborative whiteboard interactions,
- saved board notes,
- board history.

These should only be built after validating that the simple teaching board materially improves the study experience.

---

## 22. Final Implementation Principle

The feature should remain deliberately simple:

> **The AI decides the teaching intent.  
> The frontend controls the visual layout.**

The agent sends semantic actions such as:

```text
"add this bullet"
"show this title"
"emphasize this point"
```

The frontend decides where and how they appear.

This avoids fragile coordinate-based AI behavior and provides a clean path from a basic animated teaching board toward more advanced visual teaching features later.
