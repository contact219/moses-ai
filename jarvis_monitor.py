#!/usr/bin/env python3
"""
Moses System Monitor Widget
Always-on-top desktop widget with Moses HUD aesthetic
Requirements: pip install PyQt6 psutil
"""

import sys
import psutil
import time
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSizeGrip, QMenu
)
from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QPropertyAnimation,
    QEasingCurve, pyqtProperty, QRect
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont, QFontDatabase,
    QLinearGradient, QBrush, QPolygon, QPainterPath,
    QAction, QCursor
)


# ── Colour Palette ──────────────────────────────────────────────────────────
C_BG        = QColor(5, 10, 20, 210)
C_PANEL     = QColor(10, 20, 40, 180)
C_BORDER    = QColor(0, 180, 255, 80)
C_ACCENT    = QColor(0, 210, 255)
C_ACCENT2   = QColor(0, 255, 180)
C_WARN      = QColor(255, 180, 0)
C_CRIT      = QColor(255, 60, 60)
C_TEXT      = QColor(180, 230, 255)
C_DIM       = QColor(80, 140, 180)
C_GLOW      = QColor(0, 180, 255, 40)


def lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        int(a.red()   + (b.red()   - a.red())   * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue()  + (b.blue()  - a.blue())  * t),
    )


def value_color(pct: float) -> QColor:
    if pct < 0.6:
        return lerp_color(C_ACCENT2, C_ACCENT, pct / 0.6)
    elif pct < 0.85:
        return lerp_color(C_ACCENT, C_WARN, (pct - 0.6) / 0.25)
    else:
        return lerp_color(C_WARN, C_CRIT, (pct - 0.85) / 0.15)


# ── Arc / Bar Gauge ─────────────────────────────────────────────────────────
class ArcGauge(QWidget):
    def __init__(self, label: str, unit: str = "%", parent=None):
        super().__init__(parent)
        self.label = label
        self.unit  = unit
        self._value = 0.0
        self._display = 0.0
        self.setFixedSize(110, 110)

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(16)

    def set_value(self, v: float):
        self._value = max(0.0, min(1.0, v))

    def _tick(self):
        diff = self._value - self._display
        self._display += diff * 0.12
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2
        r = min(w, h) // 2 - 10

        # ── glow backdrop ──
        glow = QRadialGradient = __import__('PyQt6.QtGui', fromlist=['QRadialGradient']).QRadialGradient
        # draw subtle glow circle
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            alpha = 20 - i * 6
            p.setBrush(QBrush(QColor(0, 180, 255, alpha)))
            off = i * 4
            p.drawEllipse(cx - r - off, cy - r - off, (r + off) * 2, (r + off) * 2)

        # ── track ──
        pen = QPen(QColor(20, 50, 80), 5)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(cx - r, cy - r, r * 2, r * 2, 225 * 16, -270 * 16)

        # ── arc fill ──
        col = value_color(self._display)
        pen2 = QPen(col, 5)
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen2)
        span = int(-270 * 16 * self._display)
        p.drawArc(cx - r, cy - r, r * 2, r * 2, 225 * 16, span)

        # ── tick marks ──
        import math
        p.setPen(QPen(C_DIM, 1))
        for i in range(9):
            angle_deg = 225 - i * (270 / 8)
            angle_rad = math.radians(angle_deg)
            r_out = r + 2
            r_in  = r - 5
            x1 = cx + r_out * math.cos(angle_rad)
            y1 = cy - r_out * math.sin(angle_rad)
            x2 = cx + r_in  * math.cos(angle_rad)
            y2 = cy - r_in  * math.sin(angle_rad)
            p.drawLine(int(x1), int(y1), int(x2), int(y2))

        # ── centre value ──
        val_str = f"{int(self._display * 100)}"
        font = QFont("Courier New", 18, QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(col)
        p.drawText(QRect(0, cy - 18, w, 30), Qt.AlignmentFlag.AlignHCenter, val_str)

        # ── unit + label ──
        font2 = QFont("Courier New", 7)
        p.setFont(font2)
        p.setPen(C_DIM)
        p.drawText(QRect(0, cy + 10, w, 14), Qt.AlignmentFlag.AlignHCenter, self.unit)

        font3 = QFont("Courier New", 8, QFont.Weight.Bold)
        p.setFont(font3)
        p.setPen(C_TEXT)
        p.drawText(QRect(0, h - 18, w, 16), Qt.AlignmentFlag.AlignHCenter, self.label)


# ── Horizontal bar ───────────────────────────────────────────────────────────
class BarRow(QWidget):
    def __init__(self, label: str, unit: str = "%", parent=None):
        super().__init__(parent)
        self.label = label
        self.unit  = unit
        self._value   = 0.0
        self._display = 0.0
        self.extra_text = ""
        self.setFixedHeight(28)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def set_value(self, v: float, extra: str = ""):
        self._value = max(0.0, min(1.0, v))
        self.extra_text = extra

    def _tick(self):
        diff = self._value - self._display
        self._display += diff * 0.12
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        label_w = 55
        val_w   = 48
        bar_x   = label_w + 4
        bar_w   = w - label_w - val_w - 8
        bar_h   = 8
        bar_y   = (h - bar_h) // 2

        # label
        font = QFont("Courier New", 8)
        p.setFont(font)
        p.setPen(C_DIM)
        p.drawText(QRect(0, 0, label_w, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.label)

        # track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(20, 50, 80)))
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 3, 3)

        # fill
        col = value_color(self._display)
        fill_w = int(bar_w * self._display)
        if fill_w > 0:
            grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
            grad.setColorAt(0, C_ACCENT2)
            grad.setColorAt(1, col)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 3, 3)

        # value text
        font2 = QFont("Courier New", 8, QFont.Weight.Bold)
        p.setFont(font2)
        p.setPen(col)
        display_str = self.extra_text if self.extra_text else f"{int(self._display * 100)}{self.unit}"
        p.drawText(QRect(bar_x + bar_w + 4, 0, val_w, h),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, display_str)


