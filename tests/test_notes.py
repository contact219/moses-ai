"""Notes he puts on screen: what is kept, and how much."""
import json
import tempfile
import unittest
from pathlib import Path

from core import notes


class NotesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Path(self.dir.name) / "notes.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_a_note_is_kept_and_comes_back_in_order(self):
        a = notes.add("Dentist", "1200 Main Street", store=self.store)
        b = notes.add("For your brother", "I've been putting this off.", "line", store=self.store)
        self.assertEqual([n["id"] for n in notes.recent(3, store=self.store)], [a["id"], b["id"]])
        self.assertEqual(b["kind"], "line")
        self.assertEqual(json.loads(self.store.read_text())[0]["body"], "1200 Main Street")

    def test_nothing_to_show_is_refused_and_odd_input_is_tidied(self):
        with self.assertRaises(ValueError):
            notes.add("Empty", "   ", store=self.store)
        n = notes.add("", "x", "poster", store=self.store)
        self.assertEqual((n["title"], n["kind"]), ("Note", "note"))
        self.assertEqual(notes.recent(0, store=self.store), [])

    def test_only_the_newest_are_kept(self):
        for i in range(notes.KEEP + 5):
            notes.add(f"n{i}", str(i), store=self.store)
        kept = json.loads(self.store.read_text())
        self.assertEqual(len(kept), notes.KEEP)
        self.assertEqual(kept[-1]["body"], str(notes.KEEP + 4))

    def test_a_damaged_store_does_not_stop_a_new_note(self):
        self.store.write_text("{not json")
        notes.add("ok", "still works", store=self.store)
        self.assertEqual(notes.recent(1, store=self.store)[0]["body"], "still works")


if __name__ == "__main__":
    unittest.main()
