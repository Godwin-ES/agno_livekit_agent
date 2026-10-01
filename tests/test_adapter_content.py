from __future__ import annotations

from agno.run.agent import ReasoningStepEvent, RunCompletedEvent, RunContentEvent

from livekit_plugins_agno.agno import _to_chat_chunk


def test_only_run_content_becomes_speech() -> None:
    content = _to_chat_chunk(RunContentEvent(content="Hello"))
    completed = _to_chat_chunk(RunCompletedEvent(content="Hello"))
    reasoning = _to_chat_chunk(ReasoningStepEvent(content="private chain", reasoning_content="private chain"))

    assert content is not None
    assert content.delta.content == "Hello"
    assert completed is None
    assert reasoning is None
