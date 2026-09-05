from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import core.instructions as instructions
import core.storage as storage
from core.exporter import export_package
from core.project import ProjectModel


class ExportLineageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.app_data = self.base / "appdata"
        self.project = self.base / "project"
        self.project.mkdir()
        self.storage_patch = patch.object(storage, "app_data_dir", lambda: self.app_data)
        self.instructions_patch = patch.object(instructions, "app_data_dir", lambda: self.app_data)
        self.storage_patch.start()
        self.instructions_patch.start()
        self.addCleanup(self.storage_patch.stop)
        self.addCleanup(self.instructions_patch.stop)

    def write(self, rel: str, text: str) -> Path:
        path = self.project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_changed_export_records_deletion_and_clears_changed_state(self) -> None:
        self.write(".aiignore", "")
        self.write("app.py", "print('ok')\n")
        doomed = self.write("obsolete.py", "old\n")
        model = ProjectModel(self.project)
        model.mark_synced([".aiignore", "app.py", "obsolete.py"], initialize=True)
        doomed.unlink()

        destination = self.base / "changed.zip"
        artifacts = export_package(model, model.changed_since_sync(), destination, "changed")

        self.assertEqual((), artifacts.exported_paths)
        self.assertEqual(("obsolete.py",), artifacts.deleted_paths)
        self.assertTrue(artifacts.export_id.startswith(model.state.session_id + "-E"))
        self.assertEqual([], model.changed_since_sync())
        self.assertNotIn("obsolete.py", model.state.synced_hashes)
        instructions_text = artifacts.instructions_path.read_text(encoding="utf-8")
        self.assertIn("Paths deleted locally", instructions_text)
        self.assertIn("`obsolete.py`", instructions_text)
        self.assertIn(artifacts.export_id, instructions_text)
        with zipfile.ZipFile(destination) as zf:
            self.assertEqual([], zf.namelist())

    def test_exports_get_monotonic_ids_and_retain_baselines(self) -> None:
        self.write(".aiignore", "")
        self.write("app.py", "one\n")
        model = ProjectModel(self.project)

        first = export_package(model, [".aiignore", "app.py"], self.base / "one.zip", "all")
        self.write("app.py", "two\n")
        second = export_package(model, ["app.py"], self.base / "two.zip", "changed")

        self.assertNotEqual(first.export_id, second.export_id)
        self.assertTrue(first.export_id.endswith("E0001"))
        self.assertTrue(second.export_id.endswith("E0002"))
        self.assertIsNotNone(model.baseline_hashes_for_export(first.export_id))
        self.assertIsNotNone(model.baseline_hashes_for_export(second.export_id))


if __name__ == "__main__":
    unittest.main()
