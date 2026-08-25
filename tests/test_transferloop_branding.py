from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.instructions import _migrate_legacy_branding
from core.memory import HISTORY_HEADING, _migrate_memory_branding
from core.project import ProjectState
from core.storage import _migrate_legacy_app_data


class TransferLoopBrandingTests(unittest.TestCase):
    def test_legacy_app_data_is_copied_to_transferloop_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            legacy = root / "AIProjectSync"
            legacy.mkdir()
            (legacy / "settings.json").write_text('{"theme":"dark"}', encoding="utf-8")
            destination = root / "TransferLoop"

            _migrate_legacy_app_data(root, destination)

            self.assertEqual('{"theme":"dark"}', (destination / "settings.json").read_text(encoding="utf-8"))

    def test_existing_session_ids_are_preserved_but_new_ids_use_tl_prefix(self) -> None:
        existing = ProjectState(path=".", name="Project", session_id="APS-ABC123")
        self.assertEqual("APS-ABC123", existing.ensure_session())

        fresh = ProjectState(path=".", name="Project")
        with patch.object(ProjectState, "save", lambda self: None):
            session_id = fresh.ensure_session()
        self.assertTrue(session_id.startswith("TL-"))

    def test_instruction_branding_migration_only_changes_product_name(self) -> None:
        source = "# AI Project Sync Instructions\n\nKeep this custom sentence.\n"
        migrated = _migrate_legacy_branding(source)

        self.assertIn("# TransferLoop Instructions", migrated)
        self.assertIn("Keep this custom sentence.", migrated)

    def test_memory_branding_migration_preserves_accepted_history_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".aimemory"
            history = (
                "## Accepted Change History\n\n"
                "<!-- APS:MEMORY-ENTRY -->\n"
                "### Historical AI Project Sync entry\n"
            )
            path.write_text(
                "# AI Project Memory\n\n"
                "> This file is maintained by AI Project Sync.\n\n"
                + history,
                encoding="utf-8",
            )

            _migrate_memory_branding(path)
            migrated = path.read_text(encoding="utf-8")

            self.assertIn("maintained by TransferLoop", migrated)
            self.assertEqual(history, HISTORY_HEADING + migrated.split(HISTORY_HEADING, 1)[1])


if __name__ == "__main__":
    unittest.main()
