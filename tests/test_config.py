from __future__ import annotations

from agent.config import env_flag, participant_user_id


class Participant:
    identity = "Guest__temporary"
    attributes = {"visitor_id": "stable-visitor-123"}


def test_participant_user_id_prefers_stable_attribute() -> None:
    assert participant_user_id(Participant()) == "stable-visitor-123"


def test_participant_user_id_falls_back_to_identity() -> None:
    participant = Participant()
    participant.attributes = {}

    assert participant_user_id(participant) == "Guest__temporary"


def test_env_flag_defaults_and_parses_common_values(monkeypatch) -> None:
    monkeypatch.delenv("FEATURE_FLAG", raising=False)
    assert env_flag("FEATURE_FLAG") is False
    monkeypatch.setenv("FEATURE_FLAG", "YES")
    assert env_flag("FEATURE_FLAG") is True
