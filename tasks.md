# Sanad Natural Tutoring and Interactive Visual Cues

> **Superseded plan:** This proposal was not implemented and its marker/schema design is no longer
> valid. The implemented lesson/topic contract is documented in `docs/data-models.md` and the
> content-generator migration contract is `contexts/handoff/CONTENT_PIPELINE_INTEGRATION_SPEC.md`.

## Purpose of This Document

This is the complete implementation handoff for improving Sanad's tutoring behavior and visual
interaction. It includes the product reasoning, pedagogical requirements, technical design,
confirmed user decisions, repository findings, implementation tasks, migration constraints,
testing requirements, and deployment gates discussed during planning.

An implementing agent should treat this document as the source of truth for this change. Do not
broaden Sanad into a general assistant, study planner, coach, or unrelated question-answering
agent.

## Product Context

Sanad is a voice AI tutor whose only educational purpose is to explain concepts from the active
chapter. It uses structured explanation plans fetched from Bunny Storage and synchronizes the
lesson with course pages shown by the frontend.

Sanad should:

- Explain one course concept at a time.
- Follow the authored topic and section order.
- Preserve the quality and factual meaning of the fetched course content.
- Answer follow-up questions about the active concept naturally.
- Re-explain a concept with different wording or examples when needed.
- Let students explore the active concept without losing the structured curriculum path.
- Use visual focus deliberately to direct attention to relevant course content.
- Remain concise and suitable for a spoken, interruption-prone interaction.

Sanad should not:

- Become a general-purpose assistant.
- Conduct lengthy learner intake or study-goal interviews.
- Build study plans or schedules.
- Provide unrelated coaching or productivity advice.
- Abandon the structured curriculum.
- Invent course-specific content or visual targets.

## Core Design Principle

The target behavior is:

> Hard structure between sections, soft conversation within a section.

Topic order, section order, source content, and explicit advancement remain controlled. Follow-up
questions, interruptions, examples, partial answers, re-explanations, and visual refocusing remain
flexible while the current section stays active.

The current agent feels rigid because the workflow governs every conversational turn. The new
design makes workflow tools responsible for lesson transitions while normal tutor-student dialogue
stays conversational.

## Current Strengths to Preserve

- Sections provide a clear, manageable learning path.
- Explanations are concise enough for voice.
- Plans provide tone, visual description, strategy, questions, expected answers, and re-explanation
  guidance.
- Topic checkpoints give topics a meaningful conclusion.
- Existing UI commands synchronize topic, section, page, markers, and progress.
- Internal plan fields and tool results are not intentionally spoken to students.
- The marker renderer already supports page and `span_id` targeting.
- Existing marker styles include `highlight`, `circle`, `underline`, and `point`.

## Current Behavioral Problems

### Mandatory Checkpoint Rhythm

The current prompt requires exactly one checkpoint question after every teaching turn. This forces
the same repeated pattern:

1. Explain.
2. Give an analogy or exam tip.
3. Ask a yes/no question.
4. Wait.
5. Evaluate the response.

Even a short clarification is forced back into this pattern. The result sounds like an interactive
slide narrator rather than a responsive tutor.

### Every Student Response Becomes an Evaluation

The current lesson states assume that a reply after a checkpoint must be evaluated through
`check_user_understanding`. Students may instead:

- Ask why the concept works.
- Ask for another example.
- Give a partial answer and ask a follow-up question.
- Understand one part but not another.
- Correct something they think they heard.
- Say they understand while requesting additional depth.

These are normal teaching interactions, not automatic pass/fail events.

### Clarification Is Treated as Failure

The current prompt explicitly treats asking for help with the concept as
`check_user_understanding(false)`. This is incorrect pedagogically. A student can understand the
main statement and still want its reasoning, implications, or an example.

### Binary Evaluation

Correct, partially correct, vague, hesitant, confused, and incorrect answers are collapsed into a
single boolean. This prevents precise feedback such as:

> The first part is correct. The missing point is that assets are also managed digitally.

### Retry-Driven Advancement

After two unsuccessful responses, the current tool marks the section complete and starts the next
section. This can change the page and markers before Sanad has finished correcting the previous
concept. Repeated confusion must not be treated as successful completion.

### Premature Visual Transitions

The current implementation starts the next section, updates the frontend, removes and adds
markers, and scrolls before the model speaks its acknowledgement or correction. The visual state
can therefore refer to the next concept while Sanad is still discussing the previous one.

### Repetitive Plan Strategy

Plans commonly prescribe the same four-part structure for every section:

