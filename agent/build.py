"""Construct the Agno agent and its deliberately limited toolset."""

from __future__ import annotations

import os
from pathlib import Path

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIChat
from tools import ALL_TOOLS
from tools.external import toolkit_functions
from tools.notes import NotesStore, create_note_tools, note_functions

from .prompt import VOICE_AGENT_PROMPT


def create_agno_agent(user_id: str, *, db_path: str | Path = "data/memory.db") -> Agent:
    """Create one session-safe Agno agent for a stable visitor identity."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    note_tools = create_note_tools(user_id, NotesStore(path))
    tools = [*ALL_TOOLS, *note_functions(note_tools), *toolkit_functions()]
    return Agent(
        name="EchoRun",
        model=OpenAIChat(
            id=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
            api_key=os.environ["GROQ_API_KEY"],
            base_url=os.getenv("GROQ_URL", "https://api.groq.com/openai/v1"),
        ),
        tools=tools,
        instructions=VOICE_AGENT_PROMPT,
        markdown=False,
        add_datetime_to_context=True,
        db=SqliteDb(db_file=str(path)),
        enable_agentic_memory=True,
        add_memories_to_context=True,
        # Agno is handed only the latest user message each turn (the adapter
        # doesn't replay LiveKit's chat context), so the conversation so far
        # comes from its own session history: the last few runs, enough for
        # "tell me more about the first one" without growing every prompt.
        add_history_to_context=True,
        num_history_runs=5,
        user_id=user_id,
    )
