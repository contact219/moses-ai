"""Notes Moses puts on screen (the show_note tool), kept so they can come back.

A note is something to use, not to hear: an address, a number, a list, a
confirmation code, a message to send, or a line to say. Each one is shown as a
floating card (ui_presence.NoteCard) and saved here, newest last.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

STORE = Path(__file__).resolve().parent.parent / "memory" / "notes.json"
KEEP = 200                 # oldest notes are dropped past this
KINDS = ("note", "line")   # "line" = words for them to say or send, shown as a quote


def _load(store: Path) -> list[dict]:
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def add(title: str, body: str, kind: str = "note", store: Path | None = None) -> dict:
    """Save a note and return it. Raises ValueError if there is nothing to show."""
    store = store or STORE
    body = (body or "").strip()
    if not body:
        raise ValueError("a note needs some text")
    note = {
        "id": uuid.uuid4().hex[:12],
        "title": (title or "").strip()[:80] or "Note",
        "body": body[:4000],
        "kind": kind if kind in KINDS else "note",
        "created": time.strftime("%Y-%m-%d %H:%M"),
    }
    notes = _load(store)
    notes.append(note)
    store.parent.mkdir(parents=True, exist_ok=True)
    tmp = store.with_suffix(".tmp")
    tmp.write_text(json.dumps(notes[-KEEP:], indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(store)
    return note


def recent(n: int = 3, store: Path | None = None) -> list[dict]:
    """The last n notes, oldest first (so cards stack in the order they were made)."""
    return _load(store or STORE)[-n:] if n > 0 else []
