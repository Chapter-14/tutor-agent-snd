# Content Pipeline Integration Specification

## Status And Scope

This specification is the handoff contract for producing chapter content consumed by the current
Sanad tutor runtime. It replaces the runtime assumptions demonstrated by the older files in this
directory. It does not require a compatibility adapter, a schema version, or a `character.md`
rendering step.

All handoff files that existed before this specification are incompatible examples, not
runtime-ready artifacts. In particular, do not upload or deploy these as the current contract:

- `BRAIN_HANDOFF.md`
- `character_FULL_VOICEONLY.md`
- `system_prompt_VOICEONLY.md`
- `teaching_plan_ch18_FULL_VOICEONLY.json`
- `topics_list.json`
- `render_plan_md.py`
- the existing skills under `contexts/handoff/skills/`

They remain useful historical references for pedagogy, source coverage, classification, and term
ownership, but their output shapes and runtime integration are obsolete.

## Why The Old Pipeline Is Incompatible

The old handoff models an entire chapter as units containing ordered segments. It then renders the
chapter to `character.md`, where many segments are ready-to-speak Arabic speech scripts with mode
tags.
That does not match the implemented runtime for these reasons:

- The runtime first loads a chapter-level lesson catalog, then loads one lesson JSON file at a
  time. The old artifacts have no lesson grouping.
- Runtime progress is `LessonPlan -> Topic`; it does not execute chapter-wide units and segments.
- Runtime content is one English free-form string per topic, not nested speech segments.
- The old `character.md` renderer has no consumer in the current lesson-loading path.
- The runtime supports authored scrolling and the semantic teaching board directly.
- Assessments are optional per topic and have a fixed JSON object contract.
- Removed topic fields and all extra fields are rejected rather than translated.

Do not build a legacy reader. Regenerate the content into the contract below.

## New Pipeline

```text
course metadata + chapter source material
                  |
                  v
       choose chapter lesson groups
                  |
                  +--> lessons_list.json
                  |
                  v
     classify and design lesson topics
                  |
                  v
 write one English content string per topic
                  |
                  +--> optional topic assessment
                  |
                  v
 validate one <lesson-slug>.json per lesson
                  |
                  v
 upload catalog and lesson files to Bunny Storage
```

Pipeline requirements:

1. Use the source chapter structure and learning sequence to define a small ordered set of lessons.
2. Write the chapter catalog in English as `lessons_list.json`.
3. Create one JSON file for each catalog slug.
4. Divide each lesson into ordered topics. A topic is the runtime teaching and progress boundary.
5. Put all facts and all explanation guidance for a topic into its single English `content` string.
6. Add an assessment object only when the topic needs an authored understanding check; otherwise
   set `question` to `null`.
7. Validate exact keys, counts, sequence values, references, slugs, and file names before upload.
8. Upload only the new catalog and per-lesson files. Do not upload the historical chapter plan or a
   rendered Markdown replacement.

## Paths

Recommended local authoring paths:

```text
contexts/input/01_Course_Knowledge_Schema.md
contexts/input/ch_<chapter-folder>/content.md
contexts/output/ch_<chapter-folder>/lessons_list.json
contexts/output/ch_<chapter-folder>/<lesson-slug>.json
```

Runtime Bunny Storage paths:

```text
courses/{course_id}/01_Course_Knowledge_Schema.md
courses/{course_id}/{chapter_id}/lessons_list.json
courses/{course_id}/{chapter_id}/{lesson-slug}.json
```

`chapter_id` comes from the LiveKit participant attribute and is commonly a folder such as `ch_1`.
It is not necessarily the textbook's printed chapter number. The file name must exactly match the
catalog slug.

The repository prompt artifact is:

```text
prompts/snd-agent-system-prompt-v2.md
```

That file is for review and manual deployment. This pipeline must not update Langfuse. An operator
must manually create and promote the corresponding `snd-agent-system-prompt` version.

## Runtime Integration Reference

The runtime parses each lesson file into `LessonPlan` containing ordered `Topic` objects. The
model-callable tools are exactly:

```text
get_lesson_plan
advance_to_next_topic
check_topic_understanding
update_teaching_board
```

`advance_to_next_topic` is only for a questionless topic after the student is ready.
`check_topic_understanding` is only for an actual answer to the active authored question.

Frontend progress and visual state use:

```text
set_lesson
set_topic
topic_done
scroll
board_show
board_hide
board_clear
board_set_title
board_add_bullet
board_add_text
board_add_step
board_emphasize
```

Content authors do not emit these UI packets. They author only the exact scroll action and optional
teaching-board guidance in `content`; runtime tools own publication and state.

