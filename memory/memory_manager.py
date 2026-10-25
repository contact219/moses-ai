import json
import re
from datetime import datetime
from threading import Lock
from pathlib import Path
import sys


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR         = get_base_dir()
MEMORY_PATH      = BASE_DIR / "memory" / "long_term.json"
EPISODES_PATH    = BASE_DIR / "memory" / "episodes.json"
PENDING_PATH     = BASE_DIR / "memory" / "pending_turns.json"
_lock            = Lock()
_ep_lock         = Lock()
MAX_VALUE_LENGTH = 380
MEMORY_MAX_CHARS = 12000   # on-disk cap for ORDINARY facts (the prompt block has its own 2000-char cap)
MAX_EPISODES     = 60      # keep the most recent N session memories

# Never trimmed automatically: who they are, their health, the people in their
# life, and anything saved as critical. Ported from the web app, where losing
# a name or an allergy to a size cap was the failure that mattered most.
PROTECTED_CATEGORIES = {"identity", "health", "relationships"}
# Trimmed first when ordinary memory is over the cap (lower = goes first);
# within a category, the oldest goes first. Unlisted/custom categories sit
# between notes and preferences.
_TRIM_ORDER = {"notes": 0, "preferences": 2, "wishes": 2, "projects": 3}

def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "projects":      {},
        "relationships": {},
        "health":        {},
        "wishes":        {},
        "notes":         {},
    }

def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return _empty_memory()
    with _lock:
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _empty_memory()
                for key in base:
                    if key not in data:
                        data[key] = {}
                return data
            return _empty_memory()
        except Exception as e:
            print(f"[Memory] ⚠️ Load error: {e}")
            return _empty_memory()

def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


def is_protected(cat: str, entry: dict) -> bool:
    return cat in PROTECTED_CATEGORIES or (isinstance(entry, dict) and entry.get("importance") == "critical")


def _entry_chars(key: str, entry: dict) -> int:
    return len(json.dumps({key: entry}, ensure_ascii=False))


def _trim_to_limit(memory: dict) -> dict:
    """Keep ORDINARY memory under the cap. Protected facts are never deleted here."""
    ordinary = [(c, k, e) for c, k, e in _all_entries(memory) if not is_protected(c, e)]
    total = sum(_entry_chars(k, e) for _, k, e in ordinary)
    if total <= MEMORY_MAX_CHARS:
        return memory
    ordinary.sort(key=lambda t: (_TRIM_ORDER.get(t[0], 1), t[2].get("updated", "0000-00-00")))
    for cat, key, entry in ordinary:
        if total <= MEMORY_MAX_CHARS:
            break
        total -= _entry_chars(key, entry)
        del memory[cat][key]
        print(f"[Memory] 🗑️  Trimmed {cat}/{key}")
    return memory

def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    memory = _trim_to_limit(memory)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            new_val  = _truncate_value(str(value["value"] if isinstance(value, dict) else value))
            entry    = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            existing = target.get(key, {})
            importance = value.get("importance") if isinstance(value, dict) else None
            if importance in ("important", "critical"):
                entry["importance"] = importance
            elif isinstance(existing, dict) and existing.get("importance"):
                entry["importance"] = existing["importance"]   # an update never demotes a fact
            if not isinstance(existing, dict) or existing.get("value") != new_val \
                    or existing.get("importance") != entry.get("importance"):
                target[key] = entry
                changed = True
    return changed


def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        print(f"[Memory] 💾 Saved: {list(memory_update.keys())}")
    return memory

