# Teaching Board v2 — Frontend Specification

**For the frontend engineer working on `test-web-client`.** This is a delta against the working V1
board, not a rebuild guide. Read §1 first: about half the existing implementation is untouched.

The agent change behind it: the board's content is now **authored in the lesson plan** rather than
invented live. A Board Director LLM only decides *when* the tutor has reached an authored note;
backend code assigns ids, owns regions and capacity, and publishes every mutation. The consequence
for you is that the board can now **change things already on screen** — fill a blank, mark an answer,
reveal the next line of a definition, remove one item — instead of only appending downward.

Everything below is structured text. There is no drawing engine, no canvas, no coordinates.

---

## 1. What does not change

Leave these alone:

- **The transport.** Reliable LiveKit data messages on the `ui-control` topic, JSON, one action per
  packet, no acknowledgement expected. Keep the guarded `JSON.parse` and the board-event-first
  dispatch in `session-manager.tsx`.
- **The progression protocol.** `set_lesson`, `set_topic` (carrying `current_topic_index`,
  `question`, `choices`), `topic_done`, `scroll`, `session_ending` are unchanged, byte for byte.
  Checkpoint questions still ride on `set_topic`.
- **`board_reset` on session start, disconnect and teardown** in `agent-launcher.tsx`.
- **`dir="auto"` per item and on the title.** Still correct, and now load-bearing (§7).
- **The layout split and `min-w-0` / `min-h-0` handling** in `study/page.tsx`.
- **`prefers-reduced-motion` handling.**
- **Do not stagger entry with JavaScript timers.** The agent paces every operation against the
  spoken audio. Client-side delay double-paces it and desynchronises the board from the voice.

Ids remain opaque backend strings. The agent never sends coordinates and never sends a generation id.

## 2. What is removed

- `board_add_bullet`, `board_add_text`, `board_add_step` — replaced by one `board_add` envelope (§4).
- `board_emphasize` — replaced by `board_annotate`, which is typed (§5.4).
- The six-item flat cap — replaced by three regions with their own limits (§3).

`board_set_title`, `board_show`, `board_hide`, `board_clear` survive, with changes noted below.

---

## 3. Regions

The board is no longer one list. It is three, and an item names its own:

| Region | Cap | Meaning | Lifecycle |
| --- | --- | --- | --- |
| `pinned` | 6 | The worked example or framework skeleton the student keeps referring back to | Survives `board_clear {scope: "live"}`. Only cleared by `scope: "all"` |
| `live` | 12 | The current stage of the explanation | Cleared when the tutor moves to a stage the author marked as replacing this one |
| `temporary` | 4 | A remediation detour — an analogy, a prerequisite | Cleared whole when the tutor returns to the main line |

Suggested arrangement, top to bottom: **title · pinned band · live column · temporary tray**. The
pinned band should read as a distinct, quieter surface — it is reference material, not the current
point. The temporary tray should read as clearly provisional; the student should not mistake it for
part of the topic.

An item can move between `live` and `pinned` at runtime (§5.6). Animate that move; do not let it
teleport.

Capacity is enforced by the backend. You will never be asked to render a thirteenth live item, and
you should not implement your own overflow policy — but the column must scroll vertically, because
twelve items plus a pinned band will not fit a portrait phone.

---

## 4. Wire protocol v2

Every message carries `rev`, a monotonically increasing integer (§9).

### 4.1 Frame

```json
{"action": "board_show",  "rev": 2}
{"action": "board_hide",  "rev": 41}
{"action": "board_clear", "scope": "all",       "rev": 1}
{"action": "board_clear", "scope": "live",      "rev": 18}
{"action": "board_clear", "scope": "temporary", "rev": 33}
{"action": "board_set_title", "id": "board-title-…", "text": "Objective of Revenue Recognition", "rev": 3}
```

`board_clear` **preserves visibility** — the column must not collapse. `scope` is always present;
treat a missing `scope` as `"all"` for safety.

`board_hide` is still never sent in production flow. Keep the branch; build nothing that depends on it.

### 4.2 Add

One envelope for all thirteen kinds:

