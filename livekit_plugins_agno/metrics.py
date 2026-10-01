"""Fold LiveKit component timings into one browser-facing turn event."""

from __future__ import annotations

from typing import Any

from livekit.agents import metrics

from .events import EVENT_VERSION, now_ms


class TurnMetricsCollector:
    def __init__(self) -> None:
        self._turn = 0
        self._tools = 0
        self._stt: metrics.STTMetrics | None = None
        self._llm: metrics.LLMMetrics | None = None

    def observe_agent_event(self, event: dict[str, Any]) -> None:
        if event.get("type") == "tool.started":
            self._turn = int(event.get("turn", self._turn or 1))
            self._tools += 1

    def observe(self, value: metrics.AgentMetrics) -> dict[str, Any] | None:
        if isinstance(value, metrics.STTMetrics):
            self._turn += 1
            self._tools = 0
            self._stt = value
            self._llm = None
        elif isinstance(value, metrics.LLMMetrics):
            self._llm = value
        elif isinstance(value, metrics.TTSMetrics) and self._stt and self._llm:
            event = {
                "v": EVENT_VERSION,
                "type": "turn.metrics",
                "turn": self._turn,
                "stt_ms": round(self._stt.duration * 1000),
                "llm_ttft_ms": round(self._llm.ttft * 1000),
                "tts_ttfb_ms": round(value.ttfb * 1000),
                "e2e_ms": max(0, round((value.timestamp + value.ttfb - self._stt.timestamp) * 1000)),
                "tools": self._tools,
                "at": now_ms(),
            }
            self._stt = None
            self._llm = None
            return event
        return None
