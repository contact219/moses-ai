"""When is Moses awake? The wake-word gate's clock, with no audio involved."""
import unittest

from core.attention import Attention, WAKE_HOLD_S, SPEECH_HOLD_S, FOLLOWUP_S, HARD_LIMIT_S


class AttentionTest(unittest.TestCase):
    def test_off_means_always_listening(self):
        a = Attention(enabled=False)
        self.assertTrue(a.awake(0)); self.assertTrue(a.awake(10_000))

    def test_asleep_until_his_name_then_awake_for_a_while(self):
        a = Attention()
        self.assertFalse(a.awake(100))
        a.wake(100)
        self.assertTrue(a.awake(100 + WAKE_HOLD_S - 0.1))
        self.assertFalse(a.awake(100 + WAKE_HOLD_S + 0.1))        # said his name, then nothing

    def test_your_speech_keeps_him_and_covers_the_pause_after_it(self):
        a = Attention(); a.wake(0)
        a.heard_speech(8)                                          # still talking at 8 s
        self.assertTrue(a.awake(8 + SPEECH_HOLD_S - 0.1))          # the silence that ends your turn is still sent
        self.assertFalse(a.awake(8 + SPEECH_HOLD_S + 0.1))

    def test_speech_does_not_wake_him(self):
        a = Attention()
        a.heard_speech(5)                                          # a television, while he is asleep
        self.assertFalse(a.awake(5.1))

    def test_a_television_cannot_keep_him_awake_forever(self):
        a = Attention(); a.wake(0)
        t = 0.0
        while t < 120:                                             # non-stop "speech", he never answers
            a.heard_speech(t); t += 0.5
        self.assertFalse(a.awake(HARD_LIMIT_S + 0.1))

    def test_while_he_replies_he_stays_and_you_can_answer_without_his_name(self):
        a = Attention(); a.wake(0)
        for t in range(1, 60):                                     # a long reply / a long task
            a.engaged(t)
        self.assertTrue(a.awake(59 + FOLLOWUP_S - 0.1))
        a.heard_speech(59 + FOLLOWUP_S - 1)                        # you answer just in time
        self.assertTrue(a.awake(59 + FOLLOWUP_S + 2))
        self.assertFalse(a.awake(59 + HARD_LIMIT_S + 0.1))         # …but not past the limit unless he replies again

    def test_sleep_is_immediate(self):
        a = Attention(); a.wake(0); a.sleep()
        self.assertFalse(a.awake(0.1))


if __name__ == "__main__":
    unittest.main()
