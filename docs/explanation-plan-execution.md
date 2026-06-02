# Explanation Plan Execution

This document describes the process for executing an explanation plan, including all tools, their sequence, and detailed state management.

Source of truth: `src/tutor_agent_snd/agents/tutor_agent.py`

## Flow Diagram

```mermaid
graph TD
    A[Topic Selected] -->|Fetch Plan| B[get_explanation_plan(topic)]
    B -->|Load Section| C[start_section(section_id)]
    C -->|Remove old markers| C1[_remove_markers]
    C1 -->|Add new markers| C2[_add_markers]
    C2 --> D[Explain Strategy Points + Ask Checkpoint]
    D -->|Student Responds| E[checkpoint_passed(student_understood)]
    E -->|Evaluate Understanding| F{Understood?}
    F -->|Yes| G[Mark Checkpoint Complete]
    F -->|No| H[Return HINT + Re-explain]
    G -->|More Sections| C
    G -->|Last Section| I[Topic Complete]
    H --> D
```

## Tool Descriptions

### 1. `get_explanation_plan(topic)`

- **Purpose**: Fetches the JSON explanation plan for the selected topic from Bunny Storage. As a side effect, it also notifies the frontend of the current topic being explained.
- **Parameters**:
  - `topic` (str): The topic to fetch content for.
- **Return Value**: Success/error string with execution guidance.

### 2. `start_section(section_id)`

- **Purpose**: Prepares the section for execution, including validating prerequisites, processing UI marker transitions, and auto-scrolling.
- **Parameters**:
  - `section_id` (str): The section ID to start.
- **Side Effects** (in order):
  1. Sends a `set_section` UI control command.
  2. Sends a `remove_markers` UI control command if the section defines markers with a `remove` list.
  3. Sends an `add_markers` UI control command if the section defines markers with an `add` list.
  4. Sends a `set_checkpoint` UI control command if the section has a checkpoint.
  5. Sends a `scroll` UI control command if the section action type is `"scroll"`.
- **Return Value**: `[SUCCESS]`/`[ERROR]` formatted string including section prompt content.

### 3. `checkpoint_passed(student_understood)`

- **Purpose**: Processes the student's response and provides hints if needed.
- **Parameters**:
  - `student_understood` (bool): Whether the student understood the material.
- **Return Value**: `[SUCCESS]`, `[ERROR]`, or `[HINT]` guidance string.

### 4. `scroll_to_page(page_number)`

- **Purpose**: Sends a UI scroll command.
- **Parameters**:
  - `page_number` (int): The page number to scroll to.
- **Return Value**: Success string.

## State Transitions

1. **Plan Loading**
   - `current_plan` is set to the fetched `ExplanationPlan`.

2. **Section Execution**
   - `current_section_index` is aligned to the section sequence.
   - The section is marked `started = True` when execution begins.

3. **Marker Transition**
   - When a section defines `markers` (`UpdateUIMarkers`), the agent processes the transition in two ordered steps:
     1. **Remove**: Sends marker IDs from `markers.remove` to the frontend. This clears markers from previous sections that are no longer relevant.
     2. **Add**: Sends marker definitions from `markers.add` to the frontend. Each marker includes its `id`, `type`, `page`, `span_id`, and `delay`.
   - If a section has `markers = None`, no marker commands are sent. The frontend continues showing whatever markers it currently displays.
   - Markers are not automatically cleared when a section completes. They persist until explicitly removed by a subsequent section's `remove` list or by a frontend navigation event.

4. **Checkpoint Handling**
   - `student_responded` is set when the learner answers.
   - If understood, checkpoint is marked complete and section completion event is published.
   - If not understood, a `[HINT]` response is returned for guided retry.

5. **Completion**
   - If more sections exist, the response instructs progression to the next section.
   - On last section completion, the response instructs congratulating the learner.

## Error Handling

### Prerequisite Validation

- Each section checks its `requires_completion_of` field to ensure prerequisites are met.
- Errors:
  - **Missing prerequisites**: Abort the section and notify the user.

### Checkpoint Enforcement

- A new section cannot be started while the current started section has an incomplete checkpoint.
- Errors:
  - **Skips Section**: Notify and revert.

