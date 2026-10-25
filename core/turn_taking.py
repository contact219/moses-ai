"""Turn-taking helpers for the live voice loop: voice barge-in and turn latency.

Pure logic, no audio or network, so it can be tested on its own. Ported from
the Moses/Mina web app, where the same numbers were tuned by ear.

The one desktop difference: the browser gets echo cancellation for free and
sounddevice does not, so Moses's own voice from the speakers can reach the mic
loudly. The barge threshold therefore rises with the echo level actually
measured while he talks — it has to beat both a fixed floor and a multiple of
that running echo estimate. The estimate is learned in the first moments of
each reply (nobody talks over a reply that has barely started) and afterwards
only from blocks too quiet to be a barge, so the user's own speech never
teaches it to ignore them.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

BARGE_PEAK        = 4500   # Int16 peak floor for "the user is talking over him"
BARGE_HOLD_MS     = 350    # must persist — a cough or a door slam shouldn't cut him off
BARGE_GAP_MS      = 150    # breath-sized dips inside a phrase don't reset the clock
BARGE_COOLDOWN_MS = 1500
ECHO_MARGIN       = 3.0    # speech must be this many times louder than his echo
ECHO_ALPHA        = 0.05   # slow running average of his echo after the warm-up
ECHO_WARMUP_MS    = 400    # start of each reply: learn the echo, never trigger
ECHO_WARMUP_ALPHA = 0.3

VAD_SPEECH_PEAK   = 1500   # Int16 peak — above room noise, below normal speech
VAD_SPEECH_MIN_MS = 300    # this much speech before a turn counts for latency
LATENCY_MIN_MS    = 250    # faster than this is noise keeping the stamp moving, not a reply
LATENCY_MAX_MS    = 120_000


def chunk_peak(samples) -> int:
    """Peak absolute value of an int16 numpy block (safe for -32768)."""
    if samples is None or len(samples) == 0:
        return 0
    return max(int(samples.max()), -int(samples.min()))


class BargeDetector:
    """Decides when sustained loud speech while Moses is audible should cut him off."""

    def __init__(self, peak=BARGE_PEAK, hold_ms=BARGE_HOLD_MS, gap_ms=BARGE_GAP_MS,
                 cooldown_ms=BARGE_COOLDOWN_MS, echo_margin=ECHO_MARGIN):
        self.peak, self.hold_ms, self.gap_ms = peak, hold_ms, gap_ms
        self.cooldown_ms, self.echo_margin = cooldown_ms, echo_margin
        self.echo: float | None = None   # running mic level while he talks (persists: same room)
        self._start = 0.0
        self._last_loud = 0.0
        self._cooldown_until = 0.0
        self._audible_since = None

    def threshold(self) -> float:
        return max(self.peak, (self.echo or 0.0) * self.echo_margin)

    def feed(self, peak: int, now_ms: float, audible: bool) -> bool:
        """One mic block. Returns True exactly when a barge-in should fire."""
        if not audible:
            self._start = 0.0
            self._audible_since = None
            return False
        if self._audible_since is None:
            self._audible_since = now_ms
        if now_ms - self._audible_since < ECHO_WARMUP_MS:
            self.echo = float(peak) if self.echo is None else self.echo * (1 - ECHO_WARMUP_ALPHA) + peak * ECHO_WARMUP_ALPHA
            return False
        thr = self.threshold()
        if peak < thr:
            self.echo = float(peak) if self.echo is None else self.echo * (1 - ECHO_ALPHA) + peak * ECHO_ALPHA
        if now_ms < self._cooldown_until:
            return False
        if peak >= thr:
            if not self._start or now_ms - self._last_loud > self.gap_ms:
                self._start = now_ms
            self._last_loud = now_ms
            if now_ms - self._start >= self.hold_ms:
                self._start = 0.0
                self._cooldown_until = now_ms + self.cooldown_ms
                return True
        elif self._start and now_ms - self._last_loud > self.gap_ms:
            self._start = 0.0
        return False


class LatencyTimer:
    """The wait as heard: last speech-level block SENT -> reply audible.

    Only a turn with real speech in it counts (not a cough, not a typed or
    proactive turn). One number per reply; reset on any cut.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.speech_ms = 0.0
        self.last_speech = 0.0

    def note_sent(self, peak: int, chunk_ms: float, now_ms: float):
        if peak >= VAD_SPEECH_PEAK:
            self.speech_ms += chunk_ms
            self.last_speech = now_ms

    def reply_audible(self, audible_ms: float) -> int | None:
        armed = self.speech_ms >= VAD_SPEECH_MIN_MS and self.last_speech
        ms = round(audible_ms - self.last_speech)
        self.reset()
        if not armed or not (LATENCY_MIN_MS <= ms <= LATENCY_MAX_MS):
            return None
        return ms


# ── storage: one JSON line per measured turn ────────────────────────────────
def record_latency(path: Path, ms: int) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": int(time.time()), "ms": int(ms)}) + "\n")
    except Exception as e:
        print(f"[MOSES] ⚠️ latency record failed: {e}")


def latency_summary(path: Path, days: int = 7) -> dict | None:
    cutoff = time.time() - days * 86400
    vals = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                o = json.loads(line)
                if o.get("t", 0) >= cutoff:
                    vals.append(int(o["ms"]))
            except Exception:
                continue
    except FileNotFoundError:
        return None
    if not vals:
        return None
    vals.sort()
    pick = lambda p: vals[min(len(vals) - 1, int(p * len(vals)))]
    return {"turns": len(vals), "p50": pick(0.5), "p90": pick(0.9)}


def duration_seconds(value, default: float = 10.0) -> float:
    """goAway.time_left arrives as '50s', a number, or a timedelta."""
    try:
        if hasattr(value, "total_seconds"):
            return float(value.total_seconds())
        s = float(str(value).strip().rstrip("s"))
        return s if s > 0 else default
    except Exception:
        return default
