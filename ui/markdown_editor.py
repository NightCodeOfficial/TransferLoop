from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton,
    QSplitter, QTextBrowser, QVBoxLayout, QWidget
)

from .code_editor import CodeEditor


class MarkdownEditorDialog(QDialog):
    def __init__(
        self,
        title: str,
        markdown_text: str,
        parent=None,
        reset_text_provider: Callable[[], str] | None = None,
        reset_label: str = "Reset",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1040, 700)
        self._reset_text_provider = reset_text_provider
        self._reset_label = reset_label

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        heading = QLabel(title)
        heading.setObjectName("EditorTitle")
        help_text = QLabel("Edit the Markdown on the left. The rendered preview updates automatically on the right.")
        help_text.setObjectName("HelpText")
        root.addWidget(heading)
        root.addWidget(help_text)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(6)
        left_title = QLabel("Markdown")
        left_title.setObjectName("FieldLabel")
        self.editor = CodeEditor(Path("AI_PROJECT_INSTRUCTIONS.md"))
        self.editor.setObjectName("MarkdownEditor")
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.editor.setPlainText(markdown_text)
        self.editor.setTabStopDistance(28)
        left_layout.addWidget(left_title)
        left_layout.addWidget(self.editor, 1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(6)
        right_title = QLabel("Preview")
        right_title.setObjectName("FieldLabel")
        self.preview = QTextBrowser()
        self.preview.setObjectName("MarkdownPreview")
        self.preview.setOpenExternalLinks(True)
        right_layout.addWidget(right_title)
        right_layout.addWidget(self.preview, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([540, 500])
        root.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        if self._reset_text_provider:
            reset = QPushButton(reset_label)
            reset.setObjectName("Secondary")
            reset.clicked.connect(self.reset_text)
            buttons.addWidget(reset)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        save.setObjectName("Primary")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

        self.editor.textChanged.connect(self.refresh_preview)
        self.refresh_preview()

    def refresh_preview(self):
        self.preview.setMarkdown(self.editor.toPlainText())

    def reset_text(self):
        if not self._reset_text_provider:
            return
        answer = QMessageBox.question(
            self,
            self._reset_label,
            "Replace the current text with the current base AI instructions template?",
        )
        if answer == QMessageBox.Yes:
            self.editor.setPlainText(self._reset_text_provider())

    def markdown(self) -> str:
        return self.editor.toPlainText().rstrip() + "\n"
