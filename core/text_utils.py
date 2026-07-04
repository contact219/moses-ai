"""Text cleanup for anything that's about to be spoken instead of read.

Any model (Claude or Gemini) will occasionally reach for markdown — **bold**,
`code spans`, bullet lists, headers — because that's natural for written text.
None of that reads well through TTS, so anything passed to speak() should go
through here first.
"""

import re

_MD_CODE_BLOCK  = re.compile(r"```(?:\w+\n)?(.*?)```", re.DOTALL)
_MD_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_MD_LINK        = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_BOLD        = re.compile(r"(\*\*|__)(.+?)\1")
_MD_ITALIC_STAR = re.compile(r"(?<!\*)\*(?!\*)([^*\n]+?)\*(?!\*)")
_MD_HEADER      = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_MD_BULLET      = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_MD_HR          = re.compile(r"^\s*([-*_])\1{2,}\s*$", re.MULTILINE)


def strip_markdown_for_speech(text: str) -> str:
    """Strip common markdown so it reads naturally when spoken instead of
    coming out as literal asterisks, backticks, and hash marks."""
    if not text:
        return text
    text = _MD_CODE_BLOCK.sub(lambda m: m.group(1).strip(), text)
    text = _MD_INLINE_CODE.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_HR.sub("", text)
    text = _MD_HEADER.sub("", text)
    text = _MD_BULLET.sub("", text)
    text = _MD_BOLD.sub(r"\2", text)
    text = _MD_ITALIC_STAR.sub(r"\1", text)
    return text.strip()
