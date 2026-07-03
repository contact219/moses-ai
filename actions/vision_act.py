"""Vision-driven control loop (experimental).

Instead of clicking blind, Moses looks at the screen, decides one concrete
action toward a goal, performs it, then looks again — see → act → re-check —
for a few bounded iterations. Needs a real display; can't run headless.
"""

import base64
import io
import json
import re
from typing import Callable

from google.genai import types as gtypes

from core.persona import get_client
from actions.computer_control import computer_control

_MAX_STEPS = 6
_MODEL     = "gemini-2.5-flash"

_DECIDE_PROMPT = """You are driving a computer to accomplish a goal. You are shown a
screenshot that is {w}x{h} pixels. Decide the SINGLE next action.

Return ONLY JSON, no markdown:
{{
  "done": false,            // true when the goal is fully accomplished
  "action": "click|double_click|right_click|type|press|hotkey|scroll|wait",
  "x": 0, "y": 0,           // pixel coordinates for click actions (in the {w}x{h} space)
  "text": "",               // text for the type action
  "key": "enter",           // key for press
  "keys": "ctrl+s",         // combo for hotkey
  "direction": "down",      // for scroll
  "reason": "one short phrase describing this step"
}}

Rules:
- One action at a time. Prefer visible on-screen targets.
- Coordinates must be within the image bounds.
- Set "done": true (and no action) only when the goal is clearly complete.
GOAL: {goal}
"""


def _capture_fullres() -> tuple[bytes, int, int]:
    import mss
    import mss.tools
    with mss.mss() as sct:
        mons   = sct.monitors
        target = mons[1] if len(mons) > 1 else mons[0]
        shot   = sct.grab(target)
        png    = mss.tools.to_png(shot.rgb, shot.size)
    try:
        import PIL.Image
        img = PIL.Image.open(io.BytesIO(png)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue(), img.width, img.height
    except Exception:
        return png, target["width"], target["height"]


def _decide(goal: str, img: bytes, w: int, h: int) -> dict:
    b64 = base64.b64encode(img).decode("ascii")
    resp = get_client().models.generate_content(
        model=_MODEL,
        contents=[gtypes.Content(parts=[
            gtypes.Part(inline_data=gtypes.Blob(mime_type="image/jpeg", data=b64)),
            gtypes.Part(text=_DECIDE_PROMPT.format(goal=goal, w=w, h=h)),
        ])],
    )
    text = re.sub(r"```(?:json)?", "", (resp.text or "")).strip().rstrip("`").strip()
    return json.loads(text)


def vision_act(parameters: dict, player=None, speak: Callable | None = None) -> str:
    goal = (parameters or {}).get("goal", "").strip()
    if not goal:
        return "Tell me what you want me to do on screen."

    if speak:
        speak("On it — watching the screen and working through it.")

    steps_done = []
    for step in range(1, _MAX_STEPS + 1):
        try:
            img, w, h = _capture_fullres()
        except Exception as e:
            return f"I couldn't see the screen to do that: {e}"

        try:
            decision = _decide(goal, img, w, h)
        except Exception as e:
            return f"I looked but couldn't decide the next move: {e}"

        if decision.get("done"):
            summary = "Done — " + (steps_done[-1] if steps_done else goal[:60]) + "."
            if player:
                player.write_log(f"[VisionAct] ✅ {goal[:50]} in {step-1} steps")
            return summary

        action = (decision.get("action") or "").lower()
        reason = decision.get("reason", action)
        if not action:
            return "I couldn't work out the next step on screen."

        params = {"action": action}
        for k in ("x", "y", "text", "key", "keys", "direction"):
            if decision.get(k) not in (None, ""):
                params[k] = decision[k]

        print(f"[VisionAct] Step {step}: {action} — {reason}")
        try:
            computer_control(parameters=params, player=player)
            steps_done.append(reason)
        except Exception as e:
            return f"I got partway there, then hit a snag: {e}"

    return f"I worked through {len(steps_done)} steps on that — take a look and tell me if it needs more."
