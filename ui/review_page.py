from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QTextCharFormat, QSyntaxHighlighter
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSplitter, QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
)

from core.importer import (
    ApplyChangesError, ChangeItem, ImportInspection, apply_changes, build_text_diff,
    refresh_inspection_conflicts,
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
        self.conflict_overrides: set[str] = set()

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

        self.verification_frame = QFrame()
        self.verification_frame.setObjectName("SoftCard")
        verification_layout = QVBoxLayout(self.verification_frame)
        verification_layout.setContentsMargins(10, 9, 10, 9)
        verification_title = QLabel("AI-reported verification")
        verification_title.setObjectName("SectionTitle")
        self.verification_status = QLabel("")
        self.verification_status.setObjectName("HelpText")
        self.verification_preview = QLabel("")
        self.verification_preview.setObjectName("HelpText")
        self.verification_preview.setWordWrap(True)
        verification_layout.addWidget(verification_title)
        verification_layout.addWidget(self.verification_status)
        verification_layout.addWidget(self.verification_preview)
        self.verification_frame.setVisible(False)
        notes_layout.addWidget(self.verification_frame)

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
        refresh_inspection_conflicts(model, inspection)
        self.change_by_path = {c.path: c for c in inspection.changes}
        self.conflict_overrides = {
            path for path in self.conflict_overrides
            if path in self.change_by_path and self.change_by_path[path].conflict
        }
        self.files.clear()
        self.title.setText("Review AI Changes")

        lineage = f" · {inspection.export_id}" if inspection.export_id else ""
        self.summary.setText((inspection.overall_summary or Path(inspection.zip_path).name) + lineage)
        if inspection.stale_export:
            self.summary.setToolTip(
                "This response is based on an older TransferLoop export. TransferLoop will preserve "
                "non-overlapping edits with a three-way merge and only flag actual overlap conflicts."
            )
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

        if inspection.verification:
            status_names = {
                "passed": "Passed",
                "partial": "Partial",
                "not_run": "Not run",
                "failed": "Failed",
            }
            result_icons = {
                "passed": "✓",
                "failed": "✕",
                "not_run": "○",
                "skipped": "–",
            }
            report = inspection.verification
            self.verification_status.setText(f"Status: {status_names.get(report.status, report.status)}")
            lines = []
            for check in report.checks[:8]:
                icon = result_icons.get(check.result, "•")
                detail = f" — {html.escape(check.details)}" if check.details else ""
                lines.append(
                    f"{icon} <b>{html.escape(check.name)}</b>: "
                    f"{html.escape(status_names.get(check.result, check.result.replace('_', ' ').title()))}{detail}"
                )
            if len(report.checks) > 8:
                lines.append(f"… {len(report.checks) - 8} additional reported checks")
            for item in report.unverified[:6]:
                lines.append(f"⚠ <b>Unverified:</b> {html.escape(item)}")
            if len(report.unverified) > 6:
                lines.append(f"… {len(report.unverified) - 6} additional unverified items")
            lines.append("<i>Reported by the AI; TransferLoop did not independently run these checks.</i>")
            self.verification_preview.setText("<br>".join(lines))
            self.verification_frame.setVisible(True)
        else:
            self.verification_status.clear()
            self.verification_preview.clear()
            self.verification_frame.setVisible(False)

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
            return "Merge conflict"
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
                    detail = change.conflict_regions[0] if change.conflict_regions else change.conflict_reason
                    item.setToolTip(detail or "The incoming AI edit overlaps newer project content.")
                else:
                    item.setToolTip("")
                return

    def update_decision_summary(self):
        changes = list(self.change_by_path.values())
        accepted = sum(c.accepted for c in changes)
        rejected = sum(c.rejected for c in changes)
        pending = len(changes) - accepted - rejected
        conflicts = sum(c.conflict and not c.accepted and not c.rejected for c in changes)
        suffix = (" · 1 merge conflict" if conflicts == 1 else f" · {conflicts} merge conflicts") if conflicts else ""
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
        if change.auto_merged:
            source = html.escape(change.context_source or "newer project content")
            notes.append(
                "<p><b>Safe three-way merge:</b> TransferLoop detected changes from " + source +
                " and preserved them because the incoming AI edits do not overlap. The diff shown here is the "
                "final merged version that will be applied.</p>"
            )
        if change.conflict:
            source = html.escape(change.context_source or "newer project content")
            notes.append(
                "<p><b>Overlapping conflict:</b> " +
                html.escape(change.conflict_reason or "The incoming AI edit overlaps newer project content.") +
                " Current content came from " + source + ". TransferLoop leaves this file pending rather than "
                "silently replacing either version.</p>"
            )
            if change.conflict_regions:
                notes.append(
                    "<p><b>Conflicting region(s):</b></p><ul>" +
                    "".join(f"<li>{html.escape(region)}</li>" for region in change.conflict_regions) +
                    "</ul>"
                )
        if change.unexpected:
            notes.append("<p><b>Unexpected file:</b> the ZIP contained this change but the AI response manifest did not list it.</p>")
        self.notes.setHtml("".join(notes))
        self.update_file_state_label(change)

    def refresh_conflicts(self) -> None:
        if not self.model or not self.inspection:
            return
        refresh_inspection_conflicts(self.model, self.inspection)
        self.conflict_overrides = {
            path for path in self.conflict_overrides
            if path in self.change_by_path and self.change_by_path[path].conflict
        }
        for change in self.change_by_path.values():
            if change.conflict and change.accepted and change.path not in self.conflict_overrides:
                # The file became unsafe after it was accepted. Return it to an
                # undecided state so the UI cannot imply that overwrite approval
                # still applies to a newly changed local file.
                change.accepted = False
                change.rejected = False
            self.update_file_item(change)
        current = self.current_change()
        if current:
            self.update_file_state_label(current)
        self.update_decision_summary()

    def confirm_conflict_overwrite(self, paths: list[str], *, bulk: bool = False) -> bool:
        """Ask whether conflicted AI changes should intentionally replace local files.

        Use a bounded dialog with a scrollable file list so large conflict sets can
        never push the action buttons below the available screen area.
        """
        if not paths:
            return False

        dialog = QDialog(self)
        dialog.setModal(True)
        dialog.setWindowTitle("Overlapping edits need review" if bulk else "Overlapping edit conflict")
        dialog.resize(720, 440 if bulk or len(paths) > 1 else 310)
        dialog.setMinimumWidth(560)
        dialog.setMaximumHeight(520)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel(
            f"{len(paths)} files have overlapping edits" if len(paths) != 1
            else f"{paths[0]} has an overlapping edit"
        )
        title.setObjectName("SectionTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        explanation = QLabel(
            "TransferLoop compared the original export, the current project, and the incoming AI response. "
            "These files contain edits to the same baseline region, so they cannot be combined safely automatically. "
            "Keep them pending for updated context, or intentionally replace them with the incoming AI versions. "
            "The apply operation is backed up and transactional."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        if len(paths) > 1 or bulk:
            file_list = QListWidget(dialog)
            file_list.setObjectName("ConflictFileList")
            for path in paths:
                change = self.change_by_path.get(path)
                region = change.conflict_regions[0] if change and change.conflict_regions else ""
                file_list.addItem(f"{path} — {region}" if region else path)
            file_list.setMinimumHeight(120)
            layout.addWidget(file_list, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        keep_btn = QPushButton("Keep Pending" if bulk else "Cancel")
        overwrite_btn = QPushButton("Overwrite with AI Version")
        overwrite_btn.setObjectName("DangerButton")
        keep_btn.clicked.connect(dialog.reject)
        overwrite_btn.clicked.connect(dialog.accept)
        buttons.addWidget(keep_btn)
        buttons.addWidget(overwrite_btn)
        layout.addLayout(buttons)

        keep_btn.setDefault(True)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def set_current_acceptance(self, accepted: bool):
        self.refresh_conflicts()
        change = self.current_change()
        if not change:
            return
        if accepted and change.conflict:
            if not self.confirm_conflict_overwrite([change.path]):
                return
            self.conflict_overrides.add(change.path)
        elif not accepted:
            self.conflict_overrides.discard(change.path)
        change.accepted = accepted
        change.rejected = not accepted
        self.update_file_state_label(change)
        self.update_file_item(change)
        self.update_decision_summary()

    def accept_all_safe(self):
        self.refresh_conflicts()
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
                self.conflict_overrides.add(change.path)
                self.update_file_item(change)

        self.update_decision_summary()
        self.show_current(self.files.currentItem(), None)

    def apply_selected(self):
        if not self.model or not self.inspection:
            return
        self.refresh_conflicts()
        accepted = {path for path, change in self.change_by_path.items() if change.accepted}
        newly_conflicting = sorted(
            path for path in accepted
            if self.change_by_path[path].conflict and path not in self.conflict_overrides
        )
        if newly_conflicting:
            if not self.confirm_conflict_overwrite(newly_conflicting, bulk=len(newly_conflicting) > 1):
                return
            self.conflict_overrides.update(newly_conflicting)
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
                allow_conflicting_paths=self.conflict_overrides & accepted,
            )
        except ApplyChangesError as exc:
            QMessageBox.critical(self, "Apply failed", str(exc))
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
