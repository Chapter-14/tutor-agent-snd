# Board Requirements Inventory v1

6 Sep 2026 · Derived from `Teaching_Core_v2` (§2–§8), checked against `systemcontext.md` (the protocol as built)

---

## 0. Scope

**This document enumerates** everything that must appear on the teaching board, derived from our approved teaching moves rather than from imagination, and checked line by line against what the current vocabulary permits.

**Unit of enumeration:** a *board object* — one thing the student sees that carries a specific pedagogical job.

**This document does not decide** visual layout, colour, typography, JSON field names, or who issues the command (a live Director vs. an authored plan). Those are later decisions that this inventory is meant to inform.

---

## 1. Baseline — what the board has today

**Vocabulary (6 operations):** `clear` · `set_title` · `add_bullet` · `add_text` · `add_step` · `emphasize(target_id)`

**Binding limits:**

| Limit | Value | Direct pedagogical consequence |
|---|---|---|
| Non-title items | **6** | The governing constraint — see §6 |
| Item length | 180 chars | Enough for a line, not for a full verbatim Kieso definition |
| Title | One, 80 chars | No sub-heading for a stage inside a topic |
| Emphasis | One target, untyped | Cannot distinguish "key" from "wrong" from "warning" |
| Update | **None** | An item is written once; it can never be modified |
| Delete | `clear` only (all) | No partial cleanup |
| Persistence | None | No pinning, no recall, no state between sessions |

**Three capabilities are structurally absent, and they are not cosmetic:** update · partial delete · grouping.

---

## 2. Inventory by understanding move — the six knowledge types

"Slots" = number of non-title items in balanced mode. **These figures are my derivation from the §2 texts and have not been measured against a real authored chapter** — they need verification against Chapter 18.

| Type | What must appear on the board | Slots | Primitive required | Status |
|---|---|---|---|---|
| **Concept — successive** | The verbatim definition **split into 3–4 chunks** · the key-words line · (optionally) the names of the three divergent examples | 5–8 | Text + emphasis per chunk + **progressive reveal chunk by chunk** | Passes without the examples · progressive reveal absent |
| **Concept — coordinate (minimal pair)** | **Two adjacent columns**: the example / the near case · a row for the single distinguishing feature · the explanation line that must follow the contrast | 6–7 | **Two-column container** — the alignment *is* the pedagogy | **Impossible linearly.** Stacking the two sides destroys the effect |
| **Mechanism** | A 5–7 link chain **with visible connectors** · marking the broken link · the consequence line | 7–9 | Chain/arrows + a **"broken" state on an existing item** | **Over the cap**, and the break requires updating an item |
| **Procedure** | Worked example: numbered steps + result · then the **faded version with blanks** · then solo — **and the worked example must stay visible as the model** | 15–20 | Steps + **fillable blanks** + **pinning** + two parallel regions | **The worst break.** Our strongest-evidence move (g=0.48) is the least expressible |
| **Model / framework** | Element names first, **each with an empty slot underneath** · slots filled as we reach each one · the mnemonic line | 4–6 | **A parent item with a child filled in later** = update | **"Skeleton then fill" is an update operation, not an add** |
| **Fact / convention** | The verbatim text once · the mnemonic (possibly a vertical acrostic) | 2 | Text + vertical alignment | **The only fully covered type** |
| **Principle / rule** | The verbatim rule · two examples · the edge case | 4 | Text + distinct styling for the edge case | Passes — and leaves zero room for the exam layer |

**Reading the last column:** two types of six pass. Four do not — **and the most broken of them is the one with the strongest evidence and the cheapest UI tier in our own classification** (Procedure, Tier 0). The obstacle is not drawing. It is capacity and update.

---

## 3. Inventory by exam-rehearsal layer

This layer runs **on top of** the understanding move, on the same board, not after clearing it.

