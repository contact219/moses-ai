"""Live audio levels for the HUD.

The voice loop hands every chunk it plays (his voice) and every chunk it hears
(the mic) to a meter; the HUD reads `level` and `bands` each frame. So what
moves on screen is the actual sound, not a random number.

Cheap enough for the audio threads: one small FFT per ~64 ms chunk. Readers
never lock — a feed swaps in new values, and a frame that reads between two
feeds just sees the previous ones.
"""

from __future__ import annotations

import time

import numpy as np

BANDS = 48            # bars in the voice ring
_FULL_SCALE = 32768.0
_LEVEL_GAIN = 3.2     # speech RMS sits around 0.05–0.25 of full scale
_HOLD_S = 0.25        # after the last chunk, hold the level this long, then fall away


class AudioMeter:
    def __init__(self, sample_rate: int, bands: int = BANDS, lo_hz: float = 90.0, hi_hz: float = 6000.0):
        self.sample_rate = sample_rate
        self.n = bands
        self._edges_hz = np.geomspace(lo_hz, min(hi_hz, sample_rate / 2 - 1), bands + 1)
        self._level = 0.0
        self._bands = np.zeros(bands, dtype=np.float32)
        self._fed_at = 0.0
        self._win: np.ndarray | None = None
        self._idx: list[tuple[int, int]] | None = None

    def feed(self, samples) -> None:
        """samples: int16 PCM as bytes or an array (any shape; mono is assumed)."""
        if samples is None:
            return
        if isinstance(samples, (bytes, bytearray, memoryview)):
            x = np.frombuffer(samples, dtype=np.int16)
        else:
            x = np.asarray(samples).reshape(-1)
        if x.size < 32:
            return
        x = x.astype(np.float32) / _FULL_SCALE
        level = min(1.0, float(np.sqrt(np.mean(x * x))) * _LEVEL_GAIN)

        if self._win is None or self._win.size != x.size:
            self._win = np.hanning(x.size).astype(np.float32)
            freqs = np.fft.rfftfreq(x.size, 1.0 / self.sample_rate)
            lo = np.searchsorted(freqs, self._edges_hz[:-1])
            hi = np.maximum(np.searchsorted(freqs, self._edges_hz[1:]), lo + 1)
            self._idx = list(zip(lo.tolist(), hi.tolist()))
        mag = np.abs(np.fft.rfft(x * self._win)) / (x.size / 4)
        bands = np.fromiter((mag[a:b].max() if a < mag.size else 0.0 for a, b in self._idx),
                            dtype=np.float32, count=self.n)
        # Speech is bottom-heavy; a square root and a gentle tilt keep the top bars alive.
        bands = np.minimum(1.0, np.sqrt(bands) * np.linspace(1.6, 3.4, self.n, dtype=np.float32))

        self._bands = bands
        self._level = level
        self._fed_at = time.monotonic()

    def _decay(self) -> float:
        idle = time.monotonic() - self._fed_at
        if idle <= _HOLD_S:
            return 1.0
        return max(0.0, 1.0 - (idle - _HOLD_S) * 4.0)

    @property
    def level(self) -> float:
        """0..1 loudness right now; falls to 0 shortly after the audio stops."""
        return self._level * self._decay()

    @property
    def bands(self) -> np.ndarray:
        """`n` values 0..1, low to high frequency."""
        return self._bands * self._decay()

    def silence(self) -> None:
        self._fed_at = 0.0
