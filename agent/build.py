"""Construct the Agno agent and its deliberately limited toolset."""

from __future__ import annotations

import os
from pathlib import Path

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIChat
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.hackernews import HackerNewsTools
from agno.tools.newspaper4k import Newspaper4kTools
from agno.tools.wikipedia import WikipediaTools
from agno.tools.yfinance import YFinanceTools

from tools import ALL_TOOLS
from tools.notes import NotesStore, create_note_tools

from .prompt import VOICE_AGENT_PROMPT


def create_agno_agent(user_id: str, *, db_path: str | Path = "data/memory.db") -> Agent:
    """Create one session-safe Agno agent for a stable visitor identity."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    note_tools = create_note_tools(user_id, NotesStore(path))
    tools = [
        *ALL_TOOLS,
        note_tools.add_note,
        note_tools.list_notes,
        note_tools.clear_notes,
        DuckDuckGoTools(fixed_max_results=5, timeout=4),
        Newspaper4kTools(article_length=6000),
        WikipediaTools(),
        YFinanceTools(include_tools=["get_current_stock_price", "get_company_info"]),
        HackerNewsTools(enable_get_top_stories=True, enable_get_user_details=False),
    ]
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
        user_id=user_id,
    )
