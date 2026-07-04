"""Claude-powered agentic engine for Moses.

Gemini Live stays the ears and mouth — wake word, casual conversation, and
one-shot commands it can handle in a single turn. Anything routed through the
`agent_task` tool (main.py) as a real multi-step job lands here instead of the
old blind "plan 5 steps up front, then hope" engine.

This runs a genuine tool-use loop against Claude: Claude sees the real result
of each tool call before deciding what to do next, can take as many or as few
steps as the task actually needs, and recovers from a failed step itself
instead of bouncing out to a separate blind "replan" call.
"""

import sys
import threading
from pathlib import Path
from typing import Callable

import anthropic

from config import get_config


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()

MODEL          = "claude-opus-4-8"
MAX_ITERATIONS = 15
MAX_TOKENS     = 8000
# "high" measured noticeably slower per turn with no consistent quality win for
# most agent_task goals — Anthropic's own guidance is that "medium" often gets
# equally good agentic results in less time. Bump back to "high" here if a
# specific class of task is coming out shallow.
EFFORT         = "medium"


class ClaudeUnavailableError(RuntimeError):
    """Raised only when the very first call to Claude fails — safe point for
    the caller to fall back to the legacy Gemini planner, since no tool with
    side effects has run yet."""


def is_configured() -> bool:
    try:
        key = get_config().get("anthropic_api_key", "")
    except Exception:
        return False
    return bool(key) and key != "YOUR_ANTHROPIC_API_KEY_HERE"


_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = get_config().get("anthropic_api_key", "")
        if not api_key or api_key == "YOUR_ANTHROPIC_API_KEY_HERE":
            raise RuntimeError("No anthropic_api_key configured in config/api_keys.json")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# ─────────────────────────────────────────────────────────────────────────
