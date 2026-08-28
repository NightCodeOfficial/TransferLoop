from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.storage import AppSettings


class RecentProjectSettingsTests(unittest.TestCase):
    def test_remove_recent_only_removes_matching_project_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "First Project"
            second = root / "Second Project"
            first.mkdir()
            second.mkdir()

            settings = AppSettings(
                recent_projects=[str(first.resolve()), str(second.resolve())]
            )

            with patch.object(AppSettings, "save") as save:
                settings.remove_recent(str(first))

            self.assertEqual([str(second.resolve())], settings.recent_projects)
            save.assert_called_once_with()
            self.assertTrue(first.exists())

    def test_remove_confirmation_defaults_to_enabled(self) -> None:
        settings = AppSettings()
        self.assertTrue(settings.confirm_recent_project_removal)

    def test_remove_confirmation_preference_round_trips(self) -> None:
        payload = {
            "recent_projects": [],
            "confirm_recent_project_removal": False,
        }
        with patch("core.storage.load_json", return_value=payload):
            settings = AppSettings.load()
        self.assertFalse(settings.confirm_recent_project_removal)


if __name__ == "__main__":
    unittest.main()
