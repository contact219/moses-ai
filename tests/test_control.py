"""mosesctl ↔ a running Moses: the path a desktop keyboard shortcut takes."""
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

import mosesctl


class ControlTest(unittest.TestCase):
    def test_not_running_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": d}):
            self.assertIsNone(mosesctl.send("toggle"))
            self.assertEqual(mosesctl.main(["mosesctl", "toggle"]), 1)

    def test_unknown_command_is_refused_before_anything_is_sent(self):
        with mock.patch.object(mosesctl, "send") as send:
            self.assertEqual(mosesctl.main(["mosesctl", "format-disk"]), 2)
            send.assert_not_called()

    def test_a_command_reaches_the_window(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtCore import QCoreApplication
        import ui_presence
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": d}):
            app = QCoreApplication.instance() or QCoreApplication([])
            srv = ui_presence.ControlServer()
            self.assertTrue(srv.ok)
            self.assertEqual(srv.path, mosesctl.socket_path())      # both ends agree where to meet
            got, reply = [], []
            srv.command.connect(got.append)
            t = threading.Thread(target=lambda: reply.append(mosesctl.send("mute")))
            t.start()
            deadline = time.monotonic() + 3
            while t.is_alive() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
            t.join(1)
            srv.close()
            self.assertEqual(got, ["mute"])
            self.assertEqual(reply, ["ok"])
            self.assertFalse(os.path.exists(srv.path))               # no stale socket left behind


if __name__ == "__main__":
    unittest.main()