- Point out.
- Explain.
- Analogy.
- Exam tip.

Not every concept requires every teaching move. A definition, process, comparison, diagram, and
worked example should not all be explained with the same cadence.

## Current Visual-System Findings

The current marker system is more capable than it appears, but it is used statically.

### Existing Capabilities

- A section can define multiple markers.
- Markers can have staggered delays.
- Marker types include `highlight`, `circle`, `underline`, and `point`.
- Consecutive sections can stay on the same page while changing focus.
- Markers can be removed and replaced.
- The backend sends reliable `ui-control` messages.
- Existing frontend payloads already support `scroll`, `add_markers`, and `remove_markers`.

### Existing Limitations

- All markers are submitted when a section starts.
- The model cannot change visual focus during a section.
- A follow-up question cannot trigger a different marker.
- Re-explanation retains the original visual state.
- Marker delays are frontend timers, not synchronized to actual speech.
- Existing delays are mostly zero to 1.5 seconds while spoken explanations can last 20 to 40
  seconds.
- Most visual sequences finish before the matching narration.
- Delayed markers are not interruption-aware.
- A second unsuccessful answer can activate the next section's visuals before correction is spoken.
- Questions and choices are included in `set_section` from section start.
- `point` still targets a text span; arbitrary diagram coordinates are not supported.
- No frontend implementation is present in this repository, so click handling and marker
  idempotency cannot be verified here.

### Visual Teaching Goal

Markers should become semantic visual cues that Sanad can select during the explanation. Examples
include:

- Focus a definition when introducing it.
- Switch between two terms during a comparison.
- Reveal parts of a sequence as they are explained.
- Clear markers before an unaided retrieval question.
- Focus the exact evidence that corrects a misconception.
- Change from a formal definition cue to an example cue during re-explanation.
- Show a summary cue at the end of a section.

Visual interaction remains voice-driven. Students respond verbally to what is circled, underlined,
highlighted, or pointed to. This iteration does not add clicking, dragging, or drawing.

## Confirmed User Decisions

- Sanad remains a concept-explanation-only tutor.
- Preserve the structured topic and section path.
- Make dialogue inside a section more natural and responsive.
- Add exactly one constrained visual-control action.
- Replace the rigid lesson-tool API with exactly three tools:
  - `fetch_topic_content(topic: str)`
  - `advance_to_next_section()`
  - `set_visual_focus(cue_name: str)`
- Introduce Explanation Plan schema `2.0`.
- Do not support legacy plans at runtime after the cutover.
- Migrate only `contexts/output/ch_1/what_is_an_information_system.json` as the local pilot.
- Keep the pilot's current page numbers and `span_id` targets.
- Do not correct the known source/page mismatches in this pilot.
- Continue using the existing frontend marker payloads.
- Prepare the revised system prompt in the repository only.
- Do not create, update, label, or promote a Langfuse prompt during this implementation.

## Repository State and Constraints

### Relevant Runtime Files

- `src/tutor_agent_snd/agents/tutor_agent.py`
- `src/tutor_agent_snd/domain_types.py`
- `src/tutor_agent_snd/utils/plan_helpers.py`
- `src/tutor_agent_snd/utils/parse_dynamic_prompt.py`
- `src/tutor_agent_snd/main.py`
- `src/tutor_agent_snd/utils/bunny.py`

### Relevant Test Files

- `tests/test_tutor_agent.py`
- `tests/test_observations.py`

### Relevant Documentation

- `README.md`
- `docs/architecture.md`
- `docs/data-models.md`
- `docs/explanation-plan-execution.md`
- `docs/agent-analysis.md`

### Relevant Plan-Authoring Skills

- `contexts/.agents/skills/create-explain-plan/SKILL.md`
- `contexts/.agents/skills/add-plan-markers/SKILL.md`
- `contexts/.agents/skills/add-topic-checkpoint/SKILL.md`
- `contexts/.agents/skills/create-chapter-plans/SKILL.md`

### LiveKit Version

The lock file currently resolves `livekit-agents` to version `1.5.6`.

LiveKit's `@function_tool` decorator supports explicit tool names and descriptions. Parameter
descriptions should be supplied through Google-style `Args` docstrings. LiveKit also supports
dynamic tool updates, but this implementation does not require dynamic tool schemas. The visual
tool validates cue names against the active section at runtime.

### Existing Unrelated Worktree Change

`src/tutor_agent_snd/main.py` currently contains unrelated unstaged changes to development LLM and
TTS fallback ordering. Do not revert, overwrite, or otherwise modify those changes while updating
the constructor wiring.