## Chapter Lesson Catalog

`lessons_list.json` contains chapter metadata and an ordered, non-empty lesson list. All lesson
names and briefs are English. Every slug is a unique non-empty string and becomes a JSON file name.
`number_of_lessons` must equal the number of lesson objects.

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
      "brief": "Apply contract, obligation, price, allocation, and control rules to examples.",
      "slug": "applying_the_five_steps"
    }
  ]
}
```

Each lesson object has only:

```text
name, brief, slug
```

## Per-Lesson Plan

Create exactly one `<lesson-slug>.json` file for each catalog entry. The top-level keys are exactly:

```text
lesson_slug, title, lesson_sequence_number, total_topics, topics
```

Example `revenue_recognition_model.json`:

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
      "content": "Teach why revenue depicts the transfer of promised goods or services for the consideration the entity expects to receive. Contrast signing a contract with satisfying a promise; signing establishes the arrangement but does not by itself recognize revenue. Use the Airbus and Cathay Pacific example from the source to connect the contract, airplane delivery, transaction price, and transfer of control.\n\nTechnical terms introduced in this topic: revenue recognition; performance obligation; transaction price.\n\nTeaching guidance: begin with the purpose, then connect the five stages as one chain. Use the teaching board only as support: set a short title, add one step for each stage, and keep the complete explanation in speech. Do not read this wording verbatim.",
      "question": {
        "id": "model-objective-check",
        "type": "check_understanding",
        "question": "Why is signing a customer contract not enough by itself to recognize revenue?",
        "expected_answer": "Because revenue is recognized when the related performance obligation is satisfied and control of the promised good or service transfers to the customer.",
        "choices": [],
        "reexplain_guide": "Contrast agreeing to deliver an airplane with actually transferring control of it to the customer."
      }
    },
    {
      "id": "five-step-overview",
      "title": "The Connected Five-Step Process",
      "sequence": 2,
      "requires_completion_of": "model-objective",
      "action": null,
      "content": "Explain the five-step process as a connected decision chain: identify the customer contract, identify distinct performance obligations, determine the transaction price, allocate that price to the obligations, and recognize revenue as each obligation is satisfied. Emphasize that the first four stages establish what is being accounted for and how much belongs to each promise; the fifth determines when revenue is recorded.\n\nTeaching guidance: use one simple sale to carry the student through all five stages. Keep the recap concise and ask only whether the student is ready to continue, because this topic has no authored assessment.",
      "question": null
    }
  ]
}
```

The JSON value of `content` is still one string even when it contains paragraph breaks, headings,
or list-like text. Markdown-like authoring is allowed. Do not turn those internal lines into nested
JSON properties.

## Exact Topic Contract

Every topic has exactly these keys:

```text
id, title, sequence, requires_completion_of, action, content, question
```

Rules:

- `id`: non-empty string unique within the lesson.
- `title`: non-empty English display title.
- `sequence`: positive integer, contiguous from 1, and equal to list order.
- `requires_completion_of`: `null` or the ID of an earlier topic in the same lesson.
- `action`: `null` or exactly `{"type":"scroll","page":<positive integer>}`.
- `content`: one required, non-empty English opaque free-form string.
- `question`: `null` or the exact assessment object below.

`content` must combine the topic's factual source and all explanation guidance needed by the tutor.
It may identify technical terms in ordinary text and may tell the tutor how to use the teaching
board. It is not a ready-to-speak script and is not wording that must be spoken exactly. The runtime
does not parse headings, term lists, board directions, or any other nested convention from this
string; it passes the string through unchanged for the model to interpret.

## Optional Assessment

When present, `question` has exactly:

```text
id, type, question, expected_answer, choices, reexplain_guide
```

Example:

```json
{
  "id": "control-transfer-check",
  "type": "topic_checkpoint",
  "question": "When should the allocated revenue be recognized?",
  "expected_answer": "When the performance obligation is satisfied and control transfers to the customer.",
  "choices": [
    "When negotiations begin",
    "When an invoice is drafted",
    "When the performance obligation is satisfied and control transfers",
    "When the transaction price is estimated"
  ],
  "reexplain_guide": "Return to the final stage and contrast contract setup with fulfillment of the promised transfer."
}
```

Every question field is required when the object is present. All text values must be non-empty.
`choices` is a list of non-empty strings and may be empty for an open-response question. Keep
`question` as `null` when no assessment is pedagogically useful.

At runtime, topic `content` remains unchanged. When `question` is present, the runtime appends a
fixed private assessment packet containing the authored question, expected answer, choices, and
re-explanation guide. The tutor uses that packet to ask and evaluate the question. It is never
student-facing and its labels must never be spoken. A questionless topic receives only its content
and advances through `advance_to_next_topic` after the student is ready.

