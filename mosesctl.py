#!/usr/bin/env python3
"""Talk to a running Moses from outside — which is how a global keyboard
shortcut reaches him. GNOME on Wayland does not let an app listen for keys
when it is not focused, so the desktop's own shortcut settings run this.

    mosesctl.py toggle      show / hide the HUD
    mosesctl.py mute        mute / unmute the microphone
    mosesctl.py talk        wake him and unmute, as if you said his name   (quiet: mute)
    mosesctl.py wake        wake word on / off
    mosesctl.py persona     switch Moses <-> Mina
    mosesctl.py orb         show / hide the desktop orb
    mosesctl.py show | hide | quit

    mosesctl.py --install-shortcuts     add the two GNOME shortcuts below
    mosesctl.py --remove-shortcuts      take them out again

Standard library only, so it answers in a few milliseconds.
"""

from __future__ import annotations

import ast
import os
import socket
import subprocess
import sys
from pathlib import Path

COMMANDS = ("toggle", "show", "hide", "mute", "talk", "quiet", "wake", "persona", "orb", "quit")
SHORTCUTS = (                     # (id, name, command, default key)
    ("moses-hud", "Moses: show / hide", "toggle", "<Control><Alt>m"),
    ("moses-mute", "Moses: mute / unmute", "mute", "<Control><Alt>space"),
)
_KEYS = "org.gnome.settings-daemon.plugins.media-keys"
_BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"


def socket_path() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or os.path.join(os.path.expanduser("~"), ".moses")
    return os.path.join(base, "moses-hud.sock")


def send(cmd: str, timeout: float = 1.0) -> str | None:
    """Returns his reply, or None when Moses is not running."""
    if not hasattr(socket, "AF_UNIX"):
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(socket_path())
            s.sendall(cmd.encode() + b"\n")
            return s.recv(64).decode("utf-8", "ignore").strip() or "ok"
    except OSError:
        return None


# ── GNOME shortcuts ──────────────────────────────────────────────────────────

def _gs(*args: str) -> str:
    return subprocess.run(["gsettings", *args], capture_output=True, text=True, check=True).stdout.strip()


def _custom_list() -> list[str]:
    raw = _gs("get", _KEYS, "custom-keybindings")
    return list(ast.literal_eval(raw[raw.index("["):])) if "[" in raw else []


def _taken_bindings() -> dict[str, str]:
    """Every key combination GNOME already uses → what uses it."""
    taken: dict[str, str] = {}
    for schema in ("org.gnome.desktop.wm.keybindings", "org.gnome.shell.keybindings",
                   "org.gnome.mutter.keybindings", _KEYS):
        try:
            rows = _gs("list-recursively", schema).splitlines()
        except Exception:
            continue
        for row in rows:
            parts = row.split(" ", 2)
            if len(parts) == 3 and "<" in parts[2]:
                for combo in ast.literal_eval(parts[2]) if parts[2].startswith("[") else [parts[2].strip("'")]:
                    taken.setdefault(str(combo).lower(), parts[1])
    for path in _custom_list():
        sub = f"{_KEYS}.custom-keybinding:{path}"
        try:
            taken.setdefault(_gs("get", sub, "binding").strip("'").lower(), _gs("get", sub, "name").strip("'"))
        except Exception:
            pass
    return taken


def install_shortcuts() -> int:
    me = Path(__file__).resolve()
    paths = _custom_list()
    taken = _taken_bindings()
    for sid, name, cmd, key in SHORTCUTS:
        path = f"{_BASE}{sid}/"
        sub = f"{_KEYS}.custom-keybinding:{path}"
        owner = taken.get(key.lower())
        if owner and owner != name:
            print(f"  {key} is already used by “{owner}” — left “{name}” unset; pick a key in Settings › Keyboard.")
            key = ""
        _gs("set", sub, "name", name)
        _gs("set", sub, "command", f"{sys.executable} {me} {cmd}")
        _gs("set", sub, "binding", key)
        if path not in paths:
            paths.append(path)
        if key:
            print(f"  {key}  →  {name}")
    _gs("set", _KEYS, "custom-keybindings", str(paths))
    return 0


def remove_shortcuts() -> int:
    mine = {f"{_BASE}{sid}/" for sid, *_ in SHORTCUTS}
    for path in mine:
        for field in ("name", "command", "binding"):
            subprocess.run(["gsettings", "reset", f"{_KEYS}.custom-keybinding:{path}", field], capture_output=True)
    _gs("set", _KEYS, "custom-keybindings", str([p for p in _custom_list() if p not in mine]))
    print("  Moses shortcuts removed.")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[1] == "--install-shortcuts":
        return install_shortcuts()
    if len(argv) == 2 and argv[1] == "--remove-shortcuts":
        return remove_shortcuts()
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print(__doc__)
        return 2
    if send(argv[1]) is None:
        print("Moses is not running.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
