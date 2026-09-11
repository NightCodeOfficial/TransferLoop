from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.platform_utils import linux_file_manager_show_items_argument, show_items_in_linux_file_manager
from core.storage import _app_data_root


class LinuxSupportTests(unittest.TestCase):
    def test_app_data_root_honors_xdg_data_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"XDG_DATA_HOME": temp}, clear=False):
                with patch("core.storage.os.name", "posix"):
                    self.assertEqual(Path(temp), _app_data_root())

    def test_linux_show_items_builds_file_uris(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "project export.zip"
            second = Path(temp) / "instructions.md"
            argument = linux_file_manager_show_items_argument([first, second])

        self.assertTrue(argument.startswith("["))
        self.assertIn("file://", argument)
        self.assertIn("project%20export.zip", argument)
        self.assertIn("instructions.md", argument)

    def test_linux_show_items_requires_graphical_session_bus(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(show_items_in_linux_file_manager([Path("/tmp/example.txt")]))

    def test_linux_show_items_launches_freedesktop_interface(self) -> None:
        with patch.dict(os.environ, {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/tmp/test-bus"}, clear=False):
            with patch("core.platform_utils.shutil.which", return_value="/usr/bin/gdbus"):
                with patch("core.platform_utils.subprocess.run") as run:
                    run.return_value.returncode = 0
                    self.assertTrue(show_items_in_linux_file_manager([Path("/tmp/example.txt")]))

        command = run.call_args.args[0]
        self.assertEqual("/usr/bin/gdbus", command[0])
        self.assertIn("org.freedesktop.FileManager1", command)
        self.assertIn("org.freedesktop.FileManager1.ShowItems", command)
        self.assertIn("file:///tmp/example.txt", command[-2])


if __name__ == "__main__":
    unittest.main()