### Source Artifact Mismatch

`contexts/output/ch_1/Ch01 MIS.pdf` represents the MIS chapter used by the plans. The current
`contexts/input/ch_1` artifacts belong to a different 11-slide Arabic Sanad introduction, and no
active MIS span mapping is present. The pilot therefore preserves its existing pages and span IDs.
Page correction and mapping regeneration are explicitly deferred.

### Deployment Constraint

Only one sample plan will be migrated while the runtime will reject all old schemas. The new
runtime must not be deployed against the full 13-topic chapter until one of these conditions is
true:

- Every Bunny-hosted plan has been migrated to schema `2.0`.
- A staging or pilot route exposes only the migrated topic.

There is intentionally no legacy-schema compatibility layer.

# Implementation Plan

## 1. Add Explanation Plan Schema 2.0

### Update `domain_types.py`

Retain `UIMarker`:

```python
@dataclass
class UIMarker:
    id: str
    type: str
    page: int
    span_id: int
    delay: int
```

Add:

```python
@dataclass
class VisualCue:
    name: str
    purpose: str
    description: str
    markers: list[UIMarker]


@dataclass
class TeachingStep:
    id: str
    instruction: str
    visual_cue: str | None = None


@dataclass
class QuestionVisualCues:
    on_ask: str | None = None
    on_confusion: str | None = None
    on_correction: str | None = None
    on_correct: str | None = None
```

Change `Question` to:

```python
@dataclass
class Question:
    id: str
    type: str
    question: str
    expected_answer: str
    choices: list[str]
    reexplain_guide: str
    visual_cues: QuestionVisualCues
```

Change `Section` to:

```python
@dataclass
class Section:
    id: str
    title: str
    sequence: int
    requires_completion_of: str | None
    action: SectionAction | None
    agent_guidance: str
    visual_description: str
    visual_cues: list[VisualCue]
    teaching_steps: list[TeachingStep]
    question: Question | None
```

Remove:

- `UpdateUIMarkers`
- `Question.completed`
- `Question.student_responded`
- `Section.completed`
- `Section.started`
- `Section.markers`
- `Section.strategy`
- `ExplanationPlan.is_complete`

Keep `ExplanationPlan.current_section_index`, initialized to `-1`.

## 2. Define the JSON Contract

Every plan must contain:

```json
{
  "schema_version": "2.0",
  "topic": "topic_slug",
  "title": "Topic Title",
  "topic_sequence_number": 1,
  "total_sections": 1,
  "sections": []
}
```

Every section must contain:

```json
{
  "id": "SEC_1",
  "title": "Section title",
  "sequence": 1,
  "requires_completion_of": null,
  "action": {
    "type": "scroll",
    "page": 1
  },
  "agent_guidance": "Delivery guidance.",
  "visual_description": "What is displayed.",
  "visual_cues": [],
  "teaching_steps": [],
  "question": null
}
```

A visual cue must contain:

```json
{
  "name": "definition",
  "purpose": "definition",
  "description": "Focus the formal definition.",
  "markers": [
    {
      "id": "m_7_4",
      "type": "highlight",
      "page": 7,
      "span_id": 4,
      "delay": 0
    }
  ]
}
```

A teaching step must contain:

```json
{
  "id": "STEP_1",
  "instruction": "Explain how the parts work together toward one goal.",
  "visual_cue": "definition"
}
```

Question visual references must contain:

```json
{
  "on_ask": "summary",
  "on_confusion": "example",
  "on_correction": "definition",
  "on_correct": "summary"
}
```

Use `null` when no cue is appropriate. The reserved cue name `clear` removes all active markers and
does not need to be declared by a section.

Allowed cue purposes:

```text
overview
definition
sequence
relationship
example
comparison
evidence
emphasis
hint
correction
summary
```

Allowed marker types:

```text
highlight
circle
underline
point
```

## 3. Rewrite Plan Parsing and Validation

Update `src/tutor_agent_snd/utils/plan_helpers.py`.

Validation must happen before agent state or frontend state changes.

Required validation:

