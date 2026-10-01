from __future__ import annotations

from unittest.mock import patch

from agno.tools.function import Function

from agent.build import create_agno_agent
from tools import ALL_TOOLS


def test_model_facing_tools_have_explicit_schemas_without_injected_clients() -> None:
    functions = {tool.name: tool for tool in ALL_TOOLS if isinstance(tool, Function)}

    assert functions["get_weather"].parameters["properties"]["units"] == {
        "type": "string",
        "enum": ["celsius", "fahrenheit"],
    }
    assert all("client" not in tool.parameters.get("properties", {}) for tool in functions.values())


def test_agent_enables_bounded_history(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test")
    with patch("agent.build.Agent") as agent_class:
        create_agno_agent("visitor", db_path=tmp_path / "memory.db")

    kwargs = agent_class.call_args.kwargs
    assert kwargs["add_history_to_context"] is True
    assert 1 <= kwargs["num_history_runs"] <= 10
