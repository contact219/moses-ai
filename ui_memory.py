"""What Moses remembers — and the place to correct it.

Everything he and Mina know about you, from long_term.json (facts) and
episodes.json (past conversations), shown as it is stored. Edit a fact when
it's wrong, mark one to keep always, delete what he shouldn't have kept.
Deleting is immediate, with Undo for a few seconds — no dialog in the way.

He reads memory when a conversation starts, so the window says when your
changes reach him: closing it starts him on a fresh session with the recent
exchanges carried over (MosesLive.memory_changed).
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea,
    QTabWidget, QVBoxLayout, QWidget,
)

import memory.memory_manager as mm

# Shown in this order; anything else he filed lands after these, under its own name.
SECTIONS = [
    ("identity",      "Who you are"),
    ("relationships", "People in your life"),
    ("health",        "Health"),
    ("preferences",   "What you like"),
    ("projects",      "What you're working on"),
    ("wishes",        "Wishes and plans"),
    ("notes",         "Other notes"),
]
UNDO_MS = 7000


def pretty(key: str) -> str:
    return key.replace("_", " ").strip().capitalize() or key


def section_title(cat: str) -> str:
    return dict(SECTIONS).get(cat) or pretty(cat)


def ordered_categories(memory: dict) -> list[str]:
    known = [c for c, _ in SECTIONS]
    extra = sorted(c for c, v in memory.items() if c not in known and isinstance(v, dict) and v)
    return [c for c in known if memory.get(c)] + extra


def matches(words: list[str], *texts: str) -> bool:
    hay = " ".join(texts).lower().replace("_", " ")
    return all(w in hay for w in words)


def when(date: str, time: str = "", today: datetime | None = None) -> str:
    """'Nov 11, 15:05 · today' — the date as people read it, and how long ago."""
    try:
        d = datetime.strptime(date, "%Y-%m-%d")
    except Exception:
        return date or "date unknown"
    label = f"{d.strftime('%b')} {d.day}" + ("" if d.year == (today or datetime.now()).year else f", {d.year}")
    if time:
        label += f", {time}"
    return f"{label} · {mm._ago(date, today)}"


class _Editor(QPlainTextEdit):
    """Ctrl+Enter saves, Esc cancels."""
    save = pyqtSignal()
    cancel = pyqtSignal()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.cancel.emit(); return
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.save.emit(); return
        super().keyPressEvent(e)


class _Row(QFrame):
    """One memory: what it is, Edit / Keep always / Delete, and an editor in place."""

    def __init__(self, panel: "MemoryPanel", name: str, text: str, meta: str,
                 on_save, on_delete, keep: str | None = None, on_keep=None):
        super().__init__()
        C = panel.C
        self._on_save = on_save
        self.setObjectName("row")
        self.setStyleSheet(f"#row{{background:{C.PANEL2}; border:1px solid {C.BORDER}; border-radius:10px;}}"
                           f"#row:hover{{border-color:{C.BORDER_B};}}")
        lay = QVBoxLayout(self); lay.setContentsMargins(14, 10, 10, 10); lay.setSpacing(4)

        top = QHBoxLayout(); top.setSpacing(6)
        if name:
            n = QLabel(name); n.setStyleSheet(f"color:{C.TEXT_MED}; font: 700 9pt; background:transparent; border:none;")
            top.addWidget(n)
        top.addStretch(1)

        def button(label, tip, slot, strong=False):
            b = QPushButton(label); b.setToolTip(tip); b.setCursor(Qt.CursorShape.PointingHandCursor)
            col = C.PRI if strong else C.TEXT_DIM
            b.setStyleSheet(f"QPushButton{{color:{col}; background:transparent; border:none; font: 9pt; padding:2px 6px;}}"
                            f"QPushButton:hover{{color:{C.WHITE};}}")
            b.clicked.connect(slot)
            top.addWidget(b)
            return b

        if keep in ("on", "off"):
            button("★ Kept always" if keep == "on" else "☆ Keep always",
                   "Kept always: never trimmed when memory runs short." if keep == "on"
                   else "Never let this be trimmed when memory runs short.",
                   on_keep, strong=(keep == "on"))
        self._edit_btn = button("Edit", "Correct it", self._start_edit)
        button("Delete", "Forget this (you can undo for a few seconds)", on_delete)
        lay.addLayout(top)

        self._text = QLabel(text); self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._text.setStyleSheet(f"color:{C.WHITE}; font: 11pt; background:transparent; border:none;")
        lay.addWidget(self._text)

        self._editor = _Editor(text)
        self._editor.setToolTip("Ctrl+Enter saves · Esc cancels")
        self._editor.setStyleSheet(f"QPlainTextEdit{{color:{C.WHITE}; background:{C.BG}; border:1px solid {C.PRI};"
                                   f" border-radius:6px; font: 11pt; padding:4px;}}")
        self._editor.setFixedHeight(84)
        self._editor.hide()
        self._editor.save.connect(self._commit)
        self._editor.cancel.connect(self._stop_edit)
        lay.addWidget(self._editor)
        self._err = QLabel(""); self._err.setStyleSheet("color:#ff6688; font: 9pt; background:transparent; border:none;")
        self._err.hide(); lay.addWidget(self._err)

        bottom = QHBoxLayout()
        m = QLabel(meta); m.setStyleSheet(f"color:{C.TEXT_DIM}; font: 8pt; background:transparent; border:none;")
        bottom.addWidget(m); bottom.addStretch(1)
        self._save = QPushButton("Save"); self._cancel = QPushButton("Cancel")
        for b, col in ((self._cancel, C.TEXT_DIM), (self._save, C.PRI)):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{color:{col}; background:transparent; border:1px solid {C.BORDER_B};"
                            f" border-radius:11px; padding:2px 14px; font: 700 9pt;}}"
                            f"QPushButton:hover{{border-color:{C.PRI};}}")
            b.hide(); bottom.addWidget(b)
        self._save.clicked.connect(self._commit)
        self._cancel.clicked.connect(self._stop_edit)
        lay.addLayout(bottom)
        self.text = text

    def _start_edit(self):
        self._text.hide(); self._edit_btn.hide()
        self._editor.setPlainText(self.text); self._editor.show(); self._editor.setFocus()
        self._editor.selectAll()
        self._save.show(); self._cancel.show()

    def _stop_edit(self):
        self._editor.hide(); self._save.hide(); self._cancel.hide(); self._err.hide()
        self._text.show(); self._edit_btn.show()

    def _commit(self):
        try:
            self._on_save(self._editor.toPlainText())
        except ValueError as e:
            self._err.setText(str(e)); self._err.show()


class MemoryPanel(QWidget):
    """The window. `closed_with_changes` fires when it is closed after any change."""

    closed_with_changes = pyqtSignal()

    def __init__(self, theme, who: str = "Moses"):
        super().__init__(None, Qt.WindowType.Window)
        self.C, self.who = theme, who
        self.setWindowTitle(f"What {who} remembers")
        self.resize(640, 760)
        self.setMinimumSize(460, 420)
        self._dirty = False
        self._undo = None                 # (label, restore function)
        self._undo_timer = QTimer(self); self._undo_timer.setSingleShot(True)
        self._undo_timer.timeout.connect(self._drop_undo)

        root = QVBoxLayout(self); root.setContentsMargins(22, 18, 22, 14); root.setSpacing(10)
        self._title = QLabel(); self._sub = QLabel(); self._sub.setWordWrap(True)
        root.addWidget(self._title); root.addWidget(self._sub)

        self._search = QLineEdit(); self._search.setPlaceholderText("Find a memory…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(lambda _: self.refresh())
        root.addWidget(self._search)

        self._tabs = QTabWidget(); self._tabs.setDocumentMode(True)
        self._facts_box, self._facts = self._scroller()
        self._eps_box, self._eps = self._scroller()
        self._tabs.addTab(self._facts_box, "About you")
        self._tabs.addTab(self._eps_box, "Past conversations")
        root.addWidget(self._tabs, 1)

        foot = QHBoxLayout()
        self._count = QLabel()
        self._undo_lbl = QLabel(); self._undo_btn = QPushButton("Undo")
        self._undo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._undo_btn.clicked.connect(self._do_undo)
        foot.addWidget(self._count); foot.addStretch(1); foot.addWidget(self._undo_lbl); foot.addWidget(self._undo_btn)
        root.addLayout(foot)
        self._drop_undo()

        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self._search.setFocus())
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._do_undo)

    @staticmethod
    def _scroller():
        area = QScrollArea(); area.setWidgetResizable(True); area.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget(); lay = QVBoxLayout(inner); lay.setContentsMargins(0, 8, 8, 8); lay.setSpacing(8)
        area.setWidget(inner)
        return area, lay

    # ── showing ──────────────────────────────────────────────────────────────
    def open_for(self, who: str):
        self.who = who
        self.setWindowTitle(f"What {who} remembers")
        self.refresh()
        self.show(); self.raise_(); self.activateWindow()

    def _style(self):
        C = self.C
        self.setStyleSheet(
            f"MemoryPanel{{background:{C.BG};}} QScrollArea, QScrollArea > QWidget > QWidget{{background:{C.BG};}}"
            f"QLineEdit{{color:{C.WHITE}; background:{C.PANEL}; border:1px solid {C.BORDER}; border-radius:8px;"
            f" padding:6px 10px; font: 10pt;}} QLineEdit:focus{{border-color:{C.PRI};}}"
            f"QTabWidget::pane{{border:none;}} QTabBar::tab{{color:{C.TEXT_DIM}; background:transparent;"
            f" padding:6px 14px; font: 700 10pt; border:none; border-bottom:2px solid transparent;}}"
            f"QTabBar::tab:selected{{color:{C.PRI}; border-bottom:2px solid {C.PRI};}}"
            f"QScrollBar:vertical{{background:transparent; width:8px;}} QScrollBar::handle:vertical{{background:{C.BORDER_B};"
            f" border-radius:4px; min-height:30px;}} QScrollBar::add-line, QScrollBar::sub-line{{height:0;}}")
        self._title.setStyleSheet(f"color:{C.WHITE}; font: 700 17pt;")
        self._sub.setStyleSheet(f"color:{C.TEXT_MED}; font: 9pt;")
        self._count.setStyleSheet(f"color:{C.TEXT_DIM}; font: 9pt;")
        self._undo_lbl.setStyleSheet(f"color:{C.TEXT}; font: 9pt;")
        self._undo_btn.setStyleSheet(f"QPushButton{{color:{C.PRI}; background:transparent; border:1px solid {C.PRI};"
                                     f" border-radius:11px; padding:2px 14px; font: 700 9pt;}}")

    @staticmethod
    def _clear(lay):
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w:
                w.hide(); w.setParent(None); w.deleteLater()   # gone now, not at the next idle moment

    def _heading(self, text, always=False):
        h = QLabel(text.upper() + (f"  <span style='color:{self.C.TEXT_DIM}; letter-spacing:0;"
                                   f" font-weight:400'>· always kept</span>" if always else ""))
        h.setStyleSheet(f"color:{self.C.PRI}; font: 700 9pt; letter-spacing:2px; padding-top:8px;")
        if always:
            h.setToolTip("Never trimmed to make room: who you are, your health, your people.")
        return h

    def _empty(self, text):
        e = QLabel(text); e.setWordWrap(True); e.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e.setStyleSheet(f"color:{self.C.TEXT_DIM}; font: 10pt; padding:40px;")
        return e

    def refresh(self):
        self._style()
        other = "Mina" if self.who == "Moses" else "Moses"
        self._title.setText(f"What {self.who} remembers")
        self._sub.setText(f"{self.who} and {other} share all of this. Correct what's wrong, delete what "
                          f"shouldn't be kept — your changes reach them when you close this window.")
        words = self._search.text().lower().split()
        memory, episodes = mm.load_memory(), mm.load_episodes()

        self._clear(self._facts)
        facts = shown = 0
        for cat in ordered_categories(memory):
            rows = []
            for key, entry in memory[cat].items():
                if not (isinstance(entry, dict) and "value" in entry):
                    continue
                facts += 1
                if not matches(words, cat, key, str(entry["value"])):
                    continue
                rows.append(self._fact_row(cat, key, entry))
            if rows:
                self._facts.addWidget(self._heading(section_title(cat), cat in mm.PROTECTED_CATEGORIES))
                for r in rows:
                    self._facts.addWidget(r)
                shown += len(rows)
        if not shown:
            self._facts.addWidget(self._empty("Nothing matches." if words else
                                              f"Nothing yet. As you talk, {self.who} keeps what matters here."))
        self._facts.addStretch(1)

        self._clear(self._eps)
        eps_shown = 0
        for i in range(len(episodes) - 1, -1, -1):          # newest first
            ep = episodes[i]
            if not matches(words, ep.get("summary", ""), " ".join(ep.get("tags", []))):
                continue
            self._eps.addWidget(self._episode_row(i, ep)); eps_shown += 1
        if not eps_shown:
            self._eps.addWidget(self._empty("Nothing matches." if words else "No conversations kept yet."))
        self._eps.addStretch(1)

        self._tabs.setTabText(0, f"About you  {facts}")
        self._tabs.setTabText(1, f"Past conversations  {len(episodes)}")
        self._count.setText(f"Showing {shown + eps_shown}" if words else "")

    def _fact_row(self, cat, key, entry):
        protected = cat in mm.PROTECTED_CATEGORIES
        keep = "always" if protected else ("on" if entry.get("importance") == "critical" else "off")
        meta = f"saved {when(entry.get('updated', ''))}" if entry.get("updated") else ""
        return _Row(self, pretty(key), str(entry["value"]), meta,
                    on_save=lambda text, c=cat, k=key, e=entry: self._save_fact(c, k, e, text),
                    on_delete=lambda _=False, c=cat, k=key, e=entry: self._delete_fact(c, k, e),
                    keep=keep,
                    on_keep=lambda _=False, c=cat, k=key, e=entry: self._toggle_keep(c, k, e))

    def _episode_row(self, index, ep):
        return _Row(self, when(ep.get("date", ""), ep.get("time", "")), ep.get("summary", ""),
                    ", ".join(ep.get("tags", [])),
                    on_save=lambda text, e=ep: self._save_episode(e, text),
                    on_delete=lambda _=False, i=index, e=ep: self._delete_episode(i, e))

    # ── changing ─────────────────────────────────────────────────────────────
    def _changed(self):
        self._dirty = True
        self.refresh()

    def _save_fact(self, cat, key, entry, text):
        if text.strip() == str(entry.get("value", "")).strip():
            self.refresh(); return
        mm.edit_fact(cat, key, text, entry.get("importance"))
        self._offer_undo(f"Changed “{pretty(key)}”.", lambda: mm.restore_fact(cat, key, entry))
        self._changed()

    def _toggle_keep(self, cat, key, entry):
        on = entry.get("importance") != "critical"
        mm.edit_fact(cat, key, str(entry["value"]), "critical" if on else None)
        self._changed()

    def _delete_fact(self, cat, key, entry):
        mm.delete_fact(cat, key)
        self._offer_undo(f"Forgot “{pretty(key)}”.", lambda: mm.restore_fact(cat, key, entry))
        self._changed()

    def _save_episode(self, ep, text):
        if text.strip() == ep.get("summary", "").strip():
            self.refresh(); return
        mm.edit_episode(ep, text)
        edited = dict(ep, summary=text.strip()[:400])
        self._offer_undo("Changed a past conversation.", lambda: mm.edit_episode(edited, ep.get("summary", "")))
        self._changed()

    def _delete_episode(self, index, ep):
        if mm.delete_episode(ep):
            self._offer_undo("Forgot a past conversation.", lambda: mm.restore_episode(ep, index))
        self._changed()

    def _offer_undo(self, label, restore):
        self._undo = restore
        self._undo_lbl.setText(label); self._undo_lbl.show(); self._undo_btn.show()
        self._undo_timer.start(UNDO_MS)

    def _do_undo(self):
        if self._undo is None:
            return
        restore, self._undo = self._undo, None
        restore()
        self._drop_undo()
        self._changed()

    def _drop_undo(self):
        self._undo = None
        self._undo_lbl.hide(); self._undo_btn.hide()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            if self._search.text():
                self._search.clear()
            else:
                self.close()
            return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        self._drop_undo()
        if self._dirty:
            self._dirty = False
            self.closed_with_changes.emit()
        super().closeEvent(e)
