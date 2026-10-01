# Copyright 2025
# Licensed under the Apache License, Version 2.0

"""Agno plugin for LiveKit Agents - wraps Agno Agents as LiveKit LLMs."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from agno.agent import Agent
from agno.run.agent import RunCompletedEvent, RunContentEvent
from livekit.agents import llm
from livekit.agents.llm import ChatContext, ChatRole
from livekit.agents.types import (
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    APIConnectOptions,
    NotGivenOr,
)

from .version import __version__
from .events import EVENT_VERSION, event_to_agent_event, now_ms

__all__ = ["__version__", "LLMAdapter", "AgnoStream"]

logger = logging.getLogger(__name__)
EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


class LLMAdapter(llm.LLM):
    """Wraps an Agno Agent as a LiveKit-compatible LLM."""

    def __init__(
        self,
        agent: Agent,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        on_event: EventCallback | None = None,
    ) -> None:
        super().__init__()
        self._agent = agent
        self._session_id = session_id
        self._user_id = user_id
        self._on_event = on_event
        self._turn = 0
        self._memory_snapshot: tuple[str, ...] | None = None

    def _next_turn(self) -> int:
        self._turn += 1
        return self._turn

    def _publish(self, event: dict[str, Any]) -> None:
        if self._on_event is None:
            return
        task = asyncio.create_task(self._on_event(event))
        task.add_done_callback(self._event_task_done)

    def publish_event(self, event: dict[str, Any]) -> None:
        """Schedule an event without blocking the voice stream."""
        self._publish(event)

    @staticmethod
    def _event_task_done(task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except Exception:
            logger.exception("Agent event publisher failed")

    async def publish_memory_snapshot(self, *, force: bool = False) -> None:
        if self._on_event is None or not hasattr(self._agent, "aget_user_memories"):
            return
        try:
            memories = await self._agent.aget_user_memories(user_id=self._user_id) or []
            values = tuple(
                str(getattr(item, "memory", None) or getattr(item, "content", None) or item)
                for item in memories
            )
            if force or values != self._memory_snapshot:
                self._memory_snapshot = values
                self._publish(
                    {
                        "v": EVENT_VERSION,
                        "type": "memory.updated",
                        "memories": list(values),
                        "at": now_ms(),
                    }
                )
        except Exception:
            logger.exception("Unable to read Agno memories")

    @property
    def model(self) -> str:
        return self._agent.model.id if self._agent.model else "agno"

    @property
    def provider(self) -> str:
        return "agno"

    def chat(
        self,
        *,
        chat_ctx: ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[llm.ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> AgnoStream:
        return AgnoStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
            agent=self._agent,
            session_id=self._session_id,
            user_id=self._user_id,
            on_event=self._publish,
            turn=self._next_turn(),
            on_run_completed=self.publish_memory_snapshot,
        )


class AgnoStream(llm.LLMStream):
    """Streams responses from an Agno Agent."""

    def __init__(
        self,
        llm_adapter: LLMAdapter,
        *,
        chat_ctx: ChatContext,
        tools: list[llm.Tool],
        conn_options: APIConnectOptions,
        agent: Agent,
        session_id: str | None = None,
        user_id: str | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        turn: int = 1,
        on_run_completed: Callable[[], Awaitable[None]] | None = None,
    ):
        super().__init__(
            llm_adapter, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options
        )
        self._agent = agent
        self._session_id = session_id
        self._user_id = user_id
        self._on_event = on_event
        self._turn = turn
        self._on_run_completed = on_run_completed

    async def _run(self) -> None:
        # Convert chat context to the last user message for Agno
        user_input = self._get_user_input()
        if not user_input:
            return

        # stream_events=True: without it Agno's stream carries only content,
        # and the tool events never arrive.
        response_stream = self._agent.arun(
            input=user_input,
            stream=True,
            stream_events=True,
            session_id=self._session_id,
            user_id=self._user_id,
        )

        # Tool calls started but not yet finished. If the stream ends early
        # (the caller interrupts, LiveKit cancels the turn), each is reported
        # as failed, so the browser never shows a spinner forever.
        open_calls: dict[str, tuple[str, float]] = {}
        try:
            async for event in response_stream:
                protocol_event = event_to_agent_event(event, turn=self._turn)
                if protocol_event is not None:
                    if protocol_event["type"] == "tool.started":
                        open_calls[protocol_event["id"]] = (protocol_event["tool"], time.monotonic())
                    else:
                        open_calls.pop(protocol_event["id"], None)
                    if self._on_event is not None:
                        self._on_event(protocol_event)
                chunk = _to_chat_chunk(event)
                if chunk:
                    self._event_ch.send_nowait(chunk)
                if isinstance(event, RunCompletedEvent) and self._on_run_completed is not None:
                    task = asyncio.create_task(self._on_run_completed())
                    task.add_done_callback(LLMAdapter._event_task_done)
        finally:
            if open_calls and self._on_event is not None:
                for call_id, (tool_name, started) in open_calls.items():
                    self._on_event(
                        {
                            "v": EVENT_VERSION,
                            "type": "tool.failed",
                            "id": call_id,
                            "turn": self._turn,
                            "tool": tool_name,
                            "ms": max(0, round((time.monotonic() - started) * 1000)),
                            "error": "interrupted",
                            "at": now_ms(),
                        }
                    )
            close = getattr(response_stream, "aclose", None)
            if close is not None:
                result = close()
                if inspect.isawaitable(result):
                    await result

    def _get_user_input(self) -> str | None:
        """Extract the last user message from chat context."""
        for msg in reversed(self._chat_ctx.items):
            if msg.role == "user":
                content = msg.content
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    # Handle multimodal - extract text parts
                    return " ".join(
                        p.get("text", "") if isinstance(p, dict) else str(p)
                        for p in content
                    )
        return None


def _to_chat_chunk(event: Any) -> llm.ChatChunk | None:
    """Convert Agno event to LiveKit ChatChunk."""
    content = None

    if isinstance(event, RunContentEvent):
        content = event.content
    if content:
        return llm.ChatChunk(
            id="agno",
            delta=llm.ChoiceDelta(role="assistant", content=content),
        )
    return None