## Teaching Board Guidance

The board remains available through `update_teaching_board`. Board intent belongs inside the
free-form `content` string when useful; it is not a separate plan field.

Supported semantic actions are:

```text
show, hide, clear, set_title, add_bullet, add_text, add_step, emphasize
```

Author short titles, bullets, text, and steps. Essential facts must also be explainable by voice.
For emphasis, the runtime-generated item ID from an earlier board add operation must be reused; do
not author an ID in plan JSON.

## Forbidden Fields And Formats

Do not emit:

- `schema_version`
- old top-level fields such as `topic`, `topic_sequence_number`, `total_sections`, or `sections`
- old topic fields such as `markers`, `agent_guidance`, `visual_description`, or `strategy`
- `units`, `segments`, `speech`, `mode_tag`, `verbatim`, `source_text`, or renderer metadata
- nested content objects such as `facts`, `teaching_steps`, `technical_terms`, or `board`
- page or scroll fields outside the exact `action` object
- runtime state such as `started`, `completed`, `student_responded`, or `current_topic_index`
- Arabic lesson names, briefs, titles, content, questions, or answers in plan JSON
- `character.md` or any substitute rendered chapter prompt

The parser rejects extra plan, topic, action, and question keys. There is no schema-version switch
and no legacy compatibility path.

## Skill Migration

Existing skills must be revised before they generate runtime artifacts. Until then, their output is
intermediate research only.

| Existing stage or skill | Required migration |
| --- | --- |
| `create-topics-list` | Replace the chapter-wide topic catalog with `create-lessons-list`. Produce English lesson groups and `lessons_list.json` using the exact catalog contract. |
| `classify-sections` | Keep classification as offline analysis if useful, but map classified source units into lesson topics. Do not ship classification fields to runtime JSON. |
| `write-teaching-method` | Stop emitting Arabic speech segments, mode-tagged spines, and nested board fields. Produce one English free-form `content` string per topic containing facts and all teaching guidance. Preserve centralized term ownership as ordinary content guidance. |
| future `write-assessment` | Emit either the exact six-key `question` object or `null` for each topic. Do not create a separate runtime assessment file. |
| `render_plan_md.py` | Retire it from the runtime pipeline. JSON lesson files are consumed directly. |
| `add-plan-markers` | Retire it. There is no runtime field for visual page annotations. Keep only exact topic `action` scrolling and optional board guidance in content. |
| `add-topic-checkpoint` | Update it to modify only the exact `question` field and preserve every other exact key. |
| `create-chapter-plans` / `create-explain-plan` | Make them orchestrate one file per lesson slug and validate the new lesson/topic contract. They must not add `schema_version` or compatibility fields. |

The current handoff skills are intentionally not edited by this specification. Treat this table as
the migration backlog for their owners.

## Validation Checklist

- [ ] `lessons_list.json` exists in the chapter folder.
- [ ] `chapter`, `chapter_number`, `number_of_lessons`, and `lessons` are present.
- [ ] Every lesson `name` and `brief` is non-empty English.
- [ ] Every lesson slug is non-empty, unique, and has a matching `<slug>.json` file.
- [ ] `number_of_lessons` equals the lesson array length.
- [ ] Every lesson file has exactly the five allowed top-level keys.
- [ ] `lesson_slug` exactly matches the catalog slug and file name.
- [ ] `lesson_sequence_number` equals the lesson's one-based catalog position.
- [ ] `total_topics` is positive and equals the non-empty topic array length.
- [ ] Every topic has exactly the seven allowed topic keys.
- [ ] Topic IDs are non-empty and unique within the lesson.
- [ ] Topic sequences are contiguous from 1 and match list order.
- [ ] Every prerequisite is `null` or references an earlier topic ID.
- [ ] Every action is `null` or an exact scroll object with a positive integer page.
- [ ] Every content value is one non-empty English string containing facts and all teaching guidance.
- [ ] Content does not depend on runtime parsing of internal headings or nested conventions.
- [ ] Technical terms for Arabic output are identified in content when needed and have one owner.
- [ ] Every question is `null` or has exactly the six required keys.
- [ ] Question, answer, choices, and re-explanation text are non-empty English when present.
- [ ] No forbidden or runtime-only field is present.
- [ ] No historical `character.md`, unit/segment plan, or chapter-wide topic catalog is uploaded.
- [ ] Catalog and lesson JSON parse successfully before upload.
- [ ] The repository prompt artifact has been reviewed separately.
- [ ] Langfuse has not been modified by the content generation pipeline.
