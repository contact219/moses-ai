"""The living presence: GPU scene for the main HUD, the desktop orb, and the
control channel that lets a desktop shortcut reach a running Moses.

PresenceCanvas replaces the painted rings of ui.HudCanvas with a particle
scene on the graphics card, in the same visual language as the web landing
page — a shell of light turning around the portrait — but driven by the real
audio (core/levels.py): it swells with his voice, draws inward while you
speak, tightens into rings while he thinks, and settles when nothing is
happening. ui.HudCanvas stays as the fallback (MOSES_HUD=classic, or if the
graphics driver refuses the scene).

OrbWindow is the same presence at 150 px: frameless, always on top, parked in
a corner while you work. It is painted on the CPU on purpose — at that size it
costs nothing, and a transparent GL window is the kind of thing drivers break.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import numpy as np

from PyQt6.QtCore import QLineF, QObject, QPoint, QPointF, QRectF, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QAction, QColor, QCursor, QFont, QGuiApplication, QIcon, QPainter, QPainterPath, QPen,
    QPixmap, QRadialGradient,
)
from PyQt6.QtMultimedia import QMediaPlayer, QVideoSink
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtOpenGL import (
    QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram, QOpenGLVersionFunctionsFactory,
    QOpenGLVersionProfile,
)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QMenu, QSizePolicy, QSystemTrayIcon, QWidget

GL_POINTS, GL_FLOAT, GL_BLEND, GL_ONE = 0x0000, 0x1406, 0x0BE2, 1
GL_COLOR_BUFFER_BIT, GL_PROGRAM_POINT_SIZE, GL_POINT_SPRITE = 0x4000, 0x8642, 0x8861

PARTICLES = 14000
ACTIVE_MS, IDLE_MS = 16, 50      # 60 fps while something is happening, 20 fps at rest


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(max(0, min(255, int(a)))); return c


def _rgb(h: str) -> tuple[float, float, float]:
    c = QColor(h); return (c.redF(), c.greenF(), c.blueF())


def control_socket_path() -> str:
    """Where a running Moses listens for mosesctl. Per-user, never on disk for long."""
    base = os.environ.get("XDG_RUNTIME_DIR") or os.path.join(os.path.expanduser("~"), ".moses")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "moses-hud.sock")


# ── portrait: the still face, and the talking loop while he speaks ───────────

class FaceSource(QObject):
    """The persona's portrait. `current()` is the looping video frame while
    speaking, the still otherwise (same rule as the classic HUD)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.still: QPixmap | None = None
        self._frame: QPixmap | None = None
        self._on = False
        self.target = 0          # widest the portrait is drawn, in device pixels
        self._sink = QVideoSink(self)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._player = QMediaPlayer(self)
        self._player.setVideoSink(self._sink)
        self._player.setLoops(QMediaPlayer.Loops.Infinite)

    def set_persona(self, persona: dict):
        px = QPixmap(str(persona["face"]))
        self.still = px if not px.isNull() else None
        self._on = False
        self._frame = None
        self._player.stop()
        video = Path(persona["video"])
        self._player.setSource(QUrl.fromLocalFile(str(video)) if video.exists() else QUrl())

    def _on_frame(self, frame):
        if not self._on:
            return
        img = frame.toImage()
        if not img.isNull():
            if self.target and img.width() > self.target * 1.2:      # never upload more pixels than are drawn
                img = img.scaledToWidth(self.target, Qt.TransformationMode.FastTransformation)
            self._frame = QPixmap.fromImage(img)

    def sync(self, talking: bool):
        want = talking and not self._player.source().isEmpty()
        if want == self._on:
            return
        self._on = want
        if want:
            self._player.play()
        else:
            self._player.pause()
            self._frame = None

    def current(self) -> QPixmap | None:
        return self._frame or self.still


def draw_face(p: QPainter, src: QPixmap, cx: float, cy: float, size: float):
    """Cover-fit `src` into a circle, a little high so the eyes sit on the centre line."""
    rect = QRectF(cx - size / 2, cy - size / 2, size, size)
    clip = QPainterPath(); clip.addEllipse(rect)
    p.save()
    p.setClipPath(clip)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    k = size / min(src.width(), src.height())
    dw, dh = src.width() * k, src.height() * k
    # anchored to the top of the circle; a taller picture shows a little more of its upper half
    p.drawPixmap(QRectF(cx - dw / 2, cy - size / 2 - (dh - size) * 0.42, dw, dh), src, QRectF(src.rect()))
    p.restore()