| Exam form | What must appear | Slots | Primitive required | Status |
|---|---|---|---|---|
| **Verbatim recall** — deconstruct the definition | The verbatim text · 3–4 chunks · **one key word opposite each chunk** · the rebuilt text | 6–9 | **Aligned pairs** (chunk ↔ key word) | Two columns |
| **Multiple choice** | Stem · 4 options · **marking correct/incorrect after the answer** · 2 lines of feedback | 6–8 | An "option" item **whose state changes after the answer** | Requires updating a live item |
| **Problem solving** | The declared steps the marker looks for | 4–6 | Steps + emphasis | Passes in isolation only |
| **Comparison** | A **three-column table**: Aspect · X · Y (3–4 rows) | 9–12 cells | **Table** | Does not exist |
| **Justification** | The template "Because ______ , which leads to ______" then **both blanks filled** | 1 + 2 updates | **Named blanks inside a text item** | Does not exist |
| **Mandatory in every section** | The line **"what loses you marks"** | 1 | **A distinct warning style** — not an ordinary bullet | Renders flat and dissolves into the rest |

**Commercial note:** "what loses you marks" is the purest piece of exam strategy we own and appears in no pedagogical source. Rendering it as one bullet among bullets wastes the most visible differentiator we have.

---

## 4. Inventory by remediation ladder

The ladder fires **while the board is already full of the section's content.** That is the problem.

| Rung | What must appear | Primitive required | Status |
|---|---|---|---|
| 1 · Re-anchor | **Focus attention on one item** and fade everything else | Emphasis + **dimming the rest** | Emphasis exists · dimming does not |
| 2 · Distant-domain analogy | 1–2 **temporary** items, removed once it works | **A temporary, removable region** | Pollutes the board and permanently consumes two slots |
| 3 · Prerequisite | Content **from outside this section**, then a return to where we were | **A layer / stack (push–pop)** | Does not exist · returning means rewriting everything |
| 4 · Worked example | 4–6 items **while the original content is still visible** | Capacity + a second region | The cap breaks with certainty |
| After 4 · Stop condition | Mark the concept "not mastered" | Section-level state, not board | Not a board requirement — logged |

**Conclusion: the remediation ladder has no room on the current board at all.** And it is not a luxury: it is the direct treatment for the documented complaint "the answer is always the first one, there's no challenge."

---

## 5. Inventory by cross-cutting rules and the diagnostic question

| Source | What must appear | Primitive required | Status |
|---|---|---|---|
| §6 Term tagging | The term **in English exactly as it will appear on the exam paper**, with its Arabic gloss at first mention only | A "term" item type (EN + AR) | Written as free text, with no guarantee the displayed form matches the paper |
| §5 R4 Spaced retrieval | **Re-showing an item displayed 10 minutes ago** | **Recall a prior item** | The item is gone — no persistence, no recall |
| §5 R2 Feedback | 1 line when correct · 2–3 when wrong | Text + styling | Passes if slots remain |
| §5 R1 Slide sync | Nothing on the board — `scroll` on a separate channel | — | Outside board scope |
| §8 Diagnostic question | Shared with §3 (multiple choice) | — | As above |
| §10 check 16 Mathematics | The equation **rendered visually** — the spoken form is for TTS, not for the eye | **Equation** | Does not exist · critical for accounting and mathematics courses |
| §2-1 Reading-integration pattern | The definition appears **chunk by chunk with the speech**, not all at once | **Progressive reveal inside one composite item** | Each chunk becomes a separate item and eats the cap |

---

## 6. Capacity arithmetic — the governing constraint

One typical section = understanding move + exam-rehearsal move + the "what loses you marks" line, and remediation may enter on top.

| Component | Slots (balanced) |
|---|---|
| Understanding move (average across the six types) | 5 |
| Exam-rehearsal move | 5 |
| "What loses you marks" | 1 |
| **Total before any stumble** | **11** |
| + one remediation rung | +2 to 6 |
| **Realistic range for one section** | **11–17** |
| **Current cap** | **6** |

**Verdict:** the current cap covers **one layer out of two, with no remediation, for the two simplest types out of six.** The gap is not marginal — it is two to three times.

