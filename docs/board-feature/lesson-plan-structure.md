# Sanad Lesson Plan Structure (v2)

## Purpose

This document defines the exact content-plan files the Sanad runtime accepts. It is for people and
AI systems producing runtime-ready chapter lesson plans.

**This replaces the v1 contract** (archived at `docs/archive/lesson-plan-structure-v1.md`). The
parser accepts v2 only. There is no compatibility path, no schema-version switch, and no legacy
reader: a file carrying a v1 `content` or `question` key is rejected with a migration message.

### What changed, and why

v1 modelled a topic as seven flat keys with one opaque prose `content` string, and forbade the plan
from expressing anything about the board. Two documents showed that this was the wrong split:

- `Board_Requirements_Inventory_v1_EN.md` §9 established that most board decisions — which step to
  hide in a faded example, which property distinguishes a minimal pair, which distractor maps to
  which remediation rung — are **authoring decisions**. A model reading two sentences of live speech
  cannot make them.
- `Board_Elements_Catalog_v1_EN.md` enumerated 39 P0 elements, of which five existed.

So v2 moves the board into the plan. The author writes **beats**: semantic, id-free notes attached
to the stage of teaching they belong to. At runtime the Board Director decides only *when the tutor
has reached* a beat; deterministic code assigns ids, validates, paces, and publishes it.

The division of labour:

| Layer | Owns |
| --- | --- |
| **The plan (you)** | What is taught, in what order, in what words, and what appears on the board |
| **The tutor** | Natural spoken delivery, the conversation, judging the student's answer |
| **The Board Director** | Which authored beat the tutor has just reached |
| **Runtime code** | Ids, regions, capacity, validation, pacing, publication, lifecycle |

You never author ids, timings, positions, colours, or `board_*` events. You author *what the note is
and when it is due*.

---

## Required files and storage paths

Each chapter requires:

```text
lessons_list.json
<lesson-slug-1>.json
<lesson-slug-2>.json
...
```

Recommended local authoring layout:

```text
contexts/output/ch_<chapter-folder>/
├── lessons_list.json
├── <lesson-slug-1>.json
└── <lesson-slug-2>.json
```

Runtime Bunny Storage layout:

```text
courses/{course_id}/01_Course_Knowledge_Schema.md
courses/{course_id}/{chapter_id}/lessons_list.json
courses/{course_id}/{chapter_id}/{lesson_slug}.json
```

`chapter_id` is a storage folder identifier supplied by the LiveKit participant. It is not
necessarily the printed textbook chapter number. Every catalog slug must have a file with exactly
the same name plus `.json`.

A complete worked example ships in the repository at
`tests/fixtures/ch18_v2/revenue_recognition_model.json`. It is validated by the test suite on every
run, so it cannot drift from the parser. Copy its shape.

---

## Authoring rules

- Write all catalog labels, titles, segment content, questions, answers, beat text, and remediation
  guidance in English. The tutor translates at delivery time; the plan does not.
- A **topic** is the runtime teaching and progression boundary.
- A **segment** is the delivery unit inside a topic: one connected stage of explanation.
- A **beat** is one authored board note, attached to a segment, released when the tutor reaches it.
- Every topic must carry a `loses_marks` line. It is required, not optional.
- Use an assessment only when it is pedagogically needed. Use `null` otherwise.
- Author beats for what genuinely helps the eye. A topic with two good beats beats a topic with
  eight mediocre ones; the regions have hard capacity limits and overflow is silently dropped.
- Do not put runtime state or frontend messages in source JSON.

---

## 1. Chapter catalog: `lessons_list.json`

Unchanged from v1. Exactly four top-level keys:

```json
{
  "chapter": "Revenue Recognition",
  "chapter_number": 18,
  "number_of_lessons": 1,
  "lessons": [
    {
      "name": "The Revenue Recognition Model",
      "brief": "Understand the purpose and connected stages of the five-step model.",
      "slug": "revenue_recognition_model"
    }
  ]
}
```

