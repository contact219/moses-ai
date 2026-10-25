"""Moses and Mina: who's talking, how they sound, and how the HUD looks.

Both share one memory (long_term.json / episodes.json) — switching changes the
voice, the prompt and the look, never what they know about you. The choice
persists in config/persona.json.

Moses's voice and model stay exactly as tuned on the desktop (Charon, on the
native-audio model). Mina is Aoede, the web app's Mina voice.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR     = _base_dir()
PERSONA_FILE = BASE_DIR / "config" / "persona.json"

# HUD palettes. Moses is the original desktop cyan, untouched; Mina is the
# web app's rose (#ff8fb0) carried through every shade the HUD uses. Keys are
# ui.C attribute names — the HUD swaps one palette for the other in place.
PALETTE_MOSES = {
    "BG": "#00060a", "PANEL": "#010d14", "PANEL2": "#010f18", "DARK": "#000d14", "BAR_BG": "#011520",
    "BORDER": "#0d3347", "BORDER_B": "#1a5c7a", "BORDER_A": "#0f4060",
    "PRI": "#00d4ff", "PRI_DIM": "#007a99", "PRI_GHO": "#001f2e",
    "TEXT": "#8ffcff", "TEXT_DIM": "#3a8a9a", "TEXT_MED": "#5ab8cc", "WHITE": "#d8f8ff",
    "ZONE_DRAG": "#001a24", "ZONE_HOVER": "#001218", "ZONE_LINE": "#1a4a5a", "ZONE_TEXT": "#1e5c6a",
}
PALETTE_MINA = {
    "BG": "#0a0306", "PANEL": "#140109", "PANEL2": "#18020c", "DARK": "#12000a", "BAR_BG": "#200111",
    "BORDER": "#4a1530", "BORDER_B": "#7d2c50", "BORDER_A": "#61203e",
    "PRI": "#ff8fb0", "PRI_DIM": "#b05070", "PRI_GHO": "#2e0a18",
    "TEXT": "#ffc9da", "TEXT_DIM": "#9a4d68", "TEXT_MED": "#cc7f9c", "WHITE": "#ffe9f1",
    "ZONE_DRAG": "#24000f", "ZONE_HOVER": "#18000a", "ZONE_LINE": "#5a1a36", "ZONE_TEXT": "#6a1e42",
}

PERSONAS = {
    "moses": {
        "key": "moses", "name": "Moses", "voice": "Charon",
        "prompt": BASE_DIR / "core" / "prompt.txt",
        "face": BASE_DIR / "assets" / "moses-face.jpg",
        "video": BASE_DIR / "assets" / "moses-face.mp4",
        "title": "M.O.S.E.S", "subtitle": "Model Optimized Smart Expert System",
        "palette": PALETTE_MOSES,
    },
    "mina": {
        "key": "mina", "name": "Mina", "voice": "Aoede",
        "prompt": BASE_DIR / "core" / "prompt-mina.txt",
        "face": BASE_DIR / "assets" / "mina-face.jpg",
        "video": BASE_DIR / "assets" / "mina-face.mp4",
        "title": "M.I.N.A", "subtitle": "The Soul-Keeper · Guardian of Quiet Truths",
        "palette": PALETTE_MINA,
    },
}


def get_persona(key: str | None) -> dict:
    return PERSONAS.get((key or "").lower(), PERSONAS["moses"])


def load_persona_key() -> str:
    try:
        key = json.loads(PERSONA_FILE.read_text(encoding="utf-8")).get("persona", "moses")
        return key if key in PERSONAS else "moses"
    except Exception:
        return "moses"


def save_persona_key(key: str) -> None:
    try:
        PERSONA_FILE.parent.mkdir(parents=True, exist_ok=True)
        PERSONA_FILE.write_text(json.dumps({"persona": key}, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[PERSONA] ⚠️ could not save choice: {e}")
