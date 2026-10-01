"""Versioned events shared with the browser over LiveKit data packets."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Literal, TypedDict

from agno.run.agent import ToolCallCompletedEvent, ToolCallErrorEvent, ToolCallStartedEvent

EVENT_VERSION = 1
MAX_FIELD_BYTES = 4096
logger = logging.getLogger(__name__)


class ToolStartedEvent(TypedDict):
    v: Literal[1]
    type: Literal["tool.started"]
    id: str
    turn: int
    tool: str
    args: Any
    at: int


class ToolCompletedEvent(TypedDict):
    v: Literal[1]
    type: Literal["tool.completed"]
    id: str
    turn: int
    tool: str
    ms: int
    result: Any
    at: int


class ToolFailedEvent(TypedDict):
    v: Literal[1]
    type: Literal["tool.failed"]
    id: str
    turn: int
    tool: str
    ms: int
    error: str
    at: int


AgentEvent = ToolStartedEvent | ToolCompletedEvent | ToolFailedEvent | dict[str, Any]


class RoomEventPublisher:
    """Publish protocol events reliably without endangering the audio path."""

    def __init__(self, room: Any) -> None:
        self._room = room

    async def __call__(self, event: dict[str, Any]) -> None:
        try:
            payload = json.dumps(event, default=str, separators=(",", ":"))
            self._room.local_participant.publish_data(
                payload,
                reliable=True,
                topic="agent.events",
            )
        except Exception:
            logger.exception("Unable to publish agent event")


def now_ms() -> int:
    return int(time.time() * 1000)


def bounded_value(value: Any) -> Any:
    """Keep an args/result field JSON-safe and no larger than four KiB."""
    try:
        encoded = json.dumps(value, default=str, separators=(",", ":")).encode()
    except (TypeError, ValueError):
        value = str(value)
        encoded = json.dumps(value).encode()
    if len(encoded) <= MAX_FIELD_BYTES:
        return value
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        if "kind" in value:
            compact["kind"] = value["kind"]
        compact["truncated"] = True
        for key, item in value.items():
            if key == "kind":
                continue
            candidate = item[:3000] + "…" if isinstance(item, str) else "[truncated]"
            trial = {**compact, str(key): candidate}
            if len(json.dumps(trial, default=str, separators=(",", ":")).encode()) <= MAX_FIELD_BYTES:
                compact[str(key)] = candidate
                break
        return compact
    if isinstance(value, list):
        return {"truncated": True, "items": value[:3]}
    return str(value)[: MAX_FIELD_BYTES - 32] + "…"


def _duration_ms(tool: Any) -> int:
    duration = getattr(getattr(tool, "metrics", None), "duration", None)
    return max(0, round(float(duration or 0) * 1000))


def _structured_result(tool_name: str, raw: Any) -> Any:
    value = raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            value = raw
    if isinstance(value, dict) and "kind" in value:
        return value

    lower = tool_name.casefold()
    if "search" in lower or "news" in lower:
        return {"kind": "search", "results": value, "say": "I found the latest results."}
    if "article" in lower:
        return {"kind": "article", "article": value, "say": "I read the article."}
    if "wikipedia" in lower:
        return {"kind": "wiki", "article": value, "say": "I found the background information."}
    if "stock" in lower or "company" in lower:
        return {"kind": "stock", "data": value, "say": "I found the market data."}
    if "hacker" in lower:
        return {"kind": "list", "items": value, "say": "I found the top stories."}
    return {"kind": "generic", "value": value, "say": "The tool finished."}


def event_to_agent_event(event: Any, *, turn: int) -> AgentEvent | None:
    tool = getattr(event, "tool", None)
    if tool is None:
        return None
    common = {
        "v": EVENT_VERSION,
        "id": str(tool.tool_call_id or f"{tool.tool_name}-{turn}"),
        "turn": turn,
        "tool": str(tool.tool_name or "tool"),
        "at": now_ms(),
    }
    if isinstance(event, ToolCallStartedEvent):
        return {**common, "type": "tool.started", "args": bounded_value(tool.tool_args or {})}
    if isinstance(event, ToolCallCompletedEvent):
        result = _structured_result(common["tool"], tool.result if tool.result is not None else event.content)
        return {
            **common,
            "type": "tool.completed",
            "ms": _duration_ms(tool),
            "result": bounded_value(result),
        }
    if isinstance(event, ToolCallErrorEvent):
        return {
            **common,
            "type": "tool.failed",
            "ms": _duration_ms(tool),
            "error": str(event.error or "Tool call failed")[:1000],
        }
    return None