| Field | Type | Required contract |
| --- | --- | --- |
| `chapter` | string | Non-empty English chapter title. |
| `chapter_number` | integer | Printed chapter number used for display/context. |
| `number_of_lessons` | integer | Must equal `lessons.length`. |
| `lessons` | array | Ordered, non-empty lesson entries of exactly `name`, `brief`, `slug`. |

Catalog order matters. A lesson file's `lesson_sequence_number` must be the one-based position of
its slug in this array.

---

## 2. Per-lesson plan: `<lesson-slug>.json`

Unchanged from v1. Exactly five top-level keys:

```text
lesson_slug, title, lesson_sequence_number, total_topics, topics
```

| Field | Type | Required contract |
| --- | --- | --- |
| `lesson_slug` | string | Exactly matches the catalog slug and file name. |
| `title` | string | Non-empty English lesson title. |
| `lesson_sequence_number` | positive integer | One-based catalog position of this lesson. |
| `total_topics` | positive integer | Exactly equals `topics.length`. |
| `topics` | array | Ordered, non-empty array of exact Topic objects. |

---

## 3. Topic object

Exactly these eleven keys:

```text
id, title, sequence, requires_completion_of, action,
knowledge_type, terms, segments, assessment, loses_marks, remediation
```

| Field | Type | Required contract |
| --- | --- | --- |
| `id` | string | Non-empty, unique within its lesson. Private runtime identifier. |
| `title` | string | Non-empty English display title. Becomes the deterministic board title. |
| `sequence` | positive integer | Starts at 1, contiguous, equals array order. |
| `requires_completion_of` | string or `null` | When a string, identifies an **earlier** topic in the same lesson. |
| `action` | object or `null` | Optional exact scroll action (§7). |
| `knowledge_type` | string | One of the seven values in §3.1. |
| `terms` | array | Possibly empty. Each entry is exactly `{en, ar}`. |
| `segments` | array | Ordered, **non-empty** array of Segment objects (§4). |
| `assessment` | object or `null` | Optional exam-rehearsal move and progression gate (§6). |
| `loses_marks` | string | **Required, non-empty.** The exam-strategy line the tutor must say. |
| `remediation` | array | Possibly empty. Ordered rungs (§8). |

### 3.1 `knowledge_type`

This is not decoration. It tells the tutor what a good explanation of this topic must *do*, and it
tells the reviewer whether the segments you wrote are the right ones.

| Value | The move | Segments it implies |
| --- | --- | --- |
| `concept_successive` | Definition in parts, then key words, then an example | `understanding`, often `comparison` |
| `concept_coordinate` | A minimal pair: both sides, then the single distinguishing feature | `comparison` with a `compare` beat |
| `mechanism` | A chain of 5–7 links, then what breaks if one fails | `understanding` with a `chain` beat |
| `procedure` | Worked → faded → solo. All three. | `worked_example`, `faded_example`, `now_you_try` |
| `framework` | Element names first, then each one filled in | `understanding` with `blanks` or updated items |
| `fact` | Stated once, exactly, plus a memory hook | `understanding` with `callout` (mnemonic) |
| `principle` | The rule, two examples, the edge case | `understanding`, `warning` |

### 3.2 `terms`

```json
"terms": [
  { "en": "performance obligation", "ar": "التزام الأداء" }
]
```

`en` must be the exact form that appears on the exam paper. In an Arabic session the tutor says the
English term and gives the Arabic gloss once, at first mention. List a term once per topic, in the
topic where it is introduced.

### 3.3 `loses_marks`

One sentence naming the specific mistake and its specific cost. Not a general warning.

Good: `"Answering 'when the contract is signed'. The marker is looking for transfer of control."`

Bad: `"Be careful with this topic."`

This is the sharpest piece of exam strategy the product owns. It is rendered as a distinct callout,
never as an ordinary bullet.

