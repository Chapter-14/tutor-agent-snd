# LiveKit Voice Agent

A LiveKit-powered voice AI agent framework that demonstrates how to build realtime conversational AI with MCP (Model Context Protocol) server integration.

## Features

- 🎤 Natural voice conversations with low latency
- 🔄 Real-time voice interaction with interruption handling
- 🛠️ Tool integration via MCP servers
- 🎯 Multiple provider options (OpenAI, Deepgram, Cartesia, etc.)
- 🔌 Extensible architecture for custom tools and agents

## Prerequisites

- Python 3.10 or later
- API Keys:
  - OpenAI API key
  - Deepgram API key
  - LiveKit credentials (optional - only if deploying to LiveKit Cloud)

## Quick Start

### 1. Install Dependencies

```bash
# Install dependencies using UV
uv sync
```

### 2. Set Up Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

**Required variables:**

- `OPENAI_API_KEY` - OpenAI API key
- `DEEPGRAM_API_KEY` - Deepgram API key

**Optional for LiveKit Cloud deployment:**

- `LIVEKIT_URL` - LiveKit server URL
- `LIVEKIT_API_KEY` - LiveKit API key
- `LIVEKIT_API_SECRET` - LiveKit API secret

### 3. Download Required Model Files

Before first run, download the required model files (Silero VAD, turn detector):

```bash
# Download model files
uv run tutor-agent download-files

```

### 4. Run the Agent

```bash
# Console mode (test locally without LiveKit server)
uv run tutor-agent console

# Development mode (connects to LiveKit - optional)
uv run tutor-agent dev

# Production mode
uv run tutor-agent start
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   LiveKit   │──b─▶│ Voice Agent  │───▶│ MCP Servers │
│   Client    │     │              │     │   (Tools)   │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    │             │
              ┌─────▼────┐  ┌────▼─────┐
              │ Deepgram │  │  OpenAI  │
              │   STT    │  │ LLM/TTS  │
              └──────────┘  └──────────┘
```

## Project Structure

The project now uses a `src/` package layout.

```text
tutor-agent-snd/
├── AGENTS.md
├── Dockerfile
├── livekit.toml
├── pyproject.toml
├── README.md
├── contexts/
│   ├── GEMINI.md
│   ├── material/
│   ├── output/
│   └── prompts/
├── docs/
│   ├── architecture.md
│   ├── data-models.md
│   └── explanation-plan-execution.md
└── src/
  └── tutor_agent_snd/
    ├── __init__.py
    ├── __main__.py
    ├── main.py
    ├── agents/
    │   └── tutor_agent.py
    └── lib/
      ├── bunny.py
      └── setup_langfuse.py
```

### Important Files

- `src/tutor_agent_snd/main.py`: LiveKit worker entrypoint and pipeline setup.
- `src/tutor_agent_snd/agents/tutor_agent.py`: Tutor agent tools, plan flow, and UI-control publishing.
- `src/tutor_agent_snd/lib/bunny.py`: Bunny Storage fetch helpers.
- `src/tutor_agent_snd/lib/setup_langfuse.py`: Langfuse tracing setup.

## Voice Pipeline Configuration

The agent uses a modular voice pipeline with swappable components:

### Speech-to-Text (STT)

- **Default**: Deepgram Nova-2 (highest accuracy)
- Alternatives: AssemblyAI, Azure Speech, Whisper

### Large Language Model (LLM)

- **Default**: OpenAI GPT-4.1-mini (fast, cost-effective)
- Alternatives: Anthropic Claude, Google Gemini, Groq

### Text-to-Speech (TTS)

- **Default**: OpenAI Echo voice (natural, versatile)
- Alternatives: Cartesia (fastest), ElevenLabs (highest quality)

### Voice Activity Detection (VAD)

- **Default**: Silero VAD (reliable voice detection)

### Turn Detection

- **Default**: Multilingual Model (natural conversation flow)
- Alternatives: Semantic model, VAD-based

### Adding Custom Tools

You can also add tools directly to your agent using the `@function_tool` decorator:

```python
from livekit.agents import function_tool, RunContext
from datetime import datetime

class Assistant(Agent):
    @function_tool
    async def get_current_time(self, context: RunContext) -> str:
        """Get the current time."""
        return datetime.now().strftime("%I:%M %p")
```

### Installing Additional Providers

```bash
# Additional TTS providers
uv add livekit-plugins-cartesia livekit-plugins-elevenlabs

# Additional LLM providers
uv add livekit-plugins-anthropic livekit-plugins-google livekit-plugins-groq

# Additional STT providers
uv add livekit-plugins-assemblyai livekit-plugins-azure
```

## Deploy to LiveKit Cloud

Once you've tested your agent locally, deploy it to LiveKit Cloud for production use:

### 1. Create a LiveKit Cloud Account

Sign up at [LiveKit Cloud](https://cloud.livekit.io/)

### 2. Install the LiveKit CLI

Choose the installation method for your platform:

**Windows:**

```bash
winget install LiveKit.LiveKitCLI
```

**Mac:**

```bash
brew install livekit
```

**Linux:**

```bash
curl -sSL https://get.livekit.io/ | bash
```

### 3. Authenticate with LiveKit Cloud

Open a new terminal and authenticate:

```bash
lk cloud auth
```

### 4. Configure Environment Variables

Set up your environment variables for the cloud:

```bash
lk app env -w
```

This will write your LiveKit credentials to `.env.local`

### 5. Start Your Agent

Run your agent connected to LiveKit Cloud:

```bash
uv run tutor-agent start
```

### 6. Create an Agent in LiveKit Cloud

In a separate terminal, register your agent:

```bash
lk agent create
```

### 7. Test in the Playground

Visit the [LiveKit Agents Playground](https://agents-playground.livekit.io/) and sign in with your LiveKit organization to test your agent in the browser.

## Console Mode Testing

Console mode lets you test your agent locally without needing a LiveKit server:

```bash
# Run agent in dev mode
uv run tutor-agent dev
```

This will start an interactive console where you can speak to your agent using your microphone and speakers.

## Troubleshooting

### Python Version

Ensure you're using Python 3.10 or later:

```bash
python --version
```

### Model Downloads

TTS models may download on first use, which can take time. The Docker image pre-downloads Silero VAD to speed up startup.

### API Key Issues

- Verify all required API keys are set in `.env`
- Check that API keys are valid and have sufficient credits
- Ensure no extra whitespace in environment variable values

### Audio Issues in Console Mode

- Check microphone/speaker permissions
- Verify audio devices are correctly configured
- Try adjusting VAD sensitivity if voice detection is problematic

## Resources

- [LiveKit Agents Documentation](https://docs.livekit.io/agents/)
- [LiveKit Python SDK](https://github.com/livekit/agents)