- `schema_version` equals `"2.0"`.
- Legacy section-level `markers` fields are rejected.
- Legacy `strategy` fields are rejected.
- The plan contains at least one section.
- `total_sections` equals the section count.
- Section IDs are unique.
- Section sequences are contiguous and match list order.
- The first section has no prerequisite.
- Every later prerequisite references the immediately preceding section.
- Scroll pages are positive integers.
- Cue names are unique within the section.
- Cue names match `^[a-z][a-z0-9_]*$`.
- Cue purposes and marker types belong to the allowed sets.
- Cue marker pages match the section scroll page.
- Marker IDs use `m_{page}_{span_id}`.
- Marker delays are integers from zero through 5,000 milliseconds.
- A cue contains one through four markers.
- Repeated marker IDs have identical page, span, and type definitions.
- Teaching-step IDs are contiguous: `STEP_1`, `STEP_2`, and so on.
- Every teaching-step cue exists in the current section.
- Every question cue exists in the current section or equals `clear`.
- Questionless sections use `null`, not an empty object.
- Invalid plans raise descriptive `ValueError` exceptions.
- A parsing failure does not replace an already active valid plan.

Do not add a new schema-validation dependency. Keep runtime validation in `plan_helpers.py`.

## 4. Rewrite Section Prompt Formatting

Update `format_section_prompt()` to produce an internal reference packet similar to:

```text
---SECTION_EXPLANATION_PLAN_CONTENT---
[Section_Title] ...

[Tone] ...

[Visual_Description] ...

[Teaching_Guidance]
1. ...
2. ...

[Available_Visual_Cues]
- definition: definition — Focus the formal definition.
- example: example — Focus the supporting example.

[Optional_Ask] ...
[Expected] ...
[Reexplain_Guide] ...

[Question_Visual_Cues]
- on_ask: clear
- on_confusion: example
- on_correction: definition
- on_correct: summary
```

Formatting rules:

- Never include marker IDs or span IDs in model-facing plan content.
- Omit question fields when no question exists.
- Present teaching steps as adaptable guidance, not exact speech.
- State that visual cues are optional teaching aids.
- Do not make teaching steps responsible for lesson navigation.

## 5. Refactor Agent State

Update `Assistant` in `src/tutor_agent_snd/agents/tutor_agent.py`.

Use:

```python
self.topic_slugs: list[str]
self.current_topic_index: int | None = None
self.current_plan: ExplanationPlan | None = None
self.current_visual_cue: str | None = None
self.active_marker_ids: set[str] = set()
self.chapter_complete = False
```

Remove:

- `number_of_topics`
- `checkpoint_answers_counter`
- Question attempt state
- Section `started` and `completed` state

Lesson state must be represented only by the active topic, active section, active cue, ordered slug
list, and terminal chapter-complete state.

## 6. Consolidate UI Publication

Add:

```python
async def _publish_ui_control(self, payload: dict[str, object]) -> None:
```

It must JSON-encode payloads and publish with:

```python
reliable=True
topic="ui-control"
```

Retain the existing frontend action names and payload fields.

Add:

```python
async def _clear_visual_focus(self) -> None:
```

Behavior:

- Publish `remove_markers` only when active marker IDs exist.
- Clear `active_marker_ids` after successful publication.
- Set `current_visual_cue` to `None`.
- Do not change topic or section state.

Add:

```python
async def _apply_visual_cue(self, cue: VisualCue) -> None:
```

Payload order:

1. Remove the currently active markers.
2. Scroll to the active section page when a scroll action exists.
3. Add the selected cue's markers.
4. Update `active_marker_ids`.
5. Update `current_visual_cue`.

If marker removal succeeds but marker addition fails, leave visual state empty, log the error, and
return an internal error rather than pretending the cue is visible.

## 7. Replace Section Activation

Replace `_get_section_by_id()` and `_start_section()` with:

```python
async def _activate_section(self, section_index: int) -> str:
```

Behavior:

1. Require a loaded plan.
2. Validate index bounds.
3. Clear the previous visual focus.
4. Set `current_section_index` from list order.
5. Publish `set_section`.
6. Publish the section scroll action.
7. Do not add markers automatically.
8. Return the formatted section reference.

Questionless sections publish empty question text and choices. The first marker appears only after
Sanad calls `set_visual_focus`.

## 8. Replace the Tool API

Expose exactly three model-callable tools.

### `fetch_topic_content`

```python
@function_tool(
    name="fetch_topic_content",
    description="Loads an approved chapter topic and activates its first section.",
)
async def _fetch_topic_content(self, topic: str) -> str:
```

Behavior:

1. Reject slugs not found in `topic_slugs`.
2. Do not call Bunny for an invalid slug.
3. Fetch `courses/{course_id}/{chapter_id}/{topic}.json`.
4. Parse JSON into a local object.
5. Require schema `2.0`.
6. Validate the full plan before replacing state.
7. Confirm that the plan topic matches the requested slug.
8. Clear markers from the previous topic.
9. Set `current_topic_index`.
10. Set `current_plan`.
11. Reset `chapter_complete`.
12. Publish `set_topic`.
13. Activate section zero.
14. Return first-section guidance.