```json
{
  "action": "board_add",
  "id": "board-definition-9c1c95f3…",
  "region": "live",
  "kind": "definition",
  "payload": { "chunks": ["…", "…", "…"], "key_words": ["transfer"] },
  "group_id": null,
  "rev": 4
}
```

`group_id` is `null` or the id of a container created by an earlier `board_group` (§4.4). When set,
render this item inside that container.

### 4.3 Mutate

```json
{"action": "board_update",   "id": "…", "text": "Element name: the price", "rev": 9}
{"action": "board_update",   "id": "…", "slot": "cause",   "text": "control transferred", "rev": 10}
{"action": "board_update",   "id": "…", "slot": "opt-b",   "state": "correct", "rev": 11}
{"action": "board_annotate", "id": "…", "kind": "key",     "rev": 12}
{"action": "board_annotate", "id": "…", "kind": null,      "rev": 13}
{"action": "board_remove",   "id": "…", "rev": 14}
{"action": "board_reveal",   "id": "…", "index": 1,        "rev": 15}
{"action": "board_pin",      "id": "…", "pinned": true, "region": "pinned", "rev": 16}
```

- `board_update` **without** `slot` replaces the item's `text`. Only items whose payload has a `text`
  field receive this.
- `board_update` **with** `slot` addresses a child: a blank id (carries `text`), or an option id or
  chain link index (carries `state`).
- `board_annotate` with `kind: null` clears the annotation. When a `key` annotation moves, you will
  receive the clearing message for the old item and the setting message for the new one, in that
  order, as two packets.
- `board_reveal`'s `index` is the 0-based index of the chunk that just became visible.

### 4.4 Group

```json
{"action": "board_group", "id": "board-group-…", "region": "live", "kind": "columns", "heading": "Signing vs satisfying", "rev": 7}
```

`kind` is `box` (several lines under one heading) or `columns` (side by side — but see §8). The
container always arrives **before** its first member, in the same burst. An empty container is
possible if a later add is rejected; render nothing, or the heading alone, rather than breaking.

### 4.5 Snapshot

```json
{
  "action": "board_snapshot",
  "rev": 22,
  "visible": true,
  "title": { "id": "…", "kind": "title", "region": "live", "payload": {"text": "…"}, "group_id": null, "annotation": null, "revealed": 1, "slots": {} },
  "groups": [ { "id": "…", "kind": "box", "region": "pinned", "heading": "Worked example" } ],
  "items":  [ { "id": "…", "kind": "step", "region": "pinned", "payload": {"text": "…"}, "group_id": "…", "annotation": null, "revealed": 1, "slots": {} } ]
}
```

Replace the entire board state with this. Item order in `items` is render order.

---

## 5. Item kinds

Thirteen kinds. Each payload shape is fixed and validated backend-side; you can rely on it.

### 5.1 Text-like — `heading`, `text`, `bullet`, `step`

```json
{"text": "Reliable delivery"}
```

As in V1: heading is a stage heading inside a topic (smaller than the board title, larger than
body); bullet takes a marker; step takes an auto-incrementing number **scoped to the region**; text
is the plain line.

Text arrives pre-normalised — trimmed, sentence-cased for Latin script, within 180 characters. Do
not re-case, re-trim or truncate it.

> **Open bug carried over from V1:** `teaching-board.tsx` hardcodes
> `new Intl.NumberFormat("ar-SA")` for step numbers, rendering step 1 as `١` in English sessions.
> The session language is chosen in `agent-launcher.tsx` and passed to the agent as a participant
> attribute; thread it through and pick the locale from it.

### 5.2 `definition` — progressive reveal

```json
{"chunks": ["Revenue depicts the transfer", "of promised goods or services", "in the amount expected"], "key_words": ["transfer"]}
```

On `board_add`, render **chunk 0 only**. Each `board_reveal` makes one further chunk visible, in
order. Reserve the full height up front if that avoids the surrounding layout jumping on each
reveal; a gentle fade-in per chunk is the right motion.

`key_words` are the words the exam rewards. Emphasise each occurrence inside the revealed chunks
(weight or highlight — pick one and use it consistently). They are plain strings; match
case-insensitively and do not attempt stemming.