class Smoother:
    """Follows the meters so the picture moves like sound, not like a bar chart:
    fast up, slower down."""

    def __init__(self, n: int):
        self.out = self.mic = 0.0
        self.bands = np.zeros(n, dtype=np.float32)

    def step(self, out_meter, mic_meter, speaking: bool, muted: bool):
        o = out_meter.level if (out_meter and speaking and not muted) else 0.0
        m = mic_meter.level if (mic_meter and not speaking and not muted) else 0.0
        self.out += (o - self.out) * (0.45 if o > self.out else 0.12)
        self.mic += (m - self.mic) * (0.45 if m > self.mic else 0.10)
        src = out_meter if speaking else mic_meter
        tgt = src.bands if (src is not None and not muted) else 0.0
        self.bands += (tgt - self.bands) * 0.35


def draw_voice_ring(p: QPainter, cx, cy, r, bands: np.ndarray, color: QColor, reach: float, width: float):
    """Bars standing out from a circle: low notes at the top, mirrored left and
    right. One batched draw call — 96 separate strokes cost more than the whole
    particle scene."""
    n = len(bands)
    v = np.concatenate([bands, bands[::-1]])
    ang = -math.pi / 2 + (np.arange(n * 2) + 0.5) / (n * 2) * 2 * math.pi
    ca, sa = np.cos(ang), np.sin(ang)
    r2 = r + reach * v
    lines = [QLineF(cx + ca[i] * r, cy + sa[i] * r, cx + ca[i] * r2[i], cy + sa[i] * r2[i])
             for i in range(n * 2) if v[i] >= 0.02]
    if lines:
        p.setPen(QPen(color, width))
        p.drawLines(lines)


_GLOW: dict[str, QPixmap] = {}


def draw_glow(p: QPainter, cx, cy, radius, color: str, opacity: float):
    """Soft light behind the portrait. The gradient is rendered once per colour
    and then just stretched — a live radial gradient this large is slow."""
    px = _GLOW.get(color)
    if px is None:
        px = QPixmap(256, 256); px.fill(Qt.GlobalColor.transparent)
        g = QRadialGradient(QPointF(128, 128), 128)
        g.setColorAt(0.0, qcol(color, 200)); g.setColorAt(0.5, qcol(color, 46)); g.setColorAt(1.0, qcol(color, 0))
        q = QPainter(px); q.setPen(Qt.PenStyle.NoPen); q.setBrush(g); q.drawEllipse(0, 0, 256, 256); q.end()
        _GLOW[color] = px
    p.setOpacity(max(0.0, min(1.0, opacity)))
    p.drawPixmap(QRectF(cx - radius, cy - radius, radius * 2, radius * 2), px, QRectF(0, 0, 256, 256))
    p.setOpacity(1.0)


# ── the main scene ───────────────────────────────────────────────────────────

_VERT = """
#version 120
attribute vec4 a;                       // four random numbers per particle
uniform vec2 uRes, uC, uPtr;
uniform float uT, uSpin, uFlow, uRad, uOut, uMic, uThink, uDim, uDpr;
uniform vec3 uCol, uAcc, uIn;
varying vec3 vCol; varying float vA;
const float TAU = 6.2831853;
void main() {
  vec3 p; float size; float tw = .62 + .38 * sin(uT * 1.7 + a.w * 40.);
  if (a.z < .52) {
    // The shell around the portrait.
    float th = TAU * a.x + uSpin * (.6 + .8 * a.w);
    float ph = acos(2. * a.y - 1.);
    vec3 d = vec3(sin(ph) * cos(th), cos(ph), sin(ph) * sin(th));
    d.y *= mix(1., .16, uThink);                         // thinking: the sphere tightens into rings
    d.yz = mat2(.92, -.39, .39, .92) * d.yz;             // axis tilted toward the viewer
    float ripple = .5 + .5 * sin(ph * 7. - uT * 9.);
    float r = uRad * (1.17 + .80 * a.w * a.w) * (1. + uOut * (.08 + .34 * ripple)) * (1. - .12 * uMic);
    p = vec3(uC, 0.) + d * r;
    vCol = mix(uCol, uAcc, step(.80, a.w));
    vA = (.85 + 1.1 * uOut + .35 * uThink) * tw;
    size = 2.4 + 5.2 * a.w;
  } else if (a.z < .80) {
    // Breath: light leaves him when he speaks and comes in when you do.
    float ang = TAU * a.x;
    float s = fract(a.y + uFlow * (.45 + .9 * a.w));
    float r = uRad * (1.22 + 3.1 * s);
    p = vec3(uC + vec2(cos(ang), sin(ang)) * r, (a.w - .5) * uRad * 1.4);
    float live = max(uOut, uMic);
    vCol = mix(uCol, uIn, step(uOut, uMic) * smoothstep(.02, .15, uMic));
    vA = (.10 + 1.6 * live) * sin(3.14159 * s) * tw;
    size = 2.0 + 4.6 * a.w;
  } else {
    // Dust across the whole canvas.
    p = vec3(a.x * uRes.x, fract(a.y - uT * .005 * (.4 + a.w)) * uRes.y, (a.w - .5) * 800.);
    vCol = mix(uCol, uAcc, step(.9, a.x));
    vA = .42 * tw;
    size = 1.6 + 3.4 * a.w;
  }
  float sc = 1000. / (1000. + p.z);
  vec2 mid = uRes * .5;
  vec2 q = mid + (p.xy - mid) * sc + uPtr * p.z * .06;
  gl_Position = vec4(q.x / uRes.x * 2. - 1., 1. - q.y / uRes.y * 2., 0., 1.);
  gl_PointSize = size * sc * uDpr;
  vA *= uDim;
}
"""

