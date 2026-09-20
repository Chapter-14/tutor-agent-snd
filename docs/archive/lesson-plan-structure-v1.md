# Sanad Lesson Plan Structure

## Purpose

This document defines the exact content-plan files that the current Sanad runtime accepts. It is
for people or AI systems producing runtime-ready chapter lesson plans.

In this document, **plan** means a lesson content plan loaded by the Tutor. It does not mean a
`BoardPlan`, which is an internal, short-lived structured response produced by the Board Director.

The parser rejects unsupported keys. Do not add schema versions, helper metadata, nested teaching
objects, legacy fields, or speculative board fields.

## Required Files And Storage Paths

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

## Authoring Rules

- Write all catalog labels, lesson titles, topic titles, topic content, questions, answers, and
  re-explanation guidance in English.
- Topic `content` must contain all factual material and all Tutor guidance needed to teach that
  topic. The runtime does not retrieve an additional content field.
- Keep the plan curriculum-focused. The Tutor chooses natural spoken wording in the selected
  session language; `content` is not a ready-to-speak script.
- A topic is the runtime teaching and progression boundary. Divide lessons into a small, ordered
  sequence of independently explainable topics.
- Use an assessment only when it is pedagogically needed. Use `null` otherwise.
- Use an authored scroll only when a topic must move the student's slides to a specific page.
- Do not include runtime state or frontend messages in source JSON.

## 1. Chapter Catalog: `lessons_list.json`

The catalog has exactly four top-level keys:

```json
{
  "chapter": "Revenue Recognition",
  "chapter_number": 18,
  "number_of_lessons": 2,
  "lessons": [
    {
      "name": "The Revenue Recognition Model",
      "brief": "Understand the purpose and connected stages of the five-step model.",
      "slug": "revenue_recognition_model"
    },
    {
      "name": "Applying the Five Steps",
      "brief": "Apply the model to contract and control-transfer examples.",
      "slug": "applying_the_five_steps"
    }
  ]
}
```

| Field | Type | Required contract |
| --- | --- | --- |
| `chapter` | string | Non-empty English chapter title. |
| `chapter_number` | integer | Printed chapter number used for display/context. |
| `number_of_lessons` | integer | Must equal `lessons.length`. |
| `lessons` | array | Ordered, non-empty lesson entries. |

Each lesson entry has exactly three keys:

| Field | Type | Required contract |
| --- | --- | --- |
| `name` | string | Non-empty English lesson name. |
| `brief` | string | Non-empty English summary. |
| `slug` | string | Non-empty, unique identifier and matching lesson file name. |

Catalog order matters. A lesson file's `lesson_sequence_number` must be the one-based position of
its slug in this array.

## 2. Per-Lesson Plan: `<lesson-slug>.json`

Every lesson file has exactly these five top-level keys:

```text
lesson_slug, title, lesson_sequence_number, total_topics, topics
```

```json
{
  "lesson_slug": "revenue_recognition_model",
  "title": "The Revenue Recognition Model",
  "lesson_sequence_number": 1,
  "total_topics": 2,
  "topics": []
}
```

| Field | Type | Required contract |
| --- | --- | --- |
| `lesson_slug` | string | Non-empty; exactly matches the catalog slug and file name. |
| `title` | string | Non-empty English lesson title. |
| `lesson_sequence_number` | positive integer | One-based catalog position of this lesson. |
| `total_topics` | positive integer | Exactly equals `topics.length`. |
| `topics` | array | Ordered, non-empty array of exact Topic objects. |

## 3. Topic Object

Every topic has exactly these seven keys:

```text
id, title, sequence, requires_completion_of, action, content, question
```

| Field | Type | Required contract |
| --- | --- | --- |
| `id` | string | Non-empty and unique within its lesson. It is a private runtime identifier. |
| `title` | string | Non-empty English display title. It becomes the deterministic board title at topic activation. |
| `sequence` | positive integer | Starts at 1, is contiguous, and equals array order. |
| `requires_completion_of` | string or `null` | When a string, it must identify an earlier topic in the same lesson. |
| `action` | object or `null` | Optional exact scroll action described below. |
| `content` | string | Required, non-empty English source material and teaching guidance. |
| `question` | object or `null` | Optional exact assessment object described below. |

Example:

```json
{
  "id": "model-objective",
  "title": "Objective of Revenue Recognition",
  "sequence": 1,
  "requires_completion_of": null,
  "action": {
    "type": "scroll",
    "page": 6
  },
  "content": "Teach why revenue depicts the transfer of promised goods or services for the consideration the entity expects to receive. Contrast signing a contract with satisfying a performance obligation. Use the Airbus example to connect the contract, delivery, transaction price, and transfer of control.\n\nTechnical terms introduced in this topic: revenue recognition; performance obligation; transaction price.\n\nTeaching guidance: begin with the purpose, then connect the five stages as one chain. A short ordered board summary may help, but keep the complete explanation in speech.",
  "question": {
    "id": "model-objective-check",
    "type": "check_understanding",
    "question": "Why is signing a customer contract not enough by itself to recognize revenue?",
    "expected_answer": "Revenue is recognized when the related performance obligation is satisfied and control of the promised good or service transfers to the customer.",
    "choices": [],
    "reexplain_guide": "Contrast agreeing to deliver an airplane with actually transferring control of it to the customer."
  }
}
```

