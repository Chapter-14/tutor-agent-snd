# Data Models

> **Superseded (v1).** The topic shape described below — seven flat keys with an opaque `content`
> string and a `question` object — was retired by the teaching-beat schema. The runtime rejects it.
> The current contract is [Lesson Plan Structure](board-feature/lesson-plan-structure.md); the
> current wire protocol is [Frontend Board Spec v2](board-feature/frontend-board-spec-v2.md). This
> file is kept for history.

This document defines the chapter catalog, lesson plan JSON, and in-memory tutoring state used by
the current runtime.

Sources of truth:

- `src/tutor_agent_snd/domain_types.py`
- `src/tutor_agent_snd/utils/plan_helpers.py`
- `src/tutor_agent_snd/utils/parse_dynamic_prompt.py`

There is no `schema_version` and no legacy compatibility path.

## Storage Layout

The runtime reads these Bunny Storage objects:

```text
courses/{course_id}/01_Course_Knowledge_Schema.md
courses/{course_id}/{chapter_id}/lessons_list.json
courses/{course_id}/{chapter_id}/{lesson_slug}.json
```

The chapter catalog supplies the allowed ordered lesson slugs. Each slug identifies one lesson plan
file in the same chapter folder.

## Chapter Catalog

`lessons_list.json` has chapter metadata and an ordered non-empty lesson list:

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

| Field | Type | Contract |
| --- | --- | --- |
| `chapter` | string | Non-empty English chapter title. |
| `chapter_number` | integer | Textbook chapter number used for display and context. |
| `number_of_lessons` | integer | Must equal the length of `lessons`. |
| `lessons` | array | Ordered, non-empty list of lesson entries. |

Each lesson entry contains `name`, `brief`, and `slug`. `name` and `brief` are non-empty English
strings. `slug` is a non-empty string, is unique within the catalog, and must match its lesson JSON
file name.

The runtime turns the catalog into the dynamic prompt and passes the ordered slug list to the
agent. It does not load chapter content from `topics_list.json` or `character.md`.

## Lesson Plan JSON

Every `<lesson_slug>.json` object has exactly these keys:

```text
lesson_slug, title, lesson_sequence_number, total_topics, topics
```

Example:

```json
{
  "lesson_slug": "revenue_recognition_model",
  "title": "The Revenue Recognition Model",
  "lesson_sequence_number": 1,
  "total_topics": 2,
  "topics": [
    {
      "id": "model-objective",
      "title": "Objective of Revenue Recognition",
      "sequence": 1,
      "requires_completion_of": null,
      "action": {
        "type": "scroll",
        "page": 6
      },
      "content": "Explain that revenue depicts the transfer of promised goods or services for the consideration the entity expects to receive. Contrast contract signing with satisfying a performance obligation. Teaching guidance: use the Airbus example, then connect the five stages as one chain. Technical terms introduced in this topic: revenue recognition; performance obligation.",
      "question": {
        "id": "model-objective-check",
        "type": "check_understanding",
        "question": "Why is signing a contract not enough by itself to recognize revenue?",
        "expected_answer": "Because revenue is recognized when the related performance obligation is satisfied and control transfers to the customer.",
        "choices": [],
        "reexplain_guide": "Contrast agreeing to deliver a product with actually transferring control of it."
      }
    },
    {
      "id": "five-step-overview",
      "title": "The Connected Five-Step Process",
      "sequence": 2,
      "requires_completion_of": "model-objective",
      "action": null,
      "content": "Teach the five steps as one connected decision chain. Use the teaching board to show five short steps only if it improves the explanation. Keep all essential facts in speech. This topic has no authored assessment, so ask only whether the student is ready to continue after the explanation is complete.",
      "question": null
    }
  ]
}
```

| Field | Type | Contract |
| --- | --- | --- |
| `lesson_slug` | string | Non-empty; must equal the requested catalog slug. |
| `title` | string | Non-empty English lesson title. |
| `lesson_sequence_number` | positive integer | Must equal the slug's one-based position in `lessons_list.json`. |
| `total_topics` | positive integer | Must equal the number of entries in `topics`. |
| `topics` | array | Non-empty ordered list of exact `Topic` objects. |

Extra top-level plan keys are rejected.

## Topic JSON

Every topic has exactly these keys:

```text
id, title, sequence, requires_completion_of, action, content, question
```

| Field | Type | Contract |
| --- | --- | --- |
| `id` | string | Non-empty and unique within the lesson. |
| `title` | string | Non-empty English display title. |
| `sequence` | positive integer | Contiguous from 1 and equal to list order. |
| `requires_completion_of` | string or `null` | When set, must reference an earlier topic ID in the same lesson. |
| `action` | `TopicAction` or `null` | Optional authored page scroll. |
| `content` | string | Required, non-empty English opaque free-form content. |
| `question` | `Question` or `null` | Optional authored assessment. |

