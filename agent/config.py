"""Small configuration helpers kept independent from LiveKit wiring."""

from __future__ import annotations

import os
from typing import Any


def env_flag(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def participant_user_id(participant: Any) -> str:
    attributes = getattr(participant, "attributes", {}) or {}
    return str(attributes.get("visitor_id") or participant.identity)
