# LiveKit Agents Agno Plugin

This plugin enables seamless integration of **Agno's agentic LLMs** with the [LiveKit Agents](https://github.com/livekit/agents) framework, allowing you to use Agno's advanced tool-calling, knowledge, and memory features in real-time voice pipelines.

## Why Use This Plugin?

- **LiveKit** provides robust real-time voice infrastructure: VAD, STT, TTS, and audio streaming.
- **Agno** delivers powerful agent capabilities: tool calling, knowledge bases, memory, learning, and multi-agent orchestration.

With this plugin, you can combine LiveKit's real-time voice pipeline with Agno's intelligent agents for advanced conversational AI experiences.

---

## Project Structure

```
livekit_plugins_agno/
├── __init__.py
├── agno.py
├── version.py
└── README.md
```

---

## Installation & Setup

1. **Clone the repository:**
    ```sh
    git clone https://github.com/your-org/agno_livekit_agent.git
    cd agno_livekit_agent
    ```

2. **Install dependencies using [uv](https://github.com/astral-sh/uv):**
    ```sh
    uv sync
    ```

3. **Set up environment variables:**
    - Copy `.env.example` to `.env` (if present) or create a `.env` file in your project root.
    - Fill in your credentials as follows:
      ```
      LIVEKIT_URL=wss://your-livekit-server.livekit.cloud
      LIVEKIT_API_KEY=your-api-key
      LIVEKIT_API_SECRET=your-api-secret
      OPENAI_API_KEY=your-openai-key
      DEEPGRAM_API_KEY=your-deepgram-key
      ```
    - **Get your LiveKit credentials:**  
      Visit [LiveKit Cloud Console](https://cloud.livekit.io/) to create a project and obtain your API keys and tokens.

    - **Get your OpenAI API key:**  
      [OpenAI API Keys](https://platform.openai.com/api-keys)

    - **Get your Deepgram API key:**  
      [Deepgram Console](https://console.deepgram.com/)

---

## Running the Agent

To start the agent server locally:

```sh
uv run main.py dev
```
or
```sh
python main.py dev
```

You should see logs indicating the agent is connecting to LiveKit and waiting for participants.

---

## Testing the Agent

### 1. **Using Python (CLI)**

- Run the agent as shown above.
- You will see logs for user and agent utterances in your terminal.

### 2. **Using LiveKit Meet Custom (UI)**

- Go to [LiveKit Meet](https://meet.livekit.io).
- Enter your `LIVEKIT_URL` and a valid **token** (generate one from the [LiveKit Cloud Console](https://cloud.livekit.io/)) in the `Custom` tab.
- Enter the **room name** (should match the one your agent is listening to, e.g., `room1`).
- Join the room and interact with your agent via voice or chat.

---

## Features

- **Tool Calling:** Use Agno's @tool-decorated Python functions in your voice agent.
- **Knowledge & Memory:** Leverage Agno's knowledge base and conversation memory.
- **Session Persistence:** Maintain context across sessions with `session_id` and `user_id`.
- **Streaming Responses:** Real-time streaming of LLM output to the user.

---

## License

Apache 2.0
