from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QMimeData, QSize, QTimer, Qt, Signal, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
    QLineEdit, QScrollArea, QSplitter, QStackedWidget, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget
)

from core.exporter import export_package
from core.instructions import (
    read_base_template, read_project_instructions, save_project_instructions, write_exported_instructions,
)
from core.memory import MEMORY_FILENAME, ensure_memory
from core.ignore import DEFAULT_AIIGNORE, add_pattern, is_ignored, load_patterns
from core.importer import ImportInspection, inspect_zip, undo_last_apply, zip_signature
from core.project import ProjectDiskSnapshot, ProjectModel, likely_text_file
from core.storage import AppSettings
from .editor_workspace import EditorWorkspace
from .icons import copy_icon, folder_icon, pencil_icon
from .markdown_editor import MarkdownEditorDialog
from .settings_dialog import SettingsDialog

ROLE_REL = Qt.UserRole
ROLE_IS_DIR = Qt.UserRole + 1
ROLE_IGNORED = Qt.UserRole + 2


class ProjectPage(QWidget):
    back_requested = Signal()
    review_requested = Signal(object, object)
    project_scan_ready = Signal(int, str, object)

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.model: ProjectModel | None = None
        self.pending_import: ImportInspection | None = None
        self.last_export: Path | None = None
        self.last_instructions: Path | None = None
        self.last_export_mode: str = ""
        self.last_export_paths: tuple[str, ...] = ()
        self.scanned_zip_signatures: set[str] = set()
        self._updating_checks = False
        self.editor_sidebar_preferred = True
        self._project_disk_snapshot: ProjectDiskSnapshot | None = None
        self._project_scan_inflight = False
        self._project_scan_generation = 0
        self.project_scan_ready.connect(self._on_project_scan_ready)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(10)
        back = QPushButton("← Projects")
        back.clicked.connect(self.request_back)
        self.title = QLabel("Project")
        self.title.setObjectName("Title")
        self.sync_label = QLabel("")
        self.sync_label.setMinimumWidth(82)
        self.sync_label.setAlignment(Qt.AlignCenter)
        self.editor_return_btn = QPushButton("Editor")
        self.editor_return_btn.setObjectName("Secondary")
        self.editor_return_btn.setVisible(False)
        self.editor_return_btn.clicked.connect(self.show_editor_mode)
        settings_btn = QPushButton("Project Settings")
        settings_btn.setObjectName("Secondary")
        settings_btn.clicked.connect(self.open_settings)
        header.addWidget(back)
        header.addSpacing(4)
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.sync_label)
        header.addWidget(self.editor_return_btn)
        header.addWidget(settings_btn)
        root.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)

        # Left: project tree
        left = QFrame()
        left.setObjectName("SidebarPanel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(11)
        left_head = QHBoxLayout()
        ltitle = QLabel("Project files")
        ltitle.setObjectName("SectionTitle")
        self.file_count = QLabel("")
        self.file_count.setObjectName("Muted")
        left_head.addWidget(ltitle)
        left_head.addStretch(1)
        left_head.addWidget(self.file_count)
        left_layout.addLayout(left_head)

        tree_tools = QHBoxLayout()
        tree_tools.setSpacing(7)
        self.file_search = QLineEdit()
        self.file_search.setObjectName("TreeSearch")
        self.file_search.setPlaceholderText("Search project files…")
        self.file_search.setClearButtonEnabled(True)
        self.file_search.textChanged.connect(self.filter_tree)
        tree_menu_btn = QToolButton()
        tree_menu_btn.setObjectName("TreeMenuButton")
        tree_menu_btn.setText("⋯")
        tree_menu_btn.setToolTip("Project file options")
        tree_menu_btn.clicked.connect(lambda: self.show_tree_menu(tree_menu_btn))
        tree_tools.addWidget(self.file_search, 1)
        tree_tools.addWidget(tree_menu_btn)
        left_layout.addLayout(tree_tools)

        self.ignore_banner = QFrame()
        self.ignore_banner.setObjectName("SoftCard")
        ignore_layout = QHBoxLayout(self.ignore_banner)
        ignore_layout.setContentsMargins(11, 9, 9, 9)
        ignore_text = QLabel("Recommended exclusions can keep caches, secrets, environments, and build output out of AI exports.")
        ignore_text.setObjectName("HelpText")
        ignore_text.setWordWrap(True)
        self.add_ignore_btn = QPushButton("Add .aiignore")
        self.add_ignore_btn.setObjectName("Secondary")
        self.add_ignore_btn.clicked.connect(self.create_default_ignore)
        ignore_layout.addWidget(ignore_text, 1)
        ignore_layout.addWidget(self.add_ignore_btn)
        left_layout.addWidget(self.ignore_banner)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.tree_context_menu)
        self.tree.itemChanged.connect(self.on_item_changed)
        self.tree.itemDoubleClicked.connect(self.on_tree_double_clicked)
        left_layout.addWidget(self.tree, 1)
        splitter.addWidget(left)

        # Right: session / export / import controls
        right = QWidget()
        self.sync_controls = right
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(16)

        session = QFrame()
        session.setObjectName("WorkspaceCard")
        sl = QVBoxLayout(session)
        sl.setContentsMargins(16, 14, 16, 14)
        sl.setSpacing(6)
        session_head = QHBoxLayout()
        session_head.setSpacing(10)
        st = QLabel("AI session")
        st.setObjectName("SectionTitle")
        self.session_id = QLabel("Not initialized")
        self.session_id.setObjectName("SessionValue")
        session_head.addWidget(st)
        session_head.addStretch(1)
        session_head.addWidget(self.session_id)
        self.session_hint = QLabel("The first full export establishes project context for a new AI conversation.")
        self.session_hint.setObjectName("HelpText")
        self.session_hint.setWordWrap(True)
        sl.addLayout(session_head)
        sl.addWidget(self.session_hint)
        right_layout.addWidget(session)

        export_card = QFrame()
        export_card.setObjectName("WorkspaceCard")
        el = QVBoxLayout(export_card)
        el.setContentsMargins(16, 14, 16, 14)
        el.setSpacing(9)
        et = QLabel("Export context")
        et.setObjectName("SectionTitle")
        self.export_info = QLabel("")
        self.export_info.setObjectName("HelpText")
        self.export_info.setWordWrap(True)
        el.addWidget(et)
        el.addWidget(self.export_info)

        destination_title = QLabel("Destination")
        destination_title.setObjectName("FieldLabel")
        el.addWidget(destination_title)
        destination_row = QHBoxLayout()
        destination_row.setSpacing(8)
        self.export_folder_label = QLabel("")
        self.export_folder_label.setObjectName("PathValue")
        self.export_folder_label.setWordWrap(False)
        choose_export_folder = QToolButton()
        choose_export_folder.setObjectName("WireIconButton")
        choose_export_folder.setIcon(folder_icon())
        choose_export_folder.setIconSize(QSize(18, 18))
        choose_export_folder.setToolTip("Choose outgoing export folder")
        choose_export_folder.clicked.connect(self.choose_export_folder)
        destination_row.addWidget(self.export_folder_label, 1)
        destination_row.addWidget(choose_export_folder)
        el.addLayout(destination_row)

        self.init_btn = QPushButton("Initialize AI Session — Export All")
        self.init_btn.setObjectName("Primary")
        self.init_btn.clicked.connect(lambda: self.export_mode("all"))
        el.addWidget(self.init_btn)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.export_selected_btn = QPushButton("Export Selected")
        self.export_changed_btn = QPushButton("Export Changed")
        self.export_all_btn = QPushButton("Export All")
        self.export_selected_btn.setObjectName("Primary")
        self.export_changed_btn.setObjectName("Secondary")
        self.export_all_btn.setObjectName("Secondary")
        self.export_selected_btn.clicked.connect(lambda: self.export_mode("selected"))
        self.export_changed_btn.clicked.connect(lambda: self.export_mode("changed"))
        self.export_all_btn.clicked.connect(lambda: self.export_mode("all"))
        row.addWidget(self.export_selected_btn)
        row.addWidget(self.export_changed_btn)
        row.addWidget(self.export_all_btn)
        el.addLayout(row)

        latest_header = QHBoxLayout()
        latest_header.setSpacing(8)
        latest_title = QLabel("Ready for AI")
        latest_title.setObjectName("FieldLabel")
        self.select_ready_files_btn = QPushButton("Select in Explorer")
        self.select_ready_files_btn.setObjectName("Secondary")
        self.select_ready_files_btn.setIcon(folder_icon())
        self.select_ready_files_btn.setIconSize(QSize(16, 16))
        self.select_ready_files_btn.setToolTip(
            "Open the export folder and select all generated Ready for AI files so they can be dragged into the browser chat"
        )
        self.select_ready_files_btn.setVisible(False)
        self.select_ready_files_btn.setEnabled(False)
        self.select_ready_files_btn.clicked.connect(self.select_ready_artifacts_in_explorer)
        latest_header.addWidget(latest_title)
        latest_header.addStretch(1)
        latest_header.addWidget(self.select_ready_files_btn)
        el.addLayout(latest_header)

        latest_surface = QFrame()
        latest_surface.setObjectName("InlineCard")
        export_row = QHBoxLayout(latest_surface)
        export_row.setContentsMargins(10, 8, 8, 8)
        export_row.setSpacing(7)
        export_text = QVBoxLayout()
        export_text.setSpacing(2)
        zip_kind = QLabel("Project ZIP")
        zip_kind.setObjectName("ArtifactKind")
        self.last_export_label = QLabel("No export created yet")
        self.last_export_label.setObjectName("LatestExportName")
        self.last_export_label.setWordWrap(True)
        self.last_export_meta = QLabel("Create an export to generate the project ZIP and companion AI instructions.")
        self.last_export_meta.setObjectName("HelpText")
        self.last_export_meta.setWordWrap(True)
        export_text.addWidget(zip_kind)
        export_text.addWidget(self.last_export_label)
        export_text.addWidget(self.last_export_meta)
        self.copy_export_btn = QToolButton()
        self.copy_export_btn.setObjectName("WireIconButton")
        self.copy_export_btn.setIcon(copy_icon())
        self.copy_export_btn.setIconSize(QSize(18, 18))
        self.copy_export_btn.setToolTip("Copy project ZIP to clipboard")
        self.copy_export_btn.setEnabled(False)
        self.copy_export_btn.clicked.connect(self.copy_last_export)
        self.open_export_btn = QToolButton()
        self.open_export_btn.setObjectName("WireIconButton")
        self.open_export_btn.setIcon(folder_icon())
        self.open_export_btn.setIconSize(QSize(18, 18))
        self.open_export_btn.setToolTip("Open outgoing export folder")
        self.open_export_btn.setEnabled(True)
        self.open_export_btn.clicked.connect(self.open_export_folder)
        export_row.addLayout(export_text, 1)
        export_row.addWidget(self.copy_export_btn)
        export_row.addWidget(self.open_export_btn)
        el.addWidget(latest_surface)

        instructions_surface = QFrame()
        instructions_surface.setObjectName("InlineCard")
        instructions_row = QHBoxLayout(instructions_surface)
        instructions_row.setContentsMargins(10, 8, 8, 8)
        instructions_row.setSpacing(7)
        instructions_text = QVBoxLayout()
        instructions_text.setSpacing(2)
        instructions_kind = QLabel("AI Instructions")
        instructions_kind.setObjectName("ArtifactKind")
        self.instructions_label = QLabel("AI instructions will be generated beside the ZIP")
        self.instructions_label.setObjectName("LatestExportName")
        self.instructions_label.setWordWrap(True)
        self.instructions_meta = QLabel("Copy them into the AI chat or upload the Markdown file with the project ZIP.")
        self.instructions_meta.setObjectName("HelpText")
        self.instructions_meta.setWordWrap(True)
        instructions_text.addWidget(instructions_kind)
        instructions_text.addWidget(self.instructions_label)
        instructions_text.addWidget(self.instructions_meta)
        self.copy_instructions_btn = QToolButton()
        self.copy_instructions_btn.setObjectName("WireIconButton")
        self.copy_instructions_btn.setIcon(copy_icon())
        self.copy_instructions_btn.setIconSize(QSize(18, 18))
        self.copy_instructions_btn.setToolTip("Copy AI instructions to clipboard")
        self.copy_instructions_btn.setEnabled(False)
        self.copy_instructions_btn.clicked.connect(self.copy_last_instructions)
        self.edit_instructions_btn = QToolButton()
        self.edit_instructions_btn.setObjectName("WireIconButton")
        self.edit_instructions_btn.setIcon(pencil_icon())
        self.edit_instructions_btn.setIconSize(QSize(18, 18))
        self.edit_instructions_btn.setToolTip("Edit this project's AI instructions")
        self.edit_instructions_btn.setEnabled(False)
        self.edit_instructions_btn.clicked.connect(self.edit_ai_instructions)
        instructions_row.addLayout(instructions_text, 1)
        instructions_row.addWidget(self.copy_instructions_btn)
        instructions_row.addWidget(self.edit_instructions_btn)
        el.addWidget(instructions_surface)
        right_layout.addWidget(export_card)

        import_card = QFrame()
        import_card.setObjectName("WorkspaceCard")
        il = QVBoxLayout(import_card)
        il.setContentsMargins(16, 14, 16, 14)
        il.setSpacing(8)
        it = QLabel("AI response")
        it.setObjectName("SectionTitle")
        self.import_watch = QLabel("● Watching for AI responses")
        self.import_watch.setObjectName("Watching")
        self.import_status = QLabel("Waiting for a new AI response ZIP…")
        self.import_status.setObjectName("HelpText")
        self.import_status.setWordWrap(True)
        il.addWidget(it)
        import_content = QHBoxLayout()
        import_content.setSpacing(16)
        import_text = QVBoxLayout()
        import_text.setSpacing(4)
        import_text.addWidget(self.import_watch)
        import_text.addWidget(self.import_status)
        import_content.addLayout(import_text, 1)
        import_actions = QVBoxLayout()
        import_actions.setSpacing(7)
        self.review_btn = QPushButton("Review Changes")
        self.review_btn.setObjectName("Primary")
        self.review_btn.setVisible(False)
        self.review_btn.clicked.connect(self.open_pending_review)
        import_zip_btn = QPushButton("Import ZIP…")
        import_zip_btn.setObjectName("Secondary")
        import_zip_btn.clicked.connect(self.manual_import)
        import_actions.addWidget(self.review_btn)
        import_actions.addWidget(import_zip_btn)
        import_actions.addStretch(1)
        import_content.addLayout(import_actions)
        il.addLayout(import_content)
        right_layout.addWidget(import_card)

        right_layout.addStretch(1)
        footer = QFrame()
        footer.setObjectName("BottomStatusBar")
        safel = QHBoxLayout(footer)
        safel.setContentsMargins(10, 9, 4, 0)
        self.undo_label = QLabel("Protected by automatic backups")
        self.undo_label.setObjectName("HelpText")
        self.undo_btn = QPushButton("Undo Last Apply")
        self.undo_btn.setObjectName("TextButton")
        self.undo_btn.clicked.connect(self.undo_last)
        safel.addWidget(self.undo_label, 1)
        safel.addWidget(self.undo_btn)
        right_layout.addWidget(footer)

        # Center workspace: the existing sync dashboard is shown here until a file is opened.
        # In editor mode the same controls move into a collapsible right sidebar, avoiding
        # duplicated state or separate import/export implementations.
        self.editor_workspace = EditorWorkspace()
        self.editor_workspace.overview_requested.connect(self.show_sync_overview)
        self.editor_workspace.sidebar_toggle_requested.connect(self.toggle_sync_sidebar)
        self.editor_workspace.file_saved.connect(self.on_editor_file_saved)
        self.editor_workspace.tabs_changed.connect(self.on_editor_tabs_changed)

        self.workspace_stack = QStackedWidget()
        self.overview_host = QWidget()
        self.overview_layout = QVBoxLayout(self.overview_host)
        self.overview_layout.setContentsMargins(0, 0, 0, 0)
        self.overview_layout.addWidget(self.sync_controls)
        self.workspace_stack.addWidget(self.overview_host)
        self.workspace_stack.addWidget(self.editor_workspace)

        self.sidebar_shell = QFrame()
        self.sidebar_shell.setObjectName("EditorSyncSidebar")
        self.sidebar_shell.setMinimumWidth(330)
        self.sidebar_shell.setMaximumWidth(500)
        sidebar_outer = QVBoxLayout(self.sidebar_shell)
        sidebar_outer.setContentsMargins(8, 8, 8, 8)
        sidebar_outer.setSpacing(6)
        sidebar_head = QHBoxLayout()
        sidebar_title = QLabel("TransferLoop")
        sidebar_title.setObjectName("SectionTitle")
        collapse_sidebar = QToolButton()
        collapse_sidebar.setObjectName("TreeMenuButton")
        collapse_sidebar.setText("›")
        collapse_sidebar.setToolTip("Hide AI sync sidebar (Ctrl+Shift+B)")
        collapse_sidebar.clicked.connect(self.toggle_sync_sidebar)
        sidebar_head.addWidget(sidebar_title)
        sidebar_head.addStretch(1)
        sidebar_head.addWidget(collapse_sidebar)
        sidebar_outer.addLayout(sidebar_head)

        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setObjectName("EditorSidebarScroll")
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar_host = QWidget()
        self.sidebar_content_layout = QVBoxLayout(self.sidebar_host)
        self.sidebar_content_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_content_layout.setSpacing(0)
        self.sidebar_scroll.setWidget(self.sidebar_host)
        sidebar_outer.addWidget(self.sidebar_scroll, 1)
        self.sidebar_shell.setVisible(False)

        self.workspace_splitter = QSplitter(Qt.Horizontal)
        self.workspace_splitter.addWidget(self.workspace_stack)
        self.workspace_splitter.addWidget(self.sidebar_shell)
        self.workspace_splitter.setSizes([900, 380])
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 0)

        splitter.addWidget(self.workspace_splitter)
        splitter.setSizes([405, 875])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.main_splitter = splitter
        root.addWidget(splitter, 1)

        self.monitor_timer = QTimer(self)
        self.monitor_timer.setInterval(2000)
        self.monitor_timer.timeout.connect(self.poll_downloads)
        self.monitor_timer.timeout.connect(self.poll_project_changes)
        self.monitor_timer.start()

    def load_project(self, project_path: str) -> bool:
        target = Path(project_path).resolve()
        switching_projects = bool(self.model and self.model.root != target)
        if switching_projects and not self.editor_workspace.confirm_close_all():
            return False
        if switching_projects:
            self.editor_workspace.close_all(force=True)
            self.show_sync_overview()

        if self.pending_import:
            self.pending_import.cleanup()
        self.pending_import = None
        self.review_btn.setVisible(False)

        # Invalidate any background metadata scan that may still be finishing for
        # the previously open project.
        self._project_scan_generation += 1
        self._project_scan_inflight = False
        self._project_disk_snapshot = None

        self.model = ProjectModel(target)
        self.editor_workspace.set_project_root(self.model.root)
        ensure_memory(self.model)
        self.last_export = None
        self.last_instructions = None
        self.last_export_mode = ""
        self.last_export_paths = ()
        self.last_export_label.setText("No export created yet")
        self.last_export_meta.setText("Create an export to generate the project ZIP and companion AI instructions.")
        self.instructions_label.setText("AI instructions will be generated beside the ZIP")
        self.instructions_meta.setText("Copy them into the AI chat or upload the Markdown file with the project ZIP.")
        self.copy_export_btn.setEnabled(False)
        self.copy_instructions_btn.setEnabled(False)
        self.update_ready_files_button()
        self.edit_instructions_btn.setEnabled(True)
        self.title.setText(self.model.state.name)
        self.settings.touch_recent(project_path)
        self.refresh_tree()
        self.reset_zip_baseline()
        self.refresh_status()
        self.reset_project_disk_snapshot()
        return True

    def request_back(self):
        if not self.editor_workspace.confirm_close_all():
            return
        self.editor_workspace.close_all(force=True)
        self.show_sync_overview()
        self.back_requested.emit()

    def prepare_to_close(self) -> bool:
        return self.editor_workspace.confirm_close_all()

    def _move_sync_controls(self, target_layout, target_parent: QWidget):
        self.overview_layout.removeWidget(self.sync_controls)
        self.sidebar_content_layout.removeWidget(self.sync_controls)
        self.sync_controls.setParent(target_parent)
        target_layout.addWidget(self.sync_controls)
        self.sync_controls.show()

    def show_sync_overview(self):
        self._move_sync_controls(self.overview_layout, self.overview_host)
        self.sidebar_shell.setVisible(False)
        self.editor_workspace.set_sidebar_visible(False)
        self.workspace_stack.setCurrentWidget(self.overview_host)

    def show_editor_mode(self):
        if not self.editor_workspace.has_open_tabs():
            return
        self._move_sync_controls(self.sidebar_content_layout, self.sidebar_host)
        self.workspace_stack.setCurrentWidget(self.editor_workspace)
        self.sidebar_shell.setVisible(self.editor_sidebar_preferred)
        self.editor_workspace.set_sidebar_visible(self.editor_sidebar_preferred)
        if self.editor_sidebar_preferred:
            available = max(700, self.workspace_splitter.width())
            sidebar_width = min(400, max(340, available // 3))
            self.workspace_splitter.setSizes([max(360, available - sidebar_width), sidebar_width])

    def toggle_sync_sidebar(self):
        if self.workspace_stack.currentWidget() is not self.editor_workspace:
            return
        visible = not self.sidebar_shell.isVisible()
        self.editor_sidebar_preferred = visible
        if visible:
            self._move_sync_controls(self.sidebar_content_layout, self.sidebar_host)
            self.sidebar_shell.setVisible(True)
            available = max(700, self.workspace_splitter.width())
            self.workspace_splitter.setSizes([max(360, available - 380), 380])
        else:
            self.sidebar_shell.setVisible(False)
        self.editor_workspace.set_sidebar_visible(visible)

    def on_tree_double_clicked(self, item: QTreeWidgetItem, column: int):
        if not self.model:
            return
        rel = item.data(0, ROLE_REL)
        if rel is None:
            return
        if item.data(0, ROLE_IS_DIR):
            item.setExpanded(not item.isExpanded())
            return
        self.open_file_in_editor(str(rel))

    def open_file_in_editor(self, rel: str):
        if not self.model:
            return
        path = self.model.root / rel
        if not path.exists() or not path.is_file():
            QMessageBox.warning(self, "File unavailable", f"{rel} no longer exists in the project.")
            return
        if not likely_text_file(path):
            box = QMessageBox(self)
            box.setWindowTitle("Binary or unsupported file")
            box.setText(f"{rel} does not appear to be an editable text file.")
            open_external = box.addButton("Open Externally", QMessageBox.ButtonRole.AcceptRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is open_external:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            return
        if self.editor_workspace.open_file(rel):
            self.show_editor_mode()

    def on_editor_file_saved(self, rel: str):
        if rel == ".aiignore":
            self.refresh_tree(preserve_state=True)
        self.refresh_status(f"Saved {rel}.")
        self.reset_project_disk_snapshot()

    def on_editor_tabs_changed(self, count: int):
        self.editor_return_btn.setVisible(count > 0)
        self.editor_return_btn.setText(f"Editor ({count})" if count else "Editor")

    def after_external_project_change(self, message: str):
        self.editor_workspace.sync_from_disk()
        self.refresh_tree(preserve_state=True)
        self.refresh_status(message)
        self.reset_project_disk_snapshot()

    def _capture_tree_ui_state(self) -> tuple[dict[str, Qt.CheckState], set[str]]:
        """Remember export selections and expanded folders across live tree rebuilds."""
        checked_files: dict[str, Qt.CheckState] = {}
        expanded_dirs: set[str] = set()

        def walk(item: QTreeWidgetItem):
            rel = item.data(0, ROLE_REL)
            is_dir = bool(item.data(0, ROLE_IS_DIR))
            ignored = bool(item.data(0, ROLE_IGNORED))
            if rel is not None:
                if is_dir and item.isExpanded():
                    expanded_dirs.add(str(rel))
                elif not is_dir and not ignored and item.flags() & Qt.ItemIsUserCheckable:
                    checked_files[str(rel)] = item.checkState(0)
            for index in range(item.childCount()):
                walk(item.child(index))

        for index in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(index))
        return checked_files, expanded_dirs

    def refresh_tree(self, preserve_state: bool = False):
        if not self.model:
            return

        previous_checks: dict[str, Qt.CheckState] = {}
        previous_expanded: set[str] = set()
        if preserve_state:
            previous_checks, previous_expanded = self._capture_tree_ui_state()

        self._updating_checks = True
        self.tree.clear()
        patterns = load_patterns(self.model.root)

        root_item = QTreeWidgetItem([self.model.root.name])
        root_item.setData(0, ROLE_REL, "")
        root_item.setData(0, ROLE_IS_DIR, True)
        root_item.setFlags(root_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
        root_item.setCheckState(0, Qt.Checked)
        self.tree.addTopLevelItem(root_item)

        file_total = 0

        def add_children(parent_item: QTreeWidgetItem, directory: Path):
            nonlocal file_total
            try:
                children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except (PermissionError, OSError):
                return
            for path in children:
                try:
                    rel = path.relative_to(self.model.root).as_posix()
                    is_dir = path.is_dir()
                except OSError:
                    continue
                ignored = is_ignored(rel, patterns, is_dir)
                item = QTreeWidgetItem([path.name])
                item.setData(0, ROLE_REL, rel)
                item.setData(0, ROLE_IS_DIR, is_dir)
                item.setData(0, ROLE_IGNORED, ignored)
                if ignored:
                    item.setForeground(0, QColor("#6f7585"))
                    item.setToolTip(0, "Excluded by .aiignore")
                else:
                    if rel == MEMORY_FILENAME:
                        item.setForeground(0, QColor("#aaa2ff"))
                        item.setToolTip(0, "AI Project Memory — maintained automatically by TransferLoop and included in full/new-session exports.")
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    if is_dir:
                        item.setFlags(item.flags() | Qt.ItemIsAutoTristate)
                        item.setCheckState(0, Qt.Checked)
                    else:
                        item.setCheckState(0, previous_checks.get(rel, Qt.Checked))
                parent_item.addChild(item)
                if is_dir:
                    if not ignored:
                        add_children(item, path)
                    item.setExpanded(rel in previous_expanded if preserve_state else False)
                else:
                    file_total += 1

        add_children(root_item, self.model.root)
        root_item.setExpanded("" in previous_expanded if preserve_state else True)
        self.file_count.setText(f"{file_total} files")
        self.ignore_banner.setVisible(not (self.model.root / ".aiignore").exists())
        self._updating_checks = False
        self.update_export_info()
        if hasattr(self, "file_search"):
            self.filter_tree(self.file_search.text())

    def show_tree_menu(self, button: QToolButton):
        menu = QMenu(self)
        select_all = QAction("Select all exportable files", self)
        select_all.triggered.connect(lambda: self.set_all_file_checks(Qt.Checked))
        menu.addAction(select_all)
        clear_all = QAction("Clear selection", self)
        clear_all.triggered.connect(lambda: self.set_all_file_checks(Qt.Unchecked))
        menu.addAction(clear_all)
        menu.addSeparator()
        refresh = QAction("Refresh project files", self)
        refresh.triggered.connect(self.refresh_tree)
        menu.addAction(refresh)
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def set_all_file_checks(self, state: Qt.CheckState):
        self._updating_checks = True

        def walk(item: QTreeWidgetItem):
            for i in range(item.childCount()):
                child = item.child(i)
                if child.data(0, ROLE_IGNORED):
                    continue
                if child.flags() & Qt.ItemIsUserCheckable:
                    child.setCheckState(0, state)
                if child.data(0, ROLE_IS_DIR):
                    walk(child)

        walk(self.tree.invisibleRootItem())
        self._updating_checks = False
        self.update_export_info()

    def filter_tree(self, text: str):
        query = text.strip().lower()

        def filter_item(item: QTreeWidgetItem) -> bool:
            own_match = not query or query in item.text(0).lower()
            child_match = False
            for i in range(item.childCount()):
                if filter_item(item.child(i)):
                    child_match = True
            visible = own_match or child_match
            item.setHidden(not visible)
            if query and child_match:
                item.setExpanded(True)
            return visible

        for i in range(self.tree.topLevelItemCount()):
            filter_item(self.tree.topLevelItem(i))

    def on_item_changed(self, item: QTreeWidgetItem, column: int):
        if self._updating_checks:
            return
        self.update_export_info()

    def selected_files(self) -> list[str]:
        result: list[str] = []
        iterator = self.tree.invisibleRootItem()

        def walk(item: QTreeWidgetItem):
            for i in range(item.childCount()):
                child = item.child(i)
                if child.data(0, ROLE_IGNORED):
                    continue
                if child.data(0, ROLE_IS_DIR):
                    walk(child)
                elif child.checkState(0) == Qt.Checked:
                    result.append(child.data(0, ROLE_REL))

        walk(iterator)
        return sorted(result)

    def update_export_info(self):
        if not self.model:
            return
        selected = self.selected_files()
        total_size = 0
        for rel in selected:
            try:
                total_size += (self.model.root / rel).stat().st_size
            except OSError:
                pass
        changed = self.model.changed_since_sync() if self.model.state.initialized else []
        self.export_info.setText(f"{len(selected)} selected  •  {self.human_size(total_size)}  •  {len(changed)} locally changed")
        self.export_changed_btn.setText(f"Export Changed ({len(changed)})")
        self.export_changed_btn.setEnabled(bool(changed) and self.model.state.initialized)
        export_folder = Path(self.settings.export_folder).expanduser()
        self.export_folder_label.setText(str(export_folder))
        self.export_folder_label.setToolTip(str(export_folder))

    @staticmethod
    def human_size(size: int) -> str:
        units = ["B", "KB", "MB", "GB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024
        return f"{size} B"

    def create_default_ignore(self):
        if not self.model:
            return
        path = self.model.root / ".aiignore"
        if path.exists():
            return
        path.write_text(DEFAULT_AIIGNORE, encoding="utf-8")
        self.refresh_tree(preserve_state=True)
        self.refresh_status("Created .aiignore with recommended exclusions.")
        self.reset_project_disk_snapshot()

    def tree_context_menu(self, point):
        if not self.model:
            return
        item = self.tree.itemAt(point)
        if not item:
            return
        rel = item.data(0, ROLE_REL)
        if rel is None or rel == "":
            return
        menu = QMenu(self)
        ignored = bool(item.data(0, ROLE_IGNORED))
        is_dir = bool(item.data(0, ROLE_IS_DIR))
        path = self.model.root / rel
        if not is_dir and path.exists() and likely_text_file(path):
            edit_action = QAction("Open in Editor", self)
            edit_action.triggered.connect(lambda: self.open_file_in_editor(rel))
            menu.addAction(edit_action)
            menu.addSeparator()
        if not ignored:
            ignore_label = "Add folder to .aiignore" if is_dir else "Add file to .aiignore"
            add_ignore_action = QAction(ignore_label, self)
            add_ignore_action.triggered.connect(lambda: self.add_item_to_ignore(rel, is_dir))
            menu.addAction(add_ignore_action)
        open_action = QAction("Open in Explorer", self)
        open_action.triggered.connect(lambda: self.reveal_path(self.model.root / rel))
        menu.addAction(open_action)
        menu.exec(self.tree.viewport().mapToGlobal(point))

    def add_item_to_ignore(self, rel: str, is_dir: bool):
        if not self.model:
            return
        add_pattern(self.model.root, rel, is_dir)
        self.refresh_tree(preserve_state=True)
        kind = "folder" if is_dir else "file"
        self.refresh_status(f"Added {kind} {rel} to .aiignore")
        self.reset_project_disk_snapshot()

    def export_mode(self, mode: str):
        if not self.model:
            return
        if mode == "selected":
            paths = self.selected_files()
            if not paths:
                QMessageBox.information(self, "Nothing selected", "Select at least one file to export.")
                return
        elif mode == "changed":
            if not self.model.state.initialized:
                QMessageBox.information(self, "Initialize first", "Create a full initial export before using Export Changed.")
                return
            paths = self.model.changed_since_sync()
            if not paths:
                QMessageBox.information(self, "Already synchronized", "No local file changes were detected since the last sync.")
                return
        else:
            if not (self.model.root / ".aiignore").exists():
                box = QMessageBox(self)
                box.setWindowTitle("No .aiignore found")
                box.setText("This project does not have a .aiignore file yet.")
                box.setInformativeText("A full export may include virtual environments, caches, build output, or sensitive files. Create the recommended .aiignore before exporting?")
                create_btn = box.addButton("Create .aiignore", QMessageBox.AcceptRole)
                continue_btn = box.addButton("Export Anyway", QMessageBox.DestructiveRole)
                cancel_btn = box.addButton(QMessageBox.Cancel)
                box.exec()
                if box.clickedButton() == cancel_btn:
                    return
                if box.clickedButton() == create_btn:
                    self.create_default_ignore()
            paths = [rel for rel, _, ignored in self.model.iter_files() if not ignored]
            mode = "all"

        export_dir = Path(self.settings.export_folder).expanduser()
        try:
            export_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Export folder unavailable", f"Could not use the selected export folder:\n{export_dir}\n\n{exc}")
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session = self.model.state.ensure_session()
        filename = f"{self.model.state.name}_{session}_{mode}_{stamp}.zip"
        destination = export_dir / filename
        try:
            artifacts = export_package(self.model, paths, destination, mode)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.last_export = artifacts.zip_path
        self.last_instructions = artifacts.instructions_path
        self.last_export_mode = artifacts.mode
        self.last_export_paths = artifacts.exported_paths
        self.last_export_label.setText(artifacts.zip_path.name)
        self.last_export_label.setToolTip(str(artifacts.zip_path))
        self.last_export_meta.setText(f"Created just now  •  {self.human_size(artifacts.zip_path.stat().st_size)}")
        self.instructions_label.setText(artifacts.instructions_path.name)
        self.instructions_label.setToolTip(str(artifacts.instructions_path))
        self.instructions_meta.setText("Generated just now  •  Read first, then inspect the project ZIP")
        self.copy_export_btn.setEnabled(True)
        self.copy_instructions_btn.setEnabled(True)
        self.update_ready_files_button()
        self.edit_instructions_btn.setEnabled(True)
        self.open_export_btn.setEnabled(True)
        self.refresh_tree(preserve_state=True)
        self.refresh_status(f"Created {mode} export and AI instructions: {artifacts.zip_path.name}")
        self.reset_project_disk_snapshot()

    def choose_export_folder(self):
        start = self.settings.export_folder or str(Path.home() / "Downloads")
        folder = QFileDialog.getExistingDirectory(self, "Choose export ZIP folder", start)
        if not folder:
            return
        self.settings.export_folder = folder
        self.settings.save()
        self.update_export_info()
        self.refresh_status(f"Export destination changed to {folder}")

    def ready_artifact_paths(self) -> list[Path]:
        paths: list[Path] = []
        for artifact in (self.last_export, self.last_instructions):
            if artifact and artifact.exists():
                paths.append(artifact.resolve())
        return paths

    def update_ready_files_button(self):
        paths = self.ready_artifact_paths()
        multiple = len(paths) > 1
        self.select_ready_files_btn.setVisible(multiple)
        self.select_ready_files_btn.setEnabled(multiple)
        if multiple:
            self.select_ready_files_btn.setToolTip(
                f"Open File Explorer and select all {len(paths)} generated Ready for AI files so they can be dragged into the browser chat"
            )

    def select_ready_artifacts_in_explorer(self):
        paths = self.ready_artifact_paths()
        if len(paths) < 2:
            self.update_ready_files_button()
            QMessageBox.information(
                self,
                "Multiple files not available",
                "Create an export with multiple Ready for AI files before selecting them in Explorer.",
            )
            return

        parents = {path.parent.resolve() for path in paths}
        if len(parents) != 1:
            QMessageBox.warning(
                self,
                "Files are in different folders",
                "The generated Ready for AI files are not in the same folder, so they cannot be selected together.",
            )
            return

        folder = next(iter(parents))
        if not sys.platform.startswith("win"):
            self.reveal_path(folder)
            self.refresh_status(f"Opened the Ready for AI folder containing {len(paths)} files.")
            return

        def ps_quote(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"

        names = ", ".join(ps_quote(path.name) for path in paths)
        folder_literal = ps_quote(str(folder))
        script = f'''
$ErrorActionPreference = 'SilentlyContinue'
$folderPath = {folder_literal}
$fileNames = @({names})
$shell = New-Object -ComObject Shell.Application
$target = $null

foreach ($window in @($shell.Windows())) {{
    try {{
        $windowPath = $window.Document.Folder.Self.Path
        if ([string]::Equals(
            [System.IO.Path]::GetFullPath($windowPath),
            [System.IO.Path]::GetFullPath($folderPath),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {{
            $target = $window
            break
        }}
    }} catch {{}}
}}

if (-not $target) {{
    $shell.Open($folderPath)
    for ($attempt = 0; $attempt -lt 24 -and -not $target; $attempt++) {{
        Start-Sleep -Milliseconds 125
        foreach ($window in @($shell.Windows())) {{
            try {{
                $windowPath = $window.Document.Folder.Self.Path
                if ([string]::Equals(
                    [System.IO.Path]::GetFullPath($windowPath),
                    [System.IO.Path]::GetFullPath($folderPath),
                    [System.StringComparison]::OrdinalIgnoreCase
                )) {{
                    $target = $window
                    break
                }}
            }} catch {{}}
        }}
    }}
}}

if ($target) {{
    $view = $target.Document
    $first = $true
    foreach ($name in $fileNames) {{
        $item = $view.Folder.ParseName($name)
        if ($null -ne $item) {{
            if ($first) {{
                # SELECT | DESELECTOTHERS | ENSUREVISIBLE | FOCUSED
                $view.SelectItem($item, 29)
                $first = $false
            }} else {{
                # SELECT | ENSUREVISIBLE; keep earlier items selected.
                $view.SelectItem($item, 9)
            }}
        }}
    }}

    try {{
        Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class TransferLoopWin32 {{
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}}
"@
        [TransferLoopWin32]::SetForegroundWindow([IntPtr]$target.HWND) | Out-Null
    }} catch {{}}
}}
'''
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
                creationflags=creationflags,
            )
        except OSError as exc:
            QMessageBox.warning(self, "Could not open File Explorer", str(exc))
            return

        self.refresh_status(f"Selected {len(paths)} Ready for AI files in File Explorer.")

    def copy_last_export(self):
        if not self.last_export or not self.last_export.exists():
            QMessageBox.information(self, "No export available", "Create an export before copying it to the clipboard.")
            return
        mime = QMimeData()
        resolved = self.last_export.resolve()
        mime.setUrls([QUrl.fromLocalFile(str(resolved))])
        mime.setText(str(resolved))
        QApplication.clipboard().setMimeData(mime)
        self.refresh_status(f"Copied ZIP to clipboard: {self.last_export.name}")

    def copy_last_instructions(self):
        if not self.last_instructions or not self.last_instructions.exists():
            QMessageBox.information(self, "No instructions available", "Create an export before copying the generated AI instructions.")
            return
        try:
            markdown = self.last_instructions.read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Could not read instructions", str(exc))
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(self.last_instructions.resolve()))])
        mime.setText(markdown)
        QApplication.clipboard().setMimeData(mime)
        self.refresh_status("Copied AI instructions to the clipboard.")

    def edit_ai_instructions(self):
        if not self.model:
            return
        dialog = MarkdownEditorDialog(
            f"AI Instructions — {self.model.state.name}",
            read_project_instructions(self.model.root, self.model.state.project_instructions),
            self,
            reset_text_provider=read_base_template,
            reset_label="Reset to Base Template",
        )
        if not dialog.exec():
            return
        save_project_instructions(self.model.root, dialog.markdown())
        if self.last_export and self.last_export.exists() and self.last_export_mode:
            self.last_instructions = write_exported_instructions(
                self.model, self.last_export, self.last_export_mode, self.last_export_paths
            )
            self.instructions_label.setText(self.last_instructions.name)
            self.instructions_label.setToolTip(str(self.last_instructions))
            self.instructions_meta.setText("Updated just now  •  Generated from this project's customized instructions")
            self.copy_instructions_btn.setEnabled(True)
        self.refresh_status("Project AI instructions saved.")

    def open_export_folder(self):
        path = self.last_export.parent if self.last_export else Path(self.settings.export_folder).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Export folder unavailable", str(exc))
            return
        self.reveal_path(path)

    def reveal_path(self, path: Path):
        try:
            if sys.platform.startswith("win"):
                if path.is_file():
                    subprocess.Popen(["explorer", "/select,", str(path)])
                else:
                    os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path if path.is_dir() else path.parent)])
        except Exception:
            pass

    def reset_project_disk_snapshot(self):
        """Reset the live-project watcher baseline after an app-managed change."""
        self._project_scan_generation += 1
        self._project_scan_inflight = False
        if not self.model:
            self._project_disk_snapshot = None
            return
        try:
            self._project_disk_snapshot = self.model.disk_snapshot()
        except OSError:
            self._project_disk_snapshot = None

    def poll_project_changes(self):
        """Check for IDE/file-system edits without blocking the Qt UI thread."""
        if not self.model or not self.isVisible() or self._project_scan_inflight:
            return

        model = self.model
        generation = self._project_scan_generation
        root = str(model.root)
        self._project_scan_inflight = True

        def scan():
            try:
                snapshot = model.disk_snapshot()
            except Exception:
                snapshot = None
            self.project_scan_ready.emit(generation, root, snapshot)

        threading.Thread(
            target=scan,
            name="TransferLoopProjectScan",
            daemon=True,
        ).start()

    def _on_project_scan_ready(self, generation: int, root: str, snapshot):
        if generation != self._project_scan_generation:
            return
        if not self.model or str(self.model.root) != root:
            return

        self._project_scan_inflight = False
        if not isinstance(snapshot, ProjectDiskSnapshot):
            return

        previous = self._project_disk_snapshot
        self._project_disk_snapshot = snapshot
        if previous is None:
            return

        tracked_changed = snapshot.tracked_files != previous.tracked_files
        tree_changed = snapshot.tree_entries != previous.tree_entries
        if not tracked_changed and not tree_changed:
            return

        # Clean built-in editor tabs can be reloaded immediately. Dirty tabs keep
        # their local buffer and receive the existing external-change warning.
        self.editor_workspace.sync_from_disk()

        if tree_changed:
            self.refresh_tree(preserve_state=True)

        # changed_since_sync() hashes only after this metadata scan reports an
        # actual change, and ProjectModel reuses hashes for unchanged files.
        self.refresh_status()

    def reset_zip_baseline(self):
        self.scanned_zip_signatures.clear()
        folder = Path(self.settings.download_folder)
        if folder.exists():
            for zip_path in folder.glob("*.zip"):
                try:
                    self.scanned_zip_signatures.add(zip_signature(zip_path))
                except OSError:
                    pass

    def poll_downloads(self):
        if not self.model or not self.settings.monitor_downloads or self.pending_import:
            return
        folder = Path(self.settings.download_folder)
        if not folder.exists():
            self.import_watch.setText("▲ AI response folder unavailable")
            self.import_status.setText("Change the AI Response Folder in Preferences or Project Settings.")
            return
        for zip_path in sorted(folder.glob("*.zip"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
            try:
                sig = zip_signature(zip_path)
            except OSError:
                continue
            if sig in self.scanned_zip_signatures or sig in self.model.state.seen_zip_signatures:
                continue
            inspection = inspect_zip(self.model, zip_path)
            self.scanned_zip_signatures.add(sig)
            if inspection:
                self.pending_import = inspection
                self.import_watch.setText("✓ New response detected")
                self.import_status.setText(f"{zip_path.name}\n{len(inspection.changes)} change(s) ready to review")
                self.review_btn.setVisible(True)
                break

    def manual_import(self):
        if not self.model:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import AI response ZIP", self.settings.download_folder, "ZIP files (*.zip)")
        if not path:
            return
        zip_path = Path(path)
        try:
            sig = zip_signature(zip_path)
        except OSError:
            sig = ""
        if sig:
            # A manual import must also become part of the watcher's transient baseline.
            # Otherwise the watcher can rediscover the same ZIP immediately after the
            # review is applied, when only app-managed .aimemory has changed.
            self.scanned_zip_signatures.add(sig)
            if sig in self.model.state.seen_zip_signatures:
                answer = QMessageBox.question(
                    self,
                    "Response already applied",
                    "This exact response ZIP was already applied to this project.\n\nReview it again anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return
        inspection = inspect_zip(self.model, zip_path)
        if not inspection:
            QMessageBox.warning(
                self,
                "Could not map ZIP to project",
                "The ZIP could not be confidently mapped to this project's files.\n\nFor best results, ask the AI to include .ai-response.json and preserve project-relative file paths.",
            )
            return
        if self.pending_import:
            self.pending_import.cleanup()
        self.pending_import = inspection
        self.import_watch.setText("✓ Response imported")
        self.import_status.setText(f"{Path(path).name}\n{len(inspection.changes)} change(s) ready to review")
        self.review_btn.setVisible(True)

    def open_pending_review(self):
        if self.model and self.pending_import:
            changed_paths = {change.path for change in self.pending_import.changes}
            dirty_overlap = self.editor_workspace.dirty_paths() & changed_paths
            if not self.editor_workspace.prepare_for_external_changes(changed_paths):
                return

            # If the user saved or discarded an overlapping editor buffer, inspect the ZIP
            # again against the now-authoritative disk state so conflict flags stay accurate.
            if dirty_overlap:
                old_inspection = self.pending_import
                refreshed = inspect_zip(self.model, Path(old_inspection.zip_path))
                if refreshed:
                    old_inspection.cleanup()
                    self.pending_import = refreshed
                    self.import_status.setText(
                        f"{Path(refreshed.zip_path).name}\n{len(refreshed.changes)} change(s) ready to review"
                    )

            inspection = self.pending_import
            self.pending_import = None
            self.review_btn.setVisible(False)
            self.review_requested.emit(self.model, inspection)

    def restore_pending_review(self, inspection: ImportInspection | None):
        """Return a paused review to the project page without discarding staged files."""
        if not inspection:
            return
        if not self.model:
            inspection.cleanup()
            return
        if self.pending_import and self.pending_import is not inspection:
            self.pending_import.cleanup()
        self.pending_import = inspection
        self.import_watch.setText("✓ Response ready to review")
        self.import_status.setText(
            f"{Path(inspection.zip_path).name}\n{len(inspection.changes)} change(s) ready to review"
        )
        self.review_btn.setVisible(True)

    def refresh_status(self, message: str = ""):
        if not self.model:
            return
        state = self.model.state
        if not state.initialized:
            self.sync_label.setText("○ Not initialized")
            self.sync_label.setObjectName("Warn")
            self.init_btn.setVisible(True)
            self.session_id.setText(state.session_id or "Not initialized")
        else:
            changed = self.model.changed_since_sync()
            self.session_id.setText(state.session_id)
            self.init_btn.setVisible(False)
            if changed:
                self.sync_label.setText(f"▲ Behind · {len(changed)} local change(s)")
                self.sync_label.setObjectName("Warn")
            else:
                self.sync_label.setText("● Synced")
                self.sync_label.setObjectName("Good")
        self.sync_label.style().unpolish(self.sync_label)
        self.sync_label.style().polish(self.sync_label)
        has_backup = bool(state.last_backup)
        self.undo_btn.setVisible(has_backup)
        self.undo_label.setText("Last merge is protected by an automatic backup." if has_backup else "Protected by automatic backups")
        if message:
            self.session_hint.setText(message)
        else:
            self.session_hint.setText("This conversation has the latest project state that was exported from TransferLoop.")
        self.update_export_info()
        if not self.pending_import:
            if self.settings.monitor_downloads:
                self.import_watch.setText("● Watching for AI responses")
                self.import_status.setText(f"{self.settings.download_folder}\nWaiting for a new AI response ZIP…")
            else:
                self.import_watch.setText("○ Automatic watching is off")
                self.import_status.setText("Use Import ZIP… to choose an AI response manually.")

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self.model, self)
        if dialog.exec():
            self.reset_zip_baseline()
            self.refresh_status("Settings saved.")

    def undo_last(self):
        if not self.model:
            return
        if not self.model.state.last_backup:
            QMessageBox.information(self, "No backup available", "There is no previous apply operation to undo.")
            return
        answer = QMessageBox.question(self, "Undo last apply", "Restore the files from the backup created before the last AI merge?")
        if answer != QMessageBox.Yes:
            return
        count = undo_last_apply(self.model)
        self.editor_workspace.sync_from_disk()
        self.refresh_tree(preserve_state=True)
        self.refresh_status(f"Restored {count} file(s) from the previous backup.")
        self.reset_project_disk_snapshot()