### Topic sequencing and prerequisites

`sequence` is not a display-only field. The parser requires it to match list order exactly:

```json
[
  {"id": "foundation", "sequence": 1, "requires_completion_of": null},
  {"id": "application", "sequence": 2, "requires_completion_of": "foundation"}
]
```

A prerequisite may point only to an earlier topic ID. A forward reference, unknown ID, duplicate
topic ID, missing sequence, or skipped sequence is invalid.

## 4. Optional Topic Action

`action` is either `null` or exactly this two-key object:

```json
{
  "type": "scroll",
  "page": 6
}
```

| Field | Type | Required contract |
| --- | --- | --- |
| `type` | string | Must be exactly `scroll`. |
| `page` | positive integer | One-based slide/page destination. |

No other action type or action key is accepted. For example, `highlight`, `delay`, `section`, and
pixel-coordinate fields are invalid.

At topic activation, a valid action becomes a frontend event:

```json
{"action": "scroll", "page": 6}
```

Plan authors do not create the event themselves.

## 5. Topic Content

`content` is one opaque, non-empty English string. It may use paragraphs and Markdown-like text
for author readability, but it remains a single JSON string. The runtime passes it through
unchanged; it does not parse headings, facts, teaching steps, terms, or board directions.

Put these elements in ordinary prose where useful:

- The factual source material the Tutor needs to teach.
- Required teaching sequence and conceptual connections.
- A relevant example, comparison, or misconception to address.
- Technical terms that should remain in English in Arabic sessions.
- Exam-sensitive wording that must be preserved.
- Concise instructions for the first explanation or a re-explanation.
- Optional visual intent for the teaching board.

Good content is complete enough to guide a natural 60-to-120-word teaching turn, but it does not
attempt to dictate every spoken sentence. The Tutor adapts the wording to the student and session
language while staying faithful to the facts and sequence.

### Board guidance inside content

Board guidance is allowed only as prose inside `content`; there is no `board`, `visual_actions`,
`markers`, or `visual_description` field in runtime JSON.

Use guidance to express pedagogy, not imperative UI commands. For example:

```text
Teaching guidance: teach the five stages as one connected sequence. A short board summary with one
step per stage may help, but retain all essential explanation in speech.
```

Do not author board IDs, `board_*` events, Board Director operations, positions, timings, or a
visual script. The Board Director responds to the Tutor's actual generated sentences, and
deterministic code creates IDs, validates content, schedules it, and publishes events.

## 6. Optional Assessment Object

`question` is either `null` or an object with exactly these six keys:

```text
id, type, question, expected_answer, choices, reexplain_guide
```

```json
{
  "id": "control-transfer-check",
  "type": "topic_checkpoint",
  "question": "When should allocated revenue be recognized?",
  "expected_answer": "When the performance obligation is satisfied and control transfers to the customer.",
  "choices": [
    "When negotiations begin",
    "When an invoice is drafted",
    "When the performance obligation is satisfied and control transfers",
    "When the transaction price is estimated"
  ],
  "reexplain_guide": "Return to the final stage and contrast contract setup with fulfillment."
}
```

| Field | Type | Required contract |
| --- | --- | --- |
| `id` | string | Non-empty private question identifier. |
| `type` | string | Non-empty authored category; the parser does not restrict it to an enum. |
| `question` | string | Non-empty English question. |
| `expected_answer` | string | Non-empty English grading reference. Never student-facing. |
| `choices` | array of strings | Every choice must be non-empty. `[]` is valid for open response. |
| `reexplain_guide` | string | Non-empty English direction for the first unsuccessful answer. |

When a question exists, the runtime appends a private assessment packet to the topic content before
returning it to the Tutor. The packet contains the question, expected answer, choices, and
re-explanation guide. It must never be read aloud or sent to the frontend as lesson content.

## 7. Runtime Progression Semantics

Plan structure determines the valid progression path:

| Topic shape | Tutor behavior |
| --- | --- |
| `question: null` | Teach the topic, ask whether the student is ready, then call `advance_to_next_topic()` only after readiness. |
| Assessment object | Teach the topic, ask the authored question, evaluate an actual answer, then call `check_topic_understanding(true or false)`. |

The Tutor cannot use `advance_to_next_topic()` to skip an assessed topic. It cannot use
`check_topic_understanding()` for a questionless topic.

On a first unsuccessful assessment result, the runtime returns `reexplain_guide` and the Tutor
remains on the topic. On a second unsuccessful result, the runtime completes the topic and returns
direction to explain the expected answer before continuing. A successful completion publishes
`topic_done` and immediately activates the next topic when one exists.

## 8. Complete Minimal Example

