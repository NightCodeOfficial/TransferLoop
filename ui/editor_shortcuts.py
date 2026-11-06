from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication


class _LineCopyCutFilter(QObject):
    def eventFilter(self, watched, event) -> bool:
        if event.type() != QEvent.Type.KeyPress or not isinstance(event, QKeyEvent):
            return super().eventFilter(watched, event)

        if event.modifiers() != Qt.KeyboardModifier.ControlModifier:
            return super().eventFilter(watched, event)
        if event.key() not in (Qt.Key.Key_C, Qt.Key.Key_X):
            return super().eventFilter(watched, event)
        if not hasattr(watched, "textCursor"):
            return super().eventFilter(watched, event)

        cursor = watched.textCursor()
        if cursor.hasSelection():
            return super().eventFilter(watched, event)

        cut = event.key() == Qt.Key.Key_X
        if cut and hasattr(watched, "isReadOnly") and watched.isReadOnly():
            return super().eventFilter(watched, event)

        copy_or_cut_current_line(watched, cut=cut)
        return True


def enable_line_copy_cut(widget) -> None:
    """Give a Qt text editor VS Code-style whole-line copy/cut behavior."""
    handler = _LineCopyCutFilter(widget)
    widget.installEventFilter(handler)
    # QObject ownership keeps it alive, but retaining a Python reference avoids
    # wrapper collection on some PySide versions.
    widget._line_copy_cut_filter = handler


def copy_or_cut_current_line(widget, *, cut: bool) -> None:
    cursor = widget.textCursor()
    block = cursor.block()
    if not block.isValid():
        return

    QApplication.clipboard().setText(block.text() + "\n")
    if not cut:
        return

    document = widget.document()
    start = block.position()
    if block.next().isValid():
        end = block.next().position()
    elif block.previous().isValid():
        previous = block.previous()
        start = previous.position() + len(previous.text())
        end = block.position() + len(block.text())
    else:
        end = block.position() + len(block.text())

    edit = QTextCursor(document)
    edit.setPosition(start)
    edit.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    edit.beginEditBlock()
    edit.removeSelectedText()
    edit.endEditBlock()
    edit.setPosition(min(start, max(0, document.characterCount() - 1)))
    widget.setTextCursor(edit)
