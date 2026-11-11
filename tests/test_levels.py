"""The HUD's audio meter: what it draws has to be the sound, and it has to fall
silent when the sound stops."""
import time
import unittest

import numpy as np

from core.levels import AudioMeter, BANDS


def tone(hz, rate, n=1024, amp=8000):
    return (np.sin(2 * np.pi * hz * np.arange(n) / rate) * amp).astype(np.int16)


class AudioMeterTest(unittest.TestCase):
    def test_silence_is_zero(self):
        m = AudioMeter(24000)
        m.feed(np.zeros(1024, dtype=np.int16))
        self.assertEqual(m.level, 0.0)
        self.assertEqual(float(m.bands.max()), 0.0)

    def test_louder_reads_higher_and_stays_in_range(self):
        m = AudioMeter(24000)
        m.feed(tone(220, 24000, amp=1500)); quiet = m.level
        m.feed(tone(220, 24000, amp=12000)); loud = m.level
        m.feed(tone(220, 24000, amp=32767)); peak = m.level
        self.assertGreater(loud, quiet)
        self.assertLessEqual(peak, 1.0)
        self.assertLessEqual(float(m.bands.max()), 1.0)

    def test_a_low_note_and_a_high_note_light_different_bars(self):
        m = AudioMeter(24000)
        m.feed(tone(150, 24000)); low = int(m.bands.argmax())
        m.feed(tone(3000, 24000)); high = int(m.bands.argmax())
        self.assertEqual(len(m.bands), BANDS)
        self.assertLess(low, BANDS // 3)
        self.assertGreater(high, BANDS // 2)

    def test_accepts_bytes_and_2d_mic_frames(self):
        m = AudioMeter(16000)
        m.feed(tone(300, 16000).tobytes()); a = m.level       # playback chunks arrive as bytes
        m.feed(tone(300, 16000).reshape(-1, 1)); b = m.level  # mic frames arrive as (n, 1)
        self.assertAlmostEqual(a, b, places=5)
        m.feed(b""); m.feed(None)                              # nothing to read is not an error
        self.assertAlmostEqual(m.level, b, places=5)

    def test_falls_away_after_the_audio_stops(self):
        m = AudioMeter(24000)
        m.feed(tone(220, 24000))
        self.assertGreater(m.level, 0.1)
        m._fed_at = time.monotonic() - 1.0      # a second since the last chunk
        self.assertEqual(m.level, 0.0)
        self.assertEqual(float(m.bands.max()), 0.0)


if __name__ == "__main__":
    unittest.main()
