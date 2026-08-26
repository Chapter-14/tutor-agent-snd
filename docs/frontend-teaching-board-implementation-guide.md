# Frontend Implementation Guide: AI Teaching Board

## Goal

Implement the V1 AI Teaching Board in the frontend repository:

```text
/home/moaz/dev/work/chapter-14/sanad/web-client-snd
```

The LiveKit agent implementation is complete. Do not change the Python agent or add another
realtime channel. The frontend must render semantic board updates received through the existing
LiveKit `ui-control` data topic.

For broader product context and non-MVP ideas, see
`../tutor-agent-snd/docs/sanad_ai_teaching_board_feature.md`.

## Agent Event Contract

The implemented payload uses `action`, not `type`. Packets are UTF-8 JSON sent reliably and in
order on the `ui-control` topic.

```ts
type BoardControlEvent =
  | { action: "board_show" }
  | { action: "board_hide" }
  | { action: "board_clear" }
  | { action: "board_set_title"; id: string; text: string }
  | { action: "board_add_bullet"; id: string; text: string }
  | { action: "board_add_text"; id: string; text: string }
  | { action: "board_add_step"; id: string; text: string }
  | { action: "board_emphasize"; id: string };
```

Example payloads:

```json
{"action":"board_show"}
{"action":"board_set_title","id":"board-set-title-...","text":"TCP"}
{"action":"board_add_bullet","id":"board-add-bullet-...","text":"Reliable delivery"}
{"action":"board_add_text","id":"board-add-text-...","text":"TCP confirms packet delivery."}
{"action":"board_add_step","id":"board-add-step-...","text":"Establish the connection"}
{"action":"board_emphasize","id":"board-add-bullet-..."}
{"action":"board_clear"}
{"action":"board_hide"}
```

Apply these semantics exactly:

- `board_show`: show the board and preserve all content.
- `board_hide`: hide the board and preserve all content.
- `board_clear`: remove the title and all content, clear emphasis, and preserve visibility.
- `board_set_title`: replace the existing title; there can be only one title.
- `board_add_*`: append a content item in packet arrival order.
- `board_emphasize`: emphasize the matching title or content item and remove emphasis from every
  other item.
- Title and add events should also make the board visible. The agent normally sends `board_show`
  first, but handling this in the reducer keeps the UI robust.
- IDs are opaque backend-generated strings. Never generate, parse, or modify them in the frontend.
- Ignore duplicate add events, unknown actions, malformed payloads, missing fields, over-limit
  content, and emphasis for an unknown ID. Never let an invalid packet crash the study session.

Agent-enforced limits should also be treated as frontend validation boundaries:

- One title.
- At most six non-title content items.
- Title text: at most 80 characters after trimming.
- Bullet, text, and step text: at most 180 characters after trimming.

## Existing Integration Points

Use the current structure rather than creating a parallel session architecture:

- `src/app/(app)/[course]/[chapter]/study/page.tsx` owns the slide canvas and should own board
  state because the board is rendered beside the PDF.
- `src/components/study/agent-launcher.tsx` creates the LiveKit session and should pass the board
  dispatcher to `SessionManager`.
- `src/components/study/session-manager.tsx` already handles `RoomEvent.DataReceived` for the
  `ui-control` topic. Extend this handler with board events.
- `src/components/study/pdfCanvas.tsx` renders the current slide viewer. Keep its scrolling,
  carousel, markers, zoom, and controls working when its width changes.
- `src/types/types.ts` contains `UIControlData` and component prop types. Add the board event fields
  or use a separate discriminated board event type.

## Recommended Files

Keep the implementation small:

```text
src/components/study/teaching-board.tsx
src/lib/teaching-board.ts
```

`src/lib/teaching-board.ts` should contain the board types, initial state, runtime event guard, and
pure reducer. `teaching-board.tsx` should only render the state with normal React/DOM elements.
Do not use an HTML canvas or a whiteboard library.

Suggested state:

```ts
type BoardItemType = "title" | "bullet" | "text" | "step";

type BoardItem = {
  id: string;
  type: BoardItemType;
  text: string;
};

type BoardState = {
  visible: boolean;
  title: BoardItem | null;
  items: BoardItem[];
  emphasizedId: string | null;
};
```

Do not store derived step numbers or an `emphasized` flag on every item. Derive step numbers during
rendering and compare each item ID with `emphasizedId`.

## Implementation Steps

1. Add the board model, parser/type guard, initial state, and reducer.
2. Add reducer tests before connecting it to LiveKit.
3. Create `TeachingBoard` with separate rendering for title, bullet, text, and numbered step items.
4. In the study page, initialize the reducer and place the PDF and board in one responsive content
   region.
