"""Personal document search (lightweight RAG).

Answers questions like "what did that contract say about the deadline?" by
searching the user's own files. Dependency-free: it retrieves candidate files by
keyword overlap, reads the best matches, and lets Gemini answer from the excerpts.
PDF/DOCX are supported only if the optional libraries are already installed.
"""

import re
from pathlib import Path

from core.persona import get_client, VOICE_STYLE

# Where to look, and what to bother reading.
_SEARCH_DIRS  = [Path.home() / "Documents", Path.home() / "Desktop", Path.home() / "Downloads"]
_TEXT_EXT     = {".txt", ".md", ".py", ".json", ".csv", ".log", ".html", ".htm",
                 ".rst", ".ini", ".cfg", ".yaml", ".yml", ".tex"}
_MAX_FILES    = 400        # don't crawl an unbounded tree
_MAX_BYTES    = 200_000    # per-file read cap
_TOP_K        = 4          # files fed to the model

_WORD_RE = re.compile(r"[a-z0-9]{3,}")
_STOP = {"the", "and", "for", "you", "your", "what", "with", "that", "this", "was",
         "are", "have", "how", "who", "when", "where", "did", "does", "can", "about",
         "say", "said", "tell", "find", "show", "give"}


def _keywords(text: str) -> set:
    return {w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOP}


def _read_text(path: Path) -> str:
    ext = path.suffix.lower()
    try:
        if ext in _TEXT_EXT:
            return path.read_text(encoding="utf-8", errors="ignore")[:_MAX_BYTES]
        if ext == ".pdf":
            try:
                from pypdf import PdfReader
                return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)[:_MAX_BYTES]
            except Exception:
                return ""
        if ext == ".docx":
            try:
                import docx
                return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)[:_MAX_BYTES]
            except Exception:
                return ""
    except Exception:
        return ""
    return ""


def _candidate_files() -> list[Path]:
    files: list[Path] = []
    exts = _TEXT_EXT | {".pdf", ".docx"}
    for base in _SEARCH_DIRS:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if len(files) >= _MAX_FILES:
                break
            if p.is_file() and p.suffix.lower() in exts and p.stat().st_size < 5_000_000:
                files.append(p)
    return files


def document_search(parameters: dict, player=None, speak=None) -> str:
    query = (parameters or {}).get("query", "").strip()
    if not query:
        return "What do you want me to look up in your files?"

    q = _keywords(query)
    if not q:
        return "Give me something more specific to search your files for."

    # 1) Rank files by keyword overlap (filename first, then a cheap content peek).
    scored: list[tuple[int, Path, str]] = []
    for path in _candidate_files():
        name_score = len(q & _keywords(path.stem)) * 3
        text = _read_text(path)
        if not text:
            continue
        content_score = len(q & _keywords(text))
        total = name_score + content_score
        if total:
            scored.append((total, path, text))

    if not scored:
        return "I couldn't find anything in your documents that matches that."

    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[:_TOP_K]

    if player:
        player.write_log("[Docs] " + ", ".join(p.name for _, p, _ in top))

    # 2) Let Moses answer from the excerpts.
    context = "\n\n".join(
        f"### FILE: {p.name}\n{text[:6000]}" for _, p, text in top
    )
    try:
        resp = get_client().models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                f"Answer the user's question using ONLY these files. Cite the file "
                f"name(s) you used. If the answer isn't in them, say so plainly.\n\n"
                f"QUESTION: {query}\n\n{context}\n\n{VOICE_STYLE}"
            ),
        )
        answer = (resp.text or "").strip()
    except Exception as e:
        return f"I found matching files but couldn't read through them: {e}"

    return answer or "I looked but couldn't pull a clear answer from those files."
