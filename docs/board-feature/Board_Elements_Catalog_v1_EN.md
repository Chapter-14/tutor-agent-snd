# Board Elements Catalog v1

6 Sep 2026 · Every element and formatting capability the teaching board needs in order to execute our explanation plans · For Moath / frontend

**Priority key**
- **P0** — without it, at least one full explanation plan cannot be delivered at all
- **P1** — the plan runs but loses part of its teaching effect
- **P2** — improvement, can wait

**What the board can do today (baseline):** title · bullet · text line · numbered step · one emphasis at a time. Nothing else. Every row below marked "missing" is not currently expressible.

---

## 1. Text and headings

| Element | Why we need it | Priority |
|---|---|---|
| Topic title | Stays at the top for the whole topic | P0 (exists) |
| Section heading | "Worked example" · "Now you try" · "Comparison" — stages inside one topic | **P0** |
| Text line | The base unit | P0 (exists) |
| Verbatim quote from the textbook | Must look different, so the student knows this is the book's own wording that will appear on the exam paper | **P0** |
| Small side note | Translation or clarification, smaller and dimmer | P1 |
| Three type sizes | Heading / body / note — without hierarchy everything reads as equally important | **P0** |

---

## 2. Lists

| Element | Why we need it | Priority |
|---|---|---|
| Bullets | Properties · causes · outcomes | P0 (exists) |
| Numbered list | Procedure steps in order | P0 (exists) |
| Nested list (2 levels) | A framework element with its function underneath | **P0** |
| Progressive list | Each item appears as it is spoken, not all at once | **P0** |
| Option list (A B C D) | Multiple-choice question | **P0** |
| Correct / incorrect marker per row | Marking the answer after the student responds | **P0** |

---

## 3. Inline formatting

| Element | Why we need it | Priority |
|---|---|---|
| **Bold** | The key word inside a definition | **P0** |
| Underline a specific word | Pointing at one word while speaking | **P0** |
| Highlight (background colour) | "These five words are the definition" | **P0** |
| Text colour | Separating the two sides of a comparison | P1 |
| Strikethrough | The causal link we just broke · a common wrong answer | P1 |
| Italic | Light emphasis | P2 |
| English word inside an Arabic sentence | Every technical term we teach is English — bidirectional text must not break the sentence | **P0** |
| Bilingual term token | `Revenue (الإيراد)` rendered consistently, shown once at first mention | **P0** |
| Superscript / subscript | m² · H₂O · x₁ | **P0** |
| Monospace / code | Programming courses | P1 |
| Formatted numbers | 120,000 SAR with separators | P1 |

---

## 4. Mathematics and symbols

Entirely absent today. Blocking for accounting and mathematics courses.

| Element | Example | Priority |
|---|---|---|
| True fraction | Numerator over denominator, not `a/b` | **P0** |
| Exponent and root | x² · √ | **P0** |
| Operators and relations | ± × ÷ ≈ ≤ ≥ ≠ → | **P0** |
| Display equation | Own line, centred, not inline in a sentence | **P0** |
| Aligned solution chain | Line under line, `=` signs aligned | **P0** |
| Highlight part of an equation | "Look at the numerator" | P1 |
| Annotated arrow between two steps | "÷ 2" written above the arrow | P1 |
| Sum · integral · limit | Σ ∫ lim — mathematics courses | P1 |
| Greek letters | α β θ Δ | P1 |
| Stretchable brackets | Around a fraction or matrix | P1 |
| Matrix / vector | | P2 |
| Unit or currency attached to a number | 24,000 SAR / year | **P0** |

---

## 5. Tables

| Element | Why we need it | Priority |
|---|---|---|
| Table with header row | The general case | **P0** |
| Two-column comparison | "This is an example · this is not" — our single most-used visual | **P0** |
| Three-column table | Aspect · X · Y — the comparison exam move | **P0** |
| Shaded cell | The cell that carries the difference | **P0** |
| Highlighted row | The correct row after the student answers | P1 |
| Journal-entry table | Account · Debit · Credit, with correct numeric alignment | **P0** |
| Table that grows row by row | Filled in as the tutor speaks | P1 |

