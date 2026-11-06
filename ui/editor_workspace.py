from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from PySide6.QtCore import QSize, QTimer, Qt, Signal, QUrl
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.ignore import is_ignored, load_patterns
from core.project import likely_text_file

from .code_editor import CodeEditor
from .icons import book_icon, quill_icon
from .markdown_preview import MARKDOWN_DOCUMENT_STYLE, markdown_preview_source


@dataclass
class OpenDocument:
    rel_path: str
    path: Path
    editor: CodeEditor
    tab_widget: QWidget
    encoding: str
    newline: str
    disk_signature: tuple[int, int] | None
    preview: QTextBrowser | None = None
    read_mode: bool = False
    external_changed: bool = False
    edit_cursor_position: int = 0
    edit_scroll_value: int = 0
    edit_horizontal_scroll_value: int = 0
    read_entry_ratio: float = 0.0

    @property
    def is_markdown(self) -> bool:
        return self.preview is not None


def _disk_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


def _read_text_file(path: Path) -> tuple[str, str, str]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
        text = raw.decode(encoding)
    else:
        try:
            encoding = "utf-8"
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            encoding = "cp1252"
            text = raw.decode(encoding)

    if b"\r\n" in raw:
        newline = "\r\n"
    elif b"\r" in raw:
        newline = "\r"
    else:
        newline = "\n"
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text, encoding, newline


