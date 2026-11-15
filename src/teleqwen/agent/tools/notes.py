import json
import logging
import os
from pathlib import Path
from uuid import uuid4


def _notes_path() -> Path:
    return Path(os.getenv("TELEQWEN_NOTES", "data/notes.json")).expanduser()


def _load_notes(path: Path) -> list[dict]:
    notes = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if not isinstance(notes, list) or any(
        not isinstance(note, dict)
        or not isinstance(note.get("id"), str)
        or not isinstance(note.get("text"), str)
        for note in notes
    ):
        raise ValueError("Invalid notes file")
    return notes


def _save_notes(path: Path, notes: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def save_note(text: str) -> dict:
    """Save a persistent note when the user asks to remember something.

    Args:
        text: The information to remember.
    """
    text = text.strip()
    if not text:
        raise ValueError("Note text must not be empty")
    path = _notes_path()
    notes = _load_notes(path)
    for note in notes:
        if note["text"] == text:
            return note
    note = {"id": uuid4().hex, "text": text}
    _save_notes(path, notes + [note])
    logging.info("Note saved")
    return note


def search_notes(query: str) -> list[dict]:
    """Search notes by case-insensitive keywords. Use an empty query to list all notes.

    Args:
        query: Keywords that must all appear in the note, or an empty string.
    """
    terms = query.casefold().split()
    notes = _load_notes(_notes_path())
    return [note for note in notes if all(term in note["text"].casefold() for term in terms)]


def delete_note(note_id: str) -> str:
    """Delete a note requested by the user, using its ID from search_notes.

    Args:
        note_id: The exact ID of the note to delete.
    """
    path = _notes_path()
    notes = _load_notes(path)
    remaining = [note for note in notes if note["id"] != note_id]
    if len(remaining) == len(notes):
        raise ValueError("Note not found")
    _save_notes(path, remaining)
    logging.info("Note deleted")
    return "Note deleted"
