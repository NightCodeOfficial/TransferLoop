from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QStackedWidget
    from ui.editor_workspace import EditorWorkspace
except ModuleNotFoundError as exc:  # Allows non-GUI CI environments to run the core test suite.
    if exc.name == "PySide6":
        raise unittest.SkipTest("PySide6 is not installed in this test environment") from exc
    raise


class MarkdownReadModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        (self.project / "README.md").write_text(
            "# Demo\n\nThis is **rendered** Markdown.\n",
            encoding="utf-8",
        )
        (self.project / "app.py").write_text("print('ok')\n", encoding="utf-8")
        self.workspace = EditorWorkspace()
        self.workspace.set_project_root(self.project)
        self.addCleanup(self.workspace.close)

    def test_markdown_tab_can_toggle_between_edit_and_read_modes(self) -> None:
        self.assertTrue(self.workspace.open_file("README.md"))
        doc = self.workspace.current_document()
        self.assertIsNotNone(doc)
        assert doc is not None
        self.assertTrue(doc.is_markdown)
        self.assertIsInstance(doc.tab_widget, QStackedWidget)
        self.assertFalse(doc.read_mode)
        self.assertTrue(self.workspace.markdown_mode_btn.isVisible())
        self.assertIn("Read Markdown", self.workspace.markdown_mode_btn.toolTip())

        self.workspace.toggle_markdown_mode()
        self.assertTrue(doc.read_mode)
        self.assertIs(doc.tab_widget.currentWidget(), doc.preview)
        self.assertIn("Demo", doc.preview.toPlainText())
        self.assertIn("Edit Markdown", self.workspace.markdown_mode_btn.toolTip())

        self.workspace.toggle_markdown_mode()
        self.assertFalse(doc.read_mode)
        self.assertIs(doc.tab_widget.currentWidget(), doc.editor)


    def test_markdown_toggle_preserves_document_position(self) -> None:
        long_markdown = "# Demo\n\n" + "\n\n".join(
            f"## Section {index}\n\nParagraph {index} with enough text to make the document scroll."
            for index in range(1, 90)
        ) + "\n"
        (self.project / "README.md").write_text(long_markdown, encoding="utf-8")

        self.workspace.resize(900, 600)
        self.workspace.show()
        self.assertTrue(self.workspace.open_file("README.md"))
        self.app.processEvents()

        doc = self.workspace.current_document()
        assert doc is not None and doc.preview is not None

        editor_bar = doc.editor.verticalScrollBar()
        editor_bar.setValue(editor_bar.maximum() * 2 // 3)
        cursor = doc.editor.textCursor()
        cursor.setPosition(len(doc.editor.toPlainText()) * 2 // 3)
        doc.editor.setTextCursor(cursor)
        editor_bar.setValue(editor_bar.maximum() * 2 // 3)
        self.app.processEvents()

        original_scroll = editor_bar.value()
        original_cursor = doc.editor.textCursor().position()
        original_ratio = self.workspace._vertical_scroll_ratio(doc.editor)

        self.workspace.toggle_markdown_mode()
        self.app.processEvents()

        preview_ratio = self.workspace._vertical_scroll_ratio(doc.preview)
        self.assertAlmostEqual(preview_ratio, original_ratio, delta=0.08)

        self.workspace.toggle_markdown_mode()
        self.app.processEvents()

        self.assertEqual(doc.editor.textCursor().position(), original_cursor)
        self.assertEqual(editor_bar.value(), original_scroll)

    def test_mode_button_is_hidden_for_non_markdown_files(self) -> None:
        self.assertTrue(self.workspace.open_file("app.py"))
        doc = self.workspace.current_document()
        self.assertIsNotNone(doc)
        assert doc is not None
        self.assertFalse(doc.is_markdown)
        self.assertFalse(self.workspace.markdown_mode_btn.isVisible())

    def test_read_mode_renders_unsaved_editor_changes(self) -> None:
        self.assertTrue(self.workspace.open_file("README.md"))
        doc = self.workspace.current_document()
        assert doc is not None and doc.preview is not None
        doc.editor.setPlainText("# Unsaved heading\n\nStill local to the editor.\n")
        doc.editor.document().setModified(True)

        self.workspace.toggle_markdown_mode()

        self.assertIn("Unsaved heading", doc.preview.toPlainText())
        self.assertTrue(doc.editor.document().isModified())


if __name__ == "__main__":
    unittest.main()
