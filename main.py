"""LiveKit worker wiring for the EchoRun Agno voice agent."""

from __future__ import annotations

import logging
import os

from dotenv import find_dotenv, load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    cli,
    room_io,
)
from livekit.plugins import deepgram, noise_cancellation, silero

from agent.build import create_agno_agent
from agent.config import env_flag, participant_user_id
from tools.notes import NotesStore
from livekit_plugins_agno import LLMAdapter
from livekit_plugins_agno.events import RoomEventPublisher, notes_updated_event
from livekit_plugins_agno.metrics import TurnMetricsCollector

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
    publisher = RoomEventPublisher(ctx.room)
    metrics_collector = TurnMetricsCollector()

    async def publish_agent_event(event: dict) -> None:
        metrics_collector.observe_agent_event(event)
        await publisher(event)

    adapter = LLMAdapter(
        agno_agent,
        session_id=ctx.room.name,
        user_id=user_id,
        on_event=publish_agent_event,
    )
    session = AgentSession(
        stt=deepgram.STT(),
        llm=adapter,
        tts=deepgram.TTS(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=env_flag("PREEMPTIVE_GENERATION", default=False),
    )

    @session.on("metrics_collected")
    def on_metrics_collected(event: MetricsCollectedEvent) -> None:
        if summary := metrics_collector.observe(event.metrics):
            adapter.publish_event(summary)

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
    await adapter.publish_memory_snapshot(force=True)
    try:
        adapter.publish_event(notes_updated_event(NotesStore().list(user_id)))
    except Exception:
        logger.exception("Unable to load saved notes")
    session.say("Hi, I'm EchoRun. Ask me to look something up, calculate, or remember a note.")


if __name__ == "__main__":
    cli.run_app(server)
