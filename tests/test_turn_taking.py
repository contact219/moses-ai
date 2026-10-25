"""Run: env/bin/python -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.turn_taking import BargeDetector, LatencyTimer, duration_seconds, latency_summary, record_latency  # noqa: E402

BLOCK = 64  # ms per mic block (1024 samples at 16 kHz)


QUIET = [300] * 8  # first ~0.5s of a reply: just his (quiet) echo


def run(det, peaks, t0=0.0, audible=True):
    """Feed one peak per block; return the block index that fired, or None."""
    for i, p in enumerate(peaks):
        if det.feed(p, t0 + i * BLOCK, audible):
            return i
    return None


class Barge(unittest.TestCase):
    def test_sustained_close_speech_cuts_him_off(self):
        self.assertIsNotNone(run(BargeDetector(), QUIET + [9000] * 10))

    def test_a_cough_does_not(self):
        self.assertIsNone(run(BargeDetector(), QUIET + [9000] * 3 + [200] * 20))

    def test_nothing_fires_while_he_is_silent(self):
        self.assertIsNone(run(BargeDetector(), [9000] * 20, audible=False))

    def test_loud_speaker_echo_raises_the_bar(self):
        # No echo cancellation on the desktop: his own voice reaches the mic at
        # ~3000. After a moment of that, 6000 (echo + a bit) must not trigger...
        d = BargeDetector()
        self.assertIsNone(run(d, [3000] * 60))
        self.assertGreater(d.threshold(), 8000)
        self.assertIsNone(run(d, [6000] * 10, t0=60 * BLOCK))
        # ...but someone really talking over him (well above the echo) does.
        self.assertIsNotNone(run(d, [16000] * 10, t0=80 * BLOCK))

    def test_loud_echo_from_the_first_word_never_self_interrupts(self):
        # Speakers loud enough that his echo (7000) is over the 4500 floor.
        d = BargeDetector()
        self.assertIsNone(run(d, [7000] * 200))
        d.feed(0, 0, False)                        # reply ends; the next starts
        self.assertIsNone(run(d, [7000] * 200, t0=300 * BLOCK))

    def test_a_long_barge_does_not_teach_it_to_ignore_the_user(self):
        d = BargeDetector()
        run(d, QUIET + [9000] * 10)
        self.assertLess(d.threshold(), 9000)

    def test_cooldown_after_a_barge(self):
        d = BargeDetector()
        first = run(d, QUIET + [9000] * 10)
        self.assertIsNotNone(first)
        self.assertIsNone(run(d, [9000] * 10, t0=(first + 1) * BLOCK))   # inside 1.5s

    def test_breath_gaps_inside_a_phrase_do_not_reset(self):
        self.assertIsNotNone(run(BargeDetector(), QUIET + [9000, 9000, 100, 9000, 9000, 9000, 9000, 9000]))


class Latency(unittest.TestCase):
    def test_real_speech_then_reply(self):
        t = LatencyTimer()
        for i in range(10):
            t.note_sent(5000, BLOCK, i * BLOCK)
        self.assertEqual(t.reply_audible(9 * BLOCK + 1100), 1100)
        self.assertIsNone(t.reply_audible(5000), 'one number per reply')

    def test_no_speech_cough_or_noise_is_not_measured(self):
        t = LatencyTimer()
        self.assertIsNone(t.reply_audible(1000))          # greeting / proactive
        for i in range(50):
            t.note_sent(900, BLOCK, i * BLOCK)              # room noise
        self.assertIsNone(t.reply_audible(5000))
        t.note_sent(9000, BLOCK, 0)                          # one cough block
        self.assertIsNone(t.reply_audible(1000))

    def test_implausibly_fast_is_dropped(self):
        t = LatencyTimer()
        for i in range(10):
            t.note_sent(5000, BLOCK, i * BLOCK)
        self.assertIsNone(t.reply_audible(9 * BLOCK + 50))

    def test_storage_and_summary(self):
        import tempfile
        p = Path(tempfile.mkdtemp()) / 'latency.jsonl'
        for ms in (800, 1000, 1200, 1400):
            record_latency(p, ms)
        s = latency_summary(p)
        self.assertEqual(s['turns'], 4)
        self.assertEqual(s['p50'], 1200)


class GoAway(unittest.TestCase):
    def test_time_left_formats(self):
        from datetime import timedelta
        self.assertEqual(duration_seconds('50s'), 50)
        self.assertEqual(duration_seconds(timedelta(seconds=30)), 30)
        self.assertEqual(duration_seconds(None), 10)


if __name__ == '__main__':
    unittest.main()
