from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

ICON_COLOR = "#8d82ff"


def _canvas(size: int, color: str = ICON_COLOR) -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    return pixmap, painter


def copy_icon(size: int = 18) -> QIcon:
    pixmap, painter = _canvas(size)
    painter.drawRoundedRect(QRectF(5.3, 3.3, 9.0, 9.0), 1.5, 1.5)
    painter.drawRoundedRect(QRectF(3.3, 5.3, 9.0, 9.0), 1.5, 1.5)
    painter.end()
    return QIcon(pixmap)


def folder_icon(size: int = 18) -> QIcon:
    pixmap, painter = _canvas(size)
    path = QPainterPath()
    path.moveTo(2.7, 6.0)
    path.lineTo(6.9, 6.0)
    path.lineTo(8.2, 4.5)
    path.lineTo(14.9, 4.5)
    path.quadTo(16.0, 4.5, 16.0, 5.7)
    path.lineTo(16.0, 13.4)
    path.quadTo(16.0, 14.8, 14.6, 14.8)
    path.lineTo(3.4, 14.8)
    path.quadTo(2.0, 14.8, 2.0, 13.4)
    path.lineTo(2.0, 7.1)
    path.quadTo(2.0, 6.0, 2.7, 6.0)
    painter.drawPath(path)
    painter.drawLine(2.7, 7.5, 15.5, 7.5)
    painter.end()
    return QIcon(pixmap)


def pencil_icon(size: int = 18) -> QIcon:
    pixmap, painter = _canvas(size)
    painter.drawLine(4.0, 13.6, 5.0, 10.4)
    painter.drawLine(5.0, 10.4, 11.9, 3.5)
    painter.drawLine(11.9, 3.5, 14.5, 6.1)
    painter.drawLine(14.5, 6.1, 7.6, 13.0)
    painter.drawLine(7.6, 13.0, 4.0, 13.6)
    painter.drawLine(10.9, 4.5, 13.5, 7.1)
    painter.end()
    return QIcon(pixmap)


def book_icon(size: int = 18) -> QIcon:
    """Open-book icon used to enter Markdown reading mode."""
    pixmap, painter = _canvas(size, "#8f949e")
    path = QPainterPath()
    path.moveTo(2.8, 4.2)
    path.quadTo(6.0, 3.5, 8.6, 5.1)
    path.lineTo(8.6, 14.1)
    path.quadTo(6.0, 12.6, 2.8, 13.2)
    path.closeSubpath()
    painter.drawPath(path)

    path = QPainterPath()
    path.moveTo(15.2, 4.2)
    path.quadTo(12.0, 3.5, 9.4, 5.1)
    path.lineTo(9.4, 14.1)
    path.quadTo(12.0, 12.6, 15.2, 13.2)
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawLine(9.0, 5.0, 9.0, 14.2)
    painter.end()
    return QIcon(pixmap)


def quill_icon(size: int = 18) -> QIcon:
    """Quill icon used to return from Markdown reading mode to editing."""
    pixmap, painter = _canvas(size, "#8f949e")
    feather = QPainterPath()
    feather.moveTo(3.1, 14.7)
    feather.cubicTo(4.4, 10.0, 7.8, 5.2, 14.7, 2.8)
    feather.cubicTo(14.2, 7.8, 10.4, 12.3, 5.6, 13.4)
    feather.cubicTo(4.7, 13.7, 3.9, 14.1, 3.1, 14.7)
    painter.drawPath(feather)
    painter.drawLine(4.2, 13.8, 12.7, 5.2)
    painter.drawLine(7.2, 10.8, 5.1, 10.7)
    painter.drawLine(9.5, 8.4, 7.0, 8.2)
    painter.drawLine(11.6, 6.1, 13.8, 6.1)
    painter.end()
    return QIcon(pixmap)
