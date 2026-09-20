# Frontend Migration Guide: Teaching Board on the Board Director Architecture

## Goal

The V1 teaching board is **already implemented and working** in the frontend prototype:

```text
/home/moaz/dev/work/chapter-14/sanad/test-web-client
```

That implementation was built against the previous agent, where the tutor LLM called a board tool
once per visual action. The agent has since been restructured: the board is now driven by a
**Board Director**, a second non-speaking LLM that watches the tutor's outgoing speech, emits
batched board operations, and hands them to a deterministic executor that paces them against the
explanation before publishing.

This document covers **only the delta**. It is not a build guide. Do not rebuild the reducer, the
component, the layout, or the event parser.

## What Does Not Change

The wire contract is byte-for-byte identical. Everything below is already correct and must be left
alone:

- `src/lib/teaching-board.ts` — `BoardState`, `parseBoardControlEvent`, `teachingBoardReducer`.
  The action names, payload shapes, id semantics, six-item cap, and 80/180 character limits all
  still match the agent exactly.
- `src/components/study/teaching-board.tsx` — title, bullet, text, numbered step, exclusive
  emphasis, entry animation, `dir="auto"`, `prefers-reduced-motion`.
- `src/app/(app)/study/page.tsx` — the `lg:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]` split,
  `min-w-0` / `min-h-0` handling, and the hidden-when-absent board column.
- The guarded `JSON.parse` and board-event-first dispatch in `session-manager.tsx`.
- `board_reset` on session start, disconnect, and teardown in `agent-launcher.tsx`.
- The progression protocol. `set_lesson`, `set_topic` (carrying `current_topic_index`, `question`,
  `choices`), and `topic_done` are already the agent's vocabulary. No renaming is needed.

The agent never sends coordinates, never sends `generation_id`, and still expects no
acknowledgement. Board ids remain opaque backend strings.

---

## 1. Delete the Dead Marker Path

The agent no longer sends slide markers at all. `add_markers` and `remove_markers` are gone from the
agent's vocabulary, so this code can never run again.

Remove:

- the `add_markers` and `remove_markers` branches in `session-manager.tsx`, and the
  `pendingTimeouts` ref plus its `clearTimeout` cleanup that exist only to serve them;
- `markerPayload` and `UIMarkersUpdates` in `src/types/types.ts`, and the `add` / `remove` fields on
  `UIControlData`;
- `activeMarker` / `setActiveMarker` state in `src/app/(app)/study/page.tsx`, the prop threading
  through `agent-launcher.tsx` and `session-manager.tsx`, and the `activeMarker` prop on
  `PdfCanvas`.

`scroll` and `session_ending` are unaffected and stay exactly as they are.

---

## 2. `board_hide` Is Now Unreachable

`show` and `hide` were deliberately removed from the Board Director's vocabulary — visibility is
owned by agent-side code, not by a model. In practice the agent now emits:

- `board_show` exactly once, implicitly, with the first content item of the session;
- `board_hide` **never**.

Once the board appears it stays visible for the rest of the session, and `board_reset` on disconnect
returns it to hidden. Seven of the eight actions are reachable.

Keep the `board_hide` branch in the reducer — it costs nothing and keeps the reducer a total
function over the documented contract — but do not build UI that depends on the agent hiding the
board, and do not treat a permanently visible board as a bug.

---

## 3. Handle the Automatic Topic Frame

This is the one change with a visible UI consequence.

Every topic start now emits, deterministically and with no LLM involved:

```json
{"action":"board_clear"}
{"action":"board_set_title","id":"board-set-title-…","text":"<topic title>"}
```

These are two separate data packets, so they arrive as two `RoomEvent.DataReceived` events and
almost certainly produce two renders. Between them the board is visible, has no title, and has no
items.

The reducer already handles this correctly — `board_clear` preserves `visible`, so the column does
not collapse — but verify the render:

- The `<h3>` title block unmounts on `board_clear` and remounts on `board_set_title`. Because it is
  keyed by `state.title.id`, the enter animation replays, which is the desired effect at a topic
  boundary.
- Confirm the header does not visibly jump as the title element is removed and re-added. Reserving
  the title row's height, or animating only opacity rather than layout, is enough if it does.
