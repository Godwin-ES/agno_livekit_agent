from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

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
from livekit_plugins_agno.events import MAX_FIELD_BYTES, RoomEventPublisher, bounded_value, event_to_agent_event


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


@pytest.mark.parametrize(
    "value",
    [
        ["x" * 10_000 for _ in range(5)],
        {"kind": "search", "results": [{"title": "é" * 10_000, "url": "https://example.com"}]},
        "🌍" * 10_000,
    ],
)
def test_bounded_value_preserves_shape_and_enforces_serialized_byte_limit(value) -> None:
    bounded = bounded_value(value)

    assert len(json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode()) <= MAX_FIELD_BYTES
    if isinstance(value, dict):
        assert bounded["kind"] == "search"
        assert "results" in bounded


class FakeModel:
    id = "fake-model"


class FakeAgent:
    model = FakeModel()

    def __init__(self) -> None:
        self.kwargs = None

    def arun(self, **kwargs):
        self.kwargs = kwargs
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
async def test_adapter_requests_agno_stream_events() -> None:
    agent = FakeAgent()
    chat = ChatContext()
    chat.add_message(role="user", content="Weather?")

    _ = [chunk async for chunk in LLMAdapter(agent).chat(chat_ctx=chat)]

    assert agent.kwargs["stream_events"] is True


@pytest.mark.asyncio
async def test_room_publisher_never_raises_into_voice_pipeline() -> None:
    class BrokenParticipant:
        def publish_data(self, *_args, **_kwargs) -> None:
            raise RuntimeError("room disconnected")

    class Room:
        local_participant = BrokenParticipant()

    await RoomEventPublisher(Room())({"v": 1, "type": "tool.started"})


@pytest.mark.asyncio
async def test_room_publisher_awaits_livekit_publish() -> None:
    participant = type("Participant", (), {"publish_data": AsyncMock()})()
    room = type("Room", (), {"local_participant": participant})()

    await RoomEventPublisher(room)({"v": 1, "type": "tool.started"})

    participant.publish_data.assert_awaited_once()


def test_toolkit_result_shapes_are_normalized_for_cards() -> None:
    wiki = event_to_agent_event(
        ToolCallCompletedEvent(tool=tool_execution(tool_name="search_wikipedia", result="Ada was a mathematician")),
        turn=1,
    )
    stock = event_to_agent_event(
        ToolCallCompletedEvent(tool=tool_execution(tool_name="get_current_stock_price", result="213.40")),
        turn=1,
    )
    article = event_to_agent_event(
        ToolCallCompletedEvent(
            tool=tool_execution(tool_name="read_article", result=json.dumps({"title": "News", "text": "Body"}))
        ),
        turn=1,
    )

    assert wiki["result"]["kind"] == "wiki"
    assert wiki["result"]["article"]["content"] == "Ada was a mathematician"
    assert stock["result"]["data"]["price"] == "213.40"
    assert article["result"]["article"]["content"] == "Body"


@pytest.mark.asyncio
async def test_a_tool_call_cut_off_by_an_interruption_is_reported_as_failed() -> None:
    class InterruptedAgent(FakeAgent):
        def arun(self, **kwargs):
            async def stream():
                yield ToolCallStartedEvent(tool=tool_execution())
                raise asyncio.CancelledError

            return stream()

    events: list[dict] = []

    async def collect(event: dict) -> None:
        events.append(event)

    chat = ChatContext()
    chat.add_message(role="user", content="Weather?")
    # LiveKit's stream wrapper handles the cancellation itself; what matters
    # is that the open call is closed off for the browser.
    try:
        _ = [chunk async for chunk in LLMAdapter(InterruptedAgent(), on_event=collect).chat(chat_ctx=chat)]
    except (asyncio.CancelledError, Exception):
        pass
    await asyncio.sleep(0)

    assert [event["type"] for event in events] == ["tool.started", "tool.failed"]
    assert events[1]["error"] == "interrupted"
    assert events[1]["id"] == events[0]["id"]


def test_notes_updated_event_carries_the_saved_notes() -> None:
    from livekit_plugins_agno.events import notes_updated_event

    event = notes_updated_event(["Email Sam", "Buy milk"])

    assert event | {"at": 0} == {"v": 1, "type": "notes.updated", "notes": ["Email Sam", "Buy milk"], "at": 0}