_FRAG = """
#version 120
varying vec3 vCol; varying float vA;
void main() {
  float d = length(gl_PointCoord - .5);
  float g = smoothstep(.5, 0., d);
  gl_FragColor = vec4(vCol * g * g * vA, 1.);
}
"""


class PresenceCanvas(QOpenGLWidget):
    """Drop-in for ui.HudCanvas: same attributes (muted, speaking, state) and
    set_persona(); additionally reads two AudioMeters."""

    failed = pyqtSignal()        # the driver refused the scene — the window swaps in the classic HUD

    def __init__(self, theme, out_meter=None, mic_meter=None, parent=None):
        super().__init__(parent)
        self.C = theme
        self.out_meter, self.mic_meter = out_meter, mic_meter
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

        self.muted = False
        self.speaking = False
        self.state = "INITIALISING"
        self._label = "M.O.S.E.S"
        self.face = FaceSource(self)
        self._still_cache: tuple[int, QPixmap] | None = None

        self._gl = None
        self._prog: QOpenGLShaderProgram | None = None
        self._buf: QOpenGLBuffer | None = None
        self._ok = True
        self._t0 = time.monotonic()
        self._last = self._t0
        self._spin = 0.0
        self._flow = 0.0
        self._think = 0.0
        self._dim = 1.0
        self._ptr = [0.0, 0.0]
        self._ptr_to = [0.0, 0.0]
        self._sm = Smoother(out_meter.n if out_meter else 48)
        self._busy_until = 0.0
        self.frames = 0

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._tick)
        self._tmr.start(ACTIVE_MS)

    # persona / face ----------------------------------------------------------
    def set_persona(self, persona: dict):
        self._label = persona["title"]
        self.face.set_persona(persona)
        self._still_cache = None
        self.update()

    # pacing ------------------------------------------------------------------
    def _tick(self):
        now = time.monotonic()
        busy = (self.speaking or self.state in ("THINKING", "PROCESSING")
                or self._sm.out > 0.01 or self._sm.mic > 0.02
                or (self.mic_meter is not None and self.mic_meter.level > 0.03))
        if busy:
            self._busy_until = now + 1.5
        want = ACTIVE_MS if now < self._busy_until else IDLE_MS
        if self._tmr.interval() != want:
            self._tmr.setInterval(want)
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        self._last = time.monotonic()
        self._tmr.start()

    def hideEvent(self, e):          # hidden or minimised: draw nothing at all
        super().hideEvent(e)
        self._tmr.stop()
        self.face.sync(False)

    def mouseMoveEvent(self, e):
        self._ptr_to = [e.position().x() / max(1, self.width()) * 2 - 1,
                        e.position().y() / max(1, self.height()) * 2 - 1]

    # GL ----------------------------------------------------------------------
    def initializeGL(self):
        try:
            profile = QOpenGLVersionProfile(); profile.setVersion(2, 0)
            self._gl = QOpenGLVersionFunctionsFactory.get(profile, self.context())
            prog = QOpenGLShaderProgram(self)
            if not (prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, _VERT)
                    and prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, _FRAG)
                    and prog.link()):
                raise RuntimeError(prog.log())
            seeds = np.random.default_rng(7).random(PARTICLES * 4, dtype=np.float32).tobytes()
            buf = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            buf.create(); buf.bind(); buf.allocate(seeds, len(seeds)); buf.release()
            self._prog, self._buf = prog, buf
        except Exception as e:
            print(f"[MOSES] ⚠️ Presence scene unavailable, using the classic HUD: {e}")
            self._ok = False
            QTimer.singleShot(0, self.failed.emit)

    def _advance(self):
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        self._sm.step(self.out_meter, self.mic_meter, self.speaking, self.muted)
        thinking = 1.0 if (self.state in ("THINKING", "PROCESSING") and not self.speaking) else 0.0
        self._think += (thinking - self._think) * min(1.0, dt * 4)
        self._dim += ((0.28 if self.muted else 1.0) - self._dim) * min(1.0, dt * 5)
        self._spin += dt * (0.20 + 1.5 * self._think + 0.5 * self._sm.out)
        self._flow += dt * (0.012 + 0.75 * self._sm.out - 0.85 * self._sm.mic)
        self._ptr[0] += (self._ptr_to[0] - self._ptr[0]) * 0.06
        self._ptr[1] += (self._ptr_to[1] - self._ptr[1]) * 0.06
        self.face.sync(self.speaking and not self.muted)
        return now - self._t0

    def paintGL(self):
        t = self._advance()
        C = self.C
        dpr = self.devicePixelRatioF()
        W, H = self.width(), self.height()
        fw = min(W, H)
        cx, cy = W / 2, H / 2 - fw * 0.035
        r_face = fw * 0.25 * (1.0 + 0.045 * self._sm.out)
        accent = C.MUTED_C if self.muted else C.PRI

        p = QPainter(self)
        if self._ok and self._prog is not None:
            p.beginNativePainting()
            gl, prog = self._gl, self._prog
            bg = QColor(C.BG)
            gl.glViewport(0, 0, int(W * dpr), int(H * dpr))
            gl.glClearColor(bg.redF(), bg.greenF(), bg.blueF(), 1.0)
            gl.glClear(GL_COLOR_BUFFER_BIT)
            gl.glEnable(GL_BLEND); gl.glBlendFunc(GL_ONE, GL_ONE)
            gl.glEnable(GL_PROGRAM_POINT_SIZE); gl.glEnable(GL_POINT_SPRITE)
            prog.bind(); self._buf.bind()
            loc = prog.attributeLocation("a")
            prog.enableAttributeArray(loc)
            prog.setAttributeBuffer(loc, GL_FLOAT, 0, 4, 0)
            f = float
            prog.setUniformValue("uRes", f(W * dpr), f(H * dpr))
            prog.setUniformValue("uC", f(cx * dpr), f(cy * dpr))
            prog.setUniformValue("uPtr", f(self._ptr[0]), f(self._ptr[1]))
            for name, v in (("uT", t), ("uSpin", self._spin), ("uFlow", self._flow), ("uRad", r_face * dpr),
                            ("uOut", self._sm.out), ("uMic", self._sm.mic), ("uThink", self._think),
                            ("uDim", self._dim), ("uDpr", dpr)):
                prog.setUniformValue(name, f(v))
            prog.setUniformValue("uCol", *map(f, _rgb(accent)))
            prog.setUniformValue("uAcc", *map(f, _rgb(C.MUTED_C if self.muted else C.ACC)))
            prog.setUniformValue("uIn", *map(f, _rgb(C.WHITE)))
            gl.glDrawArrays(GL_POINTS, 0, PARTICLES)
            prog.disableAttributeArray(loc)
            self._buf.release(); prog.release()
            gl.glDisable(GL_BLEND)
            p.endNativePainting()
        else:
            p.fillRect(self.rect(), qcol(C.BG))

        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # soft light behind the portrait, breathing with the voice
        draw_glow(p, cx, cy, r_face * (1.9 + 0.5 * self._sm.out), accent,
                  (0.38 + 0.55 * self._sm.out + 0.2 * self._sm.mic) * self._dim)

        # the voice itself, as a ring of bars: his in the persona colour, yours in white
        yours = (not self.speaking) and self._sm.mic > 0.02
        draw_voice_ring(p, cx, cy, r_face * 1.07, self._sm.bands,
                        qcol(C.WHITE if yours else accent, 235 * self._dim), r_face * 0.46, max(1.6, fw * 0.0042))

        src = self.face.current()
        self.face.target = int(r_face * 2 * dpr)
        if src is not None:
            size = r_face * 2
            if src is self.face.still:        # cache the still at this size; video frames change anyway
                key = int(size * dpr * 1.06)
                if not self._still_cache or abs(self._still_cache[0] - key) > 24:
                    self._still_cache = (key, src.scaled(key, key, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                                         Qt.TransformationMode.SmoothTransformation))
                src = self._still_cache[1]
            draw_face(p, src, cx, cy, size)
            if self.muted:
                p.setBrush(qcol(C.BG, 150)); p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(cx, cy), r_face, r_face)
        else:
            p.setPen(QPen(qcol(accent, 200), 1))
            p.setFont(QFont("Courier New", 13, QFont.Weight.Bold))
            p.drawText(QRectF(cx - 90, cy - 14, 180, 28), Qt.AlignmentFlag.AlignCenter, self._label)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(qcol(accent, 150 + 105 * max(self._sm.out, self._sm.mic)), max(2.0, fw * 0.005)))
        p.drawEllipse(QPointF(cx, cy), r_face, r_face)

        # one quiet line of status
        if self.muted:
            txt, col = "MUTED", qcol(C.MUTED_C)
        elif self.speaking:
            txt, col = "SPEAKING", qcol(C.ACC)
        elif self.state in ("THINKING", "PROCESSING"):
            txt, col = self.state, qcol(C.ACC2, 150 + 105 * (0.5 + 0.5 * math.sin(t * 5)))
        elif yours:
            txt, col = "HEARING YOU", qcol(C.WHITE)
        else:
            txt, col = self.state, qcol(C.TEXT_MED, 190)
        font = QFont("Courier New", max(9, int(fw * 0.016)), QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4)
        p.setFont(font); p.setPen(QPen(col, 1))
        p.drawText(QRectF(0, cy + r_face * 1.72, W, 30), Qt.AlignmentFlag.AlignCenter, txt)
        p.end()
        self.frames += 1