---

## 4. Segment object

Exactly these five keys:

```text
id, role, content, must_say, board
```

| Field | Type | Required contract |
| --- | --- | --- |
| `id` | string | Non-empty, unique within its topic. |
| `role` | string | One of the nine stage labels below. |
| `content` | string | Non-empty English prose: the facts and delivery guidance for this stage. |
| `must_say` | array of strings | Possibly empty. Each entry is spoken verbatim. |
| `board` | object or `null` | Optional board blueprint for this stage (§5). |

### Roles

`opening` · `understanding` · `worked_example` · `faded_example` · `now_you_try` · `comparison` ·
`exam_rehearsal` · `warning` · `recap`

### `content`

This is what v1 called topic `content`, scoped down to one stage. It carries the factual source
material and the delivery guidance the tutor needs — and nothing about the board, because the board
is now expressed structurally in `board`.

Aim for enough material for forty to ninety spoken words. Write guidance, not a script:

```json
"content": "Contrast signing with satisfying. Airbus agreeing to sell aircraft to Cathay Pacific creates a contract but recognises nothing. Revenue arrives when control of the aircraft transfers. Make the single distinguishing feature explicit: an enforceable promise versus a transferred asset."
```

### `must_say`

Wording that will appear on the exam paper, and must survive translation into an Arabic session
untouched. Use it sparingly — one sentence per segment at most, usually none.

```json
"must_say": [
  "Revenue depicts the transfer of promised goods or services to customers in an amount that reflects the consideration the entity expects to be entitled to."
]
```

---

## 5. Board blueprint

A segment's `board` is `null` or exactly these four keys:

```text
region, on_enter, group, beats
```

| Field | Type | Required contract |
| --- | --- | --- |
| `region` | string | `live`, `pinned`, or `temporary`. |
| `on_enter` | string | `keep` or `clear_live`. Applied once, when this stage's first beat fires. |
| `group` | object or `null` | Exactly `{kind, heading}`; `kind` is `box` or `columns`. |
| `beats` | array | Ordered, **non-empty** array of Beat objects. |

### Regions

| Region | Capacity | Use |
| --- | --- | --- |
| `live` | 12 items | The current stage. The default. |
| `pinned` | 6 items | The worked example or framework skeleton that must stay visible while the live region turns over. |
| `temporary` | 4 items | Remediation only. Cleared automatically when the tutor returns to the main line. A rung's board **must** use this region. |

### `on_enter`

`clear_live` wipes the live region when this stage begins — use it when the new stage replaces the
old one (moving from the worked example to the faded one, or into the exam question). `keep` leaves
the board alone — use it when this stage builds on what is already shown.

Pinned items are never affected by `clear_live`. That is the point of pinning.

### `group`

Wraps this segment's beats in one visual container:

- `box` — several lines under one heading ("Worked example" as a single unit).
- `columns` — side-by-side arrangement.

The container is created automatically before the segment's first beat and needs no beat of its own.

---

## 6. Beat object

Exactly these four keys:

```text
id, kind, anchor, payload
```

| Field | Type | Required contract |
| --- | --- | --- |
| `id` | string | Non-empty, unique **within the topic** (across all segments, the assessment, and every rung). |
| `kind` | string | One of the thirteen kinds below. |
| `anchor` | string | Non-empty. The idea the tutor will be saying when this beat is due. |
| `payload` | object | Exactly the shape its `kind` requires. |

### 6.1 `anchor` — the most important field you write

The anchor is the Board Director's matching surface. It decides whether a beat lands on the right
sentence or not at all.

- Write the **idea**, in English, as a short phrase: `"revenue depicts the transfer of promised goods or services"`.
- It is matched semantically, so it works in an Arabic session. Do not translate it.
- Make it specific enough to distinguish this beat from its neighbours in the same segment. Two
  beats with anchors `"the contract"` and `"the contract criteria"` will bind unreliably.
