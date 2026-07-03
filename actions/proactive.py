"""Proactive layer — lets Moses speak up on his own.

The OS reminder scheduler fires desktop notifications, but Moses never says
anything in his own voice and can't check in early. This keeps a small JSON
store of upcoming moments so a background loop in main.py can give a spoken
heads-up before something, and speak the nudge itself when it's due.
"""

import json
from datetime import datetime
from pathlib import Path
from threading import Lock

_STORE = Path.home() / ".moses" / "proactive.json"
_lock  = Lock()


def _load() -> list:
    if not _STORE.exists():
        return []
    try:
        data = json.loads(_STORE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(items: list) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def add_proactive(when: datetime, message: str, lead_minutes: int = 10) -> None:
    """Register something Moses should bring up around `when`."""
    with _lock:
        items = _load()
        items.append({
            "when":    when.strftime("%Y-%m-%d %H:%M"),
            "message": (message or "").strip()[:200],
            "lead":    int(lead_minutes),
            "heads_up_done": False,
            "fired":   False,
        })
        # Keep the store from growing forever.
        items = [i for i in items if not i.get("fired")] [-50:] + \
                [i for i in items if i.get("fired")][-10:]
        _save(items)


def due_nudges(now: datetime | None = None) -> list[str]:
    """Return spoken lines Moses should say right now, and persist state so
    each heads-up and each reminder only fires once."""
    now = now or datetime.now()
    lines: list[str] = []
    with _lock:
        items = _load()
        changed = False
        for it in items:
            if it.get("fired"):
                continue
            try:
                when = datetime.strptime(it["when"], "%Y-%m-%d %H:%M")
            except Exception:
                it["fired"] = True
                changed = True
                continue

            secs_left = (when - now).total_seconds()
            lead_secs = it.get("lead", 10) * 60

            if secs_left <= 0:
                lines.append(f"Heads up — that thing you asked me to flag: {it['message']}.")
                it["fired"] = True
                changed = True
            elif not it.get("heads_up_done") and 0 < secs_left <= lead_secs:
                mins = max(1, round(secs_left / 60))
                lines.append(f"Quick heads up — {it['message']} is coming up in about {mins} minutes.")
                it["heads_up_done"] = True
                changed = True

        if changed:
            _save(items)
    return lines