### 5.3 `term` — bilingual token

```json
{"en": "performance obligation", "ar": "التزام الأداء"}
```

The `en` form is exactly what appears on the exam paper and must be visually primary. The `ar` gloss
is secondary — smaller, dimmer, parenthesised or on a second line. Both scripts sit in one token, so
the token needs its own bidi isolation (`unicode-bidi: isolate`, or a wrapper with explicit `dir`
per half). This token appearing inside an otherwise-Arabic board is the common case, not the edge.

### 5.4 States — `annotation`

| `kind` | Meaning | Suggested treatment |
| --- | --- | --- |
| `key` | The item the tutor is on right now. **Exclusive** — at most one on the board | The strongest emphasis you have |
| `warning` | Exam-strategy weight | Distinct from `key`, and never mistakable for an error |
| `correct` | Confirmed right after an answer | Success colour + icon (never colour alone) |
| `wrong` | Confirmed wrong | Error colour + icon |
| `broken` | A causal link the tutor just cancelled | Strikethrough, or a ✕ on the connector for a `chain` |
| `dim` | Faded so attention goes elsewhere | Reduced opacity; must stay legible |

`correct`/`wrong` must not rely on colour alone — these are graded answers and the board is used by
students with colour-vision deficiency.

### 5.5 `equation`

```json
{"latex": "\\frac{100{,}000}{150{,}000} = \\frac{2}{3}", "display": true}
```

Render with **KaTeX** (smaller and synchronous; MathJax is acceptable if already present). Required
coverage: true fractions, exponents and roots, the operator set `± × ÷ ≈ ≤ ≥ ≠ →`, and aligned
solution chains. `display: true` means own line, centred; `false` means inline.

Mathematics is **always LTR**, including inside an RTL board. Wrap the rendered node with
`dir="ltr"` and isolation so it does not reorder the Arabic sentence around it.

Load KaTeX's CSS. Guard the render call: a malformed expression must render as its raw string, not
throw inside the reducer.

### 5.6 `compare` — the minimal pair

```json
{
  "aspect_label": "Aspect",
  "columns": ["Signing the contract", "Satisfying the obligation"],
  "rows": [{"aspect": "What exists", "x": "An enforceable promise", "y": "A transferred good or service"}]
}
```

Exactly two columns. `x` belongs to `columns[0]`, `y` to `columns[1]`. On a wide viewport this is a
three-column table: aspect, x, y — the alignment is the teaching, so the two sides must line up row
by row. See §8 for portrait.

### 5.7 `table`

```json
{"variant": "journal", "header": ["Account", "Debit", "Credit"], "rows": [["Cash", "120,000", ""]]}
```

Header row always styled distinctly. Every row has one cell per header column; **a cell may be an
empty string** — a journal line fills either the debit or the credit, and the empty cell must hold
its width rather than collapsing.

`variant: "journal"` guarantees the header is exactly `["Account", "Debit", "Credit"]` and requires
**numeric alignment**: right-aligned, tabular figures (`font-variant-numeric: tabular-nums`), LTR
regardless of board direction. An accountant reads a misaligned column as a wrong answer.

### 5.8 `chain` — mechanism

```json
{"links": ["Identify the contract", "Identify obligations", "Recognise revenue"], "break_at": null}
```

Two to seven links with visible connectors between them. This is one of only two places real drawing
is warranted: an arrow between boxes. An SVG or CSS-drawn arrow is fine.

`break_at` is `null` or a 1-based link index whose **incoming** connector is drawn broken (a ✕ on the
arrow). A `board_update` with `slot` set to a 0-based link index and `state: "broken"` breaks a link
after the fact.

Vertical stacking with downward arrows is the right portrait layout for this; it does not need §8's
card treatment.

### 5.9 `blanks` — fill-in

```json
{"template": "Ratio = ___ , so the allocated amount is ___ SAR", "blanks": [{"id": "ratio", "fill": "…"}, {"id": "amount", "fill": "…"}]}
```

Split `template` on `___` and render one blank slot per placeholder, **in order**: the first `___`
is `blanks[0]`, the second `blanks[1]`. Render an unfilled blank as a visible underline of roughly
the width the answer will need — an empty gap reads as a typo.

