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
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

import logging
from typing import Annotated

from agno.agent import Agent as AgnoAgent
from agno.models.openai import OpenAIChat
from agno.db.sqlite import SqliteDb
from agno.tools import tool
from dotenv import load_dotenv
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    llm,
)
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
    inference,
    room_io,
)
from livekit.plugins import noise_cancellation, silero
#from livekit.plugins.turn_detector.multilingual import MultilingualModel
# from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import deepgram, silero

from livekit_plugins_agno import LLMAdapter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Define tools for the Agno agent
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
# Create the Agno agent
# =============================================================================
memory_db = SqliteDb(db_file="memory.db")

def create_agno_agent() -> AgnoAgent:
    """Create and configure the Agno agent with tools and instructions."""

    agent = AgnoAgent(
        # Use OpenAI's GPT-4o-mini for fast responses
        model=OpenAIChat(id=os.environ["GROQ_MODEL"], api_key=os.environ["GROQ_API_KEY"], base_url=os.environ["GROQ_URL"]),
        # Add tools for the agent to use
        tools=[get_current_time, get_weather, calculate],
        # System instructions for the voice assistant
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
        # Enable markdown for text display (TTS will handle the actual speech)
        markdown=False,
        # Keep responses focused
        add_datetime_to_context=True,
        db=memory_db,
        enable_agentic_memory=True
    )

    return agent

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a helpful voice AI assistant. The user is interacting with you via voice, even if you perceive the conversation as text.
            You eagerly assist users with their questions by providing information from your extensive knowledge.
            Your responses are concise, to the point, and without any complex formatting or punctuation including emojis, asterisks, or other symbols.
            You are curious, friendly, and have a sense of humor.""",
        )

server = AgentServer(load_threshold=2.0)

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

server.setup_fnc = prewarm

@server.rtc_session()
async def my_agent(ctx: JobContext):
    ctx.log_context_fields={"room": ctx.room.name}
    logger.info(f"Connecting to room: {ctx.room.name}")
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    print(f"Connected to room {ctx.room.name} with participant {participant.identity}")
    session = AgentSession(
        stt=deepgram.STT(),
        llm=LLMAdapter(
            create_agno_agent(),
            session_id=ctx.room.name,
            user_id=participant.identity
        ),
        tts=deepgram.TTS(),
        #turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

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
    # Run the LiveKit agent
    cli.run_app(server)
