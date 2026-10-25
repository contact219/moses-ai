"""Windows lists each audio device once per host API; Moses should list it once."""

import unittest
from unittest import mock

from actions import devices

# What sounddevice reports on a typical Windows laptop: the same mic and
# speakers under MME (0), DirectSound (1) and WASAPI (2).
WIN_DEVICES = [
    {"name": "Microsoft Sound Mapper - Input", "hostapi": 0, "max_input_channels": 2, "max_output_channels": 0},
    {"name": "Microphone (Realtek Audio)",     "hostapi": 0, "max_input_channels": 2, "max_output_channels": 0},
    {"name": "Speakers (Realtek Audio)",       "hostapi": 0, "max_input_channels": 0, "max_output_channels": 2},
    {"name": "Microphone (Realtek Audio)",     "hostapi": 1, "max_input_channels": 2, "max_output_channels": 0},
    {"name": "Speakers (Realtek Audio)",       "hostapi": 1, "max_input_channels": 0, "max_output_channels": 2},
    {"name": "Microphone (Realtek Audio)",     "hostapi": 2, "max_input_channels": 2, "max_output_channels": 0},
    {"name": "Speakers (Realtek Audio)",       "hostapi": 2, "max_input_channels": 0, "max_output_channels": 2},
]


def fake_query_devices(device=None, kind=None):
    if kind == "input":
        return WIN_DEVICES[1]          # system default mic lives on MME
    return WIN_DEVICES


class WindowsDeviceList(unittest.TestCase):
    def setUp(self):
        import sounddevice
        p1 = mock.patch.object(sounddevice, "query_devices", fake_query_devices)
        p2 = mock.patch.object(devices.platform, "system", return_value="Windows")
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def test_each_mic_listed_once(self):
        names = [n for _, n in devices.list_microphones()]
        self.assertEqual(names.count("Microphone (Realtek Audio)"), 1)

    def test_each_speaker_listed_once(self):
        self.assertEqual(devices.list_speakers(), [(2, "Speakers (Realtek Audio)")])

    def test_matching_picks_the_listed_index(self):
        self.assertEqual(devices._match_device("realtek", devices.list_microphones()),
                         (1, "Microphone (Realtek Audio)"))


if __name__ == "__main__":
    unittest.main()