- Do not write an instruction (`"show the definition now"`). Write what the tutor will be saying.

The tutor prompt requires naming the concept explicitly in the sentence that introduces it, which is
the other half of this contract. Anchors that quote the concept name bind best.

### 6.2 Beat kinds and payloads

| Kind | Payload | Notes |
| --- | --- | --- |
| `heading` | `{text}` | Stage heading inside a topic. |
| `text` | `{text}` | A definition, rule, or compact contrast. |
| `bullet` | `{text}` | One of several parallel facts. |
| `step` | `{text}` | One step of an ordered process. Do not number it yourself. |
| `definition` | `{chunks, key_words}` | Revealed chunk by chunk with the speech. |
| `term` | `{en, ar}` | Bilingual term token, shown at first mention. |
| `equation` | `{latex, display}` | Rendered mathematics. |
| `compare` | `{aspect_label, columns, rows}` | The minimal pair / comparison table. |
| `table` | `{variant, header, rows}` | `plain` or `journal`. |
| `chain` | `{links, break_at}` | A mechanism's 2–7 links with connectors. |
| `blanks` | `{template, blanks}` | A sentence with named blanks filled later. |
| `options` | `{stem, options}` | Choices whose state changes after the answer. |
| `callout` | `{kind, text}` | A distinct box, not an ordinary bullet. |

Every string in a payload must be at most **180 characters**; the board title is at most 80. Longer
text is rejected at runtime, silently.

#### `definition`

```json
{
  "chunks": [
    "Revenue depicts the transfer",
    "of promised goods or services to customers",
    "in the amount the entity expects to be entitled to"
  ],
  "key_words": ["transfer", "expects to be entitled to"]
}
```

Two to six chunks. The first appears when the beat fires; the rest are revealed as the tutor speaks
them. Split at the joints a student would pause at, not mid-clause. `key_words` are the words the
exam rewards and may be empty.

#### `compare`

```json
{
  "aspect_label": "Aspect",
  "columns": ["Signing the contract", "Satisfying the obligation"],
  "rows": [
    { "aspect": "What exists", "x": "An enforceable promise", "y": "A transferred good or service" },
    { "aspect": "Who holds control", "x": "The seller", "y": "The customer" }
  ]
}
```

Exactly two columns. `x` belongs to the first column, `y` to the second. Two to four rows works
best; the alignment *is* the teaching, so keep rows genuinely parallel.

#### `table`

```json
{
  "variant": "journal",
  "header": ["Account", "Debit", "Credit"],
  "rows": [
    ["Cash", "120,000", ""],
    ["Revenue - hardware", "", "80,000"]
  ]
}
```

Every row must have one cell per header column. A cell may be an empty string — a journal line fills
either the debit or the credit, not both. `variant: "journal"` requires the header to be exactly
`["Account", "Debit", "Credit"]` and gets numeric alignment. Use `plain` for everything else.

#### `chain`

```json
{ "links": ["Identify the contract", "Identify obligations", "Recognise revenue"], "break_at": null }
```

Two to seven links, rendered with connectors between them. `break_at` is `null`, or the 1-based
index of the link whose incoming connector is drawn as broken.

#### `blanks`

```json
{
  "template": "Ratio = ___ , so the allocated amount is ___ SAR",
  "blanks": [
    { "id": "ratio", "fill": "60,000 / 150,000" },
    { "id": "amount", "fill": "48,000" }
  ]
}
```

The template must contain exactly one `___` placeholder per blank, in order. `fill` is the answer
the runtime writes in when the tutor supplies it — it is not shown until then. This is how a faded
example and a justification template are expressed.

#### `options`

```json
{
  "stem": "Why is signing a contract not enough to recognise revenue?",
  "options": [
    { "id": "opt-signed", "text": "The contract is not in writing", "correct": false },
    { "id": "opt-control", "text": "Control has not transferred", "correct": true }
  ]
}
```