**A warning about the obvious fix:** raising 6 to 16 does not solve it on its own. Without partial delete and grouping, the board becomes a long list in which the student loses track of which idea is live — which reproduces, in another form, the complaint "it gives general stuff like it's reading." **Capacity, grouping and delete are one package.**

---

## 7. Conclusion — what is actually missing

### A) Missing protocol operations (7)

| # | Operation | Serves |
|---|---|---|
| 1 | `update_item(id, text\|state)` | Filling a framework skeleton · the faded example · filling the justification template's blanks · marking an MCQ option after the answer · marking a broken link |
| 2 | `remove_item(id)` | Removing the analogy and the prerequisite detour once remediation succeeds · freeing slots without wiping everything |
| 3 | `group(kind, items)` | The minimal pair · the comparison table · separating "worked example" from "now you try" |
| 4 | `pin(id)` | Keeping the worked example and the skeleton visible while the rest of the board turns over |
| 5 | `recall(key)` | Spaced retrieval — re-showing an item displayed earlier |
| 6 | `annotate(id, kind)` | Semantic styles: `key` · `warning` (what loses you marks) · `correct` · `wrong` · `broken` — instead of one untyped emphasis |
| 7 | `reveal_next(id)` | Progressive reveal of definition chunks with the speech, instead of four separate items |

### B) Missing item kinds (7)

`term` (EN + AR, first mention) · `equation` (rendered) · `compare_row` (Aspect · X · Y) · `chain_link` (link + connector + state) · `blank_line` (text with named blanks) · `option` (choice with state) · `callout` (warning / key)

### C) Capacity

From 6 to **12–16** slots, **conditional on** (2), (3) and (4) above. The real limit is visual, not numeric: what can be read in one glance on a portrait phone.

### D) What genuinely needs drawing — the real Tier 1

**Two things only:** the chain arrows in a mechanism · student writing on the board.

> **The most important finding in this document:** everything in (A), (B) and (C) is **structured text, not drawing.** The gap between what we need and what we have is not a graphics-engine gap — it is a **protocol** gap. This inverts the cost estimate: a "Tier 0.5" — structured text that can be updated and grouped — unlocks six of seven moves and requires no drawing engine at all.

---

## 8. Reverse inventory — what does NOT go on the board

- The tutor's narration and examples told aloud (only example names, when needed)
- Greetings, procedural questions, restatements
- Any reference to location ("on slide 7") — anchoring is synchronisation, never speech
- Any concept outside the student's own material (§9 of Teaching Core) — the prerequisite appears **temporarily** at rung 3 and is then removed
- The full slide text before explaining — that turns the product into a reading app
- Mastery state ("not mastered") — a log entry, not a board object

---

## 9. What this inventory implies about who issues the commands

Most of the required operations are **authoring decisions, not moment-to-moment reactions**: which step to hide in the faded example (the rule is "hide the steps that lose marks") · which property is the distinguishing one in a minimal pair · which link to break · which distractor maps to which remediation rung. A model reading two sentences of tutor speech cannot decide any of them.

**Consequence:** the wider the board vocabulary grows, the weaker the case for a live Board Director and the stronger the case for the board being an **authored output that deterministic code fires** alongside each segment. This inventory is not neutral in the "who decides what appears" debate — it tilts toward pre-authoring.

---

## 10. Open

1. **Portrait phone.** The minimal pair and the mechanism are both tagged "wide" in §3 of Teaching Core. Do real two-column layouts exist on a narrow portrait screen, or do they become a toggle / horizontal scroll? This decision changes the design of `group`.
2. **Do the launch courses actually contain equations?** If RIYD 1060 is among them, `equation` is not an enhancement but a launch prerequisite.
3. **Who owns clearing between the stages of a section?** Worked → faded → solo: clear, pin, or two regions? Three completely different protocol designs.
4. **Is what appeared on the board logged?** Without it we cannot connect a drop-off to what was on screen at that moment — the cheapest learning signal we have.
