"""Hear "Moses" or "Mina" on this machine, without sending audio anywhere.

A small streaming keyword spotter (sherpa-onnx, a 3-million-parameter model,
about 5 MB on disk) listens to the microphone locally. Until it hears a name,
main.py streams nothing to Google (see core/attention.py). So background talk,
the television and other people's conversations stay in the room, and cost
nothing.

It is OFF until you turn it on, because only your own voice on your own
microphone can show whether it hears you:

    env/bin/python -m core.wake_word --install     # fetch the model once (about 17 MB)
    env/bin/python -m core.wake_word --test        # 20 seconds: say "Moses" and "Mina" a few times

then switch it on from the orb / tray menu, or `mosesctl.py wake`.
MOSES_WAKE=1 / MOSES_WAKE=0 force it on or off for one run.
"""

from __future__ import annotations

import os
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import numpy as np

MODEL_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/"
             "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2")
MODEL_DIR = Path.home() / ".moses" / "models" / "kws"
FILES = {
    "encoder": "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "decoder": "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "joiner":  "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "tokens":  "tokens.txt",
}

# Each name, spelled in the model's own word pieces (from its bpe.model — fixed
# here so nothing has to tokenise at start-up). "@name" is what a hit reports.
KEYWORDS = {
    "moses": ["▁MO S ES", "▁HE Y ▁MO S ES"],
    "mina":  ["▁MIN A", "▁HE Y ▁MIN A", "▁ME EN A"],
}
BOOST = 1.5          # how hard the search leans toward the names
THRESHOLD = 0.12     # how sure it must be; lower hears more, including things that aren't names.
                     # Measured on 30 natural-voice lines: 0.25 heard 26, 0.12 heard 29, with the same false wakes.
SAMPLE_RATE = 16000


def installed(model_dir: Path = MODEL_DIR) -> bool:
    return all((model_dir / f).exists() for f in FILES.values())


def wanted() -> bool:
    """False only when MOSES_WAKE=0 forbids even loading the model."""
    return os.environ.get("MOSES_WAKE", "1") != "0"


def switched_on(configured: bool) -> bool:
    """The setting in force: the saved choice, unless MOSES_WAKE overrides it for this run."""
    env = os.environ.get("MOSES_WAKE")
    return configured if env not in ("0", "1") else env == "1"


def keywords_text(boost: float = BOOST, threshold: float = THRESHOLD) -> str:
    return "".join(f"{tokens} :{boost} #{threshold} @{name}\n"
                   for name, variants in KEYWORDS.items() for tokens in variants)


class WakeWord:
    """feed() it microphone audio; it returns 'moses' or 'mina' when one is said."""

    def __init__(self, model_dir: Path = MODEL_DIR, boost: float = BOOST, threshold: float = THRESHOLD):
        import sherpa_onnx
        kw = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
        kw.write(keywords_text(boost, threshold)); kw.close()
        try:
            self._spotter = sherpa_onnx.KeywordSpotter(
                tokens=str(model_dir / FILES["tokens"]),
                encoder=str(model_dir / FILES["encoder"]),
                decoder=str(model_dir / FILES["decoder"]),
                joiner=str(model_dir / FILES["joiner"]),
                num_threads=1,
                keywords_file=kw.name,
                keywords_score=boost,
                keywords_threshold=threshold,
                provider="cpu",
            )
        finally:
            os.unlink(kw.name)
        self._stream = self._spotter.create_stream()

    def feed(self, samples) -> str | None:
        """samples: int16 PCM at 16 kHz, bytes or array of any shape."""
        if isinstance(samples, (bytes, bytearray, memoryview)):
            x = np.frombuffer(samples, dtype=np.int16)
        else:
            x = np.asarray(samples).reshape(-1)
        self._stream.accept_waveform(SAMPLE_RATE, x.astype(np.float32) / 32768.0)
        hit = None
        while self._spotter.is_ready(self._stream):
            self._spotter.decode_stream(self._stream)
            result = self._spotter.get_result(self._stream)
            if result:
                hit = result.strip().lower()
                self._spotter.reset_stream(self._stream)
        return hit

    def reset(self) -> None:
        self._stream = self._spotter.create_stream()


def load() -> WakeWord | None:
    """The spotter, or None with a one-line reason printed (never raises: a
    missing model must not stop Moses from starting)."""
    if not wanted():
        print("[MOSES] 👂 Wake word: off (MOSES_WAKE=0) — always listening")
        return None
    if not installed():
        print("[MOSES] 👂 Wake word: model not installed — always listening. "
              "Run: env/bin/python -m core.wake_word --install")
        return None
    try:
        ww = WakeWord()
    except Exception as e:
        print(f"[MOSES] 👂 Wake word unavailable ({e}) — always listening")
        return None
    print("[MOSES] 👂 Wake word ready (switch it on or off from the orb menu)")
    return ww


def install(model_dir: Path = MODEL_DIR) -> int:
    if installed(model_dir):
        print(f"Wake-word model already in {model_dir}")
        return 0
    model_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "kws.tar.bz2"
        print("Downloading the wake-word model (about 17 MB)…")
        urllib.request.urlretrieve(MODEL_URL, archive)
        wanted_names = set(FILES.values())
        with tarfile.open(archive, "r:bz2") as tar:
            for member in tar.getmembers():
                name = Path(member.name).name
                if member.isfile() and name in wanted_names:      # only these four, flattened — never a path from the archive
                    with tar.extractfile(member) as src, open(model_dir / name, "wb") as dst:
                        dst.write(src.read())
    if not installed(model_dir):
        print("The download did not contain the expected files.")
        return 1
    print(f"Installed in {model_dir}")
    return 0


def selftest(seconds: float = 20.0) -> int:
    """Listen on the default microphone and report every time a name is heard."""
    if not installed():
        print("Model not installed. Run: env/bin/python -m core.wake_word --install")
        return 1
    import time
    import sounddevice as sd
    spotter = WakeWord()
    heard: list[str] = []
    levels: list[float] = []

    def callback(indata, frames, time_info, status):
        x = indata[:, 0]
        levels.append(float(np.sqrt(np.mean(x.astype(np.float32) ** 2))))
        name = spotter.feed(x)
        if name:
            heard.append(name)
            print(f"   heard “{name}”  ({time.strftime('%H:%M:%S')})", flush=True)

    print(f"Listening for {seconds:.0f} seconds. Say “Moses” and “Mina” a few times, the way you normally would…")
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=1024, callback=callback):
        time.sleep(seconds)
    if not levels:
        print("No audio arrived from the microphone.")
        return 1
    floor, top = float(np.percentile(levels, 20)), float(np.percentile(levels, 98))
    print(f"\nHeard a name {len(heard)} time(s): {', '.join(heard) or '—'}")
    print(f"Room noise about {floor:.0f}, loudest speech about {top:.0f} (of 32768).")
    if top < floor * 2.5:
        print("Very little rose above the room noise — was the right microphone picked up, and close enough?")
    elif not heard:
        print("Speech came through but no name was recognised. Leave the wake word off and tell me — the threshold can be tuned.")
    else:
        print("If that matches how many times you said it, switch the wake word on from the orb menu.")
    return 0


if __name__ == "__main__":
    if "--install" in sys.argv:
        sys.exit(install())
    if "--test" in sys.argv:
        sys.exit(selftest())
    print(__doc__)