- Do not add a placeholder, skeleton, or "loading" state for the gap. It is a few milliseconds.

---

## 4. Expect a Different Event Cadence

Events no longer arrive one per tutor tool call. The Director plans in batches and the executor
paces them against the spoken explanation:

- **Small bursts.** Two or three items can arrive within a few hundred milliseconds. The entry
  animation must absorb that without layout thrash. Do **not** stagger entry with JavaScript timers
  — the agent already paces the stream against speech, and adding client-side delay would
  double-pace it and desynchronise the board from the voice.
- **Long quiet stretches.** Most sentences produce no event. In a representative turn the Director
  returned an empty plan for half its windows. A visible board holding a title and two bullets is a
  normal steady state, not a stalled one.
- **Nothing after an interruption.** When the student interrupts, pending operations are cancelled
  agent-side. Already-rendered items stay; simply stop expecting more.
- **A realistic timeline**, measured end to end on a 28-second explanation whose text the tutor LLM
  generated in 0.7 seconds:

  ```text
  t= 0.0s  board_clear
  t= 0.0s  board_show
  t= 0.0s  board_set_title    Transport Layer: TCP
  t= 3.3s  board_add_bullet   Reliable delivery
  t= 7.1s  board_add_bullet   Ordering
  t=12.9s  board_add_bullet   Connection oriented
  ```

---

## 5. Mixed Arabic and English Is Now the Common Case

The Director mirrors the tutor's own wording rather than translating it. In an Arabic session the
tutor keeps technical terms in English, so a single board routinely holds both scripts:

```text
Transport Layer: TCP
• Reliable delivery
• الترتيب
• Connection oriented
• Handshake
```

`dir="auto"` is already applied per item and to the title, which resolves each item independently
and is the correct behaviour. What to verify now that this is routine rather than exceptional:

- bullet markers and step badges sit on the correct side for each item individually, so a list can
  legitimately have mixed marker sides;
- an English item inside an otherwise Arabic board does not break the `text-start` alignment of its
  neighbours;
- long Latin technical terms wrap rather than overflow the narrower board column.

Board text arrives pre-normalised: trimmed, sentence-cased for Latin script, and within the length
limits. The frontend should not re-case, re-trim, or truncate it.

---

## 6. Fix Step Numbering for English Sessions

`teaching-board.tsx` hardcodes the step number locale:

```ts
const stepNumberFormatter = new Intl.NumberFormat("ar-SA");
```

This renders step 1 as `١` regardless of session language, which is wrong for an English session.
The session language is chosen in `agent-launcher.tsx` and passed to the agent as a participant
attribute; thread it through to `TeachingBoard` and select the locale from it, or fall back to the
default locale formatter when the session is English.

---

## Verification

Run against the agent on the `003-improve-agent-plans` branch with the Board Director active.

Board behaviour:

- Start a lesson. The board opens with the topic title before the tutor's first explanatory
  sentence, with no visible flicker between clear and title.
- Let a full topic play. Items appear progressively across the explanation, roughly one per
  teaching beat, not all at once and not after the tutor has moved on.
- Interrupt mid-explanation. No new items appear; existing ones remain.
- Advance to the next topic. The board clears and re-titles in one clean transition.
- Run one Arabic and one English lesson. Check mixed-script rendering and step numbering in both.
- Let a topic run long enough to hit six items and confirm the seventh is silently ignored rather
  than overflowing the column.
- Disconnect and start a new session. The board is hidden and empty.

Regression:

- The PDF stays navigable with its carousel, zoom, and toolbar intact while the board is visible.
- Checkpoint questions still appear — they ride on `set_topic`, not a separate event.
- Nothing references markers any more; `pnpm build` fails on a missed import if the deletion in
  step 1 was partial.

Commands:

```bash
pnpm lint
pnpm type-check
pnpm build
```

`test-web-client` has no test runner and this change does not justify adding one. The reducer is
already pure; if a runner is introduced for other reasons, it is the first thing worth covering.

---

## Still Out of Scope

Freehand drawing, student editing, dragging, resizing, coordinates, shapes, arrows, diagrams,
images, equations, export, persistence, board history, speech transcription, word-level
synchronisation, render acknowledgements, and student controls for mutating board content.
