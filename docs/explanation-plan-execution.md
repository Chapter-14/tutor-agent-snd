# Explanation Plan Execution

This document describes the process for executing an explanation plan, including all tools, their sequence, and detailed state management.

## Flow Diagram

```mermaid
graph TD
    A[Topic Selected] -->|Fetch Plan| B[get_explanation_plan(topic)]
    B -->|Load Section| C[start_section(section_id)]
    C --> D[Explain Strategy Points]
    D -->|Ask Checkpoint Question| E[checkpoint_reached(checkpoint_id)]
    E -->|Student Responds| F[checkpoint_passed(checkpoint_id, understood)]
    F -->|Evaluate Understanding| G{Understood?}
    G -->|Yes| H[complete_section(section_id)]
    G -->|No| I[Provide Hint]
    H -->|Next Section| C
    I -->|Reattempt Checkpoint| E
```

## Tool Descriptions

### 1. `get_explanation_plan(topic)`
- **Purpose**: Fetches the JSON explanation plan for the selected topic from Bunny Storage.
- **Parameters**:
  - `topic` (str): The topic to fetch content for.
- **Return Value**: An `ExplanationPlan` object parsed from JSON.

### 2. `start_section(section_id)`
- **Purpose**: Prepares the section for execution, including validating prerequisites and auto-scrolling.
- **Parameters**:
  - `section_id` (int): The ID of the section to start.
- **Return Value**: None.

### 3. `checkpoint_reached(checkpoint_id)`
- **Purpose**: Pauses the agent at a checkpoint, requiring student input.
- **Parameters**:
  - `checkpoint_id` (int): The checkpoint ID.
- **Return Value**: None.
- **State Changes**:
  - Sets `awaiting_checkpoint_response = True`.

### 4. `checkpoint_passed(checkpoint_id, student_understood)`
- **Purpose**: Processes the student's response and provides hints if needed.
- **Parameters**:
  - `checkpoint_id` (int): The checkpoint ID.
  - `student_understood` (bool): Whether the student understood the material.
- **Return Value**: `SUCCESS` or `HINT`.

### 5. `complete_section(section_id)`
- **Purpose**: Marks the section complete and unlocks the next section.
- **Parameters**:
  - `section_id` (int): The section ID.
- **Return Value**: None.

### 6. `scroll_to_page(page_number)`
- **Purpose**: Sends a UI scroll command.
- **Parameters**:
  - `page_number` (int): The page number to scroll to.
- **Return Value**: None.

## State Transitions

1. **Plan Loading**
   - `current_plan` is set to the fetched `ExplanationPlan`.

2. **Section Execution**
   - `active_checkpoint_id` tracks the current checkpoint.
   - `awaiting_checkpoint_response` prevents further progress until reset.

3. **Checkpoint Handling**
   - On reaching a checkpoint, the agent pauses and awaits a valid student response.

4. **Completion**
   - Once the section is completed, it transitions to the next section.

## Error Handling

### Prerequisite Validation
- Each section checks its `requires_completion_of` field to ensure prerequisites are met.
- Errors:
  - **Missing prerequisites**: Abort the section and notify the user.

### Checkpoint Enforcement
- Checkpoint progress is blocked unless `awaiting_checkpoint_response` is reset properly.
- Errors:
  - **Skips Section**: Notify and revert.

### Tool Sequence Enforcement
- The tools must be executed in sequence.
- Errors:
  - **Out-of-order calls**: Raise exceptions and log the incident.

## Guardrails
- **No Skipping**: Prevent skipping sections or checkpoints.
- **Default Hints**: Ensure hints are provided for all misunderstood checkpoints.

## Frontend Integration
- **UI Commands**: Sent via LiveKit's `publish_data()`.
- **Scroll Format**: JSON `{"action": "scroll", "page": <number>}`.