# ── the orb ──────────────────────────────────────────────────────────────────

ORB = 150


class OrbWindow(QWidget):
    """Moses at 150 px, always on top. Click: show/hide the HUD. Drag: move it.
    Middle-click: mute. Right-click: menu."""

    clicked = pyqtSignal()
    mute_requested = pyqtSignal()
    menu_requested = pyqtSignal(QPoint)

    def __init__(self, theme, out_meter=None, mic_meter=None, store: Path | None = None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(ORB, ORB)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setWindowTitle("Moses orb")
        self.C = theme
        self.out_meter, self.mic_meter = out_meter, mic_meter
        self.muted = False
        self.speaking = False
        self.state = "LISTENING"
        self._face: QPixmap | None = None
        self._sm = Smoother(out_meter.n if out_meter else 48)
        self._t0 = time.monotonic()
        self._store = store
        self._press: QPoint | None = None
        self._dragged = False
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._tick)
        self._tmr.start(33)
        self._place()

    def set_persona(self, persona: dict):
        px = QPixmap(str(persona["face"]))
        self._face = None if px.isNull() else px.scaled(
            ORB * 2, ORB * 2, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation)
        self.setToolTip(f"{persona['name']} — click to open, right-click for more")
        self.update()

    def _place(self):
        geo = QGuiApplication.primaryScreen().availableGeometry()
        x, y = geo.right() - ORB - 28, geo.bottom() - ORB - 28
        try:
            saved = json.loads(self._store.read_text()) if self._store and self._store.exists() else {}
            sx, sy = int(saved["x"]), int(saved["y"])
            if any(s.availableGeometry().contains(QPoint(sx + ORB // 2, sy + ORB // 2))
                   for s in QGuiApplication.screens()):
                x, y = sx, sy
        except Exception:
            pass
        self.move(x, y)

    def _tick(self):
        self._sm.step(self.out_meter, self.mic_meter, self.speaking, self.muted)
        live = self.speaking or self._sm.out > 0.01 or self._sm.mic > 0.02 or self.state in ("THINKING", "PROCESSING")
        want = 33 if live else 120
        if self._tmr.interval() != want:
            self._tmr.setInterval(want)
        self.update()

    def showEvent(self, e):
        super().showEvent(e); self._tmr.start()

    def hideEvent(self, e):
        super().hideEvent(e); self._tmr.stop()

    def paintEvent(self, _):
        C = self.C
        t = time.monotonic() - self._t0
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = cy = ORB / 2
        accent = C.MUTED_C if self.muted else C.PRI
        live = max(self._sm.out, self._sm.mic)
        thinking = self.state in ("THINKING", "PROCESSING") and not self.speaking and not self.muted
        r = ORB * 0.29 * (1.0 + 0.05 * self._sm.out)

        breathe = 0.5 + 0.5 * math.sin(t * 1.3)
        g = QRadialGradient(QPointF(cx, cy), ORB / 2)
        g.setColorAt(0.0, qcol(accent, 120 + 110 * live))
        g.setColorAt(0.45, qcol(accent, 40 + 16 * breathe + 80 * live))
        g.setColorAt(1.0, qcol(accent, 0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy), ORB / 2, ORB / 2)

        yours = (not self.speaking) and self._sm.mic > 0.02
        draw_voice_ring(p, cx, cy, r + 4, self._sm.bands[::2], qcol(C.WHITE if yours else accent, 240), ORB * 0.17, 2.2)

        if thinking:                       # two arcs chasing each other
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(qcol(C.ACC2, 230), 2.4))
            rect = QRectF(cx - r - 7, cy - r - 7, (r + 7) * 2, (r + 7) * 2)
            p.drawArc(rect, int(-t * 260 * 16), 70 * 16)
            p.drawArc(rect, int((-t * 260 + 180) * 16), 70 * 16)

        p.setBrush(qcol(C.BG)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)
        if self._face is not None:
            draw_face(p, self._face, cx, cy, r * 2)
        if self.muted:
            p.setBrush(qcol(C.BG, 165)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, cy), r, r)
            p.setPen(QPen(qcol(C.MUTED_C), 3))
            p.drawLine(QPointF(cx - r * 0.45, cy + r * 0.45), QPointF(cx + r * 0.45, cy - r * 0.45))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(qcol(accent, 170 + 85 * live), 2.2))
        p.drawEllipse(QPointF(cx, cy), r, r)

    # mouse --------------------------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._dragged = False
        elif e.button() == Qt.MouseButton.MiddleButton:
            self.mute_requested.emit()

    def mouseMoveEvent(self, e):
        if self._press is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        target = e.globalPosition().toPoint() - self._press
        if not self._dragged and (target - self.pos()).manhattanLength() < 6:
            return
        self._dragged = True
        self.move(target)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        self._press = None
        if not self._dragged:
            self.clicked.emit()
        elif self._store:
            try:
                self._store.parent.mkdir(parents=True, exist_ok=True)
                self._store.write_text(json.dumps({"x": self.x(), "y": self.y()}))
            except Exception:
                pass

    def contextMenuEvent(self, e):
        self.menu_requested.emit(e.globalPos())


