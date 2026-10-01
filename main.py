"""LiveKit worker wiring for the EchoRun Agno voice agent."""

from __future__ import annotations

import logging
import os

from dotenv import find_dotenv, load_dotenv
from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli, room_io
from livekit.plugins import deepgram, noise_cancellation, silero

from agent.build import create_agno_agent
from agent.config import env_flag, participant_user_id
from livekit_plugins_agno import LLMAdapter

load_dotenv(find_dotenv())

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AGENT_NAME = os.getenv("AGENT_NAME", "echorun-agent")


class Assistant(Agent):
    """LiveKit shell; the sole behavioral prompt belongs to the Agno agent."""

    def __init__(self) -> None:
        super().__init__(instructions="")


server = AgentServer(load_threshold=2.0)


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name=AGENT_NAME)
async def voice_agent(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    user_id = participant_user_id(participant)
    logger.info("Participant connected", extra={"room": ctx.room.name, "user_id": user_id})

    agno_agent = create_agno_agent(user_id)
    session = AgentSession(
        stt=deepgram.STT(),
        llm=LLMAdapter(agno_agent, session_id=ctx.room.name, user_id=user_id),
        tts=deepgram.TTS(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=env_flag("PREEMPTIVE_GENERATION", default=False),
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
    session.say("Hi, I'm EchoRun. Ask me to look something up, calculate, or remember a note.")


if __name__ == "__main__":
    cli.run_app(server)
