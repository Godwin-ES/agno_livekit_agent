from __future__ import annotations

import pytest

from tools.notes import NotesStore, create_note_tools


@pytest.mark.asyncio
async def test_notes_are_scoped_to_stable_user_id(tmp_path) -> None:
    store = NotesStore(tmp_path / "notes.db")
    alice = create_note_tools("visitor-alice", store)
    bob = create_note_tools("visitor-bob", store)

    added = await alice.add_note("Email Sam tomorrow")
    alice_notes = await alice.list_notes()
    bob_notes = await bob.list_notes()

    assert added["kind"] == "notes"
    assert alice_notes["notes"] == ["Email Sam tomorrow"]
    assert bob_notes["notes"] == []


@pytest.mark.asyncio
async def test_clear_notes_only_clears_current_user(tmp_path) -> None:
    store = NotesStore(tmp_path / "notes.db")
    alice = create_note_tools("visitor-alice", store)
    bob = create_note_tools("visitor-bob", store)
    await alice.add_note("Alice note")
    await bob.add_note("Bob note")

    result = await alice.clear_notes()

    assert result["notes"] == []
    assert (await bob.list_notes())["notes"] == ["Bob note"]