5. Pass the reducer dispatcher through `AgentLauncher` to `SessionManager`.
6. In the existing `DataReceived` listener, safely decode and parse JSON. If the topic is
   `ui-control` and the value is a valid board event, dispatch it and return. Preserve all existing
   scroll, topic, section, marker, checkpoint, and session-ending behavior.
7. Dispatch a local reset action on session disconnect so a new session starts with a hidden,
   empty board.
8. Run lint, type checking, tests, and a production build.

Do not use unguarded `JSON.parse`. Wrap decoding/parsing in `try/catch`, verify the parsed value is a
non-null object, and narrow board events at runtime before dispatching.

## Layout and Visual Behavior

- Hidden board: the PDF uses the full content width.
- Visible board on desktop: use a responsive two-column layout with approximately 65–70% for the
  PDF and 30–35% for the board.
- Visible board on narrow screens: stack the board below the PDF in the same scrollable content
  region. Do not squeeze either surface into an unusable width.
- Keep the agent/session controls visible and usable in both layouts.
- Add `min-w-0` and `min-h-0` where needed so the existing carousel can resize without horizontal
  overflow.
- The board may scroll internally when its content does not fit, but the six-item limit should keep
  this uncommon.
- Render the board with semantic DOM elements. A `section` with an accessible label is sufficient.
- Use stable backend IDs as React keys.
- Use `dir="auto"` on the title and each item so Arabic, English, and mixed Arabic/English technical
  text render correctly. Use logical alignment such as `text-start`, not fixed left alignment.
- Number only step items, in the order step items were added. Bullets and normal text do not affect
  step numbering.
- Make explicit emphasis visually stronger than the normal item-entry animation. Use the existing
  navy/gold visual language and preserve readable contrast.
- Animate show/hide and new item appearance with short, lightweight CSS transitions. Respect
  `prefers-reduced-motion`; do not build a timeline or synchronize individual TTS words.
- A visible cleared board should remain as an empty board surface. Do not invent placeholder lesson
  content.

## Reducer Tests

Cover at least these cases:

- Show and hide preserve content.
- Clear removes content and emphasis but preserves visibility.
- Setting a second title replaces the first title.
- Bullet, text, and step events append in arrival order.
- Content events make a hidden board visible.
- Emphasis is exclusive and may target the title.
- Emphasis with an unknown ID is ignored.
- Duplicate IDs do not create duplicate items.
- A seventh content item is ignored.
- Empty, missing, wrongly typed, and over-length fields are ignored.
- Unknown actions and malformed JSON do not throw.
- Local session reset returns the exact initial state.

If the repository still has no test runner, add the smallest suitable unit-test setup for the pure
reducer. Do not introduce browser end-to-end tooling solely for this feature.

## Manual Verification Sequence

Verify the UI with events in this order, without involving the LLM:

```text
board_show
board_set_title("TCP")
board_add_bullet("Reliable delivery")
board_add_bullet("Ordered packets")
board_emphasize(first bullet ID)
board_add_step("Establish the connection")
board_hide
board_show
board_clear
```

Expected result:

- The board opens without reloading the page.
- Items appear once and in order.
- The first bullet is the only emphasized item.
- The step displays as step 1.
- Hide/show restores the same content.
- Clear leaves a visible empty board.
- The PDF remains navigable and its markers, zoom, and toolbar still work.
- Arabic and mixed Arabic/English text have the correct direction and alignment.
- Disconnecting and starting a new session produces a hidden empty board.

Run from the frontend repository:

```bash
pnpm lint
pnpm type-check
pnpm build
```

Also run the reducer tests using the test command added or already available in the repository.

## V1 Non-Goals

Do not add freehand drawing, student editing, dragging, resizing, coordinates, shapes, diagrams,
images, export, persistence, board history, speech transcription, word-level synchronization, or
student controls for mutating board content.

## Acceptance Criteria

- All eight board actions work through the existing `ui-control` LiveKit handler.
- The PDF and agent controls remain fully usable when the board is visible.
- Arabic, English, RTL, LTR, and mixed technical text render correctly.
- Title, bullets, normal text, numbered steps, clearing, hiding, and exclusive emphasis render as
  specified.
- Events update the React UI immediately without page reloads.
- Invalid events are ignored without errors or study-session disruption.
- Board state resets between LiveKit sessions and is not persisted.
- Desktop and mobile layouts are usable.
- Reducer tests, lint, type checking, and production build pass.