# Tool schemas — one real Anthropic tool per Moses action module. Parameter
# names/shapes match agent/tools.py's call_tool() dispatcher exactly.
# ─────────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "open_app",
        "description": "Open a desktop application by name (e.g. Chrome, Spotify, VS Code, Terminal).",
        "input_schema": {
            "type": "object",
            "properties": {"app_name": {"type": "string", "description": "Name of the application to open"}},
            "required": ["app_name"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the web for information, news, prices, or facts, or compare multiple items. "
            "Use this for ANY information retrieval or research — never answer from memory when "
            "the answer could be stale, specific, or time-sensitive."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A clear, focused search query"},
                "mode": {"type": "string", "enum": ["search", "compare"], "description": "Default: search"},
                "items": {"type": "array", "items": {"type": "string"}, "description": "Items to compare (compare mode only)"},
                "aspect": {"type": "string", "description": "What aspect to compare on (compare mode only)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "game_updater",
        "description": "Install, update, list, or schedule updates for Steam/Epic games.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["update", "install", "list", "download_status", "schedule"]},
                "platform": {"type": "string", "enum": ["steam", "epic", "both"], "description": "Default: both"},
                "game_name": {"type": "string"},
                "app_id": {"type": "string"},
                "shutdown_when_done": {"type": "boolean"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "browser_control",
        "description": "Directly drive a web browser window — navigate, search, click, type, scroll, read page text, press a key, or close it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["go_to", "search", "click", "type", "scroll", "get_text", "press", "close"]},
                "url": {"type": "string", "description": "For go_to"},
                "query": {"type": "string", "description": "For search"},
                "text": {"type": "string", "description": "For click/type"},
                "direction": {"type": "string", "enum": ["up", "down"], "description": "For scroll"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "file_controller",
        "description": (
            "Read, write, list, move, copy, delete, or search local files, or check disk usage. "
            "Use action=write or create_file to save anything you produced (research notes, a "
            "document, generated content) to disk."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["write", "create_file", "read", "list", "delete", "move", "copy", "find", "disk_usage"]},
                "path": {"type": "string", "description": "Use 'desktop' for the Desktop folder"},
                "name": {"type": "string", "description": "Filename"},
                "content": {"type": "string", "description": "File content, for write/create_file"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "computer_settings",
        "description": "Change a single OS-level setting — volume, brightness, wifi, display, power, closing an app, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "The setting to change"},
                "description": {"type": "string", "description": "Natural-language description of the desired change"},
                "value": {"type": "string"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "computer_control",
        "description": "Low-level mouse/keyboard/screen control — type text, click coordinates, press a hotkey, scroll, screenshot, or find/click something on screen by description.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["type", "click", "hotkey", "press", "scroll", "screenshot", "screen_find", "screen_click"]},
                "text": {"type": "string", "description": "For type"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "keys": {"type": "string", "description": "For hotkey, e.g. 'ctrl+c'"},
                "key": {"type": "string", "description": "For press"},
                "direction": {"type": "string", "enum": ["up", "down"]},
                "description": {"type": "string", "description": "For screen_find/screen_click"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "screen_process",
        "description": "Look at what's currently on the user's screen (or camera) and analyze it or answer a question about it. Use when the user references something visible.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "What to analyze or ask about the screen"},
                "angle": {"type": "string", "enum": ["screen", "camera"]},
            },
            "required": ["text"],
        },
    },
    {
        "name": "send_message",
        "description": "Send a message to a contact through a messaging platform (e.g. WhatsApp, iMessage, Slack).",
        "input_schema": {
            "type": "object",
            "properties": {
                "receiver": {"type": "string"},
                "message_text": {"type": "string"},
                "platform": {"type": "string"},
            },
            "required": ["receiver", "message_text", "platform"],
        },
    },
    {
        "name": "reminder",
        "description": "Set a reminder for a specific date and time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM"},
                "message": {"type": "string"},
            },
            "required": ["date", "time", "message"],
        },
    },
    {
        "name": "desktop_control",
        "description": "Manage the desktop itself — change wallpaper, organize/clean up files, list desktop contents, or run a desktop-related task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["wallpaper", "organize", "clean", "list", "task"]},
                "path": {"type": "string"},
                "task": {"type": "string"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "youtube_video",
        "description": "Play a YouTube video, summarize a video, or check trending videos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["play", "summarize", "trending"]},
                "query": {"type": "string", "description": "For play"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "weather_report",
        "description": "Get the current weather report for a city.",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
    {
        "name": "flight_finder",
        "description": "Search for flights between two locations on a given date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string"},
                "destination": {"type": "string"},
                "date": {"type": "string"},
            },
            "required": ["origin", "destination", "date"],
        },
    },
    {
        "name": "code_helper",
        "description": "Write, edit, run, or explain a piece of code, optionally saving it to a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["write", "edit", "run", "explain"]},
                "description": {"type": "string"},
                "language": {"type": "string"},
                "output_path": {"type": "string"},
                "file_path": {"type": "string"},
            },
            "required": ["action", "description"],
        },
    },
    {
        "name": "dev_agent",
        "description": "Hand off a larger, self-contained coding/dev task (e.g. build a small script or tool end-to-end) to Moses's dev agent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "language": {"type": "string"},
            },
            "required": ["description"],
        },
    },
]

_SLOW_TOOLS = {"web_search", "screen_process", "dev_agent", "code_helper", "browser_control", "game_updater"}

AGENT_RULES = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AGENT MODE — you've been handed a real task, not just a quick reply
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You have real tools you can call, one or more at a time, and you see each tool's actual
result before deciding what to do next. Use that — don't plan the whole thing blind, look
at what a tool actually returned and adapt from there.

RULES:
- Use web_search for ANY information retrieval, research, current events, or prices — never
  answer from memory when the answer could be stale, specific, or time-sensitive.
- Use file_controller (action: write / create_file) to save anything you produce to disk.
- Write and save content in the same language the task was given in.
- Before a slow tool call (web_search, screen_process, dev_agent, code_helper, browser_control,
  game_updater), say one short sentence out loud first, then call it. Stay quiet otherwise —
  don't narrate every step.
- If a tool call fails, read the error and actually try something different — a different tool,
  different parameters, or a smaller step. Don't repeat the exact same call and hope.
- Once the task is genuinely done, stop calling tools and give one short, confident, spoken-style
  final answer covering what you did and what came of it. That final message is the only thing
  the user hears, so make it complete on its own — don't reference steps they didn't see.
- Say each fact once. Don't open with a rundown and then close with a "bottom line" or "here's
  the picture" that restates the same numbers again — that's saying it twice. One pass, then
  stop talking. A couple of sentences per thing you found, not a report — covering more than
  one topic, one line each is enough.
