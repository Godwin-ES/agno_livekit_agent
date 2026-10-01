"""Currency conversion through the free Frankfurter API."""

from __future__ import annotations

from typing import Any

import httpx

from .http import request_json

FRANKFURTER_URL = "https://api.frankfurter.app/latest"


async def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Use when the user asks to convert money between supported currencies."""
    source = from_currency.strip().upper()
    target = to_currency.strip().upper()
    try:
        numeric_amount = float(amount)
        if numeric_amount < 0 or not source or not target:
            raise ValueError
        if source == target:
            converted = numeric_amount
            payload = {"date": None}
        else:
            payload = await request_json(
                FRANKFURTER_URL,
                params={"amount": numeric_amount, "from": source, "to": target},
                client=client,
            )
            converted = float(payload["rates"][target])
        rounded = round(converted, 2)
        return {
            "kind": "currency",
            "say": f"{numeric_amount:g} {source} is about {rounded:g} {target}.",
            "amount": numeric_amount,
            "from": source,
            "to": target,
            "converted": rounded,
            "rate": round(converted / numeric_amount, 6) if numeric_amount else 0,
            "date": payload.get("date"),
        }
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 400:
            return {"kind": "error", "say": f"The free exchange service doesn't support {target}."}
        return {"kind": "error", "say": "I couldn't reach the exchange service right now."}
    except (KeyError, TypeError, ValueError, httpx.HTTPError):
        return {"kind": "error", "say": "I couldn't convert those currencies right now."}
