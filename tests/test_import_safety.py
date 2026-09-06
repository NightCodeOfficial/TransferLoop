from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import core.importer as importer
import core.instructions as instructions
import core.storage as storage
from core.exporter import export_package
from core.importer import ApplyChangesError, ChangeItem, ImportInspection, apply_changes, inspect_zip_detailed
from core.project import ProjectModel


class ImportSafetyTests(unittest.TestCase):
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
        (self.project / ".aiignore").write_text("", encoding="utf-8")
        (self.project / "app.py").write_text("old\n", encoding="utf-8")
        self.model = ProjectModel(self.project)
        self.export = export_package(
            self.model,
            [".aiignore", "app.py"],
            self.base / "initial.zip",
            "all",
        )

    def make_response(self, name: str, manifest: dict, files: dict[str, str]) -> Path:
        path = self.base / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(".ai-response.json", json.dumps(manifest))
            for rel, text in files.items():
                zf.writestr(rel, text)
        return path

    def manifest(self, path: str = "app.py", action: str = "modified") -> dict:
        return {
            "format_version": 1,
            "session_id": self.model.state.session_id,
            "export_id": self.export.export_id,
            "summary": "test",
            "files": [{"path": path, "action": action, "summary": "change", "details": []}],
        }

    def test_wrong_session_is_rejected(self) -> None:
        manifest = self.manifest()
        manifest["session_id"] = "TL-WRONG"
        response = self.make_response("wrong.zip", manifest, {"app.py": "new\n"})
        inspection, error = inspect_zip_detailed(self.model, response)
        self.assertIsNone(inspection)
        self.assertIn("belongs to session", error)

    def test_manifest_parent_traversal_is_rejected(self) -> None:
        response = self.make_response("traversal.zip", self.manifest("../outside.txt", "deleted"), {})
        inspection, error = inspect_zip_detailed(self.model, response)
        self.assertIsNone(inspection)
        self.assertIn("unsafe or invalid", error)

    def test_aiignore_only_change_does_not_make_other_response_files_need_context(self) -> None:
        response = self.make_response("aiignore_local.zip", self.manifest(), {"app.py": "ai\n"})
        (self.project / ".aiignore").write_text("reports/\n", encoding="utf-8")

        self.assertEqual([], self.model.changed_since_sync())
        inspection, error = inspect_zip_detailed(self.model, response)

        self.assertEqual("", error)
        self.assertIsNotNone(inspection)
        assert inspection is not None
        self.assertFalse(inspection.changes[0].conflict)

    def test_aiignore_itself_still_conflicts_if_ai_tries_to_overwrite_newer_rules(self) -> None:
        manifest = self.manifest(".aiignore", "modified")
        response = self.make_response("aiignore_response.zip", manifest, {".aiignore": "ai-rule/\n"})
        (self.project / ".aiignore").write_text("local-rule/\n", encoding="utf-8")

        self.assertEqual([], self.model.changed_since_sync())
        inspection, error = inspect_zip_detailed(self.model, response)

        self.assertEqual("", error)
        self.assertIsNotNone(inspection)
        assert inspection is not None
        self.assertTrue(inspection.changes[0].conflict)

    def test_exact_export_baseline_detects_local_conflict(self) -> None:
        response = self.make_response("response.zip", self.manifest(), {"app.py": "ai\n"})
        (self.project / "app.py").write_text("local after export\n", encoding="utf-8")
        inspection, error = inspect_zip_detailed(self.model, response)
        self.assertEqual("", error)
        self.assertIsNotNone(inspection)
        assert inspection is not None
        self.assertEqual(self.export.export_id, inspection.export_id)
        self.assertTrue(inspection.changes[0].conflict)


    def test_exact_export_baseline_overrides_old_diverged_marker(self) -> None:
        # Leaving/rejecting an earlier AI proposal marks a path as diverged so it
        # can be offered for re-export. That historical marker must not create a
        # conflict when the local file still matches the exact baseline used by
        # this response.
        self.model.state.diverged_paths.append("app.py")
        self.model.state.save()
        response = self.make_response("diverged_exact.zip", self.manifest(), {"app.py": "ai\n"})

        inspection, error = inspect_zip_detailed(self.model, response)

        self.assertEqual("", error)
        self.assertIsNotNone(inspection)
        assert inspection is not None
        self.assertFalse(inspection.changes[0].conflict)

    def test_diverged_marker_still_conflicts_without_exact_export_baseline(self) -> None:
        self.model.state.diverged_paths.append("app.py")
        self.model.state.save()
        manifest = self.manifest()
        manifest.pop("export_id")
        response = self.make_response("diverged_legacy.zip", manifest, {"app.py": "ai\n"})

        inspection, error = inspect_zip_detailed(self.model, response)

        self.assertEqual("", error)
        self.assertIsNotNone(inspection)
        assert inspection is not None
        self.assertTrue(inspection.changes[0].conflict)


    def test_latest_export_legacy_baseline_mismatch_does_not_conflict_when_project_is_clean(self) -> None:
        # Older TransferLoop builds could retain an exact-export baseline that
        # disagreed with the current synchronized state even though the project
        # itself had no local edits. The review screen must agree with the
        # project page: zero locally changed means no per-file context conflict.
        baseline_path = storage.export_baselines_dir(self.project) / f"{self.export.export_id}.json"
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
        data["synced_hashes"]["app.py"] = "0" * 64
        baseline_path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual([], self.model.changed_since_sync())

        response = self.make_response("legacy_baseline.zip", self.manifest(), {"app.py": "ai\n"})
        inspection, error = inspect_zip_detailed(self.model, response)

        self.assertEqual("", error)
        self.assertIsNotNone(inspection)
        assert inspection is not None
        self.assertFalse(inspection.changes[0].conflict)

    def test_older_export_still_conflicts_when_newer_export_changed_context(self) -> None:
        first = self.export
        (self.project / "app.py").write_text("newer exported context\n", encoding="utf-8")
        second = export_package(
            self.model,
            [".aiignore", "app.py"],
            self.base / "second.zip",
            "all",
        )
        self.assertNotEqual(first.export_id, second.export_id)
        self.assertEqual([], self.model.changed_since_sync())

        manifest = self.manifest()
        manifest["export_id"] = first.export_id
        response = self.make_response("stale_response.zip", manifest, {"app.py": "old-ai-response\n"})
        inspection, error = inspect_zip_detailed(self.model, response)

        self.assertEqual("", error)
        self.assertIsNotNone(inspection)
        assert inspection is not None
        self.assertTrue(inspection.changes[0].conflict)


    def test_intentional_conflict_overwrite_becomes_synced_after_apply(self) -> None:
        response = self.make_response("override_conflict.zip", self.manifest(), {"app.py": "ai overwrite\n"})
        (self.project / "app.py").write_text("local after export\n", encoding="utf-8")

        inspection, error = inspect_zip_detailed(self.model, response)

        self.assertEqual("", error)
        self.assertIsNotNone(inspection)
        assert inspection is not None
        self.assertTrue(inspection.changes[0].conflict)
        self.assertIn("app.py", self.model.changed_since_sync())

        apply_changes(self.model, inspection, {"app.py"})

        self.assertEqual("ai overwrite\n", (self.project / "app.py").read_text(encoding="utf-8"))
        self.assertEqual([], self.model.changed_since_sync())
        self.assertNotIn("app.py", self.model.state.diverged_paths)

    def test_apply_rolls_back_all_project_files_when_a_write_fails(self) -> None:
        (self.project / "other.py").write_text("other old\n", encoding="utf-8")
        stage = self.base / "stage"
        stage.mkdir()
        first_stage = stage / "app.py"
        second_stage = stage / "other.py"
        first_stage.write_text("app new\n", encoding="utf-8")
        second_stage.write_text("other new\n", encoding="utf-8")
        inspection = ImportInspection(
            zip_path=str(self.base / "response.zip"),
            root_prefix="",
            session_id=self.model.state.session_id,
            export_id=self.export.export_id,
            overall_summary="transaction",
            changes=[
                ChangeItem("app.py", "modified", staged_path=str(first_stage)),
                ChangeItem("other.py", "modified", staged_path=str(second_stage)),
            ],
            confidence=2,
            temp_dir=str(stage),
        )

        real_copy2 = importer.shutil.copy2

        def failing_copy(src, dst, *args, **kwargs):
            if Path(src) == second_stage:
                raise OSError("simulated write failure")
            return real_copy2(src, dst, *args, **kwargs)

        with patch.object(importer.shutil, "copy2", side_effect=failing_copy):
            with self.assertRaises(ApplyChangesError) as ctx:
                apply_changes(self.model, inspection, {"app.py", "other.py"})

        self.assertIn("rolled back", str(ctx.exception))
        self.assertEqual("old\n", (self.project / "app.py").read_text(encoding="utf-8"))
        self.assertEqual("other old\n", (self.project / "other.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
