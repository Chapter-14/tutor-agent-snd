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
Provides a communication channel for server-to-client messaging, including UI actions (e.g., scrolling to specific pages).

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
   - Commands like page scrolling or UI updates are sent via the `publish_data()` method, ensuring smooth interaction.

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