---

## 6. Layout and regions

| Element | Why we need it | Priority |
|---|---|---|
| Two side-by-side columns | Comparison — the alignment itself is the teaching | **P0** |
| Box grouping several lines under one heading | "Worked example" as a single unit | **P0** |
| Pinned region at the top | The worked example stays visible while everything below it changes | **P0** |
| Temporary region that appears and is removed | An analogy or a prerequisite detour, then we return | **P0** |
| Horizontal divider | End of a stage | P1 |
| "Now you try" area | The student's space visually distinct from the explanation space | P1 |
| Vertical scroll when full | | **P0** |

---

## 7. Simple graphics

| Element | Why we need it | Priority |
|---|---|---|
| Arrow between two elements | Causal chain: this leads to this | **P0** |
| Boxes and arrows in sequence | Explaining a 5–7 link mechanism | **P0** |
| ✕ mark on an arrow or link | "What if we break this link?" | P1 |
| Circle / outline around an element | Pointing while speaking | P1 |
| Grouping brace `{` | Several items leading to one result | P2 |
| Simple tree | A framework and its elements | P2 |
| Timeline | Spreading a cost across five years | P2 |
| Image or crop from the slide | When the figure itself is the point | P2 |

---

## 8. Blanks and fill-in

| Element | Why we need it | Priority |
|---|---|---|
| Blank inside a sentence, filled later | "Because ______ , which leads to ______" | **P0** |
| Name with an empty slot underneath | Write the framework's element names first, fill each in later | **P0** |
| Hidden step in a worked example | Faded example: we hide the step that loses marks | **P0** |
| Reveal the answer after a pause | | **P0** |

---

## 9. Callout boxes

| Box | Content | Priority |
|---|---|---|
| What loses you marks | The sharpest line we have — it must not blend in with ordinary bullets | **P0** |
| Common mistake | | **P0** |
| Memory hook / mnemonic | | **P0** |
| Definition | | P1 |
| Example | | P1 |
| Will appear on the exam | | P1 |

---

## 10. Element states

| State | When | Priority |
|---|---|---|
| Emphasised now | The item the tutor is speaking about at this moment | P0 (exists, single target, untyped) |
| Dimmed | Focusing attention on one item by fading the rest | **P0** |
| Correct / incorrect | After the student answers | **P0** |
| Broken | The link we cancelled | P1 |
| Pinned | Not cleared with the rest of the board | **P0** |
| New | Appears with a light motion so the eye catches it | P1 |

---

## 11. Motion and lifecycle

| Capability | Why we need it | Priority |
|---|---|---|
| Reveal piece by piece with speech | A definition is written chunk by chunk, not dumped | **P0** |
| **Update an item already on screen** | Fill a blank · flip an option's state — without rewriting the line | **P0** |
| **Delete a single item** | Remove the temporary analogy without clearing the board | **P0** |
| Re-show an earlier item | We ask about it ten minutes later and it comes back | P1 |
| Clear all | End of topic | P0 (exists) |

---

## 12. Utility

| Element | Priority |
|---|---|
| Progress indicator (3 of 7) | P1 |
| RTL page containing English text and LTR mathematics, rendered correctly | **P0** |
| Portrait phone: what happens to two-column layouts and wide tables? | **Decision needed** |

---

## Summary

- **39 P0 elements** — no explanation plan runs without them
- **5 of them exist today** (title · bullet · text · step · single emphasis)
- Most of the gap is **not drawing**. It is text formatting, tables, regions, and the ability to update or delete an item. Actual graphics (arrows and boxes) are one section out of twelve
- The three highest-leverage additions, in order: **update an existing item · delete a single item · pin a region**. Without these the board can only append downward — it cannot fill a blank, mark an answer, or keep a worked example on screen

## Open question for the build

Portrait phone is the launch surface. Two-column comparisons and wide tables do not fit a narrow portrait viewport. Three options, each implying a different layout engine: horizontal scroll inside the element · collapse into stacked cards · rotate the board to landscape. This decision should be made before the region and table primitives are designed.

