"""Is Moses paying attention right now?

With the wake word on, the microphone is only streamed to Google while he is
"awake". Saying his name wakes him; he then stays with you for the length of
the conversation without needing his name again, and drifts off when it goes
quiet. Nothing here touches audio — it is just the clock, so it can be tested.

Awake is kept alive by three things:
  • a wake (his name, a shortcut, a typed line) — WAKE_HOLD_S to start talking
  • your speech — SPEECH_HOLD_S after it, which also carries the silence the
    model needs to hear to know your turn has ended
  • him: while he is replying or working he is awake, and for FOLLOWUP_S after

Your speech alone cannot keep him awake forever: a television is "speech" too.
Unless he actually answers, he goes back to sleep HARD_LIMIT_S after the last
real anchor (the wake, or the end of his last reply).
"""

from __future__ import annotations

WAKE_HOLD_S   = 9.0
SPEECH_HOLD_S = 6.0
FOLLOWUP_S    = 14.0
HARD_LIMIT_S  = 25.0


class Attention:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._until = 0.0      # soft deadline, pushed by speech
        self._hard = 0.0       # never awake past this without a new anchor

    def awake(self, now: float) -> bool:
        return (not self.enabled) or now < min(self._until, self._hard)

    def wake(self, now: float) -> None:
        """His name was said (or a shortcut / typed line asked for him)."""
        self._hard = now + HARD_LIMIT_S
        self._until = max(self._until, now + WAKE_HOLD_S)

    def heard_speech(self, now: float) -> None:
        """You are talking while he is awake."""
        if self.awake(now):
            self._until = max(self._until, now + SPEECH_HOLD_S)

    def engaged(self, now: float) -> None:
        """He is replying or working right now: stay, and leave room to answer him after."""
        self._hard = now + HARD_LIMIT_S
        self._until = max(self._until, now + FOLLOWUP_S)

    def sleep(self) -> None:
        self._until = self._hard = 0.0