At least two options, exactly one correct, unique ids. Each option's state flips to correct or wrong
after the student answers.

#### `callout`

```json
{ "kind": "loses_marks", "text": "Writing 'when the contract is signed'. The marker wants transfer of control." }
```

`kind` is one of `loses_marks`, `mistake`, `mnemonic`, `definition`, `example`, `exam`. Author one
`loses_marks` callout per topic, in a `warning` segment, carrying the topic's `loses_marks` line.

#### `equation`

```json
{ "latex": "\\frac{100{,}000}{150{,}000} = \\frac{2}{3}", "display": true }
```

LaTeX, rendered visually. `display: true` puts it on its own centred line; `false` keeps it inline.
Attach units and currency in the surrounding text, not inside the LaTeX, unless the unit is part of
the mathematics. Remember JSON escaping: `\frac` is written `\\frac`.

---

## 7. Optional topic action

`action` is either `null` or exactly this two-key object:

```json
{ "type": "scroll", "page": 6 }
```

`type` must be exactly `scroll`; `page` is a one-based positive integer. No other action type or key
is accepted. At topic activation this becomes the frontend event `{"action": "scroll", "page": 6}`.

---

## 8. Optional assessment

`assessment` is either `null` or an object with exactly these seven keys:

```text
id, form, question, expected_answer, options, reexplain_guide, board
```

| Field | Type | Required contract |
| --- | --- | --- |
| `id` | string | Non-empty private identifier. |
| `form` | string | `verbatim_recall`, `mcq`, `short_answer`, `problem`, `comparison`, or `justification`. |
| `question` | string | Non-empty English question. |
| `expected_answer` | string | Non-empty grading reference. **Never student-facing.** |
| `options` | array | `[]` for open response, otherwise exactly-four-key option objects. |
| `reexplain_guide` | string | Non-empty fallback direction when no rung matches. |
| `board` | object or `null` | A board blueprint (§5) for the rehearsal itself. |

An option object has exactly `id`, `text`, `correct`, `misconception`:

```json
{
  "id": "opt-cash",
  "text": "Because the customer has not paid cash yet",
  "correct": false,
  "misconception": "cash_basis"
}
```

- Exactly one option must be `correct: true` when options are present. `mcq` requires at least two.
- `misconception` is `null`, or a string that **must match the `trigger` of a remediation rung in
  the same topic**. The parser rejects a dangling reference.

This mapping is the point of the whole assessment object: it turns a wrong answer into the specific
help that wrong answer earns, rather than the same re-explanation every time.

Distractors should be *diagnostic* — each one a real misunderstanding a student holds. A distractor
nobody would pick teaches nothing.

### Progression semantics

| Topic shape | Tutor behaviour |
| --- | --- |
| `assessment: null` | Teach every segment, ask whether the student is ready, then `advance_to_next_topic()`. |
| assessment object | Teach every segment, ask the authored question, evaluate, then `check_topic_understanding(...)`. |

On a first wrong answer the runtime opens the matching remediation rung and the tutor stays on the
topic. On a second wrong answer the runtime completes the topic and directs the tutor to explain the
expected answer before continuing. A correct answer publishes `topic_done` and activates the next
topic.

---

## 9. Remediation ladder

`remediation` is a possibly-empty array. Each rung has exactly these five keys:

```text
id, rung, trigger, content, board
```

| Field | Type | Required contract |
| --- | --- | --- |
| `id` | string | Non-empty, unique within the topic. |
| `rung` | integer | 1–4. See the ladder below. |
| `trigger` | string | `"default"`, or a misconception name referenced by an assessment option. |
| `content` | string | Non-empty direction for the tutor at this rung. |
| `board` | object or `null` | A blueprint whose `region` **must** be `temporary`. |