# ── Network row ──────────────────────────────────────────────────────────────
class NetRow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.down_str = "0 B/s"
        self.up_str   = "0 B/s"
        self.setFixedHeight(22)

    def set_values(self, down_str: str, up_str: str):
        self.down_str = down_str
        self.up_str   = up_str
        self.update()

    @staticmethod
    def fmt(bps: float) -> str:
        if bps < 1024:
            return f"{bps:.0f} B/s"
        elif bps < 1024**2:
            return f"{bps/1024:.1f} KB/s"
        else:
            return f"{bps/1024**2:.1f} MB/s"

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        font = QFont("Courier New", 8)
        p.setFont(font)

        # Down
        p.setPen(C_ACCENT2)
        p.drawText(QRect(0, 0, 14, h), Qt.AlignmentFlag.AlignVCenter, "▼")
        p.setPen(C_TEXT)
        p.drawText(QRect(14, 0, w // 2 - 14, h), Qt.AlignmentFlag.AlignVCenter, self.down_str)

        # Up
        p.setPen(C_WARN)
        p.drawText(QRect(w // 2, 0, 14, h), Qt.AlignmentFlag.AlignVCenter, "▲")
        p.setPen(C_TEXT)
        p.drawText(QRect(w // 2 + 14, 0, w // 2 - 14, h), Qt.AlignmentFlag.AlignVCenter, self.up_str)


# ── Section header ───────────────────────────────────────────────────────────
class SectionHeader(QWidget):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.text = text
        self.setFixedHeight(20)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        font = QFont("Courier New", 7, QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(C_ACCENT)

        text_w = p.fontMetrics().horizontalAdvance(self.text)
        p.drawText(0, h - 5, self.text)

        line_x = text_w + 6
        pen = QPen(C_BORDER, 1)
        p.setPen(pen)
        p.drawLine(line_x, h // 2, w, h // 2)


# ── Main Widget ──────────────────────────────────────────────────────────────
class MosesMonitor(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Moses Monitor")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(280, 420)
        self.resize(300, 480)

        self._drag_pos = None
        self._prev_net = psutil.net_io_counters()
        self._prev_time = time.time()

        self._build_ui()
        self._start_timers()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(6)

        # ── Title bar ──
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 4)

        dot_widget = self._make_dots()
        title_row.addWidget(dot_widget)

        lbl = QLabel("J.A.R.V.I.S  //  SYS MONITOR")
        lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {C_ACCENT.name()}; letter-spacing: 2px;")
        title_row.addWidget(lbl)
        title_row.addStretch()
        root.addLayout(title_row)

        # ── Arc gauges row (CPU + MEM) ──
        root.addWidget(SectionHeader("CORE SYSTEMS"))
        arc_row = QHBoxLayout()
        arc_row.setSpacing(4)
        self.cpu_gauge = ArcGauge("CPU", "%")
        self.mem_gauge = ArcGauge("MEM", "%")
        arc_row.addStretch()
        arc_row.addWidget(self.cpu_gauge)
        arc_row.addStretch()
        arc_row.addWidget(self.mem_gauge)
        arc_row.addStretch()
        root.addLayout(arc_row)

        # ── CPU cores ──
        root.addWidget(SectionHeader("CPU CORES"))
        self.core_bars = []
        cpu_count = psutil.cpu_count(logical=True)
        cores_to_show = min(cpu_count, 8)
        for i in range(cores_to_show):
            bar = BarRow(f"Core {i}", "%")
            self.core_bars.append(bar)
            root.addWidget(bar)

        # ── Disk ──
        root.addWidget(SectionHeader("STORAGE"))
        self.disk_bar = BarRow("Disk /", "%")
        root.addWidget(self.disk_bar)

        # ── Network ──
        root.addWidget(SectionHeader("NETWORK I/O"))
        self.net_row = NetRow()
        root.addWidget(self.net_row)

        # ── Uptime / clock ──
        root.addWidget(SectionHeader("STATUS"))
        self.status_lbl = QLabel("UPTIME  —")
        self.status_lbl.setFont(QFont("Courier New", 8))
        self.status_lbl.setStyleSheet(f"color: {C_DIM.name()};")
        root.addWidget(self.status_lbl)

        root.addStretch()

    def _make_dots(self) -> QWidget:
        w = QWidget()
        w.setFixedSize(36, 12)
        return w

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(C_BG))
        p.drawRoundedRect(0, 0, w, h, 8, 8)

        # outer border
        pen = QPen(C_BORDER, 1)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, w - 2, h - 2, 8, 8)

        # corner accents
        accent_pen = QPen(C_ACCENT, 2)
        p.setPen(accent_pen)
        sz = 12
        # top-left
        p.drawLine(8, 2, 8 + sz, 2)
        p.drawLine(8, 2, 8, 2 + sz)
        # top-right
        p.drawLine(w - 8 - sz, 2, w - 8, 2)
        p.drawLine(w - 8, 2, w - 8, 2 + sz)
        # bottom-left
        p.drawLine(8, h - 2, 8 + sz, h - 2)
        p.drawLine(8, h - 2, 8, h - 2 - sz)
        # bottom-right
        p.drawLine(w - 8 - sz, h - 2, w - 8, h - 2)
        p.drawLine(w - 8, h - 2, w - 8, h - 2 - sz)

        # title bar separator
        p.setPen(QPen(C_BORDER, 1))
        p.drawLine(12, 30, w - 12, 30)

        # status dots (top-left of title)
        colors = [QColor(255, 80, 80), QColor(255, 200, 0), C_ACCENT2]
        for i, c in enumerate(colors):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(c))
            p.drawEllipse(14 + i * 14, 14, 8, 8)

    def _start_timers(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_stats)
        self._timer.start(1000)
        self._update_stats()

    def _update_stats(self):
        # CPU overall
        cpu_pct = psutil.cpu_percent(interval=None) / 100.0
        self.cpu_gauge.set_value(cpu_pct)

        # CPU per core
        per_core = psutil.cpu_percent(percpu=True)
        for i, bar in enumerate(self.core_bars):
            if i < len(per_core):
                bar.set_value(per_core[i] / 100.0)

        # Memory
        mem = psutil.virtual_memory()
        self.mem_gauge.set_value(mem.percent / 100.0)

        # Disk
        try:
            disk = psutil.disk_usage('/')
            used_gb = disk.used / 1024**3
            total_gb = disk.total / 1024**3
            self.disk_bar.set_value(disk.percent / 100.0,
                                    f"{used_gb:.1f}/{total_gb:.0f}G")
        except Exception:
            pass

        # Network
        now = time.time()
        net = psutil.net_io_counters()
        dt = now - self._prev_time
        if dt > 0:
            down_bps = (net.bytes_recv - self._prev_net.bytes_recv) / dt
            up_bps   = (net.bytes_sent - self._prev_net.bytes_sent) / dt
            self.net_row.set_values(NetRow.fmt(down_bps), NetRow.fmt(up_bps))
        self._prev_net  = net
        self._prev_time = now

        # Uptime
        boot = psutil.boot_time()
        up_secs = int(time.time() - boot)
        h = up_secs // 3600
        m = (up_secs % 3600) // 60
        self.status_lbl.setText(f"UPTIME  {h:02d}h {m:02d}m")

    # ── Drag to move ──
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _):
        self._drag_pos = None

    # ── Right-click context menu ──
    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #0a141e;
                color: #b4e6ff;
                border: 1px solid #00b4ff50;
                font-family: 'Courier New';
                font-size: 11px;
            }
            QMenu::item:selected { background: #001e3c; }
        """)
        quit_action = QAction("⏻  Terminate", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        menu.exec(e.globalPos())


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Moses Monitor")
    win = MosesMonitor()
    win.show()
    sys.exit(app.exec())