class QuickOpenDialog(QDialog):
    def __init__(self, paths: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quick Open")
        self.resize(640, 430)
        self.paths = paths
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type a file name or project-relative path…")
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._accept_current)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        root.addWidget(self.search)
        root.addWidget(self.list, 1)
        self._filter("")
        self.search.setFocus()

    def _filter(self, text: str) -> None:
        query = text.strip().lower()
        self.list.clear()
        matches = [path for path in self.paths if not query or query in path.lower()]
        matches.sort(key=lambda path: (0 if Path(path).name.lower().startswith(query) and query else 1, len(path), path.lower()))
        for path in matches[:300]:
            item = QListWidgetItem(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _accept_current(self) -> None:
        if self.list.currentItem():
            self.accept()

    def selected_path(self) -> str | None:
        item = self.list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else None


class EditorWorkspace(QWidget):
    overview_requested = Signal()
    sidebar_toggle_requested = Signal()
    file_saved = Signal(str)
    tabs_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_root: Path | None = None
        self.documents: dict[str, OpenDocument] = {}
        self.sidebar_visible = True

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QFrame()
        toolbar.setObjectName("EditorToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 6, 8, 6)
        toolbar_layout.setSpacing(8)
        self.overview_btn = QPushButton("Sync Overview")
        self.overview_btn.setObjectName("TextButton")
        self.overview_btn.clicked.connect(self.overview_requested.emit)
        self.path_label = QLabel("Editor")
        self.path_label.setObjectName("EditorPath")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.sidebar_btn = QPushButton("Hide AI Sync")
        self.sidebar_btn.setObjectName("Secondary")
        self.sidebar_btn.clicked.connect(self.sidebar_toggle_requested.emit)
        self.markdown_mode_btn = QToolButton()
        self.markdown_mode_btn.setObjectName("EditorModeButton")
        self.markdown_mode_btn.setAutoRaise(True)
        self.markdown_mode_btn.setIconSize(QSize(18, 18))
        self.markdown_mode_btn.setVisible(False)
        self.markdown_mode_btn.clicked.connect(self.toggle_markdown_mode)
        toolbar_layout.addWidget(self.overview_btn)
        toolbar_layout.addWidget(self.path_label, 1)
        toolbar_layout.addWidget(self.sidebar_btn)
        toolbar_layout.addWidget(self.markdown_mode_btn)
        root.addWidget(toolbar)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("EditorTabs")
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._current_tab_changed)
        root.addWidget(self.tabs, 1)

        self.find_bar = QFrame()
        self.find_bar.setObjectName("EditorFindBar")
        find_layout = QHBoxLayout(self.find_bar)
        find_layout.setContentsMargins(8, 6, 8, 6)
        find_layout.setSpacing(6)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Find")
        self.find_input.returnPressed.connect(self.find_next)
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replace")
        self.replace_input.setVisible(False)
        self.case_check = QCheckBox("Match case")
        prev_btn = QPushButton("↑")
        prev_btn.setObjectName("EditorMiniButton")
        next_btn = QPushButton("↓")
        next_btn.setObjectName("EditorMiniButton")
        self.replace_btn = QPushButton("Replace")
        self.replace_btn.setObjectName("EditorMiniButton")
        self.replace_btn.setVisible(False)
        self.replace_all_btn = QPushButton("Replace All")
        self.replace_all_btn.setObjectName("EditorMiniButton")
        close_find = QPushButton("×")
        close_find.setObjectName("EditorMiniButton")
        prev_btn.clicked.connect(lambda: self.find_next(backward=True))
        next_btn.clicked.connect(self.find_next)
        self.replace_btn.clicked.connect(self.replace_current)
        self.replace_all_btn.clicked.connect(self.replace_all)
        close_find.clicked.connect(self.hide_find)
        find_layout.addWidget(self.find_input, 1)
        find_layout.addWidget(self.replace_input, 1)
        find_layout.addWidget(self.case_check)
        find_layout.addWidget(prev_btn)
        find_layout.addWidget(next_btn)
        find_layout.addWidget(self.replace_btn)
        find_layout.addWidget(self.replace_all_btn)
        find_layout.addWidget(close_find)
        self.find_bar.setVisible(False)
        root.addWidget(self.find_bar)

        status = QFrame()
        status.setObjectName("EditorStatusBar")
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(10, 5, 10, 5)
        status_layout.setSpacing(16)
        self.status_message = QLabel("")
        self.status_message.setObjectName("StatusMuted")
        self.cursor_label = QLabel("Ln 1, Col 1")
        self.cursor_label.setObjectName("EditorStatusValue")
        self.indent_label = QLabel("Spaces: 4")
        self.indent_label.setObjectName("EditorStatusValue")
        self.encoding_label = QLabel("UTF-8")
        self.encoding_label.setObjectName("EditorStatusValue")
        self.newline_label = QLabel("LF")
        self.newline_label.setObjectName("EditorStatusValue")
        self.language_label = QLabel("Plain Text")
        self.language_label.setObjectName("EditorStatusValue")
        status_layout.addWidget(self.status_message, 1)
        status_layout.addWidget(self.cursor_label)
        status_layout.addWidget(self.indent_label)
        status_layout.addWidget(self.encoding_label)
        status_layout.addWidget(self.newline_label)
        status_layout.addWidget(self.language_label)
        root.addWidget(status)

        self._shortcuts: list[QShortcut] = []
        self._add_shortcut(QKeySequence.StandardKey.Save, self.save_current)
        self._add_shortcut("Ctrl+Shift+S", self.save_all)
        self._add_shortcut(QKeySequence.StandardKey.Find, self.show_find)
        self._add_shortcut("Ctrl+H", lambda: self.show_find(replace=True))
        self._add_shortcut("Ctrl+G", self.go_to_line)
        self._add_shortcut("Ctrl+P", self.quick_open)
        self._add_shortcut("Ctrl+W", self.close_current_tab)
        self._add_shortcut("Ctrl+Tab", lambda: self.cycle_tabs(1))
        self._add_shortcut("Ctrl+Shift+Tab", lambda: self.cycle_tabs(-1))
        self._add_shortcut("Ctrl+Shift+B", self.sidebar_toggle_requested.emit)
        self._add_shortcut("Ctrl+E", self.toggle_markdown_mode)
        self._add_shortcut("Escape", self.hide_find)

        self.external_timer = QTimer(self)
        self.external_timer.setInterval(2000)
        self.external_timer.timeout.connect(self.check_external_changes)
        self.external_timer.start()

    def _add_shortcut(self, sequence, slot) -> None:
        shortcut = QShortcut(QKeySequence(sequence), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(slot)
        self._shortcuts.append(shortcut)

    def set_project_root(self, root: Path) -> None:
        if self.project_root and self.project_root != root:
            self.close_all(force=True)
        self.project_root = root.resolve()

    def set_sidebar_visible(self, visible: bool) -> None:
        self.sidebar_visible = visible
        self.sidebar_btn.setText("Hide AI Sync" if visible else "Show AI Sync")

    def has_open_tabs(self) -> bool:
        return bool(self.documents)

    def dirty_paths(self) -> set[str]:
        return {rel for rel, doc in self.documents.items() if doc.editor.document().isModified()}

    def current_document(self) -> OpenDocument | None:
        current = self.tabs.currentWidget()
        if current is None:
            return None
        for doc in self.documents.values():
            if doc.tab_widget is current:
                return doc
        return None

    def open_file(self, rel_path: str) -> bool:
        if not self.project_root:
            return False
        rel_path = Path(rel_path).as_posix()
        existing = self.documents.get(rel_path)
        if existing:
            self.tabs.setCurrentWidget(existing.tab_widget)
            self._focus_document(existing)
            return True

        path = self.project_root / rel_path
        try:
            if path.stat().st_size > 8 * 1024 * 1024:
                answer = QMessageBox.question(
                    self,
                    "Large text file",
                    f"{rel_path} is larger than 8 MB. Open it in the built-in editor anyway?",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return False
            text, encoding, newline = _read_text_file(path)
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(self, "Could not open file", f"{rel_path}\n\n{exc}")
            return False

        editor = CodeEditor(path)
        editor.setPlainText(text)
        editor.document().setModified(False)
        editor.cursor_status_changed.connect(self._cursor_status_changed)
        editor.document().modificationChanged.connect(lambda _modified, rel=rel_path: self._update_tab_title(rel))

        tab_widget: QWidget = editor
        preview: QTextBrowser | None = None
        if path.suffix.lower() in {".md", ".markdown"}:
            stack = QStackedWidget()
            stack.setObjectName("MarkdownDocumentStack")
            preview = QTextBrowser()
            preview.setObjectName("MarkdownReadView")
            preview.setOpenExternalLinks(True)
            preview.setOpenLinks(True)
            preview.document().setBaseUrl(QUrl.fromLocalFile(str(path.parent.resolve()) + os.sep))
            preview.document().setDocumentMargin(30)
            preview.document().setDefaultStyleSheet(MARKDOWN_DOCUMENT_STYLE)
            stack.addWidget(editor)
            stack.addWidget(preview)
            tab_widget = stack

        doc = OpenDocument(
            rel_path=rel_path,
            path=path,
            editor=editor,
            tab_widget=tab_widget,
            encoding=encoding,
            newline=newline,
            disk_signature=_disk_signature(path),
            preview=preview,
        )
        self.documents[rel_path] = doc
        index = self.tabs.addTab(tab_widget, path.name)
        self.tabs.setTabToolTip(index, rel_path)
        self.tabs.setCurrentIndex(index)
        self._focus_document(doc)
        self.tabs_changed.emit(self.tabs.count())
        self._update_tab_title(rel_path)
        self._update_status_for_document(doc)
        return True

    def _tab_index(self, doc: OpenDocument) -> int:
        return self.tabs.indexOf(doc.tab_widget)

    def _update_tab_title(self, rel_path: str) -> None:
        doc = self.documents.get(rel_path)
        if not doc:
            return
        index = self._tab_index(doc)
        if index < 0:
            return
        prefix = "⚠ " if doc.external_changed else ""
        suffix = " ●" if doc.editor.document().isModified() else ""
        self.tabs.setTabText(index, f"{prefix}{doc.path.name}{suffix}")
        self.tabs.setTabToolTip(index, rel_path)

    def _current_tab_changed(self, _index: int) -> None:
        doc = self.current_document()
        self._refresh_markdown_mode_button(doc)
        if doc:
            self._update_status_for_document(doc)
            if not doc.read_mode:
                cursor = doc.editor.textCursor()
                self._cursor_status_changed(cursor.blockNumber() + 1, cursor.positionInBlock() + 1)
        else:
            self.path_label.setText("Editor")

    def _update_status_for_document(self, doc: OpenDocument) -> None:
        self.path_label.setText(doc.rel_path)
        self.path_label.setToolTip(str(doc.path))
        self.encoding_label.setText(doc.encoding.upper().replace("-SIG", " BOM"))
        self.newline_label.setText({"\r\n": "CRLF", "\r": "CR", "\n": "LF"}.get(doc.newline, "LF"))
        self.cursor_label.setVisible(not doc.read_mode)
        self.indent_label.setVisible(not doc.read_mode)
        if doc.is_markdown:
            self.language_label.setText("Markdown · Read" if doc.read_mode else "Markdown · Edit")
        else:
            self.language_label.setText(doc.editor.language)
        if doc.external_changed:
            self.status_message.setText("File changed on disk — saving will ask before overwriting.")
        else:
            self.status_message.setText("")

    def _focus_document(self, doc: OpenDocument) -> None:
        if doc.read_mode and doc.preview is not None:
            doc.preview.setFocus()
        else:
            doc.editor.setFocus()

    @staticmethod
    def _vertical_scroll_ratio(widget) -> float:
        bar = widget.verticalScrollBar()
        span = bar.maximum() - bar.minimum()
        if span <= 0:
            return 0.0
        return max(0.0, min(1.0, (bar.value() - bar.minimum()) / span))

    @staticmethod
    def _set_vertical_scroll_ratio(widget, ratio: float) -> None:
        bar = widget.verticalScrollBar()
        ratio = max(0.0, min(1.0, ratio))
        span = bar.maximum() - bar.minimum()
        bar.setValue(bar.minimum() + round(span * ratio))

    def _remember_editor_markdown_position(self, doc: OpenDocument) -> float:
        cursor = doc.editor.textCursor()
        doc.edit_cursor_position = cursor.position()
        doc.edit_scroll_value = doc.editor.verticalScrollBar().value()
        doc.edit_horizontal_scroll_value = doc.editor.horizontalScrollBar().value()
        doc.read_entry_ratio = self._vertical_scroll_ratio(doc.editor)
        return doc.read_entry_ratio

    def _restore_editor_markdown_position(self, doc: OpenDocument, preview_ratio: float) -> None:
        # If the reader was not moved, return to the exact edit position. If the
        # reader was scrolled, carry that relative document position back into
        # the source editor instead of jumping to the old cursor.
        if abs(preview_ratio - doc.read_entry_ratio) <= 0.015:
            cursor = doc.editor.textCursor()
            cursor.setPosition(min(doc.edit_cursor_position, max(0, len(doc.editor.toPlainText()))))
            doc.editor.setTextCursor(cursor)
            doc.editor.verticalScrollBar().setValue(doc.edit_scroll_value)
            doc.editor.horizontalScrollBar().setValue(doc.edit_horizontal_scroll_value)
            return

        self._set_vertical_scroll_ratio(doc.editor, preview_ratio)
        block = doc.editor.firstVisibleBlock()
        if block.isValid():
            doc.editor.setTextCursor(QTextCursor(block))
            # setTextCursor may ensure the cursor is visible and nudge the view,
            # so restore the requested relative position afterward.
            self._set_vertical_scroll_ratio(doc.editor, preview_ratio)
        doc.editor.horizontalScrollBar().setValue(doc.edit_horizontal_scroll_value)

    def _restore_markdown_preview_position(self, rel_path: str, ratio: float) -> None:
        doc = self.documents.get(rel_path)
        if not doc or not doc.read_mode or doc.preview is None:
            return
        self._set_vertical_scroll_ratio(doc.preview, ratio)

    def _refresh_markdown_preview(self, doc: OpenDocument) -> None:
        if doc.preview is None:
            return
        doc.preview.setMarkdown(markdown_preview_source(doc.editor.toPlainText()))
        doc.preview.document().setDocumentMargin(30)
        doc.preview.document().setDefaultStyleSheet(MARKDOWN_DOCUMENT_STYLE)

    def _refresh_markdown_mode_button(self, doc: OpenDocument | None) -> None:
        is_markdown = bool(doc and doc.is_markdown)
        self.markdown_mode_btn.setVisible(is_markdown)
        if not doc or not doc.is_markdown:
            return
        if doc.read_mode:
            self.markdown_mode_btn.setIcon(quill_icon())
            self.markdown_mode_btn.setToolTip("Edit Markdown (Ctrl+E)")
            self.markdown_mode_btn.setAccessibleName("Edit Markdown")
        else:
            self.markdown_mode_btn.setIcon(book_icon())
            self.markdown_mode_btn.setToolTip("Read Markdown (Ctrl+E)")
            self.markdown_mode_btn.setAccessibleName("Read Markdown")

    def toggle_markdown_mode(self) -> None:
        doc = self.current_document()
        if not doc or not doc.is_markdown or not isinstance(doc.tab_widget, QStackedWidget):
            return
        if doc.read_mode:
            preview_ratio = self._vertical_scroll_ratio(doc.preview) if doc.preview is not None else doc.read_entry_ratio
            doc.read_mode = False
            doc.tab_widget.setCurrentWidget(doc.editor)
            self._restore_editor_markdown_position(doc, preview_ratio)
            self._focus_document(doc)
        else:
            self.hide_find()
            source_ratio = self._remember_editor_markdown_position(doc)
            self._refresh_markdown_preview(doc)
            doc.read_mode = True
            if doc.preview is not None:
                doc.tab_widget.setCurrentWidget(doc.preview)
                self._set_vertical_scroll_ratio(doc.preview, source_ratio)
                # QTextBrowser can update its scroll range after the new Markdown
                # has been laid out. Apply the position again on the next event turn.
                QTimer.singleShot(
                    0,
                    lambda rel_path=doc.rel_path, ratio=source_ratio: self._restore_markdown_preview_position(rel_path, ratio),
                )
            self._focus_document(doc)
        self._refresh_markdown_mode_button(doc)
        self._update_status_for_document(doc)

    def _cursor_status_changed(self, line: int, column: int) -> None:
        self.cursor_label.setText(f"Ln {line}, Col {column}")

    def save_current(self) -> bool:
        doc = self.current_document()
        if not doc:
            return True
        return self.save_document(doc)

    def save_all(self) -> bool:
        for doc in list(self.documents.values()):
            if doc.editor.document().isModified() and not self.save_document(doc):
                return False
        return True

    def save_document(self, doc: OpenDocument) -> bool:
        if not doc.editor.document().isModified():
            return True

        current_signature = _disk_signature(doc.path)
        disk_changed = current_signature != doc.disk_signature
        if disk_changed:
            box = QMessageBox(self)
            box.setWindowTitle("File changed on disk")
            box.setIcon(QMessageBox.Icon.Warning)
            box.setText(f"{doc.rel_path} changed outside TransferLoop after this tab was opened.")
            box.setInformativeText("Choose Overwrite to save your editor version, or Reload to discard your unsaved editor changes and use the current disk version.")
            overwrite = box.addButton("Overwrite", QMessageBox.ButtonRole.AcceptRole)
            reload_btn = box.addButton("Reload", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            clicked = box.clickedButton()
            if clicked is reload_btn:
                return self.reload_document(doc)
            if clicked is not overwrite:
                return False

        text = doc.editor.toPlainText()
        if doc.newline != "\n":
            text = text.replace("\n", doc.newline)
        try:
            doc.path.parent.mkdir(parents=True, exist_ok=True)
            doc.path.write_bytes(text.encode(doc.encoding))
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(self, "Could not save file", f"{doc.rel_path}\n\n{exc}")
            return False

        doc.disk_signature = _disk_signature(doc.path)
        doc.external_changed = False
        doc.editor.document().setModified(False)
        self._update_tab_title(doc.rel_path)
        self._update_status_for_document(doc)
        self.status_message.setText(f"Saved {doc.rel_path}")
        self.file_saved.emit(doc.rel_path)
        return True

    def reload_document(self, doc: OpenDocument, *, quiet: bool = False) -> bool:
        if not doc.path.exists():
            if not quiet:
                QMessageBox.warning(self, "File no longer exists", f"{doc.rel_path} was removed from disk.")
            doc.external_changed = True
            self._update_tab_title(doc.rel_path)
            self._update_status_for_document(doc)
            return False
        try:
            text, encoding, newline = _read_text_file(doc.path)
        except (OSError, UnicodeError) as exc:
            if not quiet:
                QMessageBox.warning(self, "Could not reload file", f"{doc.rel_path}\n\n{exc}")
            return False

        cursor = doc.editor.textCursor()
        position = cursor.position()
        doc.editor.setPlainText(text)
        doc.editor.document().setModified(False)
        cursor = doc.editor.textCursor()
        cursor.setPosition(min(position, max(0, len(text))))
        doc.editor.setTextCursor(cursor)
        doc.encoding = encoding
        doc.newline = newline
        doc.disk_signature = _disk_signature(doc.path)
        doc.external_changed = False
        if doc.read_mode:
            self._refresh_markdown_preview(doc)
        self._update_tab_title(doc.rel_path)
        if self.current_document() is doc:
            self._update_status_for_document(doc)
        return True

    def check_external_changes(self) -> None:
        for doc in list(self.documents.values()):
            signature = _disk_signature(doc.path)
            if signature == doc.disk_signature:
                continue
            if doc.editor.document().isModified():
                if not doc.external_changed:
                    doc.external_changed = True
                    self._update_tab_title(doc.rel_path)
                    if self.current_document() is doc:
                        self._update_status_for_document(doc)
                continue
            if signature is None:
                doc.external_changed = True
                self._update_tab_title(doc.rel_path)
                if self.current_document() is doc:
                    self.status_message.setText("File was removed from disk.")
                continue
            if self.reload_document(doc, quiet=True) and self.current_document() is doc:
                self.status_message.setText(f"Reloaded {doc.rel_path} after an external change.")

    def sync_from_disk(self) -> None:
        """Refresh clean editor tabs after AI merges, undo, or other app-managed disk changes."""
        for doc in list(self.documents.values()):
            if doc.editor.document().isModified():
                continue
            if _disk_signature(doc.path) != doc.disk_signature:
                self.reload_document(doc, quiet=True)

    def prepare_for_external_changes(self, paths: set[str]) -> bool:
        overlapping = [doc for rel, doc in self.documents.items() if rel in paths and doc.editor.document().isModified()]
        if not overlapping:
            return True

        listed = "\n".join(f"• {doc.rel_path}" for doc in overlapping[:8])
        if len(overlapping) > 8:
            listed += f"\n• …and {len(overlapping) - 8} more"
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved editor changes")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("The AI response changes file(s) that currently have unsaved edits in the built-in editor.")
        box.setInformativeText(f"{listed}\n\nSave or discard those editor edits before opening the AI review.")
        save_btn = box.addButton("Save Local Edits", QMessageBox.ButtonRole.AcceptRole)
        discard_btn = box.addButton("Discard Local Edits", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_btn:
            return all(self.save_document(doc) for doc in overlapping)
        if clicked is discard_btn:
            return all(self.reload_document(doc) for doc in overlapping)
        return False

    def close_current_tab(self) -> None:
        index = self.tabs.currentIndex()
        if index >= 0:
            self.close_tab(index)

    def close_tab(self, index: int) -> bool:
        tab_widget = self.tabs.widget(index)
        doc = next((item for item in self.documents.values() if item.tab_widget is tab_widget), None)
        if not doc:
            return True

        if doc.editor.document().isModified():
            answer = QMessageBox.warning(
                self,
                "Unsaved changes",
                f"Save changes to {doc.rel_path} before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return False
            if answer == QMessageBox.StandardButton.Save and not self.save_document(doc):
                return False

        self.tabs.removeTab(index)
        self.documents.pop(doc.rel_path, None)
        tab_widget.deleteLater()
        self.tabs_changed.emit(self.tabs.count())
        if not self.documents:
            self.overview_requested.emit()
        return True

    def confirm_close_all(self) -> bool:
        dirty = [doc for doc in self.documents.values() if doc.editor.document().isModified()]
        if not dirty:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved editor changes")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f"{len(dirty)} open file{'s have' if len(dirty) != 1 else ' has'} unsaved changes.")
        box.setInformativeText("Save the editor changes before leaving this project?")
        save_btn = box.addButton("Save All", QMessageBox.ButtonRole.AcceptRole)
        discard_btn = box.addButton("Discard All", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is save_btn:
            return self.save_all()
        if box.clickedButton() is discard_btn:
            return True
        return False

    def close_all(self, *, force: bool = False) -> bool:
        if not force and not self.confirm_close_all():
            return False
        while self.tabs.count():
            editor = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if editor:
                editor.deleteLater()
        self.documents.clear()
        self.tabs_changed.emit(0)
        return True

    def cycle_tabs(self, offset: int) -> None:
        count = self.tabs.count()
        if count <= 1:
            return
        self.tabs.setCurrentIndex((self.tabs.currentIndex() + offset) % count)

    def quick_open(self) -> None:
        if not self.project_root:
            return
        patterns = load_patterns(self.project_root)
        paths: list[str] = []
        for base, dirs, files in os.walk(self.project_root):
            base_path = Path(base)
            rel_base_path = base_path.relative_to(self.project_root)
            rel_base = "" if str(rel_base_path) == "." else rel_base_path.as_posix()
            dirs[:] = [
                name for name in dirs
                if not is_ignored(f"{rel_base}/{name}".strip("/"), patterns, True)
            ]
            for name in files:
                path = base_path / name
                rel = path.relative_to(self.project_root).as_posix()
                if is_ignored(rel, patterns, False):
                    continue
                try:
                    if likely_text_file(path):
                        paths.append(rel)
                except OSError:
                    continue
        dialog = QuickOpenDialog(paths, self)
        if dialog.exec():
            rel = dialog.selected_path()
            if rel:
                self.open_file(rel)

    def show_find(self, replace: bool = False) -> None:
        doc = self.current_document()
        if not doc:
            return
        if doc.read_mode:
            self.toggle_markdown_mode()
            doc = self.current_document()
        self.find_bar.setVisible(True)
        self.replace_input.setVisible(replace)
        self.replace_btn.setVisible(replace)
        self.replace_all_btn.setVisible(replace)
        editor = self.current_document().editor
        selected = editor.textCursor().selectedText()
        if selected and "\u2029" not in selected and len(selected) < 200:
            self.find_input.setText(selected)
        self.find_input.setFocus()
        self.find_input.selectAll()

    def hide_find(self) -> None:
        if self.find_bar.isVisible():
            self.find_bar.setVisible(False)
            doc = self.current_document()
            if doc:
                self._focus_document(doc)

    def _find_flags(self, backward: bool = False) -> QTextDocument.FindFlags:
        flags = QTextDocument.FindFlag(0)
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        if self.case_check.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        return flags

    def find_next(self, backward: bool = False) -> None:
        doc = self.current_document()
        query = self.find_input.text()
        if not doc or not query:
            return
        editor = doc.editor
        flags = self._find_flags(backward)
        found = editor.document().find(query, editor.textCursor(), flags)
        if found.isNull():
            wrap = QTextCursor(editor.document())
            wrap.movePosition(QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start)
            found = editor.document().find(query, wrap, flags)
        if not found.isNull():
            editor.setTextCursor(found)
            editor.ensureCursorVisible()
            self.status_message.setText("")
        else:
            self.status_message.setText(f"No matches for “{query}”.")

    def replace_current(self) -> None:
        doc = self.current_document()
        query = self.find_input.text()
        if not doc or not query:
            return
        cursor = doc.editor.textCursor()
        selected = cursor.selectedText()
        matches = selected == query if self.case_check.isChecked() else selected.casefold() == query.casefold()
        if matches:
            cursor.insertText(self.replace_input.text())
            doc.editor.setTextCursor(cursor)
        self.find_next()

    def replace_all(self) -> None:
        doc = self.current_document()
        query = self.find_input.text()
        if not doc or not query:
            return
        document = doc.editor.document()
        flags = self._find_flags(False)
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        count = 0
        cursor.beginEditBlock()
        while True:
            found = document.find(query, cursor, flags)
            if found.isNull():
                break
            found.insertText(self.replace_input.text())
            cursor = found
            count += 1
        cursor.endEditBlock()
        self.status_message.setText(f"Replaced {count} occurrence{'s' if count != 1 else ''}.")

    def go_to_line(self) -> None:
        doc = self.current_document()
        if not doc:
            return
        if doc.read_mode:
            self.toggle_markdown_mode()
            doc = self.current_document()
            if not doc:
                return
        maximum = max(1, doc.editor.blockCount())
        current = doc.editor.textCursor().blockNumber() + 1
        line, ok = QInputDialog.getInt(self, "Go to Line", "Line:", current, 1, maximum)
        if not ok:
            return
        block = doc.editor.document().findBlockByNumber(line - 1)
        if block.isValid():
            cursor = doc.editor.textCursor()
            cursor.setPosition(block.position())
            doc.editor.setTextCursor(cursor)
            doc.editor.centerCursor()
            doc.editor.setFocus()
