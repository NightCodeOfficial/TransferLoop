from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy


class ElidedLabel(QLabel):
    """Single-line label that elides long text while preserving the full value in its tooltip."""

    def __init__(
        self,
        text: str = "",
        elide_mode=Qt.TextElideMode.ElideMiddle,
        parent=None,
    ):
        super().__init__(parent)
        self._full_text = ""
        self._elide_mode = elide_mode
        self.setWordWrap(False)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setText(text)

    def text(self) -> str:
        return self._full_text

    def setText(self, text: str) -> None:
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        self._refresh_elision()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_elision()

    def _refresh_elision(self) -> None:
        # Leave a few pixels of breathing room so stylesheet padding and rounding
        # never cause the final glyph to be clipped at the edge of the label.
        available = max(20, self.width() - 6)
        displayed = self.fontMetrics().elidedText(self._full_text, self._elide_mode, available)
        QLabel.setText(self, displayed)
