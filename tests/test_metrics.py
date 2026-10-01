from __future__ import annotations

from livekit.agents import metrics

from livekit_plugins_agno.metrics import TurnMetricsCollector


def test_metrics_collector_emits_one_complete_turn() -> None:
    collector = TurnMetricsCollector()
    assert collector.observe(
        metrics.STTMetrics(
            label="deepgram",
            request_id="stt",
            timestamp=100.0,
            duration=0.18,
            audio_duration=2.0,
            streamed=True,
        )
    ) is None
    collector.observe_agent_event({"type": "tool.started", "turn": 1})
    assert collector.observe(
        metrics.LLMMetrics(
            label="agno",
            request_id="llm",
            timestamp=100.2,
            duration=0.8,
            ttft=0.64,
            cancelled=False,
            completion_tokens=10,
            prompt_tokens=20,
            prompt_cached_tokens=0,
            total_tokens=30,
            tokens_per_second=20,
        )
    ) is None
    event = collector.observe(
        metrics.TTSMetrics(
            label="deepgram",
            request_id="tts",
            timestamp=101.1,
            ttfb=0.21,
            duration=0.5,
            audio_duration=1.2,
            cancelled=False,
            characters_count=20,
            streamed=True,
        )
    )

    assert event is not None
    assert event | {"at": 0} == {
        "v": 1,
        "type": "turn.metrics",
        "turn": 1,
        "stt_ms": 180,
        "llm_ttft_ms": 640,
        "tts_ttfb_ms": 210,
        "e2e_ms": 1310,
        "tools": 1,
        "at": 0,
    }
