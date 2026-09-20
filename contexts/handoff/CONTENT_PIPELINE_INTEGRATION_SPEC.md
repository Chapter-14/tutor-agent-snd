# Content Pipeline Integration Specification (v2)

## Status and scope

This specification is the handoff contract for producing chapter content consumed by the Sanad tutor
runtime. It tells the content pipeline **what to build and in what order**. It deliberately does not
restate the schema: the schema lives in one place, and duplicating it here is what let the previous
version of this document drift out of date.

> **The authoritative contract is [`docs/board-feature/lesson-plan-structure.md`](../../docs/board-feature/lesson-plan-structure.md).**
> The authoritative example is `tests/fixtures/ch18_v2/revenue_recognition_model.json`, which the
> test suite validates on every run.

**This is a hard break.** The runtime parses v2 only. Every existing chapter in Bunny Storage must
be regenerated before the agent deploys, or every session will fail at `get_lesson_plan`. There is
no dual-accept path, no schema-version switch, and no adapter — by decision, not by omission.

## What changed from v1, and why it matters to you

v1 asked for one opaque English prose string per topic, and forbade the plan from saying anything
about the teaching board. Two source documents established that this was the wrong split:

- `Board_Requirements_Inventory_v1_EN.md` §9 — which step to hide in a faded example, which property
  distinguishes a minimal pair, which distractor maps to which remediation: these are **authoring**
  decisions. A model reading two sentences of live speech cannot make them.
- `Board_Elements_Catalog_v1_EN.md` — 39 P0 board elements, of which five existed.

So the plan now carries the teaching structure explicitly, and the board's content with it.

| v1 | v2 |
| --- | --- |
| `content`: one prose string per topic | `segments[]`: ordered stages, each with its own `content` |
| Board intent as prose hints, ignored by code | `board.beats[]`: structured notes with anchors and typed payloads |
| `question`: six keys, choices as bare strings | `assessment`: options with ids, correctness, and a misconception each |
| No knowledge type | `knowledge_type`: one of seven, driving what the explanation must do |
| Exam strategy buried in prose | `loses_marks`: a required, separate, rendered line |
| One `reexplain_guide` for every wrong answer | `remediation[]`: a ladder, with rungs targeted at named misconceptions |
| Terminology guidance in prose | `terms[]`: exact exam-paper English with an Arabic gloss |

The practical consequence: **a v2 topic is several times the authoring work of a v1 topic.** Budget
for that. It is also where the product's quality now comes from — the runtime cannot teach better
than the plan is written.

## Pipeline

```text
course metadata + chapter source material
                  |
                  v
       choose chapter lesson groups ---------> lessons_list.json
                  |
                  v
     split each lesson into topics
                  |
                  v
   classify each topic's knowledge_type          <-- decides the segments below
                  |
                  v
     write ordered segments per topic
       (role, content, must_say)
                  |
                  v
        author board beats per segment            <-- kind, anchor, payload
                  |
                  v
   write loses_marks + terms per topic
                  |
                  v
   author assessment + remediation ladder         <-- distractor -> misconception -> rung
                  |
                  v
  validate one <lesson-slug>.json per lesson      <-- parse_plan, must not raise
                  |
                  v
        upload catalog and lesson files
```

### Stage notes

**Choosing `knowledge_type` first is not optional ordering.** It determines which segments the topic
needs. A `procedure` topic without `worked_example`, `faded_example` and `now_you_try` segments is
wrong regardless of how good its prose is. See §3.1 of the schema document for the mapping.

**Writing anchors is the highest-leverage step in the pipeline.** An anchor is the phrase the tutor
will be saying when a beat is due; it is what the Board Director matches against live speech. Anchors
that restate the concept name bind reliably. Anchors that are vague (`"the contract"`), instructional
(`"show the table"`), or indistinguishable from a sibling beat's anchor do not. A topic whose anchors
miss produces a board that lags or stays empty, and the failure is silent.

**Distractors must be diagnostic.** Each wrong option should be a misunderstanding a real student
holds, named by its `misconception`, and paired with a remediation rung that treats that specific
misunderstanding. A distractor nobody picks teaches nothing, and an unpaired `misconception` is a
parse error.

**Beats are a budget, not a canvas.** Regions cap at 12 live, 6 pinned, 4 temporary items. Overflow
is dropped silently. Two good beats per segment beats six mediocre ones.

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