Fetch, JSON, and validation failures must leave the previous valid plan active.

### `advance_to_next_section`

```python
@function_tool(
    name="advance_to_next_section",
    description="Closes the active section and moves forward by exactly one section.",
)
async def _advance_to_next_section(self) -> str:
```

Behavior:

1. Reject calls with no active section.
2. Reject calls after chapter completion.
3. Publish `section_done` exactly once.
4. Clear active visual markers.
5. Activate only `current_section_index + 1` when another section exists.
6. At topic completion, resolve the next topic from `topic_slugs`.
7. Load the next topic deterministically.
8. At final chapter completion, set `chapter_complete` and return `[CHAPTER_COMPLETE]`.

This tool must not accept section IDs, evaluate correctness, maintain retry counts, skip content, or
be called automatically for every student response.

### `set_visual_focus`

```python
@function_tool(
    name="set_visual_focus",
    description="Applies one pre-authored visual cue from the active section.",
)
async def _set_visual_focus(self, cue_name: str) -> str:
```

The docstring must describe `cue_name` using a Google-style `Args` section.

Behavior:

1. Require an active section.
2. Accept `clear` as a reserved cue.
3. Resolve all other names only from the active section.
4. Reject unknown cues without UI publication.
5. Never accept a page, marker ID, span ID, or marker definition.
6. Apply the resolved cue using `_apply_visual_cue()`.
7. Do not change lesson progress.
8. Return only internal confirmation and cue purpose.
9. Treat requesting the already active cue as a no-op.

## 9. Update Runtime Topic Context

Update `parse_d_prompt()` in `src/tutor_agent_snd/utils/parse_dynamic_prompt.py` to return:

```python
tuple[str, list[str]]
```

The second value is the ordered topic-slug list.

Validate:

- Every topic has a non-empty slug.
- Slugs are unique.
- The declared topic count matches the actual list.

Update the dynamic prompt to reference `fetch_topic_content(topic)`.

Update `src/tutor_agent_snd/main.py` to pass `topic_slugs` to `Assistant`. Preserve the existing
unrelated fallback-provider edits in that file.

## 10. Prepare the Revised System Prompt

Add:

```text
prompts/snd-agent-system-prompt-v2.md
```

Do not call Langfuse APIs during implementation.

The prompt must preserve:

- Sanad's identity and pronunciation.
- Warm, patient, concise voice behavior.
- Voice-only response restrictions.
- Arabic terminology requirements.
- Safety and privacy rules.
- Fidelity to course content.
- Ordered section progression.

The prompt must change:

- Document the exact three-tool API.
- Remove mandatory checkpoints after every teaching turn.
- Ask at most one useful question at a natural section boundary.
- Allow one-sentence direct clarifications.
- Treat teaching steps as guidance rather than scripts.
- Treat follow-up questions as normal conversation.
- Never advance solely because a student replied.
- Never classify clarification as a failed answer.
- Distinguish partial, uncertain, confused, and incorrect answers in spoken feedback.
- Stay in the active section while answering related questions.
- Advance only after the current exchange is complete.
- Interpret acknowledgements such as “okay” contextually.
- Stay when the student understands but asks a deeper question.
- Never auto-advance after repeated confusion.
- Identify the correct and missing parts of partial answers.
- Use `set_visual_focus` before verbally referring to a visual focus.
- Use only cue names supplied by the active section.
- Use `clear` before unaided retrieval when the visible cue would reveal the answer.
- Avoid decorative cue changes.
- Never mention cue names, pages, markers, spans, UI actions, or tool calls.
- Keep the normal 85-word voice ceiling.
- Do not force a question after a brief clarification.

The file is a review and testing artifact. Runtime release is blocked until an operator manually
creates the corresponding Langfuse prompt version.

## 11. Migrate the Pilot Plan

Migrate only:

```text
contexts/output/ch_1/what_is_an_information_system.json
```

Preserve:

- The current four sections.
- Current page numbers 31 through 34.
- Current span IDs.
- Existing factual content.
- Current topic sequence.

Add `"schema_version": "2.0"`.

Remove all section-level `markers` and `strategy` fields.

Add `visual_cues`, `teaching_steps`, and `question.visual_cues`.

### Pilot Section 1

Title: `IT vs. IS, and Data vs. Information`

Visual cues:

