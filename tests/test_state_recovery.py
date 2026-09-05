from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core.instructions as instructions
import core.storage as storage
from core.project import ProjectState


class StateRecoveryTests(unittest.TestCase):
    def test_corrupt_project_state_is_preserved_before_fresh_state_load(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            app_data = base / "appdata"
            project = base / "project"
            project.mkdir()
            with patch.object(storage, "app_data_dir", lambda: app_data), patch.object(instructions, "app_data_dir", lambda: app_data):
                state_path = storage.project_state_path(project)
                state_path.write_text("{not-json", encoding="utf-8")
                state = ProjectState.load(project)
                self.assertTrue(state.recovery_warning)
                recovery = list(state_path.parent.glob("state.corrupt_*.json"))
                self.assertEqual(1, len(recovery))
                self.assertEqual("{not-json", recovery[0].read_text(encoding="utf-8"))

    def test_pending_response_path_round_trips_in_project_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            app_data = base / "appdata"
            project = base / "project"
            project.mkdir()
            with patch.object(storage, "app_data_dir", lambda: app_data), patch.object(instructions, "app_data_dir", lambda: app_data):
                state = ProjectState.load(project)
                state.pending_response_zip = str(base / "response.zip")
                state.save()
                reopened = ProjectState.load(project)
                self.assertEqual(str(base / "response.zip"), reopened.pending_response_zip)


if __name__ == "__main__":
    unittest.main()
