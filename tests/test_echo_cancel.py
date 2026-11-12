"""Echo cancellation plumbing: picking the real mic, finding this process's
streams, and never touching the audio server when it is switched off."""
import os
import unittest
from unittest import mock

from core import echo_cancel as ec

SOURCE_OUTPUTS = """Source Output #3463
\tDriver: PipeWire
\tClient: 3462
\tSource: 59
\tProperties:
\t\tapplication.name = "PipeWire ALSA [python3.14]"
Source Output #3395
\tDriver: PipeWire
\tClient: 3300
\tSource: 60
"""
CLIENTS = """Client #3462
\tDriver: PipeWire
\tProperties:
\t\tapplication.name = "PipeWire ALSA [python3.14]"
\t\tapplication.process.id = "711988"
Client #3300
\tProperties:
\t\tapplication.process.id = "42"
"""


class PickMicTest(unittest.TestCase):
    def test_a_speaker_monitor_is_not_a_microphone(self):
        # This machine's real state with no mic plugged in: the default "source" is a monitor.
        sources = ["alsa_output.analog.monitor", "alsa_input.analog", "alsa_output.hdmi.monitor"]
        self.assertEqual(ec.pick_mic("alsa_output.analog.monitor", sources), "alsa_input.analog")

    def test_the_default_mic_wins_when_it_is_real(self):
        self.assertEqual(ec.pick_mic("usb_mic", ["alsa_input.analog", "usb_mic"]), "usb_mic")

    def test_never_our_own_virtual_mic_and_none_when_there_is_no_mic(self):
        self.assertEqual(ec.pick_mic(ec.SOURCE, [ec.SOURCE, "alsa_input.analog"]), "alsa_input.analog")
        self.assertIsNone(ec.pick_mic("x.monitor", ["x.monitor", ec.SOURCE]))


class ParseTest(unittest.TestCase):
    def test_streams_are_matched_to_this_process_through_their_client(self):
        self.assertEqual(ec.parse_streams(SOURCE_OUTPUTS), [("3463", "3462"), ("3395", "3300")])
        self.assertEqual(ec.parse_clients(CLIENTS), {"3462": "711988", "3300": "42"})

    def test_empty_or_missing_output(self):
        self.assertEqual(ec.parse_streams(None), [])
        self.assertEqual(ec.parse_clients(""), {})
        self.assertEqual(ec.parse_short("1\tmodule-x\targs\n\n"), [["1", "module-x", "args"]])


class RouteTest(unittest.TestCase):
    def test_only_this_process_is_moved(self):
        calls = []

        def fake(*args, timeout=4.0):
            calls.append(args)
            if args == ("list", "short", "modules"):
                return f"9\tmodule-echo-cancel\tsource_name={ec.SOURCE} sink_name={ec.SINK}\n"
            if args == ("list", "clients"):
                return CLIENTS
            if args == ("list", "source-outputs"):
                return SOURCE_OUTPUTS
            if args == ("list", "sink-inputs"):
                return SOURCE_OUTPUTS.replace("Source Output", "Sink Input")
            return ""

        with mock.patch.object(ec, "_pactl", fake):
            self.assertEqual(ec.route(pid=711988), (True, True))
        moved = [c for c in calls if c[0].startswith("move-")]
        self.assertEqual(moved, [("move-source-output", "3463", ec.SOURCE), ("move-sink-input", "3463", ec.SINK)])

    def test_nothing_happens_without_the_module(self):
        with mock.patch.object(ec, "_pactl", lambda *a, **k: ""):
            self.assertEqual(ec.route(pid=1), (False, False))

    def test_a_leftover_pair_is_adopted_so_it_is_removed_on_exit(self):
        mods = f"7\tmodule-echo-cancel\tsource_name={ec.SOURCE} sink_name={ec.SINK}\n"
        with mock.patch.object(ec, "available", lambda: True), \
             mock.patch.object(ec, "_pactl", lambda *a, **k: mods if a[:3] == ("list", "short", "modules") else ""):
            ec._loaded_module = None
            self.assertTrue(ec.enable().startswith("on"))
            self.assertEqual(ec._loaded_module, "7")
        ec._loaded_module = None

    def test_switched_off_by_environment(self):
        with mock.patch.dict(os.environ, {"MOSES_AEC": "0"}), mock.patch.object(ec, "_pactl") as pactl:
            self.assertFalse(ec.available())
            self.assertTrue(ec.enable().startswith("off"))
            pactl.assert_not_called()


if __name__ == "__main__":
    unittest.main()
