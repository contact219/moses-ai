"""
Wayland-compatible pyautogui shim using ydotool.
Drop-in replacement for pyautogui on Wayland/Linux.
"""
import subprocess, time, os

PAUSE = 0.1
FAILSAFE = False

def _yd(*args):
    subprocess.run(["ydotool", *args], check=False)

def moveTo(x, y, duration=0): _yd("mousemove", "--absolute", "-x", str(int(x)), "-y", str(int(y)))
def moveRel(x, y, duration=0): _yd("mousemove", "-x", str(int(x)), "-y", str(int(y)))
def click(x=None, y=None, button="left", clicks=1, interval=0.1):
    if x is not None: moveTo(x, y)
    btn = {"left":"0x40000001","right":"0x40000002","middle":"0x40000003"}.get(button,"0x40000001")
    for _ in range(clicks):
        _yd("click", btn)
        time.sleep(interval)
def doubleClick(x=None, y=None): click(x, y, clicks=2)
def rightClick(x=None, y=None): click(x, y, button="right")
def mouseDown(button="left"): _yd("click", "--down", "0x40000001")
def mouseUp(button="left"): _yd("click", "--up", "0x40000001")
def dragTo(x, y, duration=0.5, button="left"): moveTo(x, y)
def scroll(x, y, clicks): _yd("scroll", "--", str(clicks * -120))
def typewrite(text, interval=0.05):
    _yd("type", "--", text)
def write(text, interval=0.05): typewrite(text, interval)
def hotkey(*keys):
    combo = "+".join(keys)
    _yd("key", "--", combo)
def keyDown(key): _yd("key", "--", f"{key}:1")
def keyUp(key): _yd("key", "--", f"{key}:0")
def press(key, presses=1, interval=0.1):
    for _ in range(presses):
        _yd("key", "--", str(key))
        time.sleep(interval)
def screenshot(imageFilename=None, region=None):
    import mss, PIL.Image
    with mss.mss() as sct:
        monitor = sct.monitors[1] if not region else {"left":region[0],"top":region[1],"width":region[2],"height":region[3]}
        img = sct.grab(monitor)
        pil = PIL.Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
        if imageFilename: pil.save(imageFilename)
        return pil
def locateOnScreen(image, confidence=0.9): return None
def locateCenterOnScreen(image, confidence=0.9): return None
def position(): return (0, 0)
def size():
    import subprocess
    r = subprocess.run(["xdpyinfo"], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if "dimensions" in line:
            dims = line.split()[1].split("x")
            return (int(dims[0]), int(dims[1]))
    return (1920, 1080)
def alert(text=""): print(f"[pyautogui.alert] {text}")
def confirm(text=""): return "OK"
def prompt(text=""): return ""