The following contains one catalog and one runtime-ready lesson file. Replace its content with
chapter-specific material while preserving the shape exactly.

`lessons_list.json`:

```json
{
  "chapter": "Network Transport",
  "chapter_number": 4,
  "number_of_lessons": 1,
  "lessons": [
    {
      "name": "Reliable Transport",
      "brief": "Understand how reliable delivery and ordering work.",
      "slug": "reliable_transport"
    }
  ]
}
```

`reliable_transport.json`:

```json
{
  "lesson_slug": "reliable_transport",
  "title": "Reliable Transport",
  "lesson_sequence_number": 1,
  "total_topics": 2,
  "topics": [
    {
      "id": "reliable-delivery",
      "title": "Reliable Delivery",
      "sequence": 1,
      "requires_completion_of": null,
      "action": {
        "type": "scroll",
        "page": 4
      },
      "content": "Explain that reliable delivery means the receiver eventually obtains the data that the sender successfully transmits. Contrast this with best-effort delivery, where loss can occur without recovery. Technical term: reliable delivery. Teaching guidance: isolate the definition before giving the contrast. A short definition on the board can support the explanation.",
      "question": {
        "id": "reliable-delivery-check",
        "type": "check_understanding",
        "question": "What makes reliable delivery different from best-effort delivery?",
        "expected_answer": "Reliable delivery provides recovery so successfully transmitted data reaches the receiver, while best-effort delivery can lose data without recovery.",
        "choices": [],
        "reexplain_guide": "Contrast guaranteed recovery from loss with accepting that loss may happen."
      }
    },
    {
      "id": "ordered-delivery",
      "title": "Ordered Delivery",
      "sequence": 2,
      "requires_completion_of": "reliable-delivery",
      "action": null,
      "content": "Explain that ordered delivery presents received data to the application in the intended sequence. Connect ordering to reliable delivery without treating them as the same property. Technical term: ordered delivery. Teaching guidance: state the distinction first, then use one compact example. This topic has no authored assessment, so ask only whether the student is ready to continue.",
      "question": null
    }
  ]
}
```

## 9. Forbidden Fields And Formats

Do not emit any of the following in a runtime plan:

- `schema_version` or any version-compatibility field.
- Extra keys at catalog, plan, topic, action, or question level.
- Legacy top-level fields such as `topic`, `topic_sequence_number`, `total_sections`, or `sections`.
- Legacy topic fields such as `agent_guidance`, `visual_description`, `strategy`, or `markers`.
- Chapter-wide `units` or `segments` and speech-script fields such as `speech`, `mode_tag`,
  `verbatim`, or `source_text`.
- Nested content structures such as `facts`, `teaching_steps`, `technical_terms`, or `board`.
- Page/scroll fields outside the exact `action` object.
- Board item IDs, `board_*` messages, frontend coordinates, timing fields, or visual command lists.
- Runtime state including `started`, `completed`, `student_responded`, or `current_topic_index`.
- Arabic source plan text, even when the Tutor will teach an Arabic session.
- Rendered chapter prompt files such as `character.md` as a substitute for lesson JSON.

## 10. Preflight Checklist

Before upload, verify all of the following:

- [ ] The catalog has `chapter`, `chapter_number`, `number_of_lessons`, and `lessons` only.
- [ ] The catalog's lesson count matches the number of entries.
- [ ] Each catalog slug is unique and has one matching `<slug>.json` file.
- [ ] Each lesson file has exactly five allowed top-level keys.
- [ ] Each `lesson_slug` matches both catalog slug and file name.
- [ ] Each lesson sequence number matches the slug's one-based catalog position.
- [ ] Each lesson has a positive `total_topics` equal to the topic array length.
- [ ] Every topic has exactly seven allowed keys.
- [ ] Topic IDs are unique; sequences start at 1, are contiguous, and match list order.
- [ ] Every prerequisite is `null` or references an earlier topic ID.
- [ ] Every action is `null` or the exact two-key scroll object with a positive integer page.
- [ ] Every `content` value is one non-empty English string with all needed facts and guidance.
- [ ] Every `question` is `null` or contains exactly six valid keys.
- [ ] All question text, answers, choices, and re-explanation guidance are non-empty English when
  present.
- [ ] Board guidance, if any, is prose inside `content` and does not depend on runtime parsing.
- [ ] No forbidden, legacy, visual-layout, or runtime-state field is present.
- [ ] The catalog and each lesson JSON file parse successfully before upload.

## Source Of Truth

These implementation files define the contract:

- `src/tutor_agent_snd/utils/plan_helpers.py`: exact-key validation and parsing.
- `src/tutor_agent_snd/domain_types.py`: in-memory `LessonPlan`, `Topic`, `TopicAction`, and
  `Question` objects.
- `src/tutor_agent_snd/agents/tutor_agent.py`: topic activation and progression behavior.
- `docs/data-models.md`: detailed reference for the current data model.
- `docs/explanation-plan-execution.md`: detailed state-machine and frontend behavior.
