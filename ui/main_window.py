from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QStackedWidget

from core.storage import AppSettings
from .home_page import HomePage
from .project_page import ProjectPage
from .review_page import ReviewPage
from .settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TransferLoop")
        self.resize(1280, 800)
        self.setMinimumSize(980, 650)

        self.settings = AppSettings.load()
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.home = HomePage(self.settings)
        self.project = ProjectPage(self.settings)
        self.review = ReviewPage(self.settings)

        self.stack.addWidget(self.home)
        self.stack.addWidget(self.project)
        self.stack.addWidget(self.review)

        self.home.project_requested.connect(self.open_project)
        self.project.back_requested.connect(self.show_home)
        self.project.review_requested.connect(self.show_review)
        self.review.finished.connect(self.review_finished)
        self.review.cancelled.connect(self.review_cancelled)

        self._build_menu_bar()
        self.stack.setCurrentWidget(self.home)

    def _build_menu_bar(self):
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)

        file_menu = menu_bar.addMenu("File")
        open_action = QAction("Open Project…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.choose_project)
        file_menu.addAction(open_action)
        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menu_bar.addMenu("Edit")
        self.undo_apply_action = QAction("Undo Last Apply", self)
        # Ctrl+Z belongs to the built-in code editor when it has focus. Keep the
        # AI merge rollback on an explicit, non-conflicting shortcut.
        self.undo_apply_action.setShortcut("Ctrl+Alt+Z")
        self.undo_apply_action.triggered.connect(self.project.undo_last)
        edit_menu.addAction(self.undo_apply_action)
        edit_menu.addSeparator()

        preferences_action = QAction("Preferences…", self)
        preferences_action.setShortcut("Ctrl+,")
        preferences_action.triggered.connect(self.open_preferences)
        edit_menu.addAction(preferences_action)
        edit_menu.aboutToShow.connect(self._refresh_edit_menu)


    def _refresh_edit_menu(self):
        has_backup = bool(self.project.model and self.project.model.state.last_backup)
        self.undo_apply_action.setEnabled(has_backup)

    def choose_project(self):
        start = self.project.model.root if self.project.model else Path.home()
        folder = QFileDialog.getExistingDirectory(self, "Open project folder", str(start))
        if folder:
            self.open_project(folder)

    def open_preferences(self):
        dialog = SettingsDialog(self.settings, None, self)
        if dialog.exec() and self.project.model:
            self.project.refresh_status("Preferences updated.")

    def animate_page(self, widget):
        self.stack.setCurrentWidget(widget)
        # Keep transition intentionally subtle; page state should feel responsive, not theatrical.
        animation = QPropertyAnimation(widget, b"windowOpacity", self)
        animation.setDuration(140)
        animation.setStartValue(0.92)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start()
        self._page_animation = animation

    def open_project(self, path: str):
        if self.project.load_project(path):
            self.animate_page(self.project)

    def show_home(self):
        self.home.refresh()
        self.animate_page(self.home)

    def show_review(self, model, inspection):
        self.review.load_review(model, inspection)
        self.animate_page(self.review)

    def review_finished(self, message: str):
        self.project.after_external_project_change(message)
        self.animate_page(self.project)

    def review_cancelled(self, inspection):
        self.project.restore_pending_review(inspection)
        self.project.refresh_status("Review paused. Pending AI changes are still available.")
        self.animate_page(self.project)

    def closeEvent(self, event):
        if self.project.prepare_to_close():
            event.accept()
        else:
            event.ignore()