### Tool Sequence Enforcement

- The tools must be executed in sequence (`get_explanation_plan` -> `start_section` -> `checkpoint_passed`).
- Errors:
  - **Out-of-order calls**: Raise exceptions and log the incident.

## Guardrails

- **No Skipping**: Prevent skipping sections or checkpoints.
- **Default Hints**: Ensure hints are provided for all misunderstood checkpoints.

## Frontend Integration

All UI commands are sent via LiveKit's `publish_data()` method with the topic `"ui-control"`. Each payload is a JSON object containing an `"action"` field that the frontend uses for routing.

### General Payload Structure

```json
{
  "action": "<action_type>",
  ...action-specific fields
}
```

### Action Reference

| Action | Purpose | Trigger |
|--------|---------|---------|
| `scroll` | Navigate to a specific page | Section has `action.type = "scroll"` |
| `set_topic` | Notify frontend of active topic | `get_explanation_plan` called |
| `set_section` | Notify frontend of active section | `start_section` called |
| `set_checkpoint` | Display checkpoint question | Section has a checkpoint |
| `section_done` | Mark section as completed | `checkpoint_passed` with success |
| `add_markers` | Render visual markers on the page | Section defines `markers.add` |
| `remove_markers` | Remove visual markers from the page | Section defines `markers.remove` |

### Payload Formats

#### Scroll

```json
{
  "action": "scroll",
  "page": 5
}
```

- **`page`** (int): The page number to scroll to.

#### Topic Change

```json
{
  "action": "set_topic",
  "topic": "photosynthesis",
  "number_of_sections": 4
}
```

- **`topic`** (str): The slug identifying the current topic.
- **`number_of_sections`** (int): Total sections in the plan (for progress display).

#### Section Change

```json
{
  "action": "set_section",
  "section": "Light-Dependent Reactions",
  "current_section_index": 2
}
```

- **`section`** (str): The human-readable section title.
- **`current_section_index`** (int): 1-based index of the current section (for progress display).

#### Checkpoint

```json
{
  "action": "set_checkpoint",
  "checkpoint_question": "What is the role of chlorophyll in photosynthesis?"
}
```

- **`checkpoint_question`** (str): The question to display to the student.

#### Section Done

```json
{
  "action": "section_done",
  "section": "Light-Dependent Reactions"
}
```

- **`section`** (str): The title of the completed section.

#### Add Markers

```json
{
  "action": "add_markers",
  "markers": {
    "m_5_123": {
      "type": "highlight",
      "page": 5,
      "span_id": 123,
      "delay": 500
    },
    "m_5_456": {
      "type": "circle",
      "page": 5,
      "span_id": 456,
      "delay": 2000
    }
  }
}
```

- **`markers`** (object): A map where each key is a marker ID (following the `m_{page}_{span_id}` convention) and each value describes the marker:
  - **`type`** (str): Visual style — `"highlight"`, `"circle"`, `"underline"`, or `"point"`.
  - **`page`** (int): The page where the marker appears.
  - **`span_id`** (int): The target `<span>` element on the page.
  - **`delay`** (int): Milliseconds to wait before showing the marker after the section starts.

#### Remove Markers

```json
{
  "action": "remove_markers",
  "markers": ["m_3_100", "m_3_200"]
}
```

- **`markers`** (array of str): List of marker IDs to remove from the frontend. The frontend should hide and dispose of these markers immediately upon receiving this command.

### Marker Example — Full Section Transition

The following example shows the sequence of payloads sent when transitioning from Section 1 to Section 2. Section 2 defines markers that remove highlights from the previous section and add new ones for the current content.

**Step 1: Remove markers from previous section**

```json
{
  "action": "remove_markers",
  "markers": ["m_3_100", "m_3_200"]
}
```

**Step 2: Add markers for current section**

```json
{
  "action": "add_markers",
  "markers": {
    "m_5_300": {
      "type": "highlight",
      "page": 5,
      "span_id": 300,
      "delay": 0
    },
    "m_5_301": {
      "type": "circle",
      "page": 5,
      "span_id": 301,
      "delay": 1500
    }
  }
}
```

This ensures the student's visual focus shifts from the previous section's elements to the current section's elements.
