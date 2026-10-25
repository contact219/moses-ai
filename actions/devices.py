"""Audio + camera device access.

Lets Moses see every microphone, speaker and webcam attached to the machine and
choose which one to use. Selections are stored in config/api_keys.json
(audio_input_device / audio_output_device / camera_index) and honored by the
main mic/speaker streams and the vision camera capture.
"""

import glob
import platform
from pathlib import Path

from memory.config_manager import get_config_value, set_config_value

# Config keys shared with main.py and screen_processor.py
KEY_MIC     = "audio_input_device"
KEY_SPEAKER = "audio_output_device"
KEY_CAMERA  = "camera_index"


# ── audio ──────────────────────────────────────────────────────────────────

def _query_audio() -> list[dict]:
    try:
        import sounddevice as sd
        return list(sd.query_devices())
    except Exception as e:
        print(f"[Devices] ⚠️ Could not query audio devices: {e}")
        return []


def _default_hostapi() -> int | None:
    """Windows lists every device once per audio API (MME, DirectSound, WASAPI,
    WDM-KS). Keep only the API the system default device uses — the one the
    mic/speaker streams already work with — so each device shows up once."""
    if platform.system() != "Windows":
        return None
    try:
        import sounddevice as sd
        return sd.query_devices(kind="input")["hostapi"]
    except Exception:
        return None


def _list(channels_key: str) -> list[tuple[int, str]]:
    api = _default_hostapi()
    return [(i, d["name"]) for i, d in enumerate(_query_audio())
            if d.get(channels_key, 0) > 0 and (api is None or d.get("hostapi") == api)]


def list_microphones() -> list[tuple[int, str]]:
    return _list("max_input_channels")


def list_speakers() -> list[tuple[int, str]]:
    return _list("max_output_channels")


def get_audio_device(kind: str) -> int | None:
    """Return the configured device index for 'input'/'output', or None (system default)."""
    key = KEY_MIC if kind == "input" else KEY_SPEAKER
    val = get_config_value(key)
    return int(val) if isinstance(val, int) or (isinstance(val, str) and val.isdigit()) else None


def _match_device(query: str, devices: list[tuple[int, str]]) -> tuple[int, str] | None:
    if not query:
        return None
    q = query.strip().lower()
    if q.isdigit():
        idx = int(q)
        for i, name in devices:
            if i == idx:
                return (i, name)
    for i, name in devices:
        if q in name.lower():
            return (i, name)
    return None


# ── cameras ────────────────────────────────────────────────────────────────

def list_cameras() -> list[tuple[int, str]]:
    """Enumerate webcams. On Linux use /dev/video*; elsewhere (Windows) probe
    indices 0-5. Either way, confirm each one opens."""
    cams: list[tuple[int, str]] = []
    try:
        from actions.screen_processor import _probe_camera, _cv2_backend
        backend = _cv2_backend()
    except Exception:
        _probe_camera, backend = None, 0

    video_nodes = sorted(glob.glob("/dev/video*"))
    indices = ([int(Path(v).name.replace("video", "")) for v in video_nodes if v[-1].isdigit()]
               or list(range(6)))

    for idx in sorted(set(indices)):
        label = f"Camera {idx}" + (f" (/dev/video{idx})" if Path(f"/dev/video{idx}").exists() else "")
        if _probe_camera is None:
            cams.append((idx, label))
        elif _probe_camera(idx, backend):
            cams.append((idx, label + " ✓"))
    return cams


# ── tool entrypoint ──────────────────────────────────────────────────────────

def devices(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "list").lower().strip()
    query  = (params.get("name") or params.get("index") or "").strip()

    if action == "list":
        mics     = list_microphones()
        speakers = list_speakers()
        cams     = list_cameras()

        cur_mic  = get_config_value(KEY_MIC, "system default")
        cur_spk  = get_config_value(KEY_SPEAKER, "system default")
        cur_cam  = get_config_value(KEY_CAMERA, "auto")

        lines = ["Devices attached to this system:", ""]
        lines.append("Microphones:")
        lines += [f"  [{i}] {n}" for i, n in mics] or ["  (none found)"]
        lines.append(f"  → in use: {cur_mic}")
        lines.append("Speakers:")
        lines += [f"  [{i}] {n}" for i, n in speakers] or ["  (none found)"]
        lines.append(f"  → in use: {cur_spk}")
        lines.append("Cameras:")
        lines += [f"  [{i}] {n}" for i, n in cams] or ["  (none found)"]
        lines.append(f"  → in use: {cur_cam}")
        report = "\n".join(lines)
        if player:
            player.write_log("[Devices] listed audio + camera devices")
        return report

    if action in ("set_microphone", "use_microphone", "set_mic"):
        m = _match_device(query, list_microphones())
        if not m:
            return f"I couldn't find a microphone matching '{query}'."
        set_config_value(KEY_MIC, m[0])
        return f"Microphone set to [{m[0]}] {m[1]}. It'll take effect on the next reconnect."

    if action in ("set_speaker", "use_speaker", "set_output"):
        m = _match_device(query, list_speakers())
        if not m:
            return f"I couldn't find a speaker matching '{query}'."
        set_config_value(KEY_SPEAKER, m[0])
        return f"Speaker set to [{m[0]}] {m[1]}. It'll take effect on the next reconnect."

    if action in ("set_camera", "use_camera"):
        m = _match_device(query, list_cameras())
        if not m:
            return f"I couldn't find a camera matching '{query}'."
        set_config_value(KEY_CAMERA, m[0])
        return f"Camera set to [{m[0]}] {m[1]}."

    if action == "reset":
        for k in (KEY_MIC, KEY_SPEAKER):
            set_config_value(k, None)
        return "Reset audio devices back to the system defaults."

    return f"Unknown device action '{action}'. Try: list, set_microphone, set_speaker, set_camera, reset."
