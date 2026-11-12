"""Echo cancellation for the voice loop (Linux, PipeWire or PulseAudio).

Without it the mic hears Moses coming out of the speakers, so barge-in has to
guess a loudness threshold above his own echo. With it, the audio server
subtracts what is being played from what the mic hears (WebRTC AEC) before the
app ever sees it, and talking over him works on open speakers.

How: load the server's echo-cancel module, which makes a virtual mic and a
virtual speaker, then move THIS process's two audio streams onto them. Nothing
else on the machine is touched: the system's default devices are put back if
loading the module changed them, and the module is unloaded on exit if we were
the ones who loaded it.

Set MOSES_AEC=0 to switch it off.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess

SOURCE = "moses_mic"
SINK = "moses_spk"

_loaded_module: str | None = None


def _pactl(*args: str, timeout: float = 4.0) -> str | None:
    try:
        r = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None
    return r.stdout if r.returncode == 0 else None


def available() -> bool:
    return (platform.system() == "Linux" and os.environ.get("MOSES_AEC", "1") != "0"
            and shutil.which("pactl") is not None and _pactl("info") is not None)


def parse_short(text: str | None) -> list[list[str]]:
    """`pactl list short …` → rows of tab-separated fields."""
    return [line.split("\t") for line in (text or "").splitlines() if line.strip()]


def pick_mic(default_source: str, sources: list[str]) -> str | None:
    """The real microphone to clean up. A '.monitor' source is a recording of a
    speaker, not a mic — and a machine with no mic plugged in often has one as
    its default — so skip those, and our own virtual mic."""
    real = [s for s in sources if not s.endswith(".monitor") and s != SOURCE]
    if default_source in real:
        return default_source
    return real[0] if real else None


def parse_streams(text: str | None) -> list[tuple[str, str]]:
    """`pactl list source-outputs|sink-inputs` → [(stream id, client id)]."""
    out, cur = [], None
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith(("Source Output #", "Sink Input #")):
            cur = s.split("#", 1)[1]
        elif cur and s.startswith("Client:"):
            out.append((cur, s.split(":", 1)[1].strip()))
            cur = None
    return out


def parse_clients(text: str | None) -> dict[str, str]:
    """`pactl list clients` → {client id: pid}. A stream opened through the ALSA
    layer carries no pid of its own; its client does."""
    out, cur = {}, None
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("Client #"):
            cur = s.split("#", 1)[1]
        elif cur and s.startswith("application.process.id"):
            out[cur] = s.split("=", 1)[1].strip().strip('"')
    return out


def _module_id() -> str | None:
    for row in parse_short(_pactl("list", "short", "modules")):
        if len(row) >= 3 and row[1] == "module-echo-cancel" and f"source_name={SOURCE}" in row[2]:
            return row[0]
    return None


def enable() -> str:
    """Make sure the virtual mic/speaker exist. Returns a one-line status for the log."""
    global _loaded_module
    if not available():
        return "off (not available on this system)"
    existing = _module_id()
    if existing:
        # Only one Moses runs at a time (main.py checks first), so this is left
        # over from a run that ended without cleaning up: adopt it, so it is
        # removed when this one quits.
        _loaded_module = existing
        return "on (reusing the pair from an earlier run)"
    default_sink = (_pactl("get-default-sink") or "").strip()
    default_source = (_pactl("get-default-source") or "").strip()
    sources = [r[1] for r in parse_short(_pactl("list", "short", "sources")) if len(r) > 1]
    mic = pick_mic(default_source, sources)
    if not mic or not default_sink:
        return "off (no microphone found)"
    mod = _pactl(
        "load-module", "module-echo-cancel", "aec_method=webrtc",
        f"source_name={SOURCE}", f"sink_name={SINK}",
        f"source_master={mic}", f"sink_master={default_sink}",
        "source_properties='device.description=\"Moses mic (echo-cancelled)\"'",
        "sink_properties='device.description=\"Moses voice\"'",
        timeout=8.0,
    )
    if not mod or not mod.strip().isdigit():
        return "off (the audio server refused the echo-cancel module)"
    _loaded_module = mod.strip()
    # A new device can become the system default. This is for Moses only: put it back.
    if (_pactl("get-default-sink") or "").strip() != default_sink:
        _pactl("set-default-sink", default_sink)
    if default_source and (_pactl("get-default-source") or "").strip() != default_source:
        _pactl("set-default-source", default_source)
    return f"on (mic: {mic})"


def route(pid: int | None = None) -> tuple[bool, bool]:
    """Move this process's mic and speaker streams onto the echo-cancelled pair.
    Returns (mic moved, speaker moved). Call once both streams are open."""
    if not _module_id():
        return (False, False)
    pid = str(pid or os.getpid())
    mine = {c for c, owner in parse_clients(_pactl("list", "clients")).items() if owner == pid}
    mic = spk = False
    for sid, client in parse_streams(_pactl("list", "source-outputs")):
        if client in mine and _pactl("move-source-output", sid, SOURCE) is not None:
            mic = True
    for sid, client in parse_streams(_pactl("list", "sink-inputs")):
        if client in mine and _pactl("move-sink-input", sid, SINK) is not None:
            spk = True
    return (mic, spk)


def disable() -> None:
    """Unload the module if this process loaded it."""
    global _loaded_module
    if _loaded_module:
        _pactl("unload-module", _loaded_module)
        _loaded_module = None
