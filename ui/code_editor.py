from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainter, QTextCursor, QTextFormat
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QTextEdit, QWidget

from .editor_shortcuts import enable_line_copy_cut
from .markdown_editing import enter_action, is_list_or_quote_line, is_markdown_url
from .syntax_highlighter import ProjectSyntaxHighlighter, comment_prefix, detect_language


class LineNumberArea(QWidget):
    def __init__(self, editor: "CodeEditor"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.line_number_area_paint_event(event)


class CodeEditor(QPlainTextEdit):
    cursor_status_changed = Signal(int, int)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.setObjectName("CodeEditor")
        self.path = path
        self.language = detect_language(path)
        self.line_number_area = LineNumberArea(self)
        self.highlighter = ProjectSyntaxHighlighter(self.document(), self.language)

        font = QFont("Cascadia Code")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSizeF(10.5)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self._cursor_moved)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)
        self.highlight_current_line()
        enable_line_copy_cut(self)

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self, _new_block_count: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event) -> None:
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#0f1219"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        active_block = self.textCursor().blockNumber()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                color = QColor("#c7cce0") if block_number == active_block else QColor("#626a7d")
                painter.setPen(color)
                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - 8,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def highlight_current_line(self) -> None:
        if self.isReadOnly():
            self.setExtraSelections([])
            return
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor("#171b25"))
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])
        self.line_number_area.update()

    def _cursor_moved(self) -> None:
        cursor = self.textCursor()
        self.cursor_status_changed.emit(cursor.blockNumber() + 1, cursor.positionInBlock() + 1)

    def set_path(self, path: Path) -> None:
        self.path = path
        language = detect_language(path)
        if language != self.language:
            self.language = language
            self.highlighter.setDocument(None)
            self.highlighter = ProjectSyntaxHighlighter(self.document(), self.language)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.language == "Markdown" and self._handle_markdown_key(event):
            return
        if event.key() == Qt.Key.Key_Tab and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.indent_selection()
            return
        if event.key() == Qt.Key.Key_Backtab:
            self.unindent_selection()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self._insert_newline_with_indent(event)
            return
        if event.key() == Qt.Key.Key_Slash and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.toggle_comment()
            return
        super().keyPressEvent(event)

    def _handle_markdown_key(self, event: QKeyEvent) -> bool:
        modifiers = event.modifiers()
        key = event.key()

        if modifiers == Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_B:
                self._toggle_markdown_wrap("**", "**")
                return True
            if key == Qt.Key.Key_I:
                self._toggle_markdown_wrap("*", "*")
                return True
            if key == Qt.Key.Key_K:
                self._insert_markdown_link()
                return True
            if key == Qt.Key.Key_V and self._paste_markdown_url_over_selection():
                return True

        if modifiers == Qt.KeyboardModifier.NoModifier:
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._insert_markdown_newline():
                    return True
                self._insert_newline_with_indent(event)
                return True
            if key == Qt.Key.Key_Tab and self._indent_markdown_structure(False):
                return True
            if key == Qt.Key.Key_Backspace and self._delete_markdown_pair():
                return True
            if self._handle_markdown_pair(event):
                return True

        if key == Qt.Key.Key_Backtab and self._indent_markdown_structure(True):
            return True
        return False

    def _insert_markdown_newline(self) -> bool:
        cursor = self.textCursor()
        block = cursor.block()
        line = block.text()
        action = enter_action(line, cursor.positionInBlock())
        if action is None:
            return False

        if action.replace_current_with is not None:
            replacement = action.replace_current_with
            line_cursor = QTextCursor(block)
            line_cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            line_cursor.beginEditBlock()
            line_cursor.insertText(replacement)
            line_cursor.endEditBlock()
            line_cursor.setPosition(block.position() + len(replacement))
            self.setTextCursor(line_cursor)
            return True

        cursor.beginEditBlock()
        cursor.insertText("\n" + (action.next_prefix or ""))
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    def _indent_markdown_structure(self, unindent: bool) -> bool:
        cursor = self.textCursor()
        if cursor.hasSelection() and "\u2029" in cursor.selectedText():
            if unindent:
                self.unindent_selection()
            else:
                self.indent_selection()
            return True

        block = cursor.block()
        line = block.text()
        if not is_list_or_quote_line(line):
            return False

        position_in_block = cursor.positionInBlock()
        block_cursor = QTextCursor(block)
        if unindent:
            leading = len(line) - len(line.lstrip(" \t"))
            if leading <= 0:
                return True
            if line.startswith("\t"):
                remove = 1
            else:
                remove = min(4, leading)
            block_cursor.setPosition(block.position())
            block_cursor.setPosition(block.position() + remove, QTextCursor.MoveMode.KeepAnchor)
            block_cursor.removeSelectedText()
            cursor.setPosition(max(block.position(), cursor.position() - remove))
        else:
            block_cursor.setPosition(block.position())
            block_cursor.insertText("    ")
            cursor.setPosition(cursor.position() + 4)
        self.setTextCursor(cursor)
        return True

    def _toggle_markdown_wrap(self, left: str, right: str) -> None:
        cursor = self.textCursor()
        text = self.toPlainText()
        start, end = cursor.selectionStart(), cursor.selectionEnd()

        if cursor.hasSelection():
            selected = cursor.selectedText().replace("\u2029", "\n")
            if selected.startswith(left) and selected.endswith(right) and len(selected) >= len(left) + len(right):
                inner = selected[len(left):len(selected) - len(right)]
                cursor.insertText(inner)
                cursor.setPosition(start)
                cursor.setPosition(start + len(inner), QTextCursor.MoveMode.KeepAnchor)
                self.setTextCursor(cursor)
                return
            if start >= len(left) and text[start - len(left):start] == left and text[end:end + len(right)] == right:
                outer = QTextCursor(self.document())
                outer.setPosition(start - len(left))
                outer.setPosition(end + len(right), QTextCursor.MoveMode.KeepAnchor)
                outer.insertText(selected)
                outer.setPosition(start - len(left))
                outer.setPosition(start - len(left) + len(selected), QTextCursor.MoveMode.KeepAnchor)
                self.setTextCursor(outer)
                return
            replacement = left + selected + right
            cursor.insertText(replacement)
            cursor.setPosition(start + len(left))
            cursor.setPosition(start + len(left) + len(selected), QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(cursor)
            return

        cursor.insertText(left + right)
        cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, len(right))
        self.setTextCursor(cursor)

    def _insert_markdown_link(self) -> None:
        cursor = self.textCursor()
        start = cursor.selectionStart()
        selected = cursor.selectedText().replace("\u2029", "\n") if cursor.hasSelection() else ""
        if selected:
            replacement = f"[{selected}]()"
            cursor.insertText(replacement)
            cursor.setPosition(start + len(selected) + 3)
        else:
            cursor.insertText("[]()")
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 3)
        self.setTextCursor(cursor)

    def _paste_markdown_url_over_selection(self) -> bool:
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return False
        clipboard = QApplication.clipboard().text().strip()
        if not is_markdown_url(clipboard):
            return False
        selected = cursor.selectedText().replace("\u2029", "\n")
        cursor.insertText(f"[{selected}]({clipboard})")
        self.setTextCursor(cursor)
        return True

    def _handle_markdown_pair(self, event: QKeyEvent) -> bool:
        text = event.text()
        pairs = {"[": "]", "(": ")", "{": "}", "`": "`"}
        closers = set(pairs.values())
        if not text or (text not in pairs and text not in closers):
            return False

        cursor = self.textCursor()
        document_text = self.toPlainText()
        pos = cursor.position()
        if text in closers and pos < len(document_text) and document_text[pos:pos + 1] == text:
            cursor.movePosition(QTextCursor.MoveOperation.Right)
            self.setTextCursor(cursor)
            return True

        if text not in pairs:
            return False

        closing = pairs[text]
        if cursor.hasSelection():
            start = cursor.selectionStart()
            selected = cursor.selectedText().replace("\u2029", "\n")
            cursor.insertText(text + selected + closing)
            cursor.setPosition(start + 1)
            cursor.setPosition(start + 1 + len(selected), QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(cursor)
        else:
            cursor.insertText(text + closing)
            cursor.movePosition(QTextCursor.MoveOperation.Left)
            self.setTextCursor(cursor)
        return True

    def _delete_markdown_pair(self) -> bool:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        pos = cursor.position()
        text = self.toPlainText()
        if pos <= 0 or pos >= len(text):
            return False
        pairs = {"[": "]", "(": ")", "{": "}", "`": "`"}
        left, right = text[pos - 1], text[pos]
        if pairs.get(left) != right:
            return False
        cursor.beginEditBlock()
        cursor.deletePreviousChar()
        cursor.deleteChar()
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    def _line_selection_cursor(self) -> tuple[QTextCursor, str]:
        cursor = self.textCursor()
        document = self.document()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        first = document.findBlock(start)
        last = document.findBlock(end)
        if end > start and last.isValid() and end == last.position():
            last = last.previous()
        if not last.isValid():
            last = first

        line_cursor = QTextCursor(document)
        line_cursor.setPosition(first.position())
        end_pos = last.position() + max(0, last.length() - 1)
        line_cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
        return line_cursor, line_cursor.selectedText().replace("\u2029", "\n")

    def indent_selection(self) -> None:
        cursor = self.textCursor()
        if not cursor.hasSelection() or "\u2029" not in cursor.selectedText():
            spaces = 4 - (cursor.positionInBlock() % 4)
            cursor.insertText(" " * spaces)
            return
        line_cursor, text = self._line_selection_cursor()
        changed = "\n".join("    " + line for line in text.split("\n"))
        start = line_cursor.selectionStart()
        line_cursor.beginEditBlock()
        line_cursor.insertText(changed)
        line_cursor.endEditBlock()
        line_cursor.setPosition(start)
        line_cursor.setPosition(start + len(changed), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(line_cursor)

    def unindent_selection(self) -> None:
        line_cursor, text = self._line_selection_cursor()
        lines = []
        for line in text.split("\n"):
            if line.startswith("\t"):
                lines.append(line[1:])
            else:
                remove = min(4, len(line) - len(line.lstrip(" ")))
                lines.append(line[remove:])
        changed = "\n".join(lines)
        start = line_cursor.selectionStart()
        line_cursor.beginEditBlock()
        line_cursor.insertText(changed)
        line_cursor.endEditBlock()
        line_cursor.setPosition(start)
        line_cursor.setPosition(start + len(changed), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(line_cursor)

    def _insert_newline_with_indent(self, event: QKeyEvent) -> None:
        cursor = self.textCursor()
        before = cursor.block().text()[: cursor.positionInBlock()]
        leading_match = re.match(r"^[ \t]*", before)
        indent = leading_match.group(0) if leading_match else ""
        stripped = before.rstrip()
        if stripped.endswith((":", "{", "[", "(")):
            indent += "    "
        super().keyPressEvent(event)
        if indent:
            self.textCursor().insertText(indent)

    def toggle_comment(self) -> None:
        prefix = comment_prefix(self.language)
        if not prefix:
            return
        line_cursor, text = self._line_selection_cursor()
        lines = text.split("\n")
        non_blank = [line for line in lines if line.strip()]
        if not non_blank:
            return

        if prefix.endswith(" "):
            token = prefix.rstrip()
            all_commented = all(line.lstrip().upper().startswith(token.upper()) for line in non_blank)
        else:
            token = prefix
            all_commented = all(line.lstrip().startswith(token) for line in non_blank)

        changed_lines: list[str] = []
        for line in lines:
            if not line.strip():
                changed_lines.append(line)
                continue
            indent_len = len(line) - len(line.lstrip(" \t"))
            indent = line[:indent_len]
            body = line[indent_len:]
            if all_commented:
                if prefix.endswith(" "):
                    if body.upper().startswith(token.upper()):
                        body = body[len(token):]
                        if body.startswith(" "):
                            body = body[1:]
                elif body.startswith(token):
                    body = body[len(token):]
                    if body.startswith(" "):
                        body = body[1:]
                changed_lines.append(indent + body)
            else:
                spacer = "" if prefix.endswith(" ") else " "
                changed_lines.append(indent + prefix + spacer + body)

        changed = "\n".join(changed_lines)
        start = line_cursor.selectionStart()
        line_cursor.beginEditBlock()
        line_cursor.insertText(changed)
        line_cursor.endEditBlock()
        line_cursor.setPosition(start)
        line_cursor.setPosition(start + len(changed), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(line_cursor)
