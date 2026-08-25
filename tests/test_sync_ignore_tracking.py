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


class SyncIgnoreTrackingTests(unittest.TestCase):
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

    def test_paths_that_become_ignored_are_pruned_from_sync_tracking(self) -> None:
        self.write(".aiignore", "")
        self.write("app.py", "print('ok')\n")
        runtime_paths = []
        for index in range(20):
            rel = f"runtime/state_{index}.json"
            runtime_paths.append(rel)
            self.write(rel, f'{{"index": {index}}}\n')

        model = ProjectModel(self.project)
        model.mark_synced([".aiignore", "app.py", *runtime_paths], initialize=True)
        self.assertEqual(20, sum(path.startswith("runtime/") for path in model.state.synced_hashes))

        # This reproduces the real failure: runtime files were synchronized first,
        # then a later accepted .aiignore update excluded the entire directory.
        self.write(".aiignore", "runtime/\n")
        reopened = ProjectModel(self.project)

        self.assertFalse(any(path.startswith("runtime/") for path in reopened.state.synced_hashes))
        self.assertFalse(any(path.startswith("runtime/") for path in reopened.state.diverged_paths))
        self.assertEqual([".aiignore"], reopened.changed_since_sync())

    def test_ignored_diverged_paths_are_pruned_too(self) -> None:
        self.write(".aiignore", "runtime/\n")
        self.write("app.py", "print('ok')\n")
        self.write("runtime/request.json", "{}\n")

        model = ProjectModel(self.project)
        model.state.synced_hashes["runtime/request.json"] = "old"
        model.state.diverged_paths = ["runtime/request.json", "app.py"]
        model.state.save()

        reopened = ProjectModel(self.project)
        self.assertNotIn("runtime/request.json", reopened.state.synced_hashes)
        self.assertEqual(["app.py"], reopened.state.diverged_paths)

    def test_full_sync_replaces_the_old_baseline(self) -> None:
        self.write(".aiignore", "")
        self.write("app.py", "print('new')\n")
        model = ProjectModel(self.project)
        model.state.synced_hashes = {"obsolete.txt": "stale-hash"}
        model.state.diverged_paths = ["obsolete.txt"]
        model.state.save()

        model.mark_synced([".aiignore", "app.py"], initialize=True)

        self.assertEqual({".aiignore", "app.py"}, set(model.state.synced_hashes))
        self.assertEqual([], model.state.diverged_paths)
        self.assertEqual([], model.changed_since_sync())

    def test_export_does_not_reinclude_a_now_ignored_file(self) -> None:
        self.write(".aiignore", "runtime/\n")
        self.write("runtime/request.json", "{}\n")
        self.write("app.py", "print('ok')\n")
        model = ProjectModel(self.project)
        model.mark_synced([".aiignore", "app.py"], initialize=True)

        destination = self.base / "changed.zip"
        artifacts = export_package(
            model,
            ["runtime/request.json", "app.py"],
            destination,
            "changed",
        )

        self.assertEqual(("app.py",), artifacts.exported_paths)
        with zipfile.ZipFile(destination, "r") as zf:
            self.assertEqual(["app.py"], zf.namelist())


if __name__ == "__main__":
    unittest.main()
