# LiveKit Voice Agent with Agno Integration

This project demonstrates how to build a voice agent using **LiveKit's VoicePipelineAgent** with **Agno's** powerful agentic capabilities including tool calling, knowledge bases, and memory.

## Why Agno + LiveKit?

- **LiveKit** provides excellent voice infrastructure: VAD, STT, TTS, and real-time audio streaming
- **Agno** provides powerful agent capabilities: tool calling, knowledge bases, memory, learning, and multi-agent orchestration

This integration lets you combine the best of both worlds: LiveKit's voice pipeline with Agno's intelligent agents.

## Project Structure

```
livekit_agent/
├── main.py                      # Example voice agent
├── pyproject.toml               # Dependencies
├── README.md
└── livekit_plugins_agno/        # The Agno plugin (~130 lines total!)
    ├── __init__.py              # Plugin registration
    ├── agno.py                  # LLMAdapter + AgnoStream
    └── version.py
```

## Installation

1. **Clone and install dependencies:**

```bash
uv sync
```

2. **Set up environment variables:**

Create a `.env` file with:

```env
LIVEKIT_URL=wss://your-livekit-server.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret
OPENAI_API_KEY=your-openai-key
DEEPGRAM_API_KEY=your-deepgram-key
```

## Usage

### Basic Example

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools import tool
from livekit_plugins_agno import LLMAdapter

# Define tools
@tool
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Weather in {city}: Sunny, 72°F"

# Create Agno agent with tools
agno_agent = Agent(
    model=OpenAIChat(id="gpt-4o-mini"),
    tools=[get_weather],
    instructions="You are a helpful voice assistant."
)

# Wrap for LiveKit
livekit_llm = LLMAdapter(agent=agno_agent)

# Use in voice pipeline
assistant = VoicePipelineAgent(
    vad=silero.VAD.load(),
    stt=deepgram.STT(),
    llm=livekit_llm,
    tts=deepgram.TTS(),
)
```

### Running the Example Agent

```bash
python main.py dev
```

Then connect to your LiveKit room to start talking to the agent.

## Features

### Tool Calling

The example includes three tools:

- **get_current_time**: Returns the current time
- **get_weather**: Returns weather for a city (mock data)
- **calculate**: Evaluates mathematical expressions

### Session Persistence

You can enable session persistence for conversation history:

```python
livekit_llm = LLMAdapter(
    agent=agno_agent,
    session_id="my-session",
    user_id="user-123",
)
```

### Custom Agno Agents

You can use any Agno agent features:

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.knowledge.url import URLKnowledge

agent = Agent(
    model=OpenAIChat(id="gpt-4o"),
    knowledge=URLKnowledge(urls=["https://docs.example.com"]),
    instructions="You are an expert assistant...",
    learning=True,  # Enable learning from interactions
)
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    LiveKit Room                          │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐              │
│  │  User   │───▶│   VAD   │───▶│   STT   │              │
│  │  Audio  │    │(Silero) │    │(Deepgram)│              │
│  └─────────┘    └─────────┘    └────┬────┘              │
│                                      │                   │
│                                      ▼                   │
│  ┌─────────────────────────────────────────────────┐    │
│  │             LLMAdapter (Agno Plugin)             │    │
│  │  ┌─────────────────────────────────────────┐    │    │
│  │  │              Agno Agent                  │    │    │
│  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐   │    │    │
│  │  │  │  Tools  │ │Knowledge│ │ Memory  │   │    │    │
│  │  │  └─────────┘ └─────────┘ └─────────┘   │    │    │
│  │  └─────────────────────────────────────────┘    │    │
│  └──────────────────────┬──────────────────────────┘    │
│                         │                                │
│                         ▼                                │
│  ┌─────────┐    ┌─────────┐                             │
│  │   TTS   │◀───│AgnoStream│                             │
│  │(Deepgram)│    └─────────┘                             │
│  └────┬────┘                                             │
│       │                                                  │
│       ▼                                                  │
│  ┌─────────┐                                             │
│  │  Audio  │                                             │
│  │ Output  │                                             │
│  └─────────┘                                             │
└─────────────────────────────────────────────────────────┘
```

## API Reference

### LLMAdapter

```python
LLMAdapter(
    agent: Agent,           # The Agno Agent to wrap
    session_id: str = None, # Optional session ID for state
    user_id: str = None,    # Optional user ID for memory
    stream_events: bool = False,  # Stream intermediate events
)
```

### AgnoStream

Internal class that handles streaming responses. You typically don't interact with this directly.

## Contributing

Contributions welcome! Please feel free to submit issues and pull requests.

## License

MIT
