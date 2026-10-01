"""Model-facing tool definitions with explicit JSON schemas.

Agno can infer a schema from a function's signature, but the inferred one
leaks implementation details: the HTTP client that tests inject shows up as
an argument the model can fill in, and a ``Literal`` type isn't always turned
into a string enum. Every tool the model sees is declared here by hand
instead, with ``skip_entrypoint_processing`` so Agno uses the schema as is.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agno.tools.function import Function


def string(description: str, **extra: Any) -> dict[str, Any]:
    return {"type": "string", "description": description, **extra}


def number(description: str, **extra: Any) -> dict[str, Any]:
    return {"type": "number", "description": description, **extra}


def explicit_tool(
    name: str,
    description: str,
    entrypoint: Callable[..., Awaitable[Any]],
    properties: dict[str, dict[str, Any]] | None = None,
    required: list[str] | None = None,
) -> Function:
    return Function(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": properties or {},
            "required": required or [],
            "additionalProperties": False,
        },
        entrypoint=entrypoint,
        skip_entrypoint_processing=True,
    )
