"""Wake word set-up: the keyword list, the switches, and a missing model."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import wake_word as ww


class WakeWordSetupTest(unittest.TestCase):
    def test_every_spelling_reports_its_persona(self):
        lines = ww.keywords_text().strip().splitlines()
        self.assertEqual(len(lines), sum(len(v) for v in ww.KEYWORDS.values()))
        for line in lines:
            self.assertRegex(line, r"^▁[A-Z▁ ]+ :[\d.]+ #[\d.]+ @(moses|mina)$")

    def test_missing_model_or_switch_falls_back_to_always_listening(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(ww.installed(Path(d)))
            with mock.patch.object(ww, "MODEL_DIR", Path(d)), mock.patch.object(ww, "installed", lambda *a: False):
                self.assertIsNone(ww.load())
        with mock.patch.dict(os.environ, {"MOSES_WAKE": "0"}):
            self.assertFalse(ww.wanted())
            self.assertIsNone(ww.load())

    def test_off_unless_chosen_and_the_environment_can_override_for_one_run(self):
        with mock.patch.dict(os.environ, clear=False) as env:
            env.pop("MOSES_WAKE", None)
            self.assertFalse(ww.switched_on(False)); self.assertTrue(ww.switched_on(True))
            env["MOSES_WAKE"] = "1"; self.assertTrue(ww.switched_on(False))
            env["MOSES_WAKE"] = "0"; self.assertFalse(ww.switched_on(True))

    @unittest.skipUnless(ww.installed(), "wake-word model not installed on this machine")
    def test_silence_and_noise_do_not_wake_him(self):
        import numpy as np
        spotter = ww.WakeWord()
        rng = np.random.default_rng(1)
        for chunk in (np.zeros(16000 * 3, np.int16), (rng.standard_normal(16000 * 5) * 900).astype(np.int16)):
            for i in range(0, len(chunk), 1024):
                self.assertIsNone(spotter.feed(chunk[i:i + 1024]))


if __name__ == "__main__":
    unittest.main()
