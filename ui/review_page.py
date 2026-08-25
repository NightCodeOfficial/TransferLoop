from __future__ import annotations

import html
import os
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QSyntaxHighlighter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QSplitter, QTextBrowser, QTextEdit, QVBoxLayout, QWidget
)

from core.importer import ImportInspection, ChangeItem, apply_changes, build_text_diff
from core.project import ProjectModel
from core.storage import AppSettings


class DiffHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text: str):
        fmt = QTextCharFormat()
        if text.startswith("+") and not text.startswith("+++"):
            fmt.setForeground(QColor("#82d99b"))
            self.setFormat(0, len(text), fmt)
        elif text.startswith("-") and not text.startswith("---"):
            fmt.setForeground(QColor("#ff9292"))
            self.setFormat(0, len(text), fmt)
        elif text.startswith("@@"):
            fmt.setForeground(QColor("#8ab4ff"))
            self.setFormat(0, len(text), fmt)
        elif text.startswith("---") or text.startswith("+++"):
            fmt.setForeground(QColor("#c0a7ff"))
            self.setFormat(0, len(text), fmt)


class ReviewPage(QWidget):
    finished = Signal(str)
    cancelled = Signal(object)

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.model: ProjectModel | None = None
        self.inspection: ImportInspection | None = None
        self.change_by_path: dict[str, ChangeItem] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        back = QPushButton("← Back")
        back.clicked.connect(self.go_back)
        self.title = QLabel("Review AI Changes")
        self.title.setObjectName("Title")
        self.summary = QLabel("")
        self.summary.setObjectName("Muted")
        header.addWidget(back)
        header.addSpacing(8)
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.summary)
        root.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)
        self.files = QListWidget()
        self.files.setMinimumWidth(220)
        self.files.currentItemChanged.connect(self.show_current)

        self.diff = QTextEdit()
        self.diff.setReadOnly(True)
        mono = QFont("Cascadia Code")
        mono.setStyleHint(QFont.Monospace)
        self.diff.setFont(mono)
        self.highlighter = DiffHighlighter(self.diff.document())

        notes_frame = QFrame()
        notes_layout = QVBoxLayout(notes_frame)
        notes_title = QLabel("AI change notes")
        notes_title.setObjectName("SectionTitle")
        self.notes = QTextBrowser()
        notes_layout.addWidget(notes_title)
        notes_layout.addWidget(self.notes, 1)

        splitter.addWidget(self.files)
        splitter.addWidget(self.diff)
        splitter.addWidget(notes_frame)
        splitter.setSizes([240, 680, 330])
        root.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        self.file_state = QLabel("Pending")
        self.file_state.setObjectName("Muted")
        reject = QPushButton("Reject File")
        accept = QPushButton("Accept File")
        accept_all = QPushButton("Accept All")
        apply_btn = QPushButton("Apply Accepted")
        apply_btn.setObjectName("Primary")
        reject.clicked.connect(lambda: self.set_current_acceptance(False))
        accept.clicked.connect(lambda: self.set_current_acceptance(True))
        accept_all.clicked.connect(self.accept_all_and_apply)
        apply_btn.clicked.connect(self.apply_selected)
        buttons.addWidget(self.file_state)
        buttons.addStretch(1)
        buttons.addWidget(reject)
        buttons.addWidget(accept)
        buttons.addWidget(accept_all)
        buttons.addWidget(apply_btn)
        root.addLayout(buttons)

    def load_review(self, model: ProjectModel, inspection: ImportInspection):
        if self.inspection and self.inspection is not inspection:
            self.inspection.cleanup()
        self.model = model
        self.inspection = inspection
        self.change_by_path = {c.path: c for c in inspection.changes}
        self.files.clear()
        self.title.setText("Review AI Changes")
        self.summary.setText(inspection.overall_summary or Path(inspection.zip_path).name)

        for change in inspection.changes:
            prefix = {"modified": "M", "added": "A", "deleted": "D"}.get(change.action, "•")
            flags = []
            if change.conflict:
                flags.append("CONFLICT")
            if change.unexpected:
                flags.append("UNEXPECTED")
            suffix = f"   {' · '.join(flags)}" if flags else ""
            item = QListWidgetItem(f"{prefix}  {change.path}{suffix}")
            item.setData(Qt.UserRole, change.path)
            self.files.addItem(item)
        if self.files.count():
            self.files.setCurrentRow(0)

    def current_change(self) -> ChangeItem | None:
        item = self.files.currentItem()
        if not item:
            return None
        return self.change_by_path.get(item.data(Qt.UserRole))

    def show_current(self, current, previous):
        if not current or not self.model:
            return
        change = self.change_by_path[current.data(Qt.UserRole)]
        self.diff.setPlainText(build_text_diff(self.model, change))
        notes = []
        if change.summary:
            notes.append(f"<h3>{html.escape(change.summary)}</h3>")
        else:
            notes.append("<p><i>No AI notes were supplied for this file.</i></p>")
        if change.details:
            notes.append("<ul>" + "".join(f"<li>{html.escape(str(d))}</li>" for d in change.details) + "</ul>")
        if change.conflict:
            notes.append("<p><b>Conflict:</b> this local file changed after the AI's last synchronized version.</p>")
        if change.unexpected:
            notes.append("<p><b>Unexpected file:</b> the ZIP contained this change but the AI response manifest did not list it.</p>")
        self.notes.setHtml("".join(notes))
        self.file_state.setText("Accepted" if change.accepted else "Pending / Rejected")

    def set_current_acceptance(self, accepted: bool):
        change = self.current_change()
        if not change:
            return
        if accepted and change.conflict:
            answer = QMessageBox.warning(
                self,
                "Conflict detected",
                f"{change.path} changed locally after the AI session was synchronized.\n\nAccepting the AI version will overwrite the current local version. A backup will be created first.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return
        change.accepted = accepted
        self.file_state.setText("Accepted" if accepted else "Rejected")

    def accept_all_and_apply(self):
        conflicts = [c for c in self.change_by_path.values() if c.conflict]
        if conflicts:
            QMessageBox.warning(
                self,
                "Conflicts require review",
                "Accept All will not automatically overwrite conflicted files. Review those files individually first.",
            )
            for change in self.change_by_path.values():
                if not change.conflict:
                    change.accepted = True
            self.show_current(self.files.currentItem(), None)
            return
        for change in self.change_by_path.values():
            change.accepted = True
        self.apply_selected()

    def apply_selected(self):
        if not self.model or not self.inspection:
            return
        accepted = {path for path, change in self.change_by_path.items() if change.accepted}
        if not accepted:
            QMessageBox.information(self, "Nothing selected", "Accept at least one file before applying changes.")
            return
        count, backup = apply_changes(self.model, self.inspection, accepted)
        zip_path = Path(self.inspection.zip_path)
        self.inspection.cleanup()
        if self.settings.delete_import_zip_after_apply:
            try:
                zip_path.unlink(missing_ok=True)
            except OSError:
                pass
        self.finished.emit(f"Applied {count} change{'s' if count != 1 else ''}. Backup created.")
        self.inspection = None

    def go_back(self):
        # Back is navigation, not a rejection. Keep the staged inspection alive and
        # return it to ProjectPage so the same review can be reopened later. This also
        # preserves any per-file Accept/Reject choices already made in the review.
        inspection = self.inspection
        self.inspection = None
        self.model = None
        self.cancelled.emit(inspection)