| Rung | Name | The move |
| --- | --- | --- |
| 1 | re-anchor | Focus on the one idea they missed. Nothing new. |
| 2 | analogy | One analogy from a distant domain, then dropped. |
| 3 | prerequisite | The missing prior idea, briefly, then return. |
| 4 | worked example | One full example, every step aloud. |

Author at least one `"default"` rung per assessed topic. Add a targeted rung for each distractor
worth diagnosing. Anything a rung puts on the board is removed automatically when the tutor returns
to the main line, so a rung may be generous without polluting the topic.

---

## 10. Complete minimal example

```json
{
  "lesson_slug": "reliable_transport",
  "title": "Reliable Transport",
  "lesson_sequence_number": 1,
  "total_topics": 1,
  "topics": [
    {
      "id": "reliable-delivery",
      "title": "Reliable Delivery",
      "sequence": 1,
      "requires_completion_of": null,
      "action": { "type": "scroll", "page": 4 },
      "knowledge_type": "concept_coordinate",
      "terms": [{ "en": "reliable delivery", "ar": "التسليم الموثوق" }],
      "segments": [
        {
          "id": "seg-definition",
          "role": "understanding",
          "content": "Define reliable delivery: the receiver eventually obtains the data the sender successfully transmitted. Isolate the definition before any contrast.",
          "must_say": [],
          "board": {
            "region": "live",
            "on_enter": "keep",
            "group": null,
            "beats": [
              {
                "id": "b-definition",
                "kind": "definition",
                "anchor": "reliable delivery means the receiver eventually obtains the data",
                "payload": {
                  "chunks": ["Reliable delivery means", "the receiver eventually obtains the data"],
                  "key_words": ["eventually obtains"]
                }
              }
            ]
          }
        },
        {
          "id": "seg-warning",
          "role": "warning",
          "content": "Close with the exam-strategy line before the question.",
          "must_say": [],
          "board": {
            "region": "live",
            "on_enter": "keep",
            "group": null,
            "beats": [
              {
                "id": "b-loses-marks",
                "kind": "callout",
                "anchor": "where students lose the mark here",
                "payload": {
                  "kind": "loses_marks",
                  "text": "Calling it 'faster'. The marker wants recovery from loss."
                }
              }
            ]
          }
        }
      ],
      "assessment": {
        "id": "reliable-delivery-check",
        "form": "mcq",
        "question": "What makes reliable delivery different from best-effort delivery?",
        "expected_answer": "Reliable delivery recovers from loss; best-effort delivery can lose data without recovery.",
        "options": [
          { "id": "opt-recovery", "text": "It recovers from loss", "correct": true, "misconception": null },
          { "id": "opt-speed", "text": "It is faster", "correct": false, "misconception": "speed_confusion" }
        ],
        "reexplain_guide": "Contrast guaranteed recovery with accepting that loss may happen.",
        "board": null
      },
      "loses_marks": "Saying 'it is faster'. The marker wants recovery from loss.",
      "remediation": [
        {
          "id": "rung-anchor",
          "rung": 1,
          "trigger": "default",
          "content": "Re-anchor on the definition already on the board.",
          "board": null
        },
        {
          "id": "rung-speed",
          "rung": 2,
          "trigger": "speed_confusion",
          "content": "Use one analogy: registered post is not faster post, it is post that is guaranteed to arrive.",
          "board": {
            "region": "temporary",
            "on_enter": "keep",
            "group": null,
            "beats": [
              {
                "id": "b-rung-post",
                "kind": "text",
                "anchor": "registered post is not faster post",
                "payload": { "text": "Registered post: guaranteed, not faster" }
              }
            ]
          }
        }
      ]
    }
  ]
}
```

---

## 11. Forbidden fields and formats

The parser rejects every extra key at catalog, plan, topic, segment, board, beat, action,
assessment, option, and rung level. In particular, do not emit:

- `schema_version` or any version-compatibility field.
- v1 topic fields: `content`, `question`, `agent_guidance`, `visual_description`, `strategy`,
  `markers`.
