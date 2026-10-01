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
            payload = json.dumps(event, default=str, ensure_ascii=False, separators=(",", ":"))
            # publish_data is a coroutine: without the await nothing is sent.
            await self._room.local_participant.publish_data(
                payload,
                reliable=True,
                topic="agent.events",
            )
        except Exception:
            logger.exception("Unable to publish agent event")


def now_ms() -> int:
    return int(time.time() * 1000)


def notes_updated_event(notes: list[str]) -> dict[str, Any]:
    """The user's saved notes, sent on connect so a returning user sees them at once."""
    return {"v": EVENT_VERSION, "type": "notes.updated", "notes": bounded_value(list(notes)), "at": now_ms()}


def _size(value: Any) -> int:
    # ASCII-escaped JSON is never shorter than UTF-8 JSON, so a value that
    # fits here fits however the payload is encoded.
    return len(json.dumps(value, default=str, separators=(",", ":")).encode())


def _jsonable(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return str(value)


def _shrink(value: Any, max_chars: int, max_items: int, depth: int = 0) -> Any:
    if isinstance(value, str):
        return value if len(value) <= max_chars else value[:max_chars] + "…"
    if depth >= 6:
        return "…" if isinstance(value, (dict, list)) else value
    if isinstance(value, list):
        return [_shrink(item, max_chars, max_items, depth + 1) for item in value[:max_items]]
    if isinstance(value, dict):
        return {str(k): _shrink(v, max_chars, max_items, depth + 1) for k, v in list(value.items())[: max_items * 4]}
    return value


# Each step keeps less of every string and list, until the value fits.
_SHRINK_STEPS = [(2000, 10), (1000, 8), (500, 5), (240, 4), (120, 3), (60, 2), (24, 1)]


def bounded_value(value: Any) -> Any:
    """Keep an args/result field JSON-safe and no larger than four KiB when serialized.

    Long strings and lists are cut progressively while nested structure
    (a search result's titles and URLs, a card's ``kind``) is kept, so the
    browser can still render the card from a trimmed result.
    """
    value = _jsonable(value)
    if _size(value) <= MAX_FIELD_BYTES:
        return value
    for max_chars, max_items in _SHRINK_STEPS:
        candidate = _shrink(value, max_chars, max_items)
        if isinstance(candidate, dict):
            candidate = {**candidate, "truncated": True}
        if _size(candidate) <= MAX_FIELD_BYTES:
            return candidate
    if isinstance(value, dict):
        kind = value.get("kind")
        return {"kind": kind, "truncated": True} if isinstance(kind, str) and len(kind) < 64 else {"truncated": True}
    if isinstance(value, list):
        return []
    text = str(value)
    # Binary-search the longest prefix whose escaped JSON fits.
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if _size(text[:middle] + "…") <= MAX_FIELD_BYTES:
            low = middle
        else:
            high = middle - 1
    return text[:low] + "…"


def _duration_ms(tool: Any) -> int:
    duration = getattr(getattr(tool, "metrics", None), "duration", None)
    return max(0, round(float(duration or 0) * 1000))


def _parse(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw
    return raw


def _article(value: Any) -> dict[str, Any]:
    """The shape ArticleCard reads: title, content, url."""
    if isinstance(value, list):
        value = value[0] if value else {}
    if not isinstance(value, dict):
        return {"content": str(value)}
    article = {**value}
    if "content" not in article and isinstance(article.get("text"), str):
        article["content"] = article.pop("text")
    if "title" not in article and isinstance(article.get("name"), str):
        article["title"] = article["name"]
    return article


def _structured_result(tool_name: str, raw: Any, args: Any = None) -> Any:
    """Turn a tool's raw result into the shape its frontend card expects."""
    value = _parse(raw)
    if isinstance(value, dict) and "kind" in value:
        return value
    args = args if isinstance(args, dict) else {}

    lower = tool_name.casefold()
    # Wikipedia first: "search_wikipedia" would otherwise match "search".
    if "wikipedia" in lower:
        return {"kind": "wiki", "article": _article(value), "say": "I found the background information."}
    if "article" in lower:
        return {"kind": "article", "article": _article(value), "say": "I read the article."}
    if "stock_price" in lower:
        # The raw string, not the parsed number: "213.40" must not become 213.4.
        data = value if isinstance(value, dict) else {"price": str(raw).strip()}
        return {"kind": "stock", "data": {**data, "symbol": str(args.get("symbol", "")).upper()}, "say": "I found the market data."}
    if "stock" in lower or "company" in lower:
        data = value if isinstance(value, dict) else {"value": value}
        return {"kind": "stock", "data": data, "say": "I found the market data."}
    if "search" in lower or "news" in lower:
        return {"kind": "search", "results": value, "say": "I found the latest results."}
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
        result = _structured_result(
            common["tool"], tool.result if tool.result is not None else event.content, tool.tool_args
        )
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
