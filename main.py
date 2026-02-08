"""
LiveKit Voice Agent with Agno Integration

This example demonstrates how to build a voice agent using LiveKit's
VoicePipelineAgent with Agno's powerful agentic capabilities including
tool calling, knowledge bases, and memory.

Requirements:
    - LIVEKIT_URL and LIVEKIT_API_KEY/LIVEKIT_API_SECRET environment variables
    - OPENAI_API_KEY for the Agno agent
    - DEEPGRAM_API_KEY for STT/TTS (or use other providers)

Run with:
    python main.py dev
"""
import os
import json
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
from typing import Annotated

# Load env vars
load_dotenv(find_dotenv())

# Agno Imports
from agno.agent import Agent as AgnoAgent
from agno.models.openai import OpenAIChat
from agno.db.sqlite import SqliteDb
from agno.tools import tool

# LiveKit Imports
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession, # Ensure this matches your installed version (or VoicePipelineAgent)
    JobContext,
    JobProcess,
    cli,
    room_io,
)
from livekit import rtc
from livekit.plugins import noise_cancellation, silero, deepgram
from livekit_plugins_agno import LLMAdapter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# 1. Define Tools
# =============================================================================
@tool
def get_current_time() -> str:
    """Get the current time. Use this when the user asks what time it is."""
    from datetime import datetime

    return f"The current time is {datetime.now().strftime('%I:%M %p')}"

@tool
def get_weather(city: Annotated[str, "The city to get weather for"]) -> str:
    """Get the weather for a specific city. Use this when the user asks about weather."""
    # In a real application, this would call a weather API
    return f"The weather in {city} is sunny and 72°F (22°C)."

@tool
def calculate(
    expression: Annotated[str, "A mathematical expression to evaluate, e.g., '2 + 2'"],
) -> str:
    """Calculate a mathematical expression. Use this when the user asks for calculations."""
    try:
        # WARNING: In production, use a safe math parser instead of eval
        result = eval(expression, {"__builtins__": {}}, {})
        return f"The result of {expression} is {result}"
    except Exception as e:
        return f"I couldn't calculate that expression: {str(e)}"

# =============================================================================
# 2. Configure Agno Agent
# =============================================================================
memory_db = SqliteDb(db_file="memory.db")

def create_agno_agent() -> AgnoAgent:
    """Create and configure the Agno agent with tools and instructions."""
    return AgnoAgent(
        model=OpenAIChat(
            id=os.getenv("GROQ_MODEL", "gpt-4o-mini"), 
            api_key=os.getenv("GROQ_API_KEY", os.getenv("OPENAI_API_KEY")), 
            base_url=os.getenv("GROQ_URL")
        ),
        tools=[get_current_time, get_weather, calculate],
        instructions="""You are a helpful voice assistant. 

Key behaviors:
- Keep responses concise and conversational - you're speaking, not writing
- Use natural speech patterns and contractions
- When using tools, briefly explain what you're doing
- If you don't know something, say so honestly
- Be friendly and helpful

You have access to tools for:
- Getting the current time
- Checking weather for any city  
- Performing calculations

Remember: Your responses will be spoken aloud, so avoid long lists, 
markdown formatting, or complex technical jargon.""",
        markdown=False,
        add_datetime_to_context=True,
        db=memory_db,
        enable_agentic_memory=True
    )

# =============================================================================
# 3. Helper: Publish Transcript to Chat
# =============================================================================
async def publish_chat(room: rtc.Room, message: str, is_user: bool = False):
    """Publishes a transcription to the LiveKit Chat."""
    if not message or not room.local_participant:
        return

    # Create a standard LiveKit Chat Packet
    # The 'meet' frontend expects a specific JSON structure or plain text
    packet = {
        "message": message,
        "timestamp": int(datetime.now().timestamp() * 1000),
    }
    
    # Topic 'lk-chat-topic' is what the frontend listens to
    await room.local_participant.publish_data(
        payload=json.dumps(packet),
        topic="lk-chat-topic",
        reliable=True
    )
    logger.info(f"Published chat: {message}")

# =============================================================================
# 4. Main Agent Logic
# =============================================================================
class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a helpful voice AI assistant. The user is interacting with you via voice, even if you perceive the conversation as text.
            You eagerly assist users with their questions by providing information from your extensive knowledge.
            Your responses are concise, to the point, and without any complex formatting or punctuation including emojis, asterisks, or other symbols.
            You are curious, friendly, and have a sense of humor.""",
        )

server = AgentServer()

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

server.setup_fnc = prewarm

@server.rtc_session()
async def my_agent(ctx: JobContext):
    ctx.log_context_fields={"room": ctx.room.name}
    logger.info(f"Connecting to room: {ctx.room.name}")
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    logger.info(f"Connected to room {ctx.room.name} with participant {participant.identity}")
    # Initialize the session
    session = AgentSession(
        stt=deepgram.STT(),
        llm=LLMAdapter(
            create_agno_agent(),
            session_id=ctx.room.name,
            user_id=participant.identity
        ),
        tts=deepgram.TTS(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    # --- EVENT LISTENERS FOR TRANSCRIPTION ---
    
    @session.on("user_speech_committed")
    def on_user_speech(msg):
        # msg is the transcription of what the user said
        if msg and hasattr(msg, 'content'):
            asyncio.create_task(publish_chat(ctx.room, msg.content, is_user=True))

    @session.on("agent_speech_committed")
    def on_agent_speech(msg):
        # msg is the response the agent just spoke
        if msg and hasattr(msg, 'content'):
            asyncio.create_task(publish_chat(ctx.room, msg.content, is_user=False))

    # -----------------------------------------

    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: noise_cancellation.BVCTelephony()
                if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                else noise_cancellation.BVC(),
            ),
        ),
    )

    await session.generate_reply(instructions="say hello to the user")

if __name__ == "__main__":
    cli.run_app(server)
