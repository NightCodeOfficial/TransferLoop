from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core.instructions as instructions
import core.storage as storage
from core.memory import apply_memory_updates, ensure_memory
from core.project import ProjectModel


class MemoryStructureTests(unittest.TestCase):
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

    def test_existing_memory_gets_structured_durable_sections(self) -> None:
        memory = self.project / ".aimemory"
        memory.write_text(
            "# AI Project Memory\n\n## Project Overview\n\nOld context\n\n"
            "## Important Memory Rules\n\n- Keep files authoritative.\n\n"
            "## Accepted Change History\n\nHistorical entry\n",
            encoding="utf-8",
        )
        model = ProjectModel(self.project)
        ensure_memory(model)
        text = memory.read_text(encoding="utf-8")
        self.assertIn("## Current Direction", text)
        self.assertIn("## Architecture & Important Decisions", text)
        self.assertIn("## Constraints & Conventions", text)
        self.assertIn("## Open Work", text)
        self.assertIn("## Project Notes", text)
        self.assertIn("Historical entry", text)

    def test_approved_memory_updates_merge_without_transcript_storage(self) -> None:
        model = ProjectModel(self.project)
        memory = ensure_memory(model)
        apply_memory_updates(model, {
            "decisions": ["Keep the built-in editor lightweight."],
            "open_work": ["Add three-way conflict visualization."],
        })
        text = memory.read_text(encoding="utf-8")
        self.assertIn("- Keep the built-in editor lightweight.", text)
        self.assertIn("- Add three-way conflict visualization.", text)


if __name__ == "__main__":
    unittest.main()
