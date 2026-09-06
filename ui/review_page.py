from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QTextCharFormat, QSyntaxHighlighter
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSplitter, QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
)

from core.importer import (
    ApplyChangesError, ChangeItem, ImportInspection, apply_changes, build_text_diff,
)
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
        self.files.setMinimumWidth(250)
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

        self.memory_frame = QFrame()
        self.memory_frame.setObjectName("SoftCard")
        memory_layout = QVBoxLayout(self.memory_frame)
        memory_layout.setContentsMargins(10, 9, 10, 9)
        self.memory_accept = QCheckBox("Keep proposed project memory updates")
        self.memory_accept.setToolTip("These are durable project facts suggested by the AI, not a saved chat transcript.")
        self.memory_accept.toggled.connect(self.update_apply_button_state)
        self.memory_preview = QLabel("")
        self.memory_preview.setObjectName("HelpText")
        self.memory_preview.setWordWrap(True)
        memory_layout.addWidget(self.memory_accept)
        memory_layout.addWidget(self.memory_preview)
        self.memory_frame.setVisible(False)
        notes_layout.addWidget(self.memory_frame)

        splitter.addWidget(self.files)
        splitter.addWidget(self.diff)
        splitter.addWidget(notes_frame)
        splitter.setSizes([280, 660, 340])
        root.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        self.file_state = QLabel("Pending")
        self.file_state.setObjectName("Muted")
        self.decision_summary = QLabel("")
        self.decision_summary.setObjectName("Muted")
        reject = QPushButton("Reject File")
        accept = QPushButton("Accept File")
        accept_all = QPushButton("Accept Safe Changes")
        self.apply_btn = QPushButton("Apply Accepted")
        self.apply_btn.setObjectName("ApplyPrimary")
        self.apply_btn.setEnabled(False)
        reject.clicked.connect(lambda: self.set_current_acceptance(False))
        accept.clicked.connect(lambda: self.set_current_acceptance(True))
        accept_all.clicked.connect(self.accept_all_safe)
        self.apply_btn.clicked.connect(self.apply_selected)
        buttons.addWidget(self.file_state)
        buttons.addSpacing(8)
        buttons.addWidget(self.decision_summary)
        buttons.addStretch(1)
        buttons.addWidget(reject)
        buttons.addWidget(accept)
        buttons.addWidget(accept_all)
        buttons.addWidget(self.apply_btn)
        root.addLayout(buttons)

    def load_review(self, model: ProjectModel, inspection: ImportInspection):
        if self.inspection and self.inspection is not inspection:
            self.inspection.cleanup()
        self.model = model
        self.inspection = inspection
        self.change_by_path = {c.path: c for c in inspection.changes}
        self.files.clear()
        self.title.setText("Review AI Changes")

        lineage = f" · {inspection.export_id}" if inspection.export_id else ""
        self.summary.setText((inspection.overall_summary or Path(inspection.zip_path).name) + lineage)
        if inspection.stale_export:
            self.summary.setToolTip("This response is based on an older TransferLoop export. Review conflict warnings carefully.")
        else:
            self.summary.setToolTip("")

        for change in inspection.changes:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, change.path)
            self.files.addItem(item)
            self.update_file_item(change)
        if self.files.count():
            self.files.setCurrentRow(0)
        else:
            self.diff.setPlainText("No project-file changes were proposed. Review the durable memory suggestions on the right.")
            self.notes.setHtml("<p>This response only proposed durable project-memory updates.</p>")

        self.memory_accept.setChecked(False)
        if inspection.memory_updates:
            section_names = {
                "current_direction": "Current direction",
                "decisions": "Decisions",
                "constraints": "Constraints",
                "open_work": "Open work",
                "project_notes": "Project notes",
            }
            parts = []
            for key, values in inspection.memory_updates.items():
                if not values:
                    continue
                parts.append(f"{section_names.get(key, key)}: {len(values)}")
            self.memory_preview.setText(" · ".join(parts) + "\nReviewable durable context; unchecked by default.")
            self.memory_frame.setVisible(True)
        else:
            self.memory_frame.setVisible(False)
        self.update_decision_summary()
        self.update_apply_button_state()

    def current_change(self) -> ChangeItem | None:
        item = self.files.currentItem()
        if not item:
            return None
        return self.change_by_path.get(item.data(Qt.UserRole))

    @staticmethod
    def decision_text(change: ChangeItem) -> str:
        if change.accepted:
            return "Accepted"
        if change.rejected:
            return "Rejected"
        if change.conflict:
            return "Needs updated context"
        return "Pending"

    @staticmethod
    def decision_color(change: ChangeItem) -> QColor:
        if change.accepted:
            return QColor("#79dda0")
        if change.conflict and not change.rejected:
            return QColor("#ff9292")
        if change.rejected:
            return QColor("#9299aa")
        return QColor("#e8ebf2")

    def update_file_state_label(self, change: ChangeItem):
        self.file_state.setText(self.decision_text(change))
        if change.accepted:
            object_name = "AcceptedState"
        elif change.conflict and not change.rejected:
            object_name = "NeedsContextState"
        else:
            object_name = "Muted"
        self.file_state.setObjectName(object_name)
        self.file_state.style().unpolish(self.file_state)
        self.file_state.style().polish(self.file_state)

    def update_file_item(self, change: ChangeItem):
        prefix = {"modified": "M", "added": "A", "deleted": "D"}.get(change.action, "•")
        flags = []
        if change.unexpected:
            flags.append("UNEXPECTED")
        flags.append(self.decision_text(change).upper())
        text = f"{prefix}  {change.path}   {' · '.join(flags)}"
        for index in range(self.files.count()):
            item = self.files.item(index)
            if item.data(Qt.UserRole) == change.path:
                item.setText(text)
                item.setForeground(QBrush(self.decision_color(change)))
                if change.conflict and not change.accepted and not change.rejected:
                    item.setToolTip(
                        "This file changed locally after the export used by the AI. "
                        "It was not bulk-accepted because the AI may need updated context before changing it safely."
                    )
                else:
                    item.setToolTip("")
                return

    def update_decision_summary(self):
        changes = list(self.change_by_path.values())
        accepted = sum(c.accepted for c in changes)
        rejected = sum(c.rejected for c in changes)
        pending = len(changes) - accepted - rejected
        conflicts = sum(c.conflict and not c.accepted and not c.rejected for c in changes)
        suffix = (" · 1 needs updated context" if conflicts == 1 else f" · {conflicts} need updated context") if conflicts else ""
        self.decision_summary.setText(
            f"{accepted} accepted · {rejected} rejected · {pending} pending{suffix}"
        )
        self.update_apply_button_state()

    def update_apply_button_state(self):
        accepted_file = any(change.accepted for change in self.change_by_path.values())
        accepted_memory = self.memory_frame.isVisible() and self.memory_accept.isChecked()
        self.apply_btn.setEnabled(accepted_file or accepted_memory)

    def show_current(self, current, previous):
        if not current or not self.model:
            return
        change = self.change_by_path[current.data(Qt.UserRole)]
        self.diff.setPlainText(build_text_diff(self.model, change))
        notes = []
        if self.inspection and self.inspection.warnings:
            notes.append("<p><b>Response warning:</b> " + "<br>".join(html.escape(w) for w in self.inspection.warnings) + "</p>")
        if change.summary:
            notes.append(f"<h3>{html.escape(change.summary)}</h3>")
        else:
            notes.append("<p><i>No AI notes were supplied for this file.</i></p>")
        if change.details:
            notes.append("<ul>" + "".join(f"<li>{html.escape(str(d))}</li>" for d in change.details) + "</ul>")
        if change.conflict:
            notes.append(
                "<p><b>Needs updated context:</b> this local file changed after the exact export baseline used by the AI. "
                "TransferLoop leaves it pending during bulk acceptance so the AI can be given the current file before changing it.</p>"
            )
        if change.unexpected:
            notes.append("<p><b>Unexpected file:</b> the ZIP contained this change but the AI response manifest did not list it.</p>")
        self.notes.setHtml("".join(notes))
        self.update_file_state_label(change)

    def confirm_conflict_overwrite(self, paths: list[str], *, bulk: bool = False) -> bool:
        """Ask whether conflicted AI changes should intentionally replace local files."""
        if not paths:
            return False

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Some changes need updated context" if bulk else "Local file changed since export")

        if bulk:
            dialog.setText(
                "TransferLoop accepted the non-conflicting changes, but some files were left pending because their local state differs from the AI's export context."
            )
            dialog.setInformativeText(
                "If the local versions matter, keep these files pending and send their current versions to the AI first. "
                "If you intentionally want the AI versions to replace the local files, choose Ignore Warning and Overwrite. "
                "The apply operation is backed up and transactional.\n\n"
                "Files left pending:\n" + "\n".join(f"• {path}" for path in paths)
            )
            keep_btn = dialog.addButton("Keep Pending", QMessageBox.ButtonRole.RejectRole)
        else:
            dialog.setText(f"{paths[0]} changed locally after the export used by the AI.")
            dialog.setInformativeText(
                "If the local changes matter, keep this file pending and give the AI the updated file first. "
                "If you intentionally want the AI version to replace the local file, choose Ignore Warning and Overwrite. "
                "The apply operation is backed up and transactional."
            )
            keep_btn = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

        overwrite_btn = dialog.addButton("Ignore Warning and Overwrite", QMessageBox.ButtonRole.DestructiveRole)
        dialog.setDefaultButton(keep_btn)
        dialog.exec()
        return dialog.clickedButton() is overwrite_btn

    def set_current_acceptance(self, accepted: bool):
        change = self.current_change()
        if not change:
            return
        if accepted and change.conflict:
            if not self.confirm_conflict_overwrite([change.path]):
                return
        change.accepted = accepted
        change.rejected = not accepted
        self.update_file_state_label(change)
        self.update_file_item(change)
        self.update_decision_summary()

    def accept_all_safe(self):
        needs_context: list[ChangeItem] = []
        for change in self.change_by_path.values():
            if change.conflict:
                if not change.accepted and not change.rejected:
                    needs_context.append(change)
                self.update_file_item(change)
                continue
            change.accepted = True
            change.rejected = False
            self.update_file_item(change)

        if needs_context and self.confirm_conflict_overwrite(
            [change.path for change in needs_context], bulk=True
        ):
            for change in needs_context:
                change.accepted = True
                change.rejected = False
                self.update_file_item(change)

        self.update_decision_summary()
        self.show_current(self.files.currentItem(), None)

    def apply_selected(self):
        if not self.model or not self.inspection:
            return
        accepted = {path for path, change in self.change_by_path.items() if change.accepted}
        keep_memory = self.memory_frame.isVisible() and self.memory_accept.isChecked()
        if not accepted and not keep_memory:
            QMessageBox.information(self, "Nothing selected", "Accept at least one file or choose to keep the proposed project-memory updates before applying.")
            return
        try:
            count, backup = apply_changes(
                self.model,
                self.inspection,
                accepted,
                accept_memory_updates=keep_memory,
            )
        except ApplyChangesError as exc:
            QMessageBox.critical(self, "Apply failed and was rolled back", str(exc))
            return
        zip_path = Path(self.inspection.zip_path)
        self.inspection.cleanup()
        if self.settings.delete_import_zip_after_apply:
            try:
                zip_path.unlink(missing_ok=True)
            except OSError:
                pass
        memory_note = " Project memory updated." if keep_memory else ""
        self.finished.emit(
            f"Applied {count} change{'s' if count != 1 else ''}. Backup created.{memory_note}"
        )
        self.inspection = None

    def go_back(self):
        inspection = self.inspection
        self.inspection = None
        self.model = None
        self.cancelled.emit(inspection)
