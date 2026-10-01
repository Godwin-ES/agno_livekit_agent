from __future__ import annotations

import asyncio
import json

import pytest
from agno.models.metrics import Metrics
from agno.models.response import ToolExecution
from agno.run.agent import (
    RunCompletedEvent,
    RunContentEvent,
    ToolCallCompletedEvent,
    ToolCallErrorEvent,
    ToolCallStartedEvent,
)
from livekit.agents.llm import ChatContext

from livekit_plugins_agno.agno import LLMAdapter
from livekit_plugins_agno.events import RoomEventPublisher, event_to_agent_event


def tool_execution(**overrides) -> ToolExecution:
    values = {
        "tool_call_id": "call_abc",
        "tool_name": "get_weather",
        "tool_args": {"city": "Lagos"},
        "result": json.dumps({"kind": "weather", "temperature": 29}),
        "metrics": Metrics(duration=0.412),
    }
    values.update(overrides)
    return ToolExecution(**values)


def test_tool_events_map_to_versioned_protocol() -> None:
    started = event_to_agent_event(ToolCallStartedEvent(tool=tool_execution()), turn=3)
    completed = event_to_agent_event(ToolCallCompletedEvent(tool=tool_execution()), turn=3)
    failed = event_to_agent_event(
        ToolCallErrorEvent(tool=tool_execution(), error="timed out"), turn=3
    )

    assert started is not None
    assert started | {"at": 0} == {
        "v": 1,
        "type": "tool.started",
        "id": "call_abc",
        "turn": 3,
        "tool": "get_weather",
        "args": {"city": "Lagos"},
        "at": 0,
    }
    assert completed is not None
    assert completed["type"] == "tool.completed"
    assert completed["ms"] == 412
    assert completed["result"] == {"kind": "weather", "temperature": 29}
    assert failed is not None
    assert failed["type"] == "tool.failed"
    assert failed["error"] == "timed out"


def test_protocol_truncates_large_args_and_results() -> None:
    huge = "x" * 10_000
    started = event_to_agent_event(
        ToolCallStartedEvent(tool=tool_execution(tool_args={"query": huge})), turn=1
    )
    completed = event_to_agent_event(
        ToolCallCompletedEvent(tool=tool_execution(result=json.dumps({"kind": "search", "text": huge}))),
        turn=1,
    )

    assert started is not None and completed is not None
    assert len(json.dumps(started["args"]).encode()) <= 4096
    assert len(json.dumps(completed["result"]).encode()) <= 4096


class FakeModel:
    id = "fake-model"


class FakeAgent:
    model = FakeModel()

    def arun(self, **_kwargs):
        async def stream():
            yield ToolCallStartedEvent(tool=tool_execution())
            yield RunContentEvent(content="It is warm")
            yield RunCompletedEvent(content="It is warm")

        return stream()


@pytest.mark.asyncio
async def test_raising_event_callback_does_not_break_speech() -> None:
    callback_called = asyncio.Event()

    async def broken_callback(_event) -> None:
        callback_called.set()
        raise RuntimeError("publisher unavailable")

    chat = ChatContext()
    chat.add_message(role="user", content="Weather?")
    stream = LLMAdapter(FakeAgent(), on_event=broken_callback).chat(chat_ctx=chat)

    chunks = [chunk async for chunk in stream]
    await asyncio.wait_for(callback_called.wait(), timeout=1)
    await asyncio.sleep(0)

    assert [chunk.delta.content for chunk in chunks] == ["It is warm"]


@pytest.mark.asyncio
async def test_room_publisher_never_raises_into_voice_pipeline() -> None:
    class BrokenParticipant:
        def publish_data(self, *_args, **_kwargs) -> None:
            raise RuntimeError("room disconnected")

    class Room:
        local_participant = BrokenParticipant()

    await RoomEventPublisher(Room())({"v": 1, "type": "tool.started"})
