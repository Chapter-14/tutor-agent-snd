# Data Models

This document describes the data models used in the LiveKit Voice Agent, including their fields, relationships, and state management.

Source of truth: `src/tutor_agent_snd/agents/tutor_agent.py`

## ExplanationPlan

### Definition

```python
@dataclass
class ExplanationPlan:
    topic: str
    title: str
    goal: str
    total_sections: int
    sections: list[Section]
    current_section_index: int = 0
```

### Field Descriptions

- `topic` (str): The subject of the explanation plan.
- `title` (str): Human-readable title of the loaded plan.
- `goal` (str): High-level learning objective for the topic.
- `total_sections` (int): Declared number of sections in the plan.
- `sections` (list[Section]): The list of sections included in the plan.
- `current_section_index` (int): Zero-based pointer to the active section.

### Derived Properties

- `current_section` (`Section | None`): Returns active section from `current_section_index`.
- `is_complete` (bool): Returns true when all sections are marked completed.

## Section

### Definition

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
    explanation_strategy: list[str]
    checkpoint: Checkpoint | None
    completed: bool = False
    started: bool = False
```

### Field Descriptions

- `id` (str): Unique section identifier.
- `title` (str): The title of the section.
- `sequence` (int): 1-based order position.
- `requires_completion_of` (str | None): Optional prerequisite section ID.
- `action` (SectionAction | None): Optional UI action (for example, scroll).
- `agent_guidance` (str): Tone and delivery guidance for the assistant.
- `visual_description` (str): Description of what the learner should be seeing.
- `explanation_strategy` (list[str]): Ordered talking points for the section.
- `checkpoint` (Checkpoint | None): Optional checkpoint to validate understanding.
- `completed` (bool): Marks whether the section is completed.
- `started` (bool): Marks whether section execution has started.

## Checkpoint

### Definition

```python
@dataclass
class Checkpoint:
    id: str
    mandatory: bool
    question: str
    success_criteria: str
    on_confusion: str
    completed: bool = False
    student_responded: bool = False
```

### Field Descriptions

- `id` (str): Unique identifier for the checkpoint.
- `mandatory` (bool): Indicates whether this checkpoint must be satisfied.
- `question` (str): The checkpoint question text.
- `success_criteria` (str): What counts as an acceptable student response.
- `on_confusion` (str): Recovery guidance for re-explaining the concept.
- `completed` (bool): Marks whether the checkpoint was passed.
- `student_responded` (bool): Marks whether a learner response has been captured.

## SectionAction

### Definition

```python
@dataclass
class SectionAction:
    type: str
    page: int | None = None
```

### Field Descriptions

- `type` (str): Action type, currently used for frontend actions such as `scroll`.
- `page` (int | None): Optional page number for scroll actions.

## State Management

### ExplanationPlan State

- `current_plan` is the loaded plan.

### Section Progression

- `current_section_index` tracks active section navigation.
- Each section is marked `started` when execution begins and `completed` after checkpoint success.

### Checkpoint Flow

- The active checkpoint is attached to `current_plan.current_section.checkpoint`.
- `student_responded` and `completed` jointly track checkpoint status.