Extra topic keys are rejected. The removed `markers`, `agent_guidance`, `visual_description`, and
`strategy` fields are invalid.

### Content Contract

`content` is one string. It combines the factual material and all explanation guidance the model
needs for that topic. Markdown-like text, paragraph breaks, list-like text, teaching-board guidance,
examples, sequencing, and ordinary prose that identifies technical terms are allowed inside the
string.

The string is opaque to the runtime:

- The runtime validates only that it is a non-empty string.
- The runtime does not parse headings, facts, steps, term lists, or board instructions from it.
- The runtime passes it through unchanged.
- The model interprets it as source material and teaching guidance.
- It is not a ready-to-speak script or wording that must be spoken exactly; the model produces
  natural output in the selected language while preserving its facts and intent.

Plans are authored in English. For Arabic output, content can identify the technical terms that the
tutor must introduce once as an Arabic meaning plus the English term. Later uses remain English.
The system prompt controls that delivery behavior; it is not a nested data field.

## TopicAction JSON

`action` is either `null` or an object with exactly two keys:

```json
{
  "type": "scroll",
  "page": 6
}
```

| Field | Type | Contract |
| --- | --- | --- |
| `type` | string | Must be exactly `scroll`. |
| `page` | positive integer | One-based destination page. |

Extra action keys, other action types, zero, negative, missing, or non-integer page values are
rejected.

## Question JSON

`question` is either `null` or an object with exactly these keys:

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

| Field | Type | Contract |
| --- | --- | --- |
| `id` | string | Non-empty question identifier. |
| `type` | string | Non-empty authored category; the parser does not enforce an enum. |
| `question` | string | Non-empty English question text. |
| `expected_answer` | string | Non-empty English grading reference. |
| `choices` | array of strings | Every entry must be non-empty; an empty list is valid for open response. |
| `reexplain_guide` | string | Non-empty English guidance for the first unsuccessful attempt. |

When a question is present, the runtime returns the unchanged `content` followed by a fixed private
assessment packet containing the question, expected answer, choices, and re-explanation guide. That
packet is model-only control context. Its labels and hidden answer must never be exposed to the
student.

When `question` is `null`, the runtime returns only unchanged `content`. The topic completes through
`advance_to_next_topic` after the student is ready, not through assessment.

## In-Memory Models

JSON is parsed into dataclasses in `src/tutor_agent_snd/domain_types.py`.

### `LessonPlan`

```python
@dataclass
class LessonPlan:
    lesson_slug: str
    title: str
    lesson_sequence_number: int
    total_topics: int
    topics: list[Topic]
    current_topic_index: int = -1
```

`current_topic_index` is runtime-only and zero-based. `current_topic` returns the active topic or
`None`. `is_complete` is true when every topic is complete.

### `Topic`

```python
@dataclass
class Topic:
    id: str
    title: str
    sequence: int
    requires_completion_of: str | None
    action: TopicAction | None
    content: str
    question: Question | None
    completed: bool = False
    started: bool = False
```

`completed` and `started` are runtime-only and must not appear in JSON.

### `Question`

```python
@dataclass
class Question:
    id: str
    type: str
    question: str
    expected_answer: str
    choices: list[str]
    reexplain_guide: str
    completed: bool = False
    student_responded: bool = False
```

`completed` and `student_responded` are runtime-only.

### `TopicAction`

```python
@dataclass
class TopicAction:
    type: str
    page: int | None = None
```

The parser guarantees that a JSON action has type `scroll` and a positive page even though the
dataclass permits `None` for internal construction.

## State Invariants

- Only one `LessonPlan` is active in an `Assistant` instance.
- Loading a lesson sets `current_topic_index` to the first topic through topic activation.
- Topic list order and `sequence` are identical.
- A topic prerequisite can reference only an earlier topic.
- A topic with a question completes through `check_topic_understanding`.
- A topic without a question completes through `advance_to_next_topic`.
- Completing a topic marks it complete, marks its question complete when present, publishes
  `topic_done`, and activates the next topic in the lesson.
- Completing the final topic returns lesson or chapter completion information; the next lesson is
  loaded separately.

## Invalid Legacy Shapes

The runtime does not accept chapter-wide topic plan files, section arrays, schema versions, rendered
chapter prompt files, or compatibility aliases. Content must be regenerated as `lessons_list.json`
plus one exact lesson JSON file per slug.
