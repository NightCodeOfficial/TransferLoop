from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget
)

from core.instructions import (
    read_base_template, read_project_instructions, reset_project_instructions_to_base,
    save_base_template, save_project_instructions,
)
from core.memory import refresh_memory_overview
from core.storage import AppSettings

from .editor_shortcuts import enable_line_copy_cut
from core.project import ProjectModel
from .markdown_editor import MarkdownEditorDialog


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, model: ProjectModel | None = None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.model = model
        self.setWindowTitle("Project Settings" if model else "Preferences")
        self.resize(760, 590)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)
        tabs = QTabWidget()
        root.addWidget(tabs)

        general = QWidget()
        general_layout = QVBoxLayout(general)
        general_layout.setContentsMargins(18, 18, 18, 18)
        general_layout.setSpacing(18)

        response_title = QLabel("AI Response Folder")
        response_title.setObjectName("SectionTitle")
        response_help = QLabel("The folder TransferLoop watches for ZIP files downloaded from ChatGPT, Claude, or another AI.")
        response_help.setObjectName("HelpText")
        response_help.setWordWrap(True)
        general_layout.addWidget(response_title)
        general_layout.addWidget(response_help)

        self.download_edit = QLineEdit(settings.download_folder)
        response_browse = QPushButton("Browse…")
        response_browse.setObjectName("Secondary")
        response_browse.clicked.connect(self.choose_download_folder)
        response_row = QHBoxLayout()
        response_row.setSpacing(8)
        response_row.addWidget(self.download_edit, 1)
        response_row.addWidget(response_browse)
        general_layout.addLayout(response_row)

        self.monitor_check = QCheckBox("Automatically watch this folder for new AI response ZIPs")
        self.monitor_check.setChecked(settings.monitor_downloads)
        general_layout.addWidget(self.monitor_check)

        outgoing_title = QLabel("Outgoing Export Folder")
        outgoing_title.setObjectName("SectionTitle")
        outgoing_help = QLabel("The default location where project ZIPs and their companion AI instructions files are saved before you upload them to the AI.")
        outgoing_help.setObjectName("HelpText")
        outgoing_help.setWordWrap(True)
        general_layout.addSpacing(4)
        general_layout.addWidget(outgoing_title)
        general_layout.addWidget(outgoing_help)

        self.export_edit = QLineEdit(settings.export_folder)
        export_browse = QPushButton("Browse…")
        export_browse.setObjectName("Secondary")
        export_browse.clicked.connect(self.choose_export_folder)
        export_row = QHBoxLayout()
        export_row.setSpacing(8)
        export_row.addWidget(self.export_edit, 1)
        export_row.addWidget(export_browse)
        general_layout.addLayout(export_row)

        self.delete_check = QCheckBox("Delete an imported response ZIP after accepted changes are safely applied")
        self.delete_check.setChecked(settings.delete_import_zip_after_apply)
        general_layout.addWidget(self.delete_check)
        general_layout.addStretch(1)
        tabs.addTab(general, "General")

        # The global base template is editable in Preferences. Existing projects keep their own copied version.
        ai_tab = QWidget()
        ai_layout = QVBoxLayout(ai_tab)
        ai_layout.setContentsMargins(18, 18, 18, 18)
        ai_layout.setSpacing(12)
        ai_title = QLabel("Base AI Instructions Template")
        ai_title.setObjectName("SectionTitle")
        ai_help = QLabel(
            "This is the starting protocol copied into each newly opened project. Editing it changes the default for future projects; existing projects keep their own customized copy."
        )
        ai_help.setObjectName("HelpText")
        ai_help.setWordWrap(True)
        ai_layout.addWidget(ai_title)
        ai_layout.addWidget(ai_help)

        base_card = QFrame()
        base_card.setObjectName("InlineCard")
        base_row = QHBoxLayout(base_card)
        base_row.setContentsMargins(12, 10, 12, 10)
        base_text = QVBoxLayout()
        name = QLabel("TransferLoop workflow + response ZIP protocol")
        name.setObjectName("LatestExportName")
        desc = QLabel("Explains how the project exchange works, `.aimemory`, authoritative files, and the required `.ai-response.json` response format.")
        desc.setObjectName("HelpText")
        desc.setWordWrap(True)
        base_text.addWidget(name)
        base_text.addWidget(desc)
        edit_base = QPushButton("Edit Markdown…")
        edit_base.setObjectName("Secondary")
        edit_base.clicked.connect(self.edit_base_instructions)
        base_row.addLayout(base_text, 1)
        base_row.addWidget(edit_base)
        ai_layout.addWidget(base_card)
        ai_layout.addStretch(1)
        tabs.addTab(ai_tab, "AI Instructions")

        if model:
            project = QWidget()
            layout = QVBoxLayout(project)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(12)

            context_title = QLabel("Project context")
            context_title.setObjectName("SectionTitle")
            context_help = QLabel("Describe what this project is, its environment, architecture, and conventions. This becomes part of `.aimemory` and fresh-session AI context.")
            context_help.setObjectName("HelpText")
            context_help.setWordWrap(True)
            layout.addWidget(context_title)
            layout.addWidget(context_help)
            self.context_edit = QTextEdit()
            enable_line_copy_cut(self.context_edit)
            self.context_edit.setPlaceholderText("Describe what this project does, important architecture, environment, conventions, or anything the AI should always know.")
            self.context_edit.setPlainText(model.state.project_context)
            layout.addWidget(self.context_edit, 1)

            instructions_title = QLabel("Project AI instructions")
            instructions_title.setObjectName("SectionTitle")
            instructions_help = QLabel(
                "This project has its own copy of the base instructions. Customize it without changing the global template used for other projects."
            )
            instructions_help.setObjectName("HelpText")
            instructions_help.setWordWrap(True)
            layout.addWidget(instructions_title)
            layout.addWidget(instructions_help)

            project_instruction_card = QFrame()
            project_instruction_card.setObjectName("InlineCard")
            pr = QHBoxLayout(project_instruction_card)
            pr.setContentsMargins(12, 10, 12, 10)
            pit = QVBoxLayout()
            pname = QLabel("AI_PROJECT_INSTRUCTIONS.md")
            pname.setObjectName("LatestExportName")
            pdesc = QLabel("Stored in TransferLoop's project profile, not inside your source project.")
            pdesc.setObjectName("HelpText")
            pit.addWidget(pname)
            pit.addWidget(pdesc)
            edit_project = QPushButton("Edit Markdown…")
            edit_project.setObjectName("Secondary")
            edit_project.clicked.connect(self.edit_project_instructions)
            pr.addLayout(pit, 1)
            pr.addWidget(edit_project)
            layout.addWidget(project_instruction_card)
            tabs.addTab(project, "Project AI Context")

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        save.setObjectName("Primary")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.save_and_close)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

    def edit_base_instructions(self):
        dialog = MarkdownEditorDialog("Base AI Instructions", read_base_template(), self)
        if dialog.exec():
            save_base_template(dialog.markdown())

    def edit_project_instructions(self):
        if not self.model:
            return
        dialog = MarkdownEditorDialog(
            f"AI Instructions — {self.model.state.name}",
            read_project_instructions(self.model.root, self.model.state.project_instructions),
            self,
            reset_text_provider=read_base_template,
            reset_label="Reset to Base Template",
        )
        if dialog.exec():
            save_project_instructions(self.model.root, dialog.markdown())

    def choose_download_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose AI response folder", self.download_edit.text())
        if folder:
            self.download_edit.setText(folder)

    def choose_export_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose outgoing export folder", self.export_edit.text())
        if folder:
            self.export_edit.setText(folder)

    def save_and_close(self):
        self.settings.download_folder = self.download_edit.text().strip() or str(Path.home() / "Downloads")
        self.settings.export_folder = self.export_edit.text().strip() or str(Path.home() / "Downloads")
        self.settings.monitor_downloads = self.monitor_check.isChecked()
        self.settings.delete_import_zip_after_apply = self.delete_check.isChecked()
        self.settings.save()
        if self.model:
            self.model.state.project_context = self.context_edit.toPlainText().strip()
            self.model.state.save()
            refresh_memory_overview(self.model)
        self.accept()
