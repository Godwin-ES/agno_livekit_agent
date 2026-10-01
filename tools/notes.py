"""User-scoped persistent notes."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class NotesStore:
    def __init__(self, db_path: str | Path = "data/memory.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def add(self, user_id: str, text: str) -> list[str]:
        with self._connect() as connection:
            connection.execute("INSERT INTO notes (user_id, text) VALUES (?, ?)", (user_id, text))
        return self.list(user_id)

    def list(self, user_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT text FROM notes WHERE user_id = ? ORDER BY id", (user_id,)
            ).fetchall()
        return [str(row[0]) for row in rows]

    def clear(self, user_id: str) -> list[str]:
        with self._connect() as connection:
            connection.execute("DELETE FROM notes WHERE user_id = ?", (user_id,))
        return []


@dataclass
class UserNoteTools:
    user_id: str
    store: NotesStore

    async def add_note(self, text: str) -> dict[str, Any]:
        """Use when the user asks to save, remember, or jot down a temporary note."""
        clean = " ".join(text.split())[:500]
        if not clean:
            return {"kind": "error", "say": "Tell me what you'd like me to note."}
        notes = self.store.add(self.user_id, clean)
        return {"kind": "notes", "say": f"I added the note: {clean}.", "notes": notes}

    async def list_notes(self) -> dict[str, Any]:
        """Use when the user asks what notes they have saved."""
        notes = self.store.list(self.user_id)
        say = f"You have {len(notes)} saved note{'s' if len(notes) != 1 else ''}." if notes else "You don't have any saved notes."
        return {"kind": "notes", "say": say, "notes": notes}

    async def clear_notes(self) -> dict[str, Any]:
        """Use only when the user explicitly asks to delete all of their notes."""
        return {"kind": "notes", "say": "I cleared your notes.", "notes": self.store.clear(self.user_id)}


def create_note_tools(user_id: str, store: NotesStore | None = None) -> UserNoteTools:
    return UserNoteTools(user_id=user_id, store=store or NotesStore())