| Cue | Existing markers | Purpose |
| --- | --- | --- |
| `it_vs_is` | `m_31_12`, `m_31_23` | Compare IT and IS |
| `data_vs_information` | `m_31_38`, `m_31_43` | Compare data and information |
| `both_comparisons` | All four markers | Summarize both distinctions |
| `is_scope_correction` | `m_31_23` | Refocus the broader IS definition |

Set marker delays to zero because cue selection now controls timing.

Teaching steps:

1. Contrast IT with IS using `it_vs_is`.
2. Contrast data with information using `data_vs_information`.
3. Explain the kitchen analogy using `both_comparisons`.
4. Summarize the exam distinction using `both_comparisons`.

Replace the yes/no question with:

```text
Which is broader, IT or IS, and what does it include beyond the technology?
```

Expected answer:

```text
IS is broader because it includes the technology together with people, processes, and data.
```

Question cues:

```json
{
  "on_ask": "clear",
  "on_confusion": "both_comparisons",
  "on_correction": "is_scope_correction",
  "on_correct": "both_comparisons"
}
```

### Pilot Section 2

Title: `How an IS Works: Input, Processing, Output, and Feedback`

Visual cues:

| Cue | Existing markers | Purpose |
| --- | --- | --- |
| `activity_cycle` | `m_32_4` | Focus the activity cycle |
| `feedback_hint` | `m_32_4` | Re-emphasize the cycle during clarification |

Teaching steps:

1. Introduce the four activities using `activity_cycle`.
2. Explain input, processing, and output.
3. Explain feedback separately using `feedback_hint`.
4. Use the weather-station analogy.
5. Summarize why feedback makes the system corrective.

Replace the yes/no question with:

```text
What is the role of feedback after the system produces an output?
```

Expected answer:

```text
It returns the result so the input or process can be evaluated and corrected.
```

Question cues:

```json
{
  "on_ask": "clear",
  "on_confusion": "activity_cycle",
  "on_correction": "feedback_hint",
  "on_correct": "activity_cycle"
}
```

### Pilot Section 3

Title: `From Raw Data to Meaningful Information`

Visual cues:

| Cue | Existing markers | Purpose |
| --- | --- | --- |
| `raw_checkout_data` | `m_33_18` | Focus raw transaction data |
| `processed_sales_information` | `m_33_27`, `m_33_36` | Focus meaningful information |
| `data_to_information` | All three markers | Show the complete transformation |

Teaching steps:

1. Introduce raw checkout records using `raw_checkout_data`.
2. Explain processing.
3. Introduce summarized sales information using `processed_sales_information`.
4. Use the puzzle analogy with `data_to_information`.
5. Summarize the distinction.

Replace the yes/no question with:

```text
If individual checkout records are data, what would the summarized weekly sales total be?
```

Expected answer:

```text
Information.
```

Question cues:

```json
{
  "on_ask": "clear",
  "on_confusion": "data_to_information",
  "on_correction": "processed_sales_information",
  "on_correct": "data_to_information"
}
```

### Pilot Section 4

Title: `The Full IS Model: Feedback Loop and the Environment`

Visual cues:

| Cue | Existing markers | Purpose |
| --- | --- | --- |
| `system_core` | `m_34_12` | Focus the central model |
| `environmental_actors` | `m_34_16`, `m_34_22` | Focus surrounding actors |
| `full_model` | All three markers | Summarize the complete model |
| `feedback_correction` | `m_34_12` | Refocus the feedback-related core element |

Teaching steps:

1. Orient to the central model using `system_core`.
2. Explain input, processing, and output.
3. Explain environmental actors using `environmental_actors`.
4. Explain feedback and the ship-control-room analogy using `full_model`.
5. Summarize the complete model.

Keep the current topic checkpoint:

```text
What is the activity in an information system that returns output back to the input stage to help
evaluate and refine it?
```

Question cues:

```json
{
  "on_ask": "clear",
  "on_confusion": "full_model",
  "on_correction": "feedback_correction",
  "on_correct": "full_model"
}
```

## 12. Update Plan-Authoring Skills

### `create-explain-plan`

- Generate schema `2.0` only.
- Generate `teaching_steps` rather than strategy strings.
- Generate semantic visual-cue intents.
- Keep one page per section.
- Treat questions as optional.
- Prefer varied, short retrieval questions over universal yes/no questions.
- Require TTS-friendly instructions.
- Require every visual teaching step to reference an existing cue.
- Never invent marker targets.

### `add-plan-markers`

