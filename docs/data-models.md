# Data Models

This document describes the data models used in the LiveKit Voice Agent, including their fields, relationships, and state management.

## ExplanationPlan

### Definition
```python
@dataclass
class ExplanationPlan:
    topic: str
    sections: list[Section]
```

### Field Descriptions
- `topic` (str): The subject of the explanation plan.
- `sections` (list[Section]): The list of sections included in the plan.

## Section

### Definition
```python
@dataclass
class Section:
    id: int
    title: str
    actions: list[SectionAction]
    requires_completion_of: list[int]
    completed: bool = False
```

### Field Descriptions
- `id` (int): Unique identifier for the section.
- `title` (str): The title of the section.
- `actions` (list[SectionAction]): The actions to be executed in the section.
- `requires_completion_of` (list[int]): List of prerequisite section IDs.
- `completed` (bool): Marks whether the section is completed.

## Checkpoint

### Definition
```python
@dataclass
class Checkpoint:
    id: int
    question: str
    completed: bool = False
```

### Field Descriptions
- `id` (int): Unique identifier for the checkpoint.
- `question` (str): The checkpoint question text.
- `completed` (bool): Marks whether the checkpoint was passed.

## SectionAction

### Definition
```python
@dataclass
class SectionAction:
    type: str
    content: str
```

### Field Descriptions
- `type` (str): The type of action (e.g., `explanation`, `checkpoint`).
- `content` (str): The action's content.

## State Management

### ExplanationPlan State
- `current_plan` is the loaded plan.

### Section Progression
- Each section is marked `completed` once its actions are executed.

### Checkpoint Flow
- `active_checkpoint_id` tracks the ongoing checkpoint.
- `awaiting_checkpoint_response` enforces response collection before continuation.