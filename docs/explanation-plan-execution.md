# Explanation Plan Execution

This document describes the process for executing an explanation plan, including all tools, their sequence, and detailed state management.

Source of truth: `src/tutor_agent_snd/agents/tutor_agent.py`

## Flow Diagram

```mermaid
graph TD
    A[Topic Selected] -->|Fetch Plan| B[get_explanation_plan(topic)]
    B -->|Load Section| C[start_section(section_id)]
  C --> D[Explain Strategy Points + Ask Checkpoint]
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

- **Purpose**: Prepares the section for execution, including validating prerequisites and auto-scrolling.
- **Parameters**:
  - `section_id` (str): The section ID to start.
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

3. **Checkpoint Handling**
   - `student_responded` is set when the learner answers.
   - If understood, checkpoint is marked complete and section completion event is published.
   - If not understood, a `[HINT]` response is returned for guided retry.

4. **Completion**
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

- **UI Commands**: Sent via LiveKit's `publish_data()`.
- **Scroll Format**: JSON `{"action": "scroll", "page": <number>}`.
- **Topic Change Format**: JSON `{"action": "set_topic", "topic": "<slug>", "number_of_sections": <n>}`.
- **Section Change Format**: JSON `{"action": "set_section", "section": "<title>", "current_section_index": <n>}`.
- **Checkpoint Format**: JSON `{"action": "set_checkpoint", "checkpoint_question": "<question>"}`.
- **Section Done Format**: JSON `{"action": "section_done", "section": "<title>"}`.