- Legacy top-level fields: `topic`, `topic_sequence_number`, `total_sections`, `sections`.
- Chapter-wide `units` or `segments`, or speech-script fields such as `speech`, `mode_tag`,
  `verbatim`, `source_text`.
- Board item ids, `board_*` messages, regions on individual beats, frontend coordinates, colours,
  timings, animation, or z-order.
- Runtime state: `started`, `completed`, `student_responded`, `current_topic_index`.
- Arabic source plan text, even when the tutor will teach an Arabic session. The only Arabic in a
  plan is the `ar` field of a `terms` entry or a `term` beat.
- Rendered chapter prompt files such as `character.md` as a substitute for lesson JSON.

---

## 12. Preflight checklist

Structure:

- [ ] The catalog has `chapter`, `chapter_number`, `number_of_lessons`, `lessons` only.
- [ ] Each catalog slug is unique and has one matching `<slug>.json` file.
- [ ] Each lesson file has exactly five top-level keys; `lesson_slug` matches catalog and file name.
- [ ] `lesson_sequence_number` equals the slug's one-based catalog position.
- [ ] `total_topics` equals the topic array length.
- [ ] Every topic has exactly eleven keys; ids unique; sequences contiguous from 1 and matching order.
- [ ] Every prerequisite is `null` or references an earlier topic id.
- [ ] Every action is `null` or the exact two-key scroll object.

Teaching:

- [ ] Every topic's `knowledge_type` matches the segments actually written (a `procedure` has
      worked, faded and solo stages).
- [ ] Every topic has a non-empty, specific `loses_marks` line.
- [ ] Every segment has exactly five keys, a valid role, and non-empty `content`.
- [ ] `must_say` is used only for genuinely examinable wording.
- [ ] Every technical term appears in `terms` with its exact exam-paper English form.

Board:

- [ ] Every board blueprint has exactly four keys and a valid region.
- [ ] Every remediation rung's board uses `region: "temporary"`.
- [ ] Beat ids are unique within the topic.
- [ ] Every anchor names the idea the tutor will be saying, and is distinguishable from its
      neighbours.
- [ ] Every payload matches its kind exactly; no string exceeds 180 characters.
- [ ] No segment's beats exceed its region's capacity (live 12, pinned 6, temporary 4).
- [ ] `on_enter: "clear_live"` is used where a stage replaces the previous one.

Assessment:

- [ ] Every assessment is `null` or has exactly seven keys.
- [ ] Exactly one option is correct; `mcq` has at least two options.
- [ ] Every `misconception` matches a remediation rung's `trigger`.
- [ ] Each distractor is a real misunderstanding, not filler.
- [ ] At least one `"default"` remediation rung exists for each assessed topic.

Final:

- [ ] No forbidden, legacy, visual-layout, or runtime-state field is present.
- [ ] Every JSON file parses.
- [ ] The plan passes `parse_plan` without raising `PlanValidationError`.

Validate locally before upload:

```bash
uv run python -c "
import json, sys
from tutor_agent_snd.utils.plan_helpers import parse_plan
parse_plan(json.load(open(sys.argv[1])))
print('valid')
" path/to/<lesson-slug>.json
```

---

## Source of truth

These implementation files define the contract; where this document and the code disagree, the code
wins and this document is the bug.

- `src/tutor_agent_snd/utils/plan_helpers.py` — exact-key validation, per-kind payload validation.
- `src/tutor_agent_snd/domain_types.py` — in-memory plan objects and the enumerated vocabularies.
- `src/tutor_agent_snd/board/cursor.py` — how beats become fireable board operations.
- `src/tutor_agent_snd/agents/tutor_agent.py` — topic activation, progression, remediation routing.
- `tests/fixtures/ch18_v2/` — the validated worked example.
- `docs/board-feature/frontend-board-spec-v2.md` — how each beat kind is rendered.
