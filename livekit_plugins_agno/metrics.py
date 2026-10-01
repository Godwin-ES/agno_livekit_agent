"""Fold LiveKit component timings into one browser-facing turn event."""

from __future__ import annotations

from typing import Any

from livekit.agents import metrics

from .events import EVENT_VERSION, now_ms


def _ms(seconds: float | None) -> int | None:
    """Milliseconds, or None when LiveKit reported no real measurement (0 or missing)."""
    if seconds is None or seconds <= 0:
        return None
    return round(seconds * 1000)


class TurnMetricsCollector:
    """One ``turn.metrics`` event per reply, from LiveKit's per-component metrics.

    A field is ``None`` when it wasn't measured, never a made-up number.
    Streaming STT reports ``duration=0``, so its latency comes from the
    end-of-utterance metrics' ``transcription_delay`` when those arrive. A
    typed message has no STT or end-of-utterance at all. End to end (the user
    stops speaking to the first audio of the reply) is end-of-utterance delay
    plus LLM first token plus TTS first byte, so it's only given when all
    three were measured.
    """

    def __init__(self) -> None:
        self._turn = 0
        self._tools = 0
        self._stt: metrics.STTMetrics | None = None
        self._eou: metrics.EOUMetrics | None = None
        self._llm: metrics.LLMMetrics | None = None
        self._turn_open = False

    def _start_turn(self) -> None:
        if not self._turn_open:
            self._turn += 1
            self._tools = 0
            self._turn_open = True

    def observe_agent_event(self, event: dict[str, Any]) -> None:
        if event.get("type") == "tool.started":
            self._start_turn()
            self._tools += 1

    def observe(self, value: metrics.AgentMetrics) -> dict[str, Any] | None:
        if isinstance(value, metrics.STTMetrics):
            self._start_turn()
            self._stt = value
        elif isinstance(value, metrics.EOUMetrics):
            self._start_turn()
            self._eou = value
        elif isinstance(value, metrics.LLMMetrics):
            self._start_turn()
            self._llm = value
        elif isinstance(value, metrics.TTSMetrics) and self._llm is not None:
            stt_ms = _ms(self._stt.duration) if self._stt else None
            if stt_ms is None and self._eou is not None:
                stt_ms = _ms(self._eou.transcription_delay)
            llm_ms = _ms(self._llm.ttft)
            tts_ms = _ms(value.ttfb)
            eou_ms = _ms(self._eou.end_of_utterance_delay) if self._eou else None
            e2e_ms = eou_ms + llm_ms + tts_ms if None not in (eou_ms, llm_ms, tts_ms) else None
            event = {
                "v": EVENT_VERSION,
                "type": "turn.metrics",
                "turn": self._turn,
                "stt_ms": stt_ms,
                "llm_ttft_ms": llm_ms,
                "tts_ttfb_ms": tts_ms,
                "e2e_ms": e2e_ms,
                "tools": self._tools,
                "at": now_ms(),
            }
            self._stt = self._eou = self._llm = None
            self._turn_open = False
            return event
        return None
