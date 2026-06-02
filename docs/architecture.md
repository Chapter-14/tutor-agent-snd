# LiveKit Voice Agent Architecture

## High-Level Architecture Overview

The LiveKit Voice Agent is designed to provide real-time voice tutoring by utilizing various cutting-edge technologies, including LiveKit SDK, Language Models (LLMs), and Bunny Storage API. It is built to handle streaming audio, dynamic content delivery, and interactive question-answer sessions efficiently.

```mermaid
graph TD
    A[Student] -->|Audio Input| B[LiveKit Server]
    B -->|Streaming Audio| C[STT (Speech-to-Text)]
    C -->|Text Output| D[LLM (Language Model)]
    D -->|Instruction| E[TTS (Text-to-Speech)]
    E -->|Audio Output| A
    D -->|Fetch Content| F[Bunny Storage API]
    D -->|UI Control Commands| G[Frontend UI]
```

## Current Repository Layout

The runtime code is organized under `src/tutor_agent_snd`.

```text
src/tutor_agent_snd/
├── __main__.py                # Module entrypoint (python -m tutor_agent_snd)
├── main.py                    # Worker entrypoint and pipeline wiring
├── agents/
│   └── tutor_agent.py         # Assistant class and function tools
└── lib/
   ├── bunny.py               # Bunny Storage integration
   └── setup_langfuse.py      # Langfuse tracing integration
```

The rest of the repository is split into:

- `contexts/`: course/chapter material and generated topic artifacts.
- `docs/`: implementation and design documents.
- root config files (`pyproject.toml`, `livekit.toml`, `Dockerfile`) for packaging/runtime setup.

### Components

#### 1. **LiveKit SDK Integration**

Handles the voice pipeline, including:

- **Speech-to-Text (STT)**: Converts raw audio into text for processing.
- **Voice Activity Detection (VAD)**: Identifies segments of speech in the audio stream.
- **Text-to-Speech (TTS)**: Converts generated text responses back to audio.

#### 2. **Language Model (LLM)**

Processes incoming text, generates tutoring strategies, and manages interaction flow.

#### 3. **Bunny Storage API**

Used to fetch course materials, including explanation plans and multimedia content.

#### 4. **Agent Session**

Configures the agent by initializing sessions for users based on their attributes (e.g., `course_id`, `chapter_id`, `language`). Handles session lifecycles and context.

#### 5. **Job Context**

Provides a communication channel for server-to-client messaging, including UI actions such as scrolling to specific pages and updating the current topic.

## Code Location Mapping

- Session bootstrap and worker run loop: `src/tutor_agent_snd/main.py`
- Tutor behavior and tool definitions: `src/tutor_agent_snd/agents/tutor_agent.py`
- Content retrieval from Bunny: `src/tutor_agent_snd/lib/bunny.py`
- Observability setup (Langfuse + tracing): `src/tutor_agent_snd/lib/setup_langfuse.py`

## Data Flow Explanation

The data flow can be summarized in the following steps:

1. **Student Audio Input**:
   - Audio is picked up by LiveKit SDK and processed via VAD to detect voice activity.
2. **Speech-to-Text (STT)**:
   - Transcribed audio is sent to the LLM for processing.
3. **LLM Processing**:
   - The LLM generates tutoring strategies, fetches content from Bunny Storage if needed, and responds.
4. **Text-to-Speech (TTS)**:
   - Generated text is converted into audio output and sent back to the student.
5. **Frontend Integration**:
   - Commands like page scrolling, topic updates, section changes, checkpoint display, and UI markers are sent via the `publish_data()` method with the topic `"ui-control"`, ensuring smooth interaction. Each command follows a consistent JSON format with an `"action"` field for frontend routing. For example:
     - Topic update: `{"action": "set_topic", "topic": "<topic_slug>", "number_of_sections": <n>}`.
     - Add visual markers: `{"action": "add_markers", "markers": {"m_5_123": {"type": "highlight", "page": 5, "span_id": 123, "delay": 500}}}`.
   
   See [Explanation Plan Execution](./explanation-plan-execution.md#frontend-integration) for the full payload format reference.

## Entry Point Initialization

The agent's initialization begins with setting up the user session. Here's an overview:

1. **Environment Setup**:
   - Load API keys and environment variables using `load_dotenv`.
   - Initialize required models (e.g., VAD, TTS).

2. **Agent Session Creation**:
   - `AgentSession` is created with user attributes (`course_id`, `chapter_id`, etc.).

3. **Job Context Initialization**:
   - Establishes a communication bridge between the agent and the LiveKit room.

4. **LiveKit Connectivity**:
   - Connects to the LiveKit room and waits for streaming audio from the student.

5. **Plan Loading**:
   - Fetches the `ExplanationPlan` based on the topic and prepares for execution.
