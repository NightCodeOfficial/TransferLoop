from __future__ import annotations

from math import cos, radians, sin

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QRadialGradient

ICON_COLOR = "#8d82ff"
LOGO_VIOLET = QColor("#8f82ff")
LOGO_VIOLET_SOFT = QColor("#b0a7ff")
LOGO_MINT = QColor("#79dda0")
LOGO_MINT_SOFT = QColor("#a9efc3")
LOGO_DARK = QColor("#141821")
LOGO_DARK_SOFT = QColor("#1c2130")
LOGO_BORDER = QColor("#353d4f")

SMALL_ICON_SIZES = (16, 20, 24, 32)
APP_ICON_SIZES = SMALL_ICON_SIZES + (40, 48, 64, 96, 128, 256)


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


def _arc_path(size: float, margin: float, start_deg: float, span_deg: float) -> QPainterPath:
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    path = QPainterPath()
    path.arcMoveTo(rect, start_deg)
    path.arcTo(rect, start_deg, span_deg)
    return path


def _point_on_circle(center: float, radius: float, angle_deg: float) -> QPointF:
    angle = radians(angle_deg)
    return QPointF(center + radius * cos(angle), center - radius * sin(angle))


def _arrow_head(end_point: QPointF, angle_deg: float, size: float, forward_ccw: bool = True) -> QPolygonF:
    tangent = angle_deg + (90 if forward_ccw else -90)
    back = radians(tangent + 180)
    left = radians(tangent + 150)
    right = radians(tangent - 150)
    base = QPointF(end_point.x() + cos(back) * size * 0.92, end_point.y() - sin(back) * size * 0.92)
    left_pt = QPointF(base.x() + cos(left) * size * 0.78, base.y() - sin(left) * size * 0.78)
    right_pt = QPointF(base.x() + cos(right) * size * 0.78, base.y() - sin(right) * size * 0.78)
    return QPolygonF([end_point, left_pt, right_pt])


def _paint_background(painter: QPainter, size: int, minimalist: bool) -> None:
    bg_rect = QRectF(1.0, 1.0, size - 2.0, size - 2.0)
    radius = size * (0.22 if minimalist else 0.18)
    if minimalist:
        painter.setPen(Qt.NoPen)
        painter.setBrush(LOGO_DARK)
        painter.drawRoundedRect(bg_rect, radius, radius)
        return

    bg_gradient = QLinearGradient(bg_rect.topLeft(), bg_rect.bottomRight())
    bg_gradient.setColorAt(0.0, LOGO_DARK_SOFT)
    bg_gradient.setColorAt(1.0, LOGO_DARK)
    painter.setPen(QPen(LOGO_BORDER, max(1.0, size * 0.02)))
    painter.setBrush(bg_gradient)
    painter.drawRoundedRect(bg_rect, radius, radius)

    glow = QRadialGradient(size * 0.50, size * 0.52, size * 0.34)
    glow.setColorAt(0.0, QColor(255, 255, 255, 14))
    glow.setColorAt(0.55, QColor(255, 255, 255, 5))
    glow.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(QRectF(size * 0.16, size * 0.18, size * 0.68, size * 0.68))


def _paint_logo(painter: QPainter, size: int, minimalist: bool) -> None:
    _paint_background(painter, size, minimalist)

    margin = size * (0.17 if minimalist else 0.20)
    ring_width = max(2.8 if minimalist else 2.4, size * (0.18 if minimalist else 0.115))
    center = size / 2
    radius = (size - 2 * margin) / 2
    arrow_size = size * (0.18 if minimalist else 0.145)

    violet_pen = QPen(LOGO_VIOLET, ring_width)
    violet_pen.setCapStyle(Qt.RoundCap)
    violet_pen.setJoinStyle(Qt.RoundJoin)
    mint_pen = QPen(LOGO_MINT, ring_width)
    mint_pen.setCapStyle(Qt.RoundCap)
    mint_pen.setJoinStyle(Qt.RoundJoin)
    painter.setBrush(Qt.NoBrush)

    if minimalist:
        violet_start, violet_span = 28, 150
        mint_start, mint_span = 208, 150
        violet_tip_angle, mint_tip_angle = 182, 362
    else:
        violet_start, violet_span = 24, 170
        mint_start, mint_span = 204, 170
        violet_tip_angle, mint_tip_angle = 194, 374

    painter.setPen(violet_pen)
    painter.drawPath(_arc_path(float(size), margin, violet_start, violet_span))
    painter.setPen(mint_pen)
    painter.drawPath(_arc_path(float(size), margin, mint_start, mint_span))

    painter.setPen(Qt.NoPen)
    painter.setBrush(LOGO_VIOLET_SOFT if not minimalist else LOGO_VIOLET)
    painter.drawPolygon(_arrow_head(_point_on_circle(center, radius, violet_tip_angle), violet_tip_angle, arrow_size, forward_ccw=True))
    painter.setBrush(LOGO_MINT_SOFT if not minimalist else LOGO_MINT)
    painter.drawPolygon(_arrow_head(_point_on_circle(center, radius, mint_tip_angle), mint_tip_angle, arrow_size, forward_ccw=True))

    if minimalist:
        return

    inner_pen = QPen(QColor(255, 255, 255, 30), max(1.0, size * 0.02))
    inner_pen.setCapStyle(Qt.RoundCap)
    painter.setPen(inner_pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(_arc_path(float(size), size * 0.335, 48, 264))

    core_glow = QRadialGradient(size * 0.50, size * 0.50, size * 0.10)
    core_glow.setColorAt(0.0, QColor(255, 255, 255, 110))
    core_glow.setColorAt(0.35, QColor(185, 193, 255, 85))
    core_glow.setColorAt(1.0, QColor(185, 193, 255, 0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(core_glow)
    painter.drawEllipse(QRectF(size * 0.41, size * 0.41, size * 0.18, size * 0.18))


def transferloop_logo_pixmap(size: int = 64) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    minimalist = size <= 32
    _paint_logo(painter, size, minimalist=minimalist)
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in APP_ICON_SIZES:
        icon.addPixmap(transferloop_logo_pixmap(size))
    return icon


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


def trash_icon(size: int = 18) -> QIcon:
    """Minimal red outline trash icon used for non-destructive recent-project removal."""
    pixmap, painter = _canvas(size, "#ff6b74")
    painter.drawLine(5.0, 5.8, 13.0, 5.8)
    painter.drawLine(7.1, 4.0, 10.9, 4.0)
    painter.drawLine(7.9, 3.1, 10.1, 3.1)
    body = QPainterPath()
    body.moveTo(6.0, 7.2)
    body.lineTo(6.7, 14.2)
    body.quadTo(6.8, 15.0, 7.7, 15.0)
    body.lineTo(10.3, 15.0)
    body.quadTo(11.2, 15.0, 11.3, 14.2)
    body.lineTo(12.0, 7.2)
    painter.drawPath(body)
    painter.drawLine(8.2, 8.4, 8.4, 13.4)
    painter.drawLine(9.8, 8.4, 9.6, 13.4)
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
