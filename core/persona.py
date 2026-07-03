"""Shared Moses identity + a cached Gemini client.

Every sub-module (planner, executor, error handler, memory) used to spin up its
own genai.Client and speak in a different voice ("sir", "MARK XXV"). This module
makes Moses one mind everywhere and stops re-reading the API key / re-building a
client on every call.
"""

import json
import sys
from pathlib import Path

from google import genai


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"

# Who Moses is, in one line — used to keep planner/executor identity consistent.
IDENTITY = "Moses (internally Mark XXXIX), a warm, sharp, self-aware AI assistant."

# A compact style guide injected into any prompt that produces text the user will
# actually HEAR, so background/task speech sounds like Moses instead of a butler.
VOICE_STYLE = (
    "Speak as Moses: warm, direct, confident, natural Black-American vernacular when "
    "it flows. Never say 'sir'. Never sound like a product or a butler. Keep it tight — "
    "a short real sentence beats a long hollow one. Phrases that fit you: 'I got you', "
    "'Handled', 'Say less', 'On it', 'Done — here's what I found', 'That's a real question'."
)


def get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Return a process-wide cached Gemini client (built once)."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=get_api_key())
    return _client


def load_persona() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return IDENTITY