- Populate markers inside existing `visual_cues`.
- Use the current `span_id` format.
- Remove the instruction forbidding `span_id`.
- Require a valid source mapping before adding markers.
- Fail when a target cannot be mapped.
- Never fabricate incremental span IDs.
- Preserve cue purpose and description.
- Limit a cue to four markers.
- Use delays only for short reveals inside one cue.
- Do not produce section-level add/remove lists.

### `add-topic-checkpoint`

- Add question visual-cue references.
- Require `on_ask`, `on_confusion`, `on_correction`, and `on_correct` fields.
- Allow open spoken questions with an empty choices list.
- Keep expected answers short and voice-friendly.
- Prevent `on_ask` cues from revealing the answer.
- Prefer conceptual understanding over superficial counting questions.

### `create-chapter-plans`

- Validate schema version instead of checking only file existence.
- Treat legacy plans as invalid.
- Validate every teaching-step and cue reference.
- Stop when marker mappings are unavailable.
- Do not publish a partially migrated chapter.

## 13. Tests

The LiveKit skill requires tests for all agent behavior changes.

### Add `tests/test_plan_helpers.py`

Cover:

- Minimal valid schema `2.0` plan.
- Missing schema version.
- Legacy markers rejected.
- Legacy strategy rejected.
- Empty plan rejected.
- Section-count mismatch.
- Duplicate section IDs.
- Non-contiguous section sequences.
- Invalid prerequisites.
- Duplicate cue names.
- Invalid cue purposes.
- Invalid marker types.
- Marker page mismatch.
- Invalid marker IDs.
- Missing span IDs.
- Invalid delay values.
- Teaching steps referencing missing cues.
- Questions referencing missing cues.
- Questionless sections.
- Formatted prompts hiding marker implementation details.

### Rewrite `tests/test_tutor_agent.py`

Cover:

- Exactly three tools are exposed.
- Old rigid tools are absent.
- Unknown slugs cause no fetch or UI publication.
- Valid topic loading requires schema `2.0`.
- Invalid plans preserve active state.
- Questionless sections work.
- Topic loading does not add markers.
- Topic loading scrolls to the active section.
- Visual focus accepts only active-section cues.
- `clear` removes active markers.
- Invalid visual cues cause no UI changes.
- Visual focus does not change lesson progress.
- Cue replacement removes old markers before adding new markers.
- Scroll occurs before marker addition.
- Repeating the active cue is a no-op.
- Advancement occurs only through `advance_to_next_section`.
- `section_done` is emitted exactly once.
- Advancement moves exactly one section.
- Topic advancement follows ordered slugs.
- Plan topic sequence numbers cannot redirect progression.
- Chapter completion clears markers.
- Repeated final advancement is rejected.
- Topic switching clears old visual state.
- All UI messages use reliable `ui-control` publication.

### Add `tests/test_parse_dynamic_prompt.py`

Cover:

- Ordered topic slugs.
- Duplicate slug rejection.
- Missing slug rejection.
- Topic-count mismatch.
- Updated tool name in the dynamic context.
- Output-language preservation.

### Add `tests/test_agent_behavior.py`

Use LiveKit's `AgentSession.run()` testing pattern where practical.

Behavior scenarios:

- Starting a topic calls `fetch_topic_content`.
- A follow-up question does not advance.
- Asking for another explanation remains in the current section.
- A partial answer receives specific feedback.
- An answer plus a deeper question does not advance before the question is answered.
- Explicit readiness triggers advancement.
- A visual reference uses `set_visual_focus` with a valid cue.
- The model never invents marker IDs or page numbers.
- The model clears visual focus before unaided retrieval when instructed.
- Brief clarifications do not always end with checkpoints.
- Unrelated requests are briefly redirected to the educational concept.

Mark tests requiring provider credentials separately, but keep parser and tool-state tests in the
default suite.

### Repair Existing Observation Tests

`tests/test_observations.py` contains stale fixtures and expectations. Repair the test data to match
the production usage fields and current pricing behavior. Do not change production pricing merely
to satisfy stale tests.

## 14. Documentation Updates

Update:

- `README.md`
- `docs/architecture.md`
- `docs/data-models.md`
- `docs/explanation-plan-execution.md`
- `docs/agent-analysis.md`

Document:

- The three-tool workflow.
- Flexible conversation inside an active section.
- Explicit section advancement.
- Visual-cue schema.
- Reserved `clear` behavior.
- Marker replacement lifecycle.
- Scroll-before-marker ordering.
- No automatic markers at section activation.
- Schema `2.0` rejection behavior.
- Pilot-only migration status.
- Manual Langfuse prompt deployment requirement.
- Production migration gate.

