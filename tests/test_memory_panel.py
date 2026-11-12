"""The memory panel and the reply meter. Temp files only — never the real memory/."""
import json
import os
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import memory.memory_manager as mm  # noqa: E402
import ui_memory  # noqa: E402
from core.turn_taking import latency_summary, recent_latencies  # noqa: E402


class Theme:
    BG = PANEL = PANEL2 = BAR_BG = "#000000"
    BORDER = BORDER_A = BORDER_B = PRI_GHO = "#222222"
    PRI = TEXT = TEXT_MED = TEXT_DIM = WHITE = GREEN = ACC = RED = "#ffffff"


_APP = None


def app():
    global _APP
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication([])   # kept: a collected app takes its widgets down
    return _APP


class Helpers(unittest.TestCase):
    def test_sections_come_in_a_human_order_and_odd_ones_follow(self):
        mem = {"notes": {"a": {}}, "identity": {"b": {}}, "stormi_interests": {"c": {}}, "wishes": {}}
        self.assertEqual(ui_memory.ordered_categories(mem), ["identity", "notes", "stormi_interests"])
        self.assertEqual(ui_memory.section_title("stormi_interests"), "Stormi interests")
        self.assertEqual(ui_memory.section_title("relationships"), "People in your life")

    def test_search_needs_every_word(self):
        self.assertTrue(ui_memory.matches(["red", "color"], "preferences", "favorite_color", "red"))
        self.assertFalse(ui_memory.matches(["blue"], "preferences", "favorite_color", "red"))
        self.assertTrue(ui_memory.matches([], "anything"))

    def test_dates_read_like_people_say_them(self):
        today = datetime(2026, 11, 11)
        self.assertEqual(ui_memory.when("2026-11-11", "15:05", today), "Nov 11, 15:05 · today")
        self.assertEqual(ui_memory.when("2025-05-29", "", today), "May 29, 2025 · 17 months ago")
        self.assertEqual(ui_memory.when("", ""), "date unknown")


class Panel(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        self._saved = (mm.MEMORY_PATH, mm.EPISODES_PATH)
        mm.MEMORY_PATH, mm.EPISODES_PATH = d / "lt.json", d / "ep.json"
        mm.save_fact("identity", "name", "Ted")
        mm.save_fact("preferences", "favorite_color", "red")
        mm.record_episode("They planned the trip to Houston.", ["travel"])
        app()
        self.panel = ui_memory.MemoryPanel(Theme(), "Mina")
        self.fired = []
        self.panel.closed_with_changes.connect(lambda: self.fired.append(1))
        self.panel.open_for("Mina")

    def tearDown(self):
        self.panel.close()
        mm.MEMORY_PATH, mm.EPISODES_PATH = self._saved

    def test_it_shows_what_is_stored(self):
        self.assertEqual(self.panel._tabs.tabText(0), "About you  2")
        self.assertEqual(self.panel._tabs.tabText(1), "Past conversations  1")
        self.assertIn("Mina", self.panel._title.text())

    def test_delete_then_undo_puts_it_back_exactly(self):
        before = mm.load_memory()["preferences"]["favorite_color"]
        self.panel._delete_fact("preferences", "favorite_color", before)
        self.assertNotIn("favorite_color", mm.load_memory()["preferences"])
        self.panel._do_undo()
        self.assertEqual(mm.load_memory()["preferences"]["favorite_color"], before)

    def test_edit_keep_and_episode_changes_are_saved_and_announced_on_close(self):
        e = mm.load_memory()["preferences"]["favorite_color"]
        self.panel._save_fact("preferences", "favorite_color", e, "green")
        e = mm.load_memory()["preferences"]["favorite_color"]
        self.assertEqual(e["value"], "green")
        self.panel._toggle_keep("preferences", "favorite_color", e)
        self.assertEqual(mm.load_memory()["preferences"]["favorite_color"]["importance"], "critical")
        ep = mm.load_episodes()[0]
        self.panel._delete_episode(0, ep)
        self.assertEqual(mm.load_episodes(), [])
        self.panel._do_undo()
        self.assertEqual(mm.load_episodes(), [ep])
        self.assertEqual(self.fired, [])
        self.panel.close()
        self.assertEqual(self.fired, [1], "closing after changes tells the voice loop once")

    def test_closing_without_changes_says_nothing(self):
        e = mm.load_memory()["preferences"]["favorite_color"]
        self.panel._save_fact("preferences", "favorite_color", e, "  red ")   # same text: not a change
        self.panel.close()
        self.assertEqual(self.fired, [])

    def test_search_filters_both_tabs(self):
        self.panel._search.setText("houston")
        self.assertEqual(self.panel._count.text(), "Showing 1")


class ReplyTimes(unittest.TestCase):
    def test_recent_turns_feed_the_meter_oldest_first(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "lat.jsonl"
            now = int(time.time())
            lines = [{"t": now - 30 * 86400, "ms": 9000}] + [{"t": now - 10 + i, "ms": 1000 + i} for i in range(30)]
            p.write_text("".join(json.dumps(x) + "\n" for x in lines))
            got = recent_latencies(p, 24)
            self.assertEqual(len(got), 24)
            self.assertEqual(got[-1], 1029)
            self.assertNotIn(9000, got, "older than a week is left out")
            self.assertEqual(latency_summary(p)["turns"], 30)
            self.assertEqual(recent_latencies(Path(d) / "missing.jsonl"), [])

    def test_the_meter_keeps_the_last_few_and_colours_by_speed(self):
        app()
        from ui_presence import ReplyMeter
        m = ReplyMeter(Theme())
        m.set_data(None, None, list(range(100, 4000, 100)))
        self.assertEqual(len(m.history), ReplyMeter.KEEP)
        m.set_data(800, {"turns": 3, "p50": 900, "p90": 2000})
        self.assertEqual(m.history[-1], 800)
        m.resize(200, 84)
        m.grab()                                   # paints without error


if __name__ == "__main__":
    unittest.main()