- If something is genuinely impossible, unsafe, or you're stuck, say so plainly instead of
  pretending it worked.
- Never use markdown in anything you say out loud (no **bold**, no `code spans`, no # headers,
  no - bullet lists, no [links](url)). Every lead-in sentence and final answer gets spoken aloud,
  not read on a screen — write plain sentences the way you'd actually say them.
"""


def _build_system_prompt() -> str:
    from core.persona import load_persona, VOICE_STYLE
    return f"{load_persona()}\n\n{VOICE_STYLE}\n{AGENT_RULES}"


def run(
    goal: str,
    speak: Callable | None = None,
    cancel_flag: threading.Event | None = None,
) -> str:
    from agent.tools import call_tool
    try:
        from memory.memory_manager import recall_relevant, record_episode
    except Exception:
        recall_relevant = lambda *_a, **_k: ""
        record_episode  = lambda *_a, **_k: None

    client        = get_client()
    system_prompt = _build_system_prompt()

    user_content = f"Task from the user: {goal}"
    memory_context = recall_relevant(goal, k=6)
    if memory_context:
        user_content += f"\n\n[Relevant things you know about them]\n{memory_context}"

    messages = [{"role": "user", "content": user_content}]

    print(f"\n[ClaudeAgent] 🎯 Goal: {goal}")

    for iteration in range(MAX_ITERATIONS):
        if cancel_flag and cancel_flag.is_set():
            if speak:
                speak("Cancelled that one.")
            return "Task cancelled."

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": EFFORT},
                tools=TOOLS,
                messages=messages,
            )
        except Exception as e:
            if iteration == 0:
                # Nothing has run yet — safe for the caller to fall back to the legacy planner.
                raise ClaudeUnavailableError(str(e)) from e
            print(f"[ClaudeAgent] ⚠️ API error mid-task: {e}")
            msg = "Ran into a snag with my reasoning engine partway through that one."
            if speak:
                speak(msg)
            return msg

        for block in response.content:
            if block.type == "thinking" and getattr(block, "thinking", ""):
                print(f"[ClaudeAgent] 🧠 {block.thinking[:300]}")

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "tool_use":
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            # Speak any short lead-in text Claude wrote before a slow tool call.
            if speak:
                lead_in = "".join(b.text for b in response.content if b.type == "text").strip()
                if lead_in and any(b.name in _SLOW_TOOLS for b in tool_use_blocks):
                    speak(lead_in)

            tool_results = []
            for block in tool_use_blocks:
                if cancel_flag and cancel_flag.is_set():
                    break
                print(f"[ClaudeAgent] ▶️ {block.name} {block.input}")
                try:
                    result = call_tool(block.name, dict(block.input), speak)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result)[:8000],
                    })
                    print(f"[ClaudeAgent] ✅ {block.name} -> {str(result)[:150]}")
                except Exception as e:
                    print(f"[ClaudeAgent] ❌ {block.name} failed: {e}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Error: {e}",
                        "is_error": True,
                    })

            if cancel_flag and cancel_flag.is_set():
                if speak:
                    speak("Cancelled that one.")
                return "Task cancelled."

            messages.append({"role": "user", "content": tool_results})
            continue

        elif response.stop_reason in ("end_turn", "stop_sequence"):
            final_text = "".join(b.text for b in response.content if b.type == "text").strip()
            final_text = final_text or "Handled."
            if speak:
                speak(final_text)
            record_episode(f"Completed a task: {goal[:120]} — {final_text[:200]}")
            print(f"[ClaudeAgent] ✅ Done in {iteration + 1} turn(s)")
            return final_text

        elif response.stop_reason == "max_tokens":
            print("[ClaudeAgent] ⚠️ Hit max_tokens mid-turn")
            msg = "That answer ran long — I had to cut it short, but the work up to that point is done."
            if speak:
                speak(msg)
            return msg

        else:
            print(f"[ClaudeAgent] ⚠️ Unexpected stop_reason: {response.stop_reason}")
            break

    msg = "That one took more back-and-forth than expected — stopping here instead of spinning forever."
    if speak:
        speak(msg)
    return msg
