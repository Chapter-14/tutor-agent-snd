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
    markers: UpdateUIMarkers | None
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
- `markers` (UpdateUIMarkers | None): Optional marker transition. When present, its `remove` list is processed before its `add` list when the section starts. When `None`, no marker changes occur for this section.
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

## UIMarker

Represents a single visual marker to be rendered on the frontend. Markers draw the student's attention to specific elements on the page (for example, highlighting a diagram, circling a keyword, or underlining a formula).

### Definition

```python
@dataclass
class UIMarker:
    id: str
    type: str
    page: int
    span_id: int
    delay: int
```

### Field Descriptions

- `id` (str): Unique identifier following the scheme `m_{page}_{span_id}`. Example: `"m_5_123"` identifies a marker on page 5 targeting span element 123. This ID is used both for deduplication on the frontend and for removal requests.
- `type` (str): The visual style of the marker. Accepted values:
  - `"highlight"` — background highlight over the target element.
  - `"circle"` — circular outline around the target element.
  - `"underline"` — underline beneath the target element.
  - `"point"` — arrow or pointer indicator at the target element.
- `page` (int): The page number (1-based) where the marker should appear. Must correspond to a valid page in the chapter material.
- `span_id` (int): The identifier of the target `<span>` element within the page. The frontend uses this to locate the exact DOM element to apply the marker to.
- `delay` (int): Delay in **milliseconds** before the marker becomes visible after the section starts. Useful for staggered reveal of multiple markers (for example, first highlight the title, then 2 seconds later circle the diagram).

### ID Convention

Marker IDs follow the pattern `m_{page}_{span_id}` to guarantee uniqueness across an entire chapter. Two markers on different pages or targeting different spans will never collide.

## UpdateUIMarkers

Groups the markers to add and remove when a section begins. Each `Section` can optionally carry an `UpdateUIMarkers` instance that describes the marker transition for that section.

### Definition

```python
@dataclass
class UpdateUIMarkers:
    add: list[UIMarker]
    remove: list[str]
```

### Field Descriptions

- `add` (list[UIMarker]): Markers to render on the frontend when the section starts.
- `remove` (list[str]): Marker IDs to remove from the frontend when the section starts. This is used to clean up markers from a previous section that should no longer be visible.

### Transition Semantics

When `start_section` is called, the agent processes markers in two steps:

1. **Remove** — All marker IDs listed in `remove` are sent to the frontend for cleanup.
2. **Add** — All markers in `add` are sent to the frontend for rendering.

The remove step always executes before the add step so that a marker can be removed and immediately re-added (for example, to change its type) without conflicts.

## State Management

### ExplanationPlan State

- `current_plan` is the loaded plan.

### Section Progression

- `current_section_index` tracks active section navigation.
- Each section is marked `started` when execution begins and `completed` after checkpoint success.

### Checkpoint Flow

- The active checkpoint is attached to `current_plan.current_section.checkpoint`.
- `student_responded` and `completed` jointly track checkpoint status.

### Marker Lifecycle

- Markers are defined per-section inside the `markers` field (`UpdateUIMarkers | None`).
- On `start_section`, if the section has markers:
  1. All IDs in `markers.remove` are sent to the frontend for cleanup.
  2. All `UIMarker` objects in `markers.add` are sent to the frontend for rendering.
- If `markers` is `None`, no marker commands are sent and the frontend retains whatever markers it currently shows.
- The frontend is responsible for marker persistence until an explicit remove command is received.
