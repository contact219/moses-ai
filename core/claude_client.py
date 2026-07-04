"""Thin Claude wrapper for codegen actions (code_helper, dev_agent).

Exposes the same `.generate_content(contents) -> response.text` shape the
Gemini `_Compat` wrappers in those modules used, so swapping the model
underneath them didn't require restructuring the calling code — just what's
actually generating the code.
"""

import base64

import anthropic

from config import get_config

MODEL         = "claude-opus-4-8"
MAX_TOKENS    = 8000
DEFAULT_EFFORT = "medium"  # "high" measured ~2x slower for little quality gain on
                           # single-shot codegen/explain calls — see agent/claude_agent.py
                           # for the multi-step loop, which is where "high" earns its keep.

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = get_config().get("anthropic_api_key", "")
        if not api_key or api_key == "YOUR_ANTHROPIC_API_KEY_HERE":
            raise RuntimeError("No anthropic_api_key configured in config/api_keys.json")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


class _Response:
    """Minimal drop-in for the one attribute callers read: response.text"""

    def __init__(self, text: str):
        self.text = text


class ClaudeCodeModel:
    """Compat shim matching the old Gemini `_Compat.generate_content()` shape."""

    def __init__(self, model: str = MODEL, max_tokens: int = MAX_TOKENS, effort: str = DEFAULT_EFFORT):
        self._model      = model
        self._max_tokens = max_tokens
        self._effort     = effort

    def generate_content(self, contents) -> _Response:
        client = _get_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            thinking={"type": "adaptive"},
            output_config={"effort": self._effort},
            messages=[{"role": "user", "content": contents}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        return _Response(text)


def get_code_model(effort: str = DEFAULT_EFFORT) -> ClaudeCodeModel:
    """A Claude Opus 4.8 model handle for codegen — same call shape as the
    old `_get_gemini()` / `_get_model()` helpers it replaces."""
    return ClaudeCodeModel(effort=effort)


def analyze_image(image_bytes: bytes, prompt: str, media_type: str = "image/png") -> str:
    """Vision call for screen-debug style analysis. Returns plain text."""
    client = _get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": DEFAULT_EFFORT},
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.b64encode(image_bytes).decode("utf-8"),
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()


def is_rate_limit(error: Exception) -> bool:
    if isinstance(error, anthropic.RateLimitError):
        return True
    msg = str(error).lower()
    return "429" in msg or "rate_limit" in msg or "quota" in msg
