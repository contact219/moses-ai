"""Take a screenshot that actually shows the screen.

On a Wayland desktop an ordinary app cannot read the screen: the old mss
capture returns an all-black image there. The desktop's own screenshot portal
(org.freedesktop.portal.Screenshot) can — GNOME asks once whether to allow it
and then remembers. On X11, Windows and macOS, mss works and is used.

The portal answers over D-Bus, so capturing runs in the Qt main thread.
`capture()` may be called from any thread: off the main thread it hands the
job to the main thread and waits.

GNOME writes each capture to ~/Pictures. The file is read and deleted at once
— these are Moses's screenshots, not the user's.
"""

from __future__ import annotations

import io
import os
import platform
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

MAX_W, MAX_H = 1600, 1000      # plenty to read a screen; keeps each image ~150–300 KB
JPEG_Q = 82
PORTAL_TIMEOUT_S = 8.0


def wayland() -> bool:
    return platform.system() == "Linux" and os.environ.get("XDG_SESSION_TYPE") == "wayland"


def to_jpeg(png_or_any: bytes, max_w: int = MAX_W, max_h: int = MAX_H) -> bytes:
    from PIL import Image
    img = Image.open(io.BytesIO(png_or_any)).convert("RGB")
    img.thumbnail((max_w, max_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_Q)
    return buf.getvalue()


def looks_blank(jpeg: bytes) -> bool:
    """An all-black (or all-one-colour) frame is what a capture that saw nothing looks like."""
    from PIL import Image, ImageStat
    st = ImageStat.Stat(Image.open(io.BytesIO(jpeg)).convert("L"))
    return st.stddev[0] < 1.5


def _mss_png() -> bytes:
    import mss
    import mss.tools
    with mss.mss() as sct:
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        shot = sct.grab(mon)
        return mss.tools.to_png(shot.rgb, shot.size)


def portal_file_path(uri: str) -> Path | None:
    """Only a local file:// result from the portal is read (and later deleted)."""
    u = urlparse(uri or "")
    if u.scheme != "file" or not u.path:
        return None
    return Path(unquote(u.path))


class _Portal:
    """Lives in the Qt main thread. One request at a time."""

    def __init__(self):
        from PyQt6.QtCore import QObject, pyqtSlot
        from PyQt6.QtDBus import QDBusConnection, QDBusMessage

        outer = self

        class _Rx(QObject):
            @pyqtSlot(QDBusMessage)
            def response(self, msg):
                outer._on_response(msg)

        self._bus = QDBusConnection.sessionBus()
        self._rx = _Rx()
        self._handle: str | None = None
        self._result: tuple[int, dict] | None = None
        self._subscribed = self._bus.connect(
            "org.freedesktop.portal.Desktop", "", "org.freedesktop.portal.Request",
            "Response", self._rx.response)

    def _on_response(self, msg):
        if self._handle and msg.path() == self._handle:
            code, results = msg.arguments()
            self._result = (int(code), dict(results))

    def grab_png(self) -> bytes:
        """Blocking, but keeps the Qt event loop turning while it waits."""
        from PyQt6.QtCore import QCoreApplication, QEventLoop
        from PyQt6.QtDBus import QDBusInterface, QDBusMessage
        if not self._subscribed:
            raise RuntimeError("could not listen for the screenshot portal's answer")
        token = f"moses_{os.getpid()}_{int(time.time() * 1000)}"
        iface = QDBusInterface("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                               "org.freedesktop.portal.Screenshot", self._bus)
        self._result = None
        reply = iface.call("Screenshot", "", {"handle_token": token, "interactive": False})
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            raise RuntimeError(f"screenshot portal: {reply.errorMessage()}")
        self._handle = str(reply.arguments()[0])
        deadline = time.monotonic() + PORTAL_TIMEOUT_S
        app = QCoreApplication.instance()
        while self._result is None and time.monotonic() < deadline:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        self._handle = None
        if self._result is None:
            raise RuntimeError("the screenshot portal did not answer (is a permission prompt waiting on screen?)")
        code, results = self._result
        if code != 0:
            raise PermissionError("screenshots are not allowed for Moses — allow them in GNOME Settings › Apps")
        path = portal_file_path(str(results.get("uri", "")))
        if path is None or not path.exists():
            raise RuntimeError(f"the screenshot portal returned no file ({results.get('uri')!r})")
        try:
            return path.read_bytes()
        finally:
            try:
                path.unlink()
            except OSError:
                pass


_portal: _Portal | None = None
_bridge = None          # QObject in the main thread that runs capture jobs for other threads


def _main_thread() -> bool:
    from PyQt6.QtCore import QCoreApplication, QThread
    app = QCoreApplication.instance()
    return app is not None and QThread.currentThread() == app.thread()


def _capture_here() -> bytes:
    global _portal
    if wayland():
        if _portal is None:
            _portal = _Portal()
        jpeg = to_jpeg(_portal.grab_png())
    else:
        jpeg = to_jpeg(_mss_png())
    if looks_blank(jpeg):
        raise RuntimeError("the screenshot came back blank")
    return jpeg


def install_bridge() -> None:
    """Call once from the Qt main thread (MosesUI does)."""
    global _bridge
    from PyQt6.QtCore import QObject, pyqtSignal, Qt

    class _Bridge(QObject):
        job = pyqtSignal(object)

        def __init__(self):
            super().__init__()
            self.job.connect(self._run, Qt.ConnectionType.QueuedConnection)

        def _run(self, box):
            try:
                box["jpeg"] = _capture_here()
            except Exception as e:
                box["error"] = e
            box["done"].set()

    _bridge = _Bridge()


def capture(timeout: float = PORTAL_TIMEOUT_S + 4) -> bytes:
    """A JPEG of the whole primary screen. Raises with a plain reason on failure."""
    try:
        here = _main_thread()
    except Exception:
        here = False
    if here or (_bridge is None and not wayland()):
        return _capture_here()
    if _bridge is None:
        raise RuntimeError("screen capture is not set up (no window running)")
    box = {"done": threading.Event()}
    _bridge.job.emit(box)
    if not box["done"].wait(timeout):
        raise RuntimeError("the screenshot took too long")
    if "error" in box:
        raise box["error"]
    return box["jpeg"]