Never render the `fill` value on add. It arrives later via `board_update` with that blank's `slot`.
Fill it in place with a brief highlight; do not re-render the line.

### 5.10 `options` — multiple choice

```json
{"stem": "Why is signing not enough?", "options": [{"id": "opt-a", "text": "…", "correct": false}]}
```

Render the stem, then the options labelled A, B, C, D in order. **Ignore `correct` on render** — it
is in the payload for the backend's benefit and revealing it early gives the answer away. Option
state arrives only via `board_update` with the option's `slot` and `state: "correct" | "wrong"`.

These options are *not* interactive. The student answers by voice; the board reflects the outcome.
Do not attach click handlers. (The `set_topic` checkpoint UI is a separate, existing surface.)

### 5.11 `callout`

```json
{"kind": "loses_marks", "text": "Writing 'when the contract is signed'. The marker wants transfer of control."}
```

Six kinds: `loses_marks`, `mistake`, `mnemonic`, `definition`, `example`, `exam`. Each needs its own
recognisable treatment — icon, border, background.

**`loses_marks` is the highest-value item on the board.** It is the product's sharpest
differentiator and it must be impossible to mistake for an ordinary bullet. Give it the strongest
non-error styling you have. It appears at most once per topic.

---

## 6. Event cadence

- **Small bursts.** A fired beat can arrive as two or three packets within a few hundred
  milliseconds (clear → group → add). Absorb that without layout thrash.
- **Long quiet stretches.** Most sentences produce nothing. A board holding a title and three items
  for thirty seconds is a normal steady state, not a stall.
- **Nothing after an interruption.** Pending operations are cancelled agent-side; already-rendered
  items stay. Simply stop expecting more.
- **Mutations arrive late by design.** A blank is filled, or an option marked, tens of seconds after
  the item first appeared. Items must remain addressable for the whole topic.

Representative timeline for one topic:

```text
t= 0.0s  board_clear {scope:"all"}
t= 0.0s  board_show
t= 0.0s  board_set_title   Objective of Revenue Recognition
t= 4.1s  board_add         definition  (chunk 0 visible)
t= 7.6s  board_reveal      index 1
t=11.2s  board_reveal      index 2
t=15.8s  board_group       columns "Signing vs satisfying"
t=15.8s  board_add         compare    (in that group)
t=24.3s  board_add         callout    loses_marks
t=31.0s  board_clear       {scope:"live"}
t=31.1s  board_add         options
t=48.9s  board_update      slot opt-cash  state wrong
t=50.2s  board_update      slot opt-control state correct
```

---

## 7. Mixed Arabic and English

The common case, not the exception. In an Arabic session the tutor keeps technical terms in English,
so one board routinely holds both scripts:

```text
Objective of Revenue Recognition
• Performance obligation (التزام الأداء)
• السيطرة تنتقل للعميل
  120,000 SAR × 2/3 = 80,000 SAR
```

Requirements:

- `dir="auto"` per item resolves each item independently — correct, and already in place. A list may
  legitimately have markers on different sides.
- An English item inside an otherwise-Arabic board must not break its neighbours' alignment.
- Long Latin technical terms wrap rather than overflow the narrow column.
- Numbers, currency and equations are LTR inside RTL text and need explicit isolation. `120,000 SAR`
  inside an Arabic sentence must not reorder.
- Bilingual `term` tokens and journal tables each need their own isolation boundary.

---

## 8. Portrait phone — the locked decision

Portrait is the launch surface. Two-column comparisons and wide tables do not fit it. The decision,
made and closed: **stacked cards with aligned labels. No horizontal scroll. No rotation.**

### `compare` in portrait

Each row becomes one card that keeps its aspect label, so the contrast survives vertically:

```text
┌────────────────────────────────┐
│ What exists                    │
│ Signing → An enforceable       │
│           promise              │
│ Satisfying → A transferred     │
│              good or service   │
└────────────────────────────────┘
┌────────────────────────────────┐
│ Who holds control              │
│ Signing → The seller           │
│ Satisfying → The customer      │
└────────────────────────────────┘
```