## Runtime integration reference

The runtime parses each lesson file into `LessonPlan` → `Topic` → `Segment` → `Beat`. The
model-callable tools are exactly:

```text
get_lesson_plan(lesson)
advance_to_next_topic()
check_topic_understanding(student_understood, chosen_option_id)
```

There is no board tool. `update_teaching_board` was removed and must not appear in any generated
artifact or prompt.

Frontend events the runtime owns (content authors never emit these):

```text
set_lesson · set_topic · topic_done · scroll · session_ending
board_show · board_hide · board_clear · board_set_title
board_add · board_update · board_annotate · board_remove
board_reveal · board_pin · board_group · board_snapshot
```

## Prompts

The repository prompt artifacts are:

```text
prompts/snd-agent-system-prompt-v3.md
prompts/snd-board-director-prompt-v2.md
```

These are for review and manual deployment. **This pipeline must not update Langfuse.** An operator
creates and promotes the corresponding `snd-agent-system-prompt` and `snd-board-director-prompt`
versions, and must do so in the same release as the regenerated content.

## Skill migration backlog

The v1 handoff artifacts (`BRAIN_HANDOFF.md`, `character_FULL_VOICEONLY.md`,
`teaching_plan_ch18_FULL_VOICEONLY.json`, `topics_list.json`, `render_plan_md.py`, and the skills
under `contexts/handoff/skills/`) remain useful historical references for pedagogy, source coverage
and term ownership. Their output shapes are obsolete. Do not build a legacy reader.

| Stage or skill | Required migration for v2 |
| --- | --- |
| `create-topics-list` | Produce English lesson groups and `lessons_list.json`. Unchanged from v1 migration. |
| `classify-sections` | **Now ships to runtime.** Its output becomes each topic's `knowledge_type`, which must be one of the seven enumerated values. |
| `write-teaching-method` | Produce ordered `segments` with roles, per-segment `content`, and `must_say` for examinable wording — not one prose blob, not Arabic speech scripts. |
| **`author-board-beats`** (new) | For each segment, author `board.beats[]`: kind, anchor, typed payload. Choose region and `on_enter`. This stage did not exist in v1. |
| **`write-exam-layer`** (new) | Produce the topic's `loses_marks` line and, where appropriate, an `exam_rehearsal` segment. Mandatory per topic. |
| `add-topic-checkpoint` | Emit the seven-key `assessment`, with option ids, exactly one correct option, and a `misconception` on each diagnostic distractor. |
| **`write-remediation`** (new) | Author the rung ladder, one rung per named misconception plus at least one `default`. Rung boards must use `region: "temporary"`. |
| `render_plan_md.py` | Retired. JSON lesson files are consumed directly. |
| `add-plan-markers` | Retired. Only the exact `action` scroll object remains. |
| `create-chapter-plans` / `create-explain-plan` | Orchestrate one file per lesson slug and run `parse_plan` before writing. No `schema_version`, no compatibility fields. |

## Validation

Every generated lesson file must parse. This is a gate, not a suggestion — the runtime's only
response to an invalid plan is to refuse the lesson.

```bash
uv run python -c "
import json, sys
from tutor_agent_snd.utils.plan_helpers import parse_plan
parse_plan(json.load(open(sys.argv[1])))
print('valid')
" contexts/output/ch_1/<lesson-slug>.json
```

`PlanValidationError` messages name the exact path of the offending field
(`Topic 3 segment 1 board beat 4 payload row 1 must have one cell per header column`). Fix the
content; do not loosen the parser.

Then work the **Preflight checklist** in §12 of the schema document. It is organised as structure /
teaching / board / assessment, and the teaching and board sections are the ones that catch quality
problems rather than syntax problems.

## Release choreography

Because this is a hard break, these must land together:

1. Regenerate and validate every chapter for the launch courses.
2. Deploy the agent carrying the v2 parser.
3. Upload the regenerated catalog and lesson files.
4. Promote both prompts in Langfuse.
5. Ship the frontend build implementing
   [`docs/board-feature/frontend-board-spec-v2.md`](../../docs/board-feature/frontend-board-spec-v2.md).

Steps 2 and 3 in either order will break live sessions if separated. Treat them as one release.
