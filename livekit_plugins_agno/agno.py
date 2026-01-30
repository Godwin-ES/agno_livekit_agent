# Copyright 2025
# Licensed under the Apache License, Version 2.0

"""Agno plugin for LiveKit Agents - wraps Agno Agents as LiveKit LLMs."""

from __future__ import annotations

from typing import Any

from agno.agent import Agent
from agno.run.agent import RunContentEvent, RunOutput
from livekit.agents import llm
from livekit.agents.llm import ChatContext, ChatRole
from livekit.agents.types import (
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    APIConnectOptions,
    NotGivenOr,
)

from .version import __version__

__all__ = ["__version__", "LLMAdapter", "AgnoStream"]


class LLMAdapter(llm.LLM):
    """Wraps an Agno Agent as a LiveKit-compatible LLM."""

    def __init__(
        self,
        agent: Agent,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        super().__init__()
        self._agent = agent
        self._session_id = session_id
        self._user_id = user_id

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
    ):
        super().__init__(
            llm_adapter, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options
        )
        self._agent = agent
        self._session_id = session_id
        self._user_id = user_id

    async def _run(self) -> None:
        # Convert chat context to the last user message for Agno
        user_input = self._get_user_input()
        if not user_input:
            return

        # Run agent with streaming
        response_stream = self._agent.arun(
            input=user_input,
            stream=True,
            session_id=self._session_id,
            user_id=self._user_id,
        )

        async for event in response_stream:
            chunk = _to_chat_chunk(event)
            if chunk:
                self._event_ch.send_nowait(chunk)

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
    elif isinstance(event, RunOutput) and event.content:
        content = (
            str(event.content) if not isinstance(event.content, str) else event.content
        )
    elif hasattr(event, "content") and event.content:
        content = str(event.content)

    if content:
        return llm.ChatChunk(
            id="agno",
            delta=llm.ChoiceDelta(role="assistant", content=content),
        )
    return None