The two column names repeat on every card. That repetition is deliberate: it is what preserves the
pairing once the columns are gone. Keep the two sides visually distinguished (a consistent accent
per side) so the student can scan one side down the stack.

### `table` in portrait

One card per row; the header becomes the label of each field within the card. A journal table keeps
its numeric alignment inside the card.

### `columns` groups in portrait

Stack the members vertically under the group heading.

Above the breakpoint, render true columns and true tables. The backend is layout-agnostic and sends
the same payload either way — the choice is entirely yours, per viewport.

---

## 9. Revision, reconnect and divergence

`rev` increments on every accepted mutation and appears on every message. With `update` and `remove`
in the vocabulary, a dropped or reordered packet now **corrupts** state rather than merely omitting a
line, so the counter is not optional bookkeeping.

Rules:

1. Track the last applied `rev`. Apply a message only when its `rev` is greater.
2. On a gap (`rev` jumps by more than one), the board has diverged. Render what you have and mark
   yourself as needing a resync rather than guessing.
3. A `board_update`, `board_annotate`, `board_remove`, `board_reveal` or `board_pin` for an unknown
   id must be **ignored silently**. It must never throw inside the reducer.
4. `board_snapshot` replaces everything.

> **Status:** the backend exposes `BoardRuntime.publish_snapshot()` and it is covered by tests, but
> **no automatic trigger is wired yet** — nothing currently sends a snapshot on reconnect, because
> the agent has no inbound data-channel handler. Implement the client side against the message shape
> now; the trigger (a `board_resync` request from the client, or a `participant_connected` hook) is
> a tracked follow-up on the agent side. Until it lands, a mid-topic reconnect shows an empty board
> until the next topic boundary, which is the V1 behaviour and not a regression.

---

## 10. Verification checklist

Run against the agent on the `003-improve-agent-plans` branch with the `ch18_v2` fixture chapter.

Board behaviour:

- [ ] Topic start: `board_clear {scope:"all"}` → `board_show` → `board_set_title`, with no visible
      flicker and no header jump between the clear and the title.
- [ ] A `definition` appears as one chunk and grows with the speech, without the page jumping.
- [ ] A `compare` renders as true columns on desktop and as aligned cards at 390px.
- [ ] A journal table's debit and credit columns align; empty cells hold their width.
- [ ] An equation renders as a true fraction and stays LTR inside an Arabic board.
- [ ] The `loses_marks` callout is unmistakably distinct from a bullet.
- [ ] Answering the checkpoint wrong marks that option wrong and the correct one correct.
- [ ] A remediation item appears in the temporary tray and disappears when the tutor moves on.
- [ ] The pinned worked example survives the live region clearing beneath it.
- [ ] Interrupt mid-explanation: no new items; existing ones remain.

Language and accessibility:

- [ ] One Arabic and one English lesson: mixed-script rendering, per-item direction, step numbering
      locale correct in both.
- [ ] `correct` / `wrong` are distinguishable without colour.
- [ ] `prefers-reduced-motion` suppresses reveal and entry animation without losing content.
- [ ] The live column scrolls when full; the pinned band stays visible while it does.

Regression:

- [ ] The PDF stays navigable with carousel, zoom and toolbar intact.
- [ ] Checkpoint questions still appear — they ride on `set_topic`, not a board event.
- [ ] Disconnect and start a new session: the board is hidden and empty.
- [ ] `pnpm lint && pnpm type-check && pnpm build` all pass.

---

## 11. Still out of scope

Freehand drawing, student editing, dragging, resizing, coordinates, images, export, board history,
persistence across sessions, speech transcription, word-level synchronisation, render
acknowledgements, and student controls for mutating board content.

The only real drawing in scope is the `chain` connector (§5.8).

---

## Source of truth

- `src/tutor_agent_snd/board/state.py` — every payload published to you originates here.
- `src/tutor_agent_snd/board/models.py` — item kinds, annotation kinds, region names.
- `tests/test_board_state.py` — the exact shape of every message, asserted.
- `docs/board-feature/lesson-plan-structure.md` — what each beat kind means pedagogically.
