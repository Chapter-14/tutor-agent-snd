# Current Tutor Agent Context and Constraints

## Purpose of This Document

This document describes only the executable, uncommented behavior in:

- `src/tutor_agent_snd/main.py`
- `src/tutor_agent_snd/agents/tutor_agent.py`

Treat these two files as the complete source of truth for this simplified agent. Do not infer capabilities from repository documentation, unused imports, helper implementations, or commented-out code.

## Agent Identity and Purpose

The agent is a private, voice-based AI tutor. It joins a LiveKit room, listens to one participant, and responds with synthesized speech. Its intended role is to guide the student through content for a selected course chapter while coordinating a small set of visual actions in the frontend.

The agent receives its tutoring persona and subject context from two external prompt sources:

1. A Langfuse prompt named `snd-agent-system-prompt`.
2. A Bunny Storage Markdown file at `courses/{course_id}/{chapter_id}/character.md`.

These are concatenated with an explicit instruction to speak in the participant's selected language. The actual educational facts, topic list, persona, and conversational rules contained in those external prompts are not visible in the two source files and therefore are not defined here.

## Runtime Context

The agent reads these attributes from the connected participant:

| Attribute | Default | Use |
| --- | --- | --- |
| `course_id` | `phys_1040` | Selects the course content path. |
| `chapter_id` | `ch_1` | Selects the chapter content path. |
| `language` | `Arabic` | Configures speech services and the response-language instruction. |
| `user_name` | `undefined` | Used in observability metadata. |
| `user_id` | `undefined` | Used in observability metadata. |

The LiveKit room name is used as the session ID.

## Conversation Behavior

When the agent enters the session, it is instructed to:

1. Greet the user by name.
2. Ask the user to choose a topic from a list that is expected to appear after the agent finishes speaking, without giving examples.
3. Alternatively, allow the user to ask another question.

There is no executable code in the two source files that sends the user's name to the `Assistant` or displays the topic list. The opening instruction asks for a name-based greeting, but the agent can only know the name if one of its external prompt sources contains it or the runtime framework provides it through some mechanism not shown here. The frontend must also provide the expected topic list independently.

The agent can answer conversationally using the combined system and chapter character prompts. It must speak in the value of the participant's `language` attribute.

## Active Tools and Frontend Actions

All frontend control messages are reliable LiveKit data messages published on the `ui-control` topic.

### Scroll to a Page

The agent can request that the frontend scroll to a page:

```json
{"action": "scroll", "page": 3}
```

The tool accepts any integer. The source files do not validate page bounds or confirm that the page exists.

### Set the Current Topic

The agent exposes a tool intended to send the selected topic and section count:

```json
{
  "action": "set_topic",
  "topic": "topic name",
  "number_of_sections": 4
}
```

However, this tool reads `current_plan.total_sections`, while `current_plan` starts as `None` and no active code in the two source files assigns a plan. In the current simplified setup, calling this tool would fail before publishing the message. It must not be treated as a usable capability unless plan initialization is added elsewhere.

### Add Visual Markers

The agent can add one or more frontend markers. Each marker is keyed by its ID and carries a type, page, span ID, and delay:

```json
{
  "action": "add_markers",
  "add": {
    "marker-id": {
      "type": "marker type",
      "page": 3,
      "span_id": "span-id",
      "delay": 0
    }
  }
}
```

The two source files do not define the valid marker types, page range, span IDs, delay units, or frontend rendering behavior.

### Remove Visual Markers

The agent can remove markers by ID:

```json
{"action": "remove_markers", "remove": ["marker-id-1", "marker-id-2"]}
```

## Effective Capability Boundaries

Within the defined source boundary, the agent can:

- Hold a voice conversation with a student.
- Use the loaded system and chapter character prompts as conversational context.
- Speak in the participant-selected language.
- Ask the student to select a topic or ask a question.
- Scroll the frontend to a page.
- Add and remove frontend markers.
- Notify the frontend when the session time limit is reached.

Within the same boundary, the agent does not have an operational mechanism to:

- Fetch or load a topic-specific explanation plan after a topic is selected.
- Initialize or advance through plan sections.
- Track section completion or chapter completion.
- Ask and evaluate structured checkpoint questions.
- Validate topic names, page numbers, marker values, or whether frontend actions succeeded.
- Display the topic list referenced by its opening message.
- Reliably use the current-topic tool, because no current plan is initialized.
- Produce text output through LiveKit room output; room text output is disabled.

Do not claim these unavailable behaviors or fabricate plan state, section progress, topic metadata, marker coordinates, or frontend confirmation.

## Language Constraints

Only `English` and `Arabic` have explicit speech-service mappings:

| Participant language | Speech-service code |
| --- | --- |
| `English` | `en` |
| `Arabic` | `ar` |

Any other language value falls back to English (`en`) for speech recognition and synthesis, even though the conversational instruction still tells the model to speak in the original language value. This can cause a mismatch between model output and speech processing.

## Voice Pipeline

The active voice pipeline is:

- Speech-to-text: Deepgram `nova-3`.
- Primary language model: Cerebras `gemma-4-31b`, temperature `0.3`.
- Production fallback language model: Cerebras `zai-glm-4.7`, temperature `0.3`.
- Primary text-to-speech: ElevenLabs `eleven_flash_v2_5` with a configured Arabic voice.
- Production fallback text-to-speech: Cartesia `sonic-3.5` with a configured English voice.
- Voice activity detection: Silero with activation threshold `0.6` and minimum speech duration `0.3` seconds.
- Input noise cancellation: LiveKit BVC.
- Turn detection: speech-to-text based, with dynamic endpointing.
- Interruptions: adaptive and enabled, including false-interruption recovery.
- Preemptive response generation: disabled.

In production, the language model and text-to-speech adapters each retry a provider once before switching to their fallback. Outside production, each adapter receives the primary provider twice, so there is no distinct fallback provider.

The room subscribes to audio only, and LiveKit text output is disabled.

## Prompt and Environment Selection

The `ENVIRONMENT` variable defaults to `development`.

- In production, the Langfuse system prompt uses the `production` label.
- In other environments, it uses the `latest` label.
- In production, approximately 30% of sessions are recorded.
- In other environments, sessions are not recorded by this logic.

## Session Limit

`MAX_SESSION_DURATION` defaults to `1800` seconds. If it is greater than zero, a watchdog waits for that duration, publishes:

```json
{
  "action": "session_ending",
  "message": "Session ending due to time limit."
}
```

It then shuts down the agent session while draining pending work. A value of zero or less disables this watchdog.

## Rules for an AI Using This Context

1. Treat the externally loaded prompts as the source of tutoring content, but do not invent their contents when they are unavailable.
2. Respond in the participant's requested language, while recognizing that only English and Arabic are fully configured in the speech pipeline.
3. Use scrolling and markers only when the required page and marker data are known from available context.
4. Do not report a frontend action as successful merely because a message was published; no acknowledgment is implemented.
5. Do not call the current-topic tool in this simplified setup because its required plan state is never initialized.
6. Do not claim structured topic-plan, section, checkpoint, progress-tracking, or chapter-completion capabilities.
7. Do not assume the user name or topic list is available to the agent merely because the opening instruction refers to them.
