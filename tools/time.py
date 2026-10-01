"""Local time lookup backed by Open-Meteo geocoding and zoneinfo."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .geocoding import geocode


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def get_time(place: str, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """Use when the user asks for the current local time in a city or place."""
    try:
        location = await geocode(place, client=client)
        if not location:
            return {"kind": "error", "say": f"I couldn't find a place called {place}."}
        timezone = str(location["timezone"])
        local = _utc_now().astimezone(ZoneInfo(timezone))
        display_time = local.strftime("%I:%M %p").lstrip("0")
        offset = local.strftime("%z")
        offset = f"{offset[:3]}:{offset[3:]}"
        name = str(location["name"])
        return {
            "kind": "time",
            "say": f"It's {display_time} in {name}.",
            "place": ", ".join(filter(None, [name, location.get("country")])),
            "time": display_time,
            "timezone": timezone,
            "utc_offset": offset,
        }
    except (KeyError, ZoneInfoNotFoundError):
        return {"kind": "error", "say": f"I couldn't determine the local time in {place}."}
    except Exception:
        return {"kind": "error", "say": "I couldn't reach the time service right now."}