def format_memory_for_prompt(memory: dict | None) -> str:
    if not memory:
        return ""

    lines = []

    identity  = memory.get("identity", {})
    id_fields = ["name", "age", "birthday", "city", "job", "language", "school", "nationality"]
    for field in id_fields:
        entry = identity.get(field)
        if entry:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        if key in id_fields:
            continue
        val = entry.get("value") if isinstance(entry, dict) else entry
        if val:
            lines.append(f"{key.replace('_', ' ').title()}: {val}")

    prefs = memory.get("preferences", {})
    if prefs:
        lines.append("")
        lines.append("Preferences:")
        for key, entry in list(prefs.items())[:15]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    projects = memory.get("projects", {})
    if projects:
        lines.append("")
        lines.append("Active Projects / Goals:")
        for key, entry in list(projects.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    rels = memory.get("relationships", {})
    if rels:
        lines.append("")
        lines.append("People in their life:")
        for key, entry in list(rels.items())[:10]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    wishes = memory.get("wishes", {})
    if wishes:
        lines.append("")
        lines.append("Wishes / Plans / Wants:")
        for key, entry in list(wishes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    notes = memory.get("notes", {})
    if notes:
        lines.append("")
        lines.append("Other notes:")
        for key, entry in list(notes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key}: {val}")

    if not lines:
        return ""

    header = "[WHAT YOU KNOW ABOUT THIS PERSON — use naturally, never recite like a list]\n"
    result = header + "\n".join(lines)
    if len(result) > 2000:
        result = result[:1997] + "…"

    return result + "\n"

def save_fact(category: str, key: str, value: str, importance: str | None = None,
              replaces: str | None = None) -> str:
    """The save_memory tool. `replaces` ("category/key") removes the fact this one supersedes."""
    category = (category or "notes").strip().lower() or "notes"
    payload = {"value": value}
    if importance:
        payload["importance"] = importance
    if replaces and "/" in replaces:
        old_cat, old_key = [x.strip() for x in replaces.split("/", 1)]
        if (old_cat, old_key) != (category, key):
            mem = load_memory()
            if old_key in mem.get(old_cat, {}):
                del mem[old_cat][old_key]
                save_memory(mem)
                print(f"[Memory] ♻️  {old_cat}/{old_key} replaced by {category}/{key}")
    update_memory({category: {key: payload}})
    return f"Saved {category}/{key}"


def forget_matching(query: str = "", category: str = "", key: str = "") -> list[str]:
    """The forget_memory tool. Deletes exactly what was asked and returns what went.

    category+key deletes that one fact. Otherwise every fact (and episode) that
    contains ALL the meaningful words of the query is deleted — strict on
    purpose: forgetting the wrong thing is worse than asking again.
    """
    removed: list[str] = []
    mem = load_memory()
    if category and key:
        if key in mem.get(category, {}):
            removed.append(f"{category}/{key}: {mem[category][key].get('value', '')}")
            del mem[category][key]
    else:
        words = _keywords(query)
        if not words:
            return []
        for cat, k, entry in list(_all_entries(mem)):
            if words <= _keywords(f"{k.replace('_', ' ')} {entry.get('value', '')}"):
                removed.append(f"{cat}/{k}: {entry.get('value', '')}")
                del mem[cat][k]
    if removed:
        save_memory(mem)
    if query and not (category and key):
        words = _keywords(query)
        with _ep_lock:
            eps = load_episodes_unlocked()
            keep = [e for e in eps if not (words and words <= _keywords(e.get("summary", "") + " " + " ".join(e.get("tags", []))))]
            gone = [e for e in eps if e not in keep]
            if gone:
                EPISODES_PATH.write_text(json.dumps(keep, indent=2, ensure_ascii=False), encoding="utf-8")
                removed += [f"episode {e.get('date', '?')}: {e.get('summary', '')}" for e in gone]
    for r in removed:
        print(f"[Memory] 🧹 Forgot {r}")
    return removed


def remember(key: str, value: str, category: str = "notes") -> str:
    valid = {"identity", "preferences", "projects", "relationships", "health", "wishes", "notes"}
    if category not in valid:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    memory = load_memory()
    cat    = memory.get(category, {})
    if key in cat:
        del cat[key]
        memory[category] = cat
        save_memory(memory)
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"


forget_memory = forget


# ───────────────────────────────────────────────────────────────────────────
# EPISODIC MEMORY — what actually happened, session by session.
# Long-term memory stores stable facts ("their dog is named Kobe"). Episodes
# store events ("last time we booked a flight to Houston"), so Moses can check
# in on things across sessions the way the persona promises.
# ───────────────────────────────────────────────────────────────────────────

def load_episodes_unlocked() -> list:
    if not EPISODES_PATH.exists():
        return []
    try:
        data = json.loads(EPISODES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[Memory] ⚠️ Episode load error: {e}")
        return []


def load_episodes() -> list:
    with _ep_lock:
        return load_episodes_unlocked()


# ── Pending turns: what was said since the last episode was written ─────────
# Episodes are distilled every few turns; whatever was said after the last one
# used to vanish when the app closed. It's now kept on disk and distilled at
# the next start.
def save_pending(turns: list[str]) -> None:
    try:
        if turns:
            PENDING_PATH.write_text(json.dumps(turns, ensure_ascii=False), encoding="utf-8")
        elif PENDING_PATH.exists():
            PENDING_PATH.unlink()
    except Exception as e:
        print(f"[Memory] ⚠️ pending turns not saved: {e}")


def take_pending() -> list[str]:
    try:
        turns = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
        PENDING_PATH.unlink()
        return [t for t in turns if isinstance(t, str)]
    except Exception:
        return []


EPISODE_PROMPT = (
    "Summarize this conversation slice for an assistant's long-term memory.\n"
    "Line 1: \"SUMMARY: \" then ONE past-tense sentence capturing what the user did, asked, "
    "or shared that is worth remembering next time. Use only what was actually said: no numbers, "
    "dates or times of day they didn't give, and no words like again/still/finally that claim a "
    "history nobody mentioned.\n"
    "Line 2: \"TAGS: \" then 3-6 lowercase comma-separated topic words (people, health, work, "
    "feelings, plans — whatever fits).\n"
    "If nothing is worth keeping, reply with exactly NONE.\n\n"
)


def parse_episode(raw: str) -> tuple[str, list[str]] | None:
    raw = (raw or "").strip()
    if not raw or raw.upper() == "NONE":
        return None
    sm = re.search(r"^\s*SUMMARY:\s*(.+)$", raw, re.I | re.M)
    tm = re.search(r"^\s*TAGS:\s*(.+)$", raw, re.I | re.M)
    summary = (sm.group(1) if sm else raw.split("\n")[0]).strip()
    if not summary or summary.upper() == "NONE":
        return None
    tags = []
    if tm:
        for t in tm.group(1).split(","):
            t = re.sub(r"[^a-z0-9 _-]", "", t.strip().lower())
            if t and len(t) < 24:
                tags.append(t)
    return summary, tags[:6]


def fallback_summary(turns: list[str]) -> str:
    """If the summarizer can't be reached, keep the user's own words rather than nothing."""
    said = [t[len("User:"):].strip() for t in turns if t.startswith("User:")]
    return ("They said: " + " / ".join(said))[:380] if said else ""


def record_episode(summary: str, tags: list | None = None) -> None:
    """Append one event to episodic memory (keeps only the most recent N)."""
    summary = (summary or "").strip()
    if not summary:
        return
    now = datetime.now()
    episode = {
        "date":    now.strftime("%Y-%m-%d"),
        "time":    now.strftime("%H:%M"),
        "summary": summary[:400],
        "tags":    [t.lower() for t in (tags or []) if t],
    }
    with _ep_lock:
        try:
            episodes = json.loads(EPISODES_PATH.read_text(encoding="utf-8")) \
                if EPISODES_PATH.exists() else []
            if not isinstance(episodes, list):
                episodes = []
        except Exception:
            episodes = []
        episodes.append(episode)
        episodes = episodes[-MAX_EPISODES:]
        EPISODES_PATH.parent.mkdir(parents=True, exist_ok=True)
        EPISODES_PATH.write_text(
            json.dumps(episodes, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(f"[Memory] 📓 Episode saved: {summary[:60]}")


def format_episodes_for_prompt(n: int = 8) -> str:
    episodes = load_episodes()
    if not episodes:
        return ""
    lines = ["[RECENT HISTORY — things you did with them lately, reference naturally]"]
    for ep in episodes[-n:]:
        lines.append(f"  - {ep.get('date', '?')}: {ep.get('summary', '')}")
    return "\n".join(lines) + "\n"


_WORD_RE = re.compile(r"[a-z0-9]{3,}")
_STOP = {"the", "and", "for", "you", "your", "what", "with", "that", "this", "was",
         "are", "have", "how", "who", "when", "where", "did", "does", "can", "about"}


def _keywords(text: str) -> set:
    return {w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOP}


def recall_relevant(query: str, k: int = 5) -> str:
    """Dependency-free relevance search over long-term facts + episodes.
    Scores entries by keyword overlap with the query and returns the top k."""
    q = _keywords(query)
    if not q:
        return ""

    scored = []

    for cat, key, entry in _all_entries(load_memory()):
        val = entry.get("value", "")
        overlap = len(q & _keywords(f"{key} {val}"))
        if overlap:
            scored.append((overlap, f"{key.replace('_', ' ')}: {val}"))

    for ep in load_episodes():
        overlap = len(q & _keywords(ep.get("summary", "") + " " + " ".join(ep.get("tags", []))))
        if overlap:
            scored.append((overlap, f"({ep.get('date', '?')}) {ep.get('summary', '')}"))

    if not scored:
        return ""

    scored.sort(key=lambda t: t[0], reverse=True)
    top = [text for _, text in scored[:k]]
    return "\n".join(f"- {t}" for t in top)