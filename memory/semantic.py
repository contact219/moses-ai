"""Meaning-based recall, as a RESCUE behind keyword recall — never in front of it.

Ported from the Moses/Mina web app (semantic.js), where it is live:
  - keyword recall found something  -> its answer stands; a meaning match is
    added only if it clears a higher bar;
  - keyword recall found nothing    -> memories close in MEANING are offered,
    labelled as only possibly related, so the model can still tell a wedding
    from a divorce instead of being handed the wrong memory as THE answer.

Same model, input format and thresholds as the web app (calibrated there on
labelled cases, leakage traps included). Vectors are cached in
memory/embeddings.json, stamped with a hash of the text, so an edited fact is
re-embedded and a deleted one drops out.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import struct
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

from memory.memory_manager import BASE_DIR, _all_entries, load_episodes, load_memory

INDEX_PATH     = BASE_DIR / "memory" / "embeddings.json"
MODEL          = "gemini-embedding-2"
DIMS           = 768
BATCH          = 32
MIN_SIMILARITY = 0.72          # web app default (MEMORY_SEMANTIC_MIN)
STRONG         = MIN_SIMILARITY + 0.08
QUERY_TIMEOUT  = 1.5           # recall runs inside a live voice turn

_lock = threading.Lock()
_pool  = ThreadPoolExecutor(max_workers=1, thread_name_prefix="semantic")    # index refreshes
_qpool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="semantic-q")  # queries never wait behind a refresh


def _client():
    from core.persona import get_client
    return get_client()


def _normalize(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _embed(texts: list[str], kind: str) -> list[list[float]]:
    from google.genai import types
    out = []
    for i in range(0, len(texts), BATCH):
        chunk = [f"task: search result | query: {t}" if kind == "query" else f"title: none | text: {t}"
                 for t in texts[i:i + BATCH]]
        # One Content per text: a flat list of strings is embedded as ONE input.
        resp = _client().models.embed_content(
            model=MODEL,
            contents=[types.Content(parts=[types.Part(text=t)]) for t in chunk],
            config=types.EmbedContentConfig(output_dimensionality=DIMS),
        )
        embs = resp.embeddings or []
        if len(embs) != len(chunk):
            raise RuntimeError(f"embedding count {len(embs)} != {len(chunk)}")
        out += [_normalize(e.values) for e in embs]
    return out


def _pack(v):   return base64.b64encode(struct.pack(f"{len(v)}f", *v)).decode()
def _unpack(s): b = base64.b64decode(s); return list(struct.unpack(f"{len(b) // 4}f", b))
def _hash(t):   return hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]


def _docs() -> dict[str, str]:
    """Everything recall can find: id -> the text that represents it."""
    docs = {}
    for cat, key, entry in _all_entries(load_memory()):
        docs[f"fact:{cat}/{key}"] = f"{key.replace('_', ' ')}: {entry.get('value', '')}"
    for i, ep in enumerate(load_episodes()):
        docs[f"ep:{ep.get('date', '?')} {ep.get('time', '')} #{i}"] = \
            f"({ep.get('date', '?')}) {ep.get('summary', '')}"
    return docs


def refresh() -> int:
    """Bring the index in line with memory: embed new/edited docs, drop deleted ones."""
    with _lock:
        try:
            index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except Exception:
            index = {}
        docs = _docs()
        stale = [d for d, t in docs.items() if index.get(d, {}).get("h") != _hash(t)]
        if stale:
            vecs = _embed([docs[d] for d in stale], "doc")
            for d, v in zip(stale, vecs):
                index[d] = {"h": _hash(docs[d]), "v": _pack(v)}
        dropped = [d for d in index if d not in docs]
        for d in dropped:
            del index[d]
        if stale or dropped:
            INDEX_PATH.write_text(json.dumps(index), encoding="utf-8")
        return len(stale)


def refresh_in_background():
    def run():
        try:
            n = refresh()
            if n:
                print(f"[Memory] 🧭 embedded {n} memory item(s)")
        except Exception as e:
            print(f"[Memory] ⚠️ semantic index refresh failed: {e}")
    _pool.submit(run)


def search(query: str, k: int = 3) -> list[tuple[float, str]]:
    """(similarity, text) for the closest memories, best first. [] on any failure/timeout."""
    try:
        qv = _qpool.submit(_embed, [query], "query").result(timeout=QUERY_TIMEOUT)[0]
    except (FutureTimeout, Exception) as e:
        print(f"[Memory] ⚠️ semantic recall skipped: {e or 'timeout'}")
        return []
    try:
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    docs = _docs()
    scored = []
    for d, rec in index.items():
        if d in docs and rec.get("h") == _hash(docs[d]):
            v = _unpack(rec["v"])
            scored.append((sum(a * b for a, b in zip(qv, v)), docs[d]))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:k]


def hybrid_recall(query: str, keyword_result: str) -> str:
    """Keyword answer first; meaning matches only as a labelled rescue or a strong extra."""
    near = [(s, t) for s, t in search(query) if s >= MIN_SIMILARITY]
    if keyword_result:
        extra = [t for s, t in near if s >= STRONG and t not in keyword_result]
        return keyword_result + ("".join(f"\n- {t}" for t in extra) if extra else "")
    if not near:
        return ""
    return ("Nothing matched those words exactly. These memories are only POSSIBLY related — "
            "use one only if it truly answers what they asked, otherwise say you don't have it:\n"
            + "\n".join(f"- {t}" for _, t in near))