# ── tray + menu ──────────────────────────────────────────────────────────────

def round_icon(face_path: str, ring: str) -> QIcon:
    size = 128
    px = QPixmap(size, size); px.fill(Qt.GlobalColor.transparent)
    src = QPixmap(face_path)
    p = QPainter(px); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if not src.isNull():
        draw_face(p, src, size / 2, size / 2, size - 12)
    p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(qcol(ring), 6))
    p.drawEllipse(QRectF(6, 6, size - 12, size - 12))
    p.end()
    return QIcon(px)


def build_menu(parent, labels: dict, on: dict) -> QMenu:
    """labels/on are keyed: show, mute, persona, orb, quit."""
    m = QMenu(parent)
    for key in ("show", "mute", "persona", "orb", None, "quit"):
        if key is None:
            m.addSeparator(); continue
        act = QAction(labels[key], m)
        act.triggered.connect(on[key])
        m.addAction(act)
    return m


def make_tray(parent, icon: QIcon) -> QSystemTrayIcon | None:
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray = QSystemTrayIcon(icon, parent)
    tray.show()
    return tray


# ── control channel ──────────────────────────────────────────────────────────

class ControlServer(QObject):
    """One line in, one line out, over a per-user local socket. mosesctl.py is
    the client; a desktop keyboard shortcut runs it."""

    command = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path = control_socket_path()
        self._srv = QLocalServer(self)
        self._srv.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        QLocalServer.removeServer(self.path)       # a stale socket from a crash
        self.ok = self._srv.listen(self.path)
        self._srv.newConnection.connect(self._accept)

    def _accept(self):
        while self._srv.hasPendingConnections():
            sock = self._srv.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._read(s))
            sock.disconnected.connect(sock.deleteLater)

    def _read(self, sock):
        line = bytes(sock.readAll()).decode("utf-8", "ignore").strip().split("\n")[0][:40]
        if line:
            self.command.emit(line)
            sock.write(b"ok\n"); sock.flush()
        sock.disconnectFromServer()

    def close(self):
        self._srv.close()
        QLocalServer.removeServer(self.path)