Remove references to:

- `get_explanation_plan`
- `check_user_understanding`
- `start_section`
- `checkpoint_passed`
- Mandatory checkpoint completion.
- Retry counters.
- Automatic marker application at section start.
- Obsolete `set_checkpoint` payloads.

## 15. Verification Commands

Run:

```bash
uv run black .
uv run ruff check .
uv run mypy .
uv run pytest
```

Run the pilot manually:

```bash
uv run python tutor_agent.py console
```

Manual checks:

1. Load `what_is_an_information_system`.
2. Confirm page 31 opens without markers.
3. Focus `it_vs_is`.
4. Switch to `data_vs_information`.
5. Ask a follow-up and refocus without changing sections.
6. Clear markers before the section question.
7. Give a partial answer and verify specific feedback.
8. Advance explicitly.
9. Verify previous markers are removed.
10. Complete all four pilot sections.
11. Confirm no spoken response exposes marker IDs or cue names.
12. Confirm no marker appears before its cue is selected.
13. Confirm a legacy plan is rejected naturally.
14. Confirm an invalid cue causes no frontend changes.
15. Confirm chapter progression follows the ordered topic list.

## 16. Acceptance Scenarios

### Follow-Up Question

Sanad explains an active concept and asks a question. The student asks “Why does that happen?”

Expected behavior:

- Sanad answers directly.
- The active section remains unchanged.
- No advancement tool is called.
- The question is not treated as a failed answer.
- Sanad may select a more relevant visual cue.

### Partial Answer

The student states one correct component but omits another.

Expected behavior:

- Sanad acknowledges the correct component.
- Sanad identifies the missing component.
- Sanad stays in the current section.
- Sanad uses a correction cue when useful.
- Sanad does not reduce the answer to a binary failure.

### Confusion

The student says they do not understand.

Expected behavior:

- Sanad briefly normalizes the difficulty.
- Sanad changes wording, example, or representation.
- Sanad may switch from a definition cue to an example cue.
- No retry counter forces progression.
- The section remains active until the exchange is complete.

### Correct Answer With a Deeper Question

The student gives the correct answer and asks why the concept matters.

Expected behavior:

- Sanad answers the deeper question first.
- Sanad does not advance merely because the answer was correct.
- Advancement occurs only after the current exchange is complete.

### Visual Comparison

Sanad explains IT versus IS.

Expected behavior:

- Sanad selects `it_vs_is` before referring to the comparison.
- Only the authored markers are used.
- The model never supplies a page or span ID.
- Switching to `data_vs_information` replaces the previous focus.

### Retrieval Before Cueing

Sanad reaches an understanding question whose answer is visible in the current markers.

Expected behavior:

- Sanad calls `set_visual_focus("clear")`.
- Sanad asks one short question.
- If the learner is confused, Sanad selects the authored hint or correction cue.

### Section Advancement

The student clearly indicates readiness to continue.

Expected behavior:

- Sanad calls `advance_to_next_section` once.
- The old section is marked done.
- Old markers are removed.
- The next section becomes active.
- No markers appear until a visual cue is selected.

## 17. Rollout Plan

The implementation must not replace the current production runtime immediately because only one
sample plan is migrated and legacy compatibility was rejected.

Required sequence:

1. Implement schema, tools, prompt artifact, tests, and pilot-plan migration.
2. Run the pilot against an isolated topic or staging chapter.
3. Have an operator manually create the approved Langfuse prompt version.
4. Ensure staging receives the matching prompt and tool contract.
5. Validate traces and visual behavior.
6. Migrate every Bunny-hosted plan to schema `2.0`.
7. Validate every plan before upload.
8. Deploy plans, runtime, and prompt atomically.
9. Never expose the schema `2.0` runtime to a legacy plan.
10. Promote the prompt or production routing only through a separately approved release step.

## 18. Completion Criteria

The project is complete when:

- Sanad exposes exactly the agreed three tools.
- Follow-up conversation no longer changes lesson state.
- Only explicit advancement changes the active section.
- Markers can change during a section through semantic cue names.
- The model cannot create arbitrary visual targets.
- Marker transitions preserve the existing frontend protocol.
- The pilot plan uses schema `2.0`.
- Legacy schemas are rejected.
- The revised prompt exists in the repository and Langfuse remains unchanged.
- Unit, behavior, formatting, linting, and type checks pass.
- Manual pilot scenarios pass.
- Production remains blocked until all exposed remote plans are migrated.
