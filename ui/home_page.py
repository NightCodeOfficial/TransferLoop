from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

from core.storage import AppSettings
from .icons import copy_icon, folder_icon, trash_icon
from .elided_label import ElidedLabel


class RecentProjectCard(QFrame):
    open_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, project_path: str, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        path = Path(project_path)
        self.available = path.exists() and path.is_dir()

        self.setObjectName("RecentProjectCard")
        self.setCursor(Qt.PointingHandCursor if self.available else Qt.ArrowCursor)
        self.setMinimumHeight(84)
        self.setToolTip("Open project" if self.available else "Project folder is currently unavailable")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(17, 13, 13, 13)
        layout.setSpacing(7)

        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(8)

        name = QLabel(path.name or str(path))
        name.setObjectName("RecentProjectName")
        name.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        name_row.addWidget(name, 1)

        if not self.available:
            unavailable = QLabel("Unavailable")
            unavailable.setObjectName("Warn")
            unavailable.setToolTip("The saved project path does not currently exist. The recent entry was kept so it is not lost because of a disconnected drive or temporary sync issue.")
            name_row.addWidget(unavailable)

        layout.addLayout(name_row)

        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.setSpacing(7)

        path_label = ElidedLabel(str(path))
        path_label.setObjectName("RecentProjectPath")
        path_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        path_row.addWidget(path_label, 1)

        copy_btn = QToolButton()
        copy_btn.setObjectName("WireIconButton")
        copy_btn.setIcon(copy_icon())
        copy_btn.setIconSize(QSize(18, 18))
        copy_btn.setToolTip("Copy project path")
        copy_btn.clicked.connect(self.copy_path)
        path_row.addWidget(copy_btn)

        folder_btn = QToolButton()
        folder_btn.setObjectName("WireIconButton")
        folder_btn.setIcon(folder_icon())
        folder_btn.setIconSize(QSize(18, 18))
        folder_btn.setToolTip("Open project folder" if self.available else "Project folder is unavailable")
        folder_btn.setEnabled(self.available)
        folder_btn.clicked.connect(self.open_folder)
        path_row.addWidget(folder_btn)

        remove_btn = QToolButton()
        remove_btn.setObjectName("DangerIconButton")
        remove_btn.setIcon(trash_icon())
        remove_btn.setIconSize(QSize(18, 18))
        remove_btn.setToolTip("Remove from recent projects")
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.project_path))
        path_row.addWidget(remove_btn)

        layout.addLayout(path_row)

    def copy_path(self):
        QApplication.clipboard().setText(self.project_path)

    def open_folder(self):
        if self.available:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.project_path))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.available:
            self.open_requested.emit(self.project_path)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class HomePage(QWidget):
    project_requested = Signal(str)

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        root = QVBoxLayout(self)
        root.setContentsMargins(44, 36, 44, 36)
        root.setSpacing(20)

        title = QLabel("TransferLoop")
        title.setObjectName("Title")
        subtitle = QLabel("Keep a local project synchronized with an AI coding conversation — without giving the AI direct access to your computer.")
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        open_btn = QPushButton("Open a Project")
        open_btn.setObjectName("Primary")
        open_btn.setMinimumHeight(44)
        open_btn.clicked.connect(self.choose_project)
        root.addWidget(open_btn)

        recent_row = QHBoxLayout()
        recent_label = QLabel("Recent projects")
        recent_label.setObjectName("SectionTitle")
        self.project_search = QLineEdit()
        self.project_search.setObjectName("TreeSearch")
        self.project_search.setPlaceholderText("Search projects…")
        self.project_search.setClearButtonEnabled(True)
        self.project_search.setMaximumWidth(360)
        self.project_search.textChanged.connect(self.filter_projects)
        recent_row.addWidget(recent_label)
        recent_row.addStretch(1)
        recent_row.addWidget(self.project_search)
        root.addLayout(recent_row)

        self.recent = QListWidget()
        self.recent.setObjectName("RecentProjectList")
        self.recent.setSpacing(10)
        self.recent.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.recent.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        root.addWidget(self.recent, 1)
        self.refresh()

    def refresh(self):
        self.recent.clear()
        for project in self.settings.recent_projects:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 88))
            item.setData(Qt.UserRole, project)
            self.recent.addItem(item)

            card = RecentProjectCard(project)
            card.open_requested.connect(self.project_requested.emit)
            card.remove_requested.connect(self.remove_recent_project)
            self.recent.setItemWidget(item, card)
        self.filter_projects(self.project_search.text())

    def filter_projects(self, text: str):
        query = text.strip().casefold()
        for index in range(self.recent.count()):
            item = self.recent.item(index)
            path_text = str(item.data(Qt.UserRole) or "")
            path = Path(path_text)
            haystack = f"{path.name}\n{path_text}".casefold()
            item.setHidden(bool(query) and query not in haystack)

    def remove_recent_project(self, project_path: str):
        if self.settings.confirm_recent_project_removal:
            path = Path(project_path)
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Remove project")
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setText("Are you sure you want to remove this project?")
            dialog.setInformativeText(
                f'"{path.name}" will be removed from Recent projects. '
                "The project folder and TransferLoop's saved project history will not be deleted."
            )

            dont_ask = QCheckBox("Don't ask again")
            dialog.setCheckBox(dont_ask)

            remove_btn = dialog.addButton("Remove", QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = dialog.addButton(QMessageBox.StandardButton.Cancel)
            dialog.setDefaultButton(cancel_btn)
            dialog.exec()

            if dialog.clickedButton() is not remove_btn:
                return

            if dont_ask.isChecked():
                self.settings.confirm_recent_project_removal = False
                self.settings.save()

        self.settings.remove_recent(project_path)
        self.refresh()

    def choose_project(self):
        folder = QFileDialog.getExistingDirectory(self, "Open project folder", str(Path.home()))
        if folder:
            self.project_requested.emit(folder)
