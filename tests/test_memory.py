"""Memory rules. Every test runs on temp files — never the real memory/."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import memory.memory_manager as mm  # noqa: E402


class TempMemory(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        self._saved = (mm.MEMORY_PATH, mm.EPISODES_PATH, mm.PENDING_PATH, mm.MEMORY_MAX_CHARS)
        mm.MEMORY_PATH, mm.EPISODES_PATH, mm.PENDING_PATH = d / "lt.json", d / "ep.json", d / "pend.json"

    def tearDown(self):
        mm.MEMORY_PATH, mm.EPISODES_PATH, mm.PENDING_PATH, mm.MEMORY_MAX_CHARS = self._saved


class Trimming(TempMemory):
    def test_protected_facts_survive_any_amount_of_notes(self):
        mm.MEMORY_MAX_CHARS = 600
        mm.save_fact("identity", "name", "Ted")
        mm.save_fact("relationships", "granddaughter", "Stormi")
        mm.save_fact("health", "allergy", "penicillin")
        mm.save_fact("preferences", "shoes", "loves red sneakers", importance="critical")
        for i in range(40):
            mm.save_fact("notes", f"note_{i}", "x" * 60)
        m = mm.load_memory()
        self.assertEqual(m["identity"]["name"]["value"], "Ted")
        self.assertIn("granddaughter", m["relationships"])
        self.assertIn("allergy", m["health"])
        self.assertIn("shoes", m["preferences"])
        self.assertLess(len(m["notes"]), 40, "ordinary notes were trimmed")

    def test_notes_go_before_preferences(self):
        mm.MEMORY_MAX_CHARS = 400
        mm.save_fact("preferences", "food", "pizza")
        for i in range(10):
            mm.save_fact("notes", f"n{i}", "y" * 50)
        self.assertIn("food", mm.load_memory()["preferences"])

    def test_an_update_never_demotes_a_critical_fact(self):
        mm.save_fact("preferences", "meds_time", "8pm", importance="critical")
        mm.save_fact("preferences", "meds_time", "9pm")
        e = mm.load_memory()["preferences"]["meds_time"]
        self.assertEqual((e["value"], e.get("importance")), ("9pm", "critical"))

    def test_replaces_removes_the_old_fact(self):
        mm.save_fact("projects", "training_10k", "training for a 10k")
        mm.save_fact("projects", "half_marathon", "training for a half marathon", replaces="projects/training_10k")
        p = mm.load_memory()["projects"]
        self.assertNotIn("training_10k", p)
        self.assertIn("half_marathon", p)


class Forgetting(TempMemory):
    def test_exact_fact(self):
        mm.save_fact("notes", "secret_word", "pineapple")
        self.assertEqual(len(mm.forget_matching(category="notes", key="secret_word")), 1)
        self.assertNotIn("secret_word", mm.load_memory()["notes"])

    def test_query_is_strict_all_words(self):
        mm.save_fact("notes", "old_address", "12 Elm Street")
        mm.save_fact("notes", "work_address", "400 Main Street")
        gone = mm.forget_matching("old address")
        self.assertEqual(len(gone), 1)
        self.assertIn("work_address", mm.load_memory()["notes"])

    def test_nothing_matched_deletes_nothing(self):
        mm.save_fact("notes", "a", "b c d")
        self.assertEqual(mm.forget_matching("zebra"), [])
        self.assertIn("a", mm.load_memory()["notes"])

    def test_episodes_too(self):
        mm.record_episode("They talked about the lake house sale", ["house"])
        mm.record_episode("They planned a birthday dinner", ["family"])
        gone = mm.forget_matching("lake house")
        self.assertEqual(len(gone), 1)
        self.assertEqual(len(mm.load_episodes()), 1)


class Episodes(TempMemory):
    def test_pending_turns_round_trip(self):
        mm.save_pending(["User: hi", "Moses: hey"])
        self.assertEqual(mm.take_pending(), ["User: hi", "Moses: hey"])
        self.assertEqual(mm.take_pending(), [], "taken once")

    def test_parse(self):
        self.assertEqual(mm.parse_episode("SUMMARY: They booked a flight.\nTAGS: Travel, Houston!, plans"),
                         ("They booked a flight.", ["travel", "houston", "plans"]))
        self.assertIsNone(mm.parse_episode("NONE"))

    def test_episodes_say_how_long_ago(self):
        from datetime import datetime
        t = datetime(2026, 10, 25)
        self.assertEqual(mm._ago("2026-10-25", t), "today")
        self.assertEqual(mm._ago("2026-10-20", t), "5 days ago")
        self.assertEqual(mm._ago("2026-07-08", t), "3 months ago")
        mm.record_episode("They went fishing", [])
        self.assertIn("(today)", mm.format_episodes_for_prompt())
        self.assertNotIn("lately", mm.format_episodes_for_prompt())

    def test_fallback_keeps_their_words(self):
        self.assertIn("my knee hurts", mm.fallback_summary(["User: my knee hurts", "Moses: sorry"]))


class Hybrid(unittest.TestCase):
    def test_rescue_only_when_keywords_fail(self):
        import memory.semantic as sem
        orig = sem.search
        try:
            sem.search = lambda q, k=3: [(0.9, "granddaughter: Stormi"), (0.75, "likes stickers"), (0.5, "noise")]
            self.assertEqual(sem.hybrid_recall("x", "- kw hit"), "- kw hit\n- granddaughter: Stormi")
            r = sem.hybrid_recall("x", "")
            self.assertIn("POSSIBLY related", r)
            self.assertIn("likes stickers", r)
            self.assertNotIn("noise", r)
            sem.search = lambda q, k=3: []
            self.assertEqual(sem.hybrid_recall("x", ""), "")
        finally:
            sem.search = orig


class ByHand(TempMemory):
    """The memory panel: what they change is exactly what is kept."""

    def test_an_edit_replaces_the_value_and_can_clear_the_mark(self):
        mm.save_fact("preferences", "coffee", "black", importance="critical")
        mm.edit_fact("preferences", "coffee", "  oat milk latte  ")
        e = mm.load_memory()["preferences"]["coffee"]
        self.assertEqual(e["value"], "oat milk latte")
        self.assertNotIn("importance", e, "an edit by hand may demote, unlike the model's saves")
        mm.edit_fact("preferences", "coffee", "oat milk latte", importance="critical")
        self.assertEqual(mm.load_memory()["preferences"]["coffee"]["importance"], "critical")

    def test_an_empty_edit_is_refused_and_changes_nothing(self):
        mm.save_fact("notes", "gate_code", "4411")
        with self.assertRaises(ValueError):
            mm.edit_fact("notes", "gate_code", "   ")
        self.assertEqual(mm.load_memory()["notes"]["gate_code"]["value"], "4411")

    def test_delete_takes_only_that_fact(self):
        mm.save_fact("relationships", "brother", "Marcus")
        mm.save_fact("relationships", "sister", "Dana")
        self.assertTrue(mm.delete_fact("relationships", "brother"))
        self.assertFalse(mm.delete_fact("relationships", "brother"))
        self.assertEqual(list(mm.load_memory()["relationships"]), ["sister"])
        self.assertEqual(mm.forget("sister", "relationships"), "Forgotten: relationships/sister")

    def test_episodes_are_edited_and_deleted_one_at_a_time(self):
        mm.record_episode("They talked about the move to Houston.", ["move"])
        mm.record_episode("They talked about the move to Austin.", ["move"])
        first, second = mm.load_episodes()
        self.assertTrue(mm.edit_episode(first, "They decided against Houston."))
        self.assertEqual(mm.load_episodes()[0]["summary"], "They decided against Houston.")
        self.assertFalse(mm.delete_episode(first), "the old text no longer matches anything")
        self.assertTrue(mm.delete_episode(second))
        self.assertEqual([e["summary"] for e in mm.load_episodes()], ["They decided against Houston."])
        with self.assertRaises(ValueError):
            mm.edit_episode(mm.load_episodes()[0], "")


if __name__ == "__main__":
    unittest.main()
