from __future__ import annotations

from livekit.agents import metrics

from livekit_plugins_agno.metrics import TurnMetricsCollector


def test_metrics_collector_does_not_invent_unavailable_stt_or_e2e_latency() -> None:
    collector = TurnMetricsCollector()
    assert collector.observe(
        metrics.STTMetrics(
            label="deepgram",
            request_id="stt",
            timestamp=100.0,
            duration=0,
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
        "stt_ms": None,
        "llm_ttft_ms": 640,
        "tts_ttfb_ms": 210,
        "e2e_ms": None,
        "tools": 1,
        "at": 0,
    }


def test_metrics_collector_supports_typed_turn_without_stt() -> None:
    collector = TurnMetricsCollector()
    collector.observe(
        metrics.LLMMetrics(
            label="agno", request_id="typed", timestamp=100.2, duration=0.8, ttft=0.2,
            cancelled=False, completion_tokens=1, prompt_tokens=1, prompt_cached_tokens=0,
            total_tokens=2, tokens_per_second=10,
        )
    )
    event = collector.observe(
        metrics.TTSMetrics(
            label="deepgram", request_id="typed-tts", timestamp=101, ttfb=0.1,
            duration=0.4, audio_duration=1, cancelled=False, characters_count=10, streamed=True,
        )
    )

    assert event is not None
    assert event["turn"] == 1
    assert event["stt_ms"] is None
    assert event["e2e_ms"] is None


def test_end_to_end_latency_comes_from_end_of_utterance_llm_and_tts() -> None:
    collector = TurnMetricsCollector()
    collector.observe(metrics.STTMetrics(label="deepgram", request_id="s", timestamp=100.0, duration=0, audio_duration=2.0, streamed=True))
    collector.observe(metrics.EOUMetrics(timestamp=100.1, end_of_utterance_delay=0.5, transcription_delay=0.15, on_user_turn_completed_delay=0))
    collector.observe(
        metrics.LLMMetrics(label="agno", request_id="l", timestamp=100.2, duration=0.8, ttft=0.64, cancelled=False,
                           completion_tokens=1, prompt_tokens=1, prompt_cached_tokens=0, total_tokens=2, tokens_per_second=10)
    )
    event = collector.observe(
        metrics.TTSMetrics(label="deepgram", request_id="t", timestamp=101, ttfb=0.21, duration=0.4, audio_duration=1,
                           cancelled=False, characters_count=10, streamed=True)
    )

    assert event is not None
    assert event["stt_ms"] == 150
    assert event["e2e_ms"] == 500 + 640 + 210
