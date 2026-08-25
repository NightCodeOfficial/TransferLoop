from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core.instructions as instructions
import core.project as project_module
import core.storage as storage
from core.project import ProjectModel


class ExternalProjectDetectionTests(unittest.TestCase):
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

    def test_disk_snapshot_detects_external_edits_and_tree_changes(self) -> None:
        self.write(".aiignore", ".venv/\n")
        app = self.write("app.py", "one\n")
        self.write("src/helper.py", "helper\n")
        self.write(".venv/ignored.py", "ignored\n")

        model = ProjectModel(self.project)
        first = model.disk_snapshot()

        self.assertIn("app.py", first.tracked_files)
        self.assertIn("src/helper.py", first.tracked_files)
        self.assertNotIn(".venv/ignored.py", first.tracked_files)
        self.assertIn((".venv", True, True), first.tree_entries)
        self.assertNotIn((".venv/ignored.py", False, True), first.tree_entries)

        # Simulate an IDE save. Keep the file size the same and force a newer
        # timestamp so the metadata watcher catches changes without hashing.
        before_stat = app.stat()
        app.write_text("two\n", encoding="utf-8")
        os.utime(
            app,
            ns=(before_stat.st_atime_ns, before_stat.st_mtime_ns + 1_000_000_000),
        )
        second = model.disk_snapshot()

        self.assertNotEqual(
            first.tracked_files["app.py"],
            second.tracked_files["app.py"],
        )
        self.assertEqual(first.tree_entries, second.tree_entries)

        self.write("src/new_file.py", "new\n")
        third = model.disk_snapshot()
        self.assertNotEqual(second.tree_entries, third.tree_entries)
        self.assertIn(("src/new_file.py", False, False), third.tree_entries)

        (self.project / "src/new_file.py").unlink()
        fourth = model.disk_snapshot()
        self.assertNotEqual(third.tree_entries, fourth.tree_entries)
        self.assertNotIn(("src/new_file.py", False, False), fourth.tree_entries)

    def test_hashes_are_reused_until_file_metadata_changes(self) -> None:
        self.write(".aiignore", "")
        app = self.write("app.py", "one\n")
        self.write("helper.py", "helper\n")
        model = ProjectModel(self.project)

        real_sha256 = project_module.sha256_file
        with patch.object(project_module, "sha256_file", wraps=real_sha256) as hasher:
            first = model.all_hashes()
            first_call_count = hasher.call_count
            self.assertGreater(first_call_count, 0)

            second = model.all_hashes()
            self.assertEqual(first, second)
            self.assertEqual(first_call_count, hasher.call_count)

            before_stat = app.stat()
            app.write_text("two\n", encoding="utf-8")
            os.utime(
                app,
                ns=(before_stat.st_atime_ns, before_stat.st_mtime_ns + 1_000_000_000),
            )
            third = model.all_hashes()

            self.assertNotEqual(first["app.py"], third["app.py"])
            self.assertEqual(first_call_count + 1, hasher.call_count)


if __name__ == "__main__":
    unittest.main()
