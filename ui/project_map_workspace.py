from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence, QPainter, QPainterPath, QPen, QPolygonF, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from core.project import ProjectModel
from core.storage import load_json, project_map_layout_path, save_json
from core.project_map import (
    RELATIONSHIP_TYPES,
    coverage_summary,
    entry_status,
    load_project_map,
    relationship_index,
    save_project_map,
    sync_project_map_managed,
)

ROLE_RELATION = Qt.ItemDataRole.UserRole

STATUS_LABELS = {
    "documented": "Documented",
    "needs_review": "Needs review",
    "missing": "Missing description",
}
STATUS_COLORS = {
    "documented": QColor("#79dda0"),
    "needs_review": QColor("#f1c978"),
    "missing": QColor("#7e8596"),
}

SUPPORT_FILE_NAMES = {
    ".aiignore",
    ".aimemory",
    ".gitignore",
    "requirements.txt",
    "requirements-build.txt",
    "run.bat",
    "run.sh",
    "setup.bat",
    "uninstall.bat",
    "build_windows_assets.py",
    "install_windows.ps1",
    "uninstall_windows.ps1",
}


def _is_support_file(path: str) -> bool:
    name = Path(path).name.lower()
    return (
        name in SUPPORT_FILE_NAMES
        or name.startswith("readme")
        or name.endswith(".aimemory")
        or name.endswith("_ai_instructions.md")
    )


def _top_group(path: str) -> str:
    parts = path.split("/")
    return parts[0] if len(parts) > 1 else "Project root"


def _shorten(text: str, limit: int) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)].rstrip() + "…"


class RelationshipEdge(QGraphicsPathItem):
    """Orthogonal relationship line used only for focused, readable graphs."""

    def __init__(
        self,
        source_path: str,
        target_path: str,
        relationship: dict,
        start: QPointF,
        end: QPointF,
        *,
        label: str = "",
        strong: bool = False,
    ):
        super().__init__()
        self.source_path = source_path
        self.target_path = target_path
        self.relationship = relationship
        self.label = label
        self.strong = strong
        self.arrow = QGraphicsPolygonItem(self)
        self.label_item: QGraphicsTextItem | None = None
        self._normal_opacity = 0.82 if strong else 0.62
        self.setZValue(-10)
        self._apply_style(strong)
        if label:
            self._ensure_label(label)
        self.update_geometry(start, end)
        detail = relationship.get("description", "")
        source = relationship.get("source", "static")
        self.setToolTip(
            f"{source_path} → {target_path}\n"
            f"{relationship.get('type', 'depends_on')} · {source}"
            + (f"\n{detail}" if detail else "")
        )

    def _apply_style(self, strong: bool) -> None:
        authored = self.relationship.get("source") != "static"
        color = QColor("#8f82ff") if authored else QColor("#657087")
        pen = QPen(color, 1.9 if authored or strong else 1.35)
        if authored:
            pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.arrow.setPen(QPen(color, 0))
        self.arrow.setBrush(QBrush(color))
        self.setOpacity(self._normal_opacity)

    def _ensure_label(self, label: str) -> None:
        if self.label_item is None:
            self.label_item = QGraphicsTextItem(self)
            font = QFont()
            font.setPointSizeF(7.5)
            font.setBold(True)
            self.label_item.setFont(font)
            self.label_item.setDefaultTextColor(QColor("#8f98aa"))
        self.label_item.setPlainText(label)

    def update_geometry(self, start: QPointF, end: QPointF) -> None:
        path = QPainterPath(start)
        dx = end.x() - start.x()
        if abs(dx) >= 70:
            mid_x = start.x() + dx * 0.5
            path.lineTo(mid_x, start.y())
            path.lineTo(mid_x, end.y())
            path.lineTo(end)
            last_from = QPointF(mid_x, end.y())
        else:
            gutter_x = max(start.x(), end.x()) + 48.0
            path.lineTo(gutter_x, start.y())
            path.lineTo(gutter_x, end.y())
            path.lineTo(end)
            last_from = QPointF(gutter_x, end.y())
        self.setPath(path)

        direction = end - last_from
        length = max(1.0, (direction.x() ** 2 + direction.y() ** 2) ** 0.5)
        ux, uy = direction.x() / length, direction.y() / length
        perp = QPointF(-uy, ux)
        base = QPointF(end.x() - ux * 9.0, end.y() - uy * 9.0)
        self.arrow.setPolygon(
            QPolygonF(
                [
                    end,
                    QPointF(base.x() + perp.x() * 4.0, base.y() + perp.y() * 4.0),
                    QPointF(base.x() - perp.x() * 4.0, base.y() - perp.y() * 4.0),
                ]
            )
        )

        if self.label:
            self._ensure_label(self.label)
            rect = self.label_item.boundingRect()
            self.label_item.setPos(
                (start.x() + end.x()) * 0.5 - rect.width() * 0.5,
                (start.y() + end.y()) * 0.5 - rect.height() - 3,
            )

    def set_emphasis(self, emphasized: bool, dimmed: bool = False) -> None:
        opacity = 0.07 if dimmed else (1.0 if emphasized else self._normal_opacity)
        self.setOpacity(opacity)


class ProjectMapNode(QGraphicsRectItem):
    WIDTH = 238.0
    HEIGHT = 92.0

    def __init__(
        self,
        path: str,
        entry: dict,
        click_callback,
        double_click_callback,
        *,
        subtitle: str = "",
    ):
        super().__init__(0, 0, self.WIDTH, self.HEIGHT)
        self.path = path
        self.entry = entry
        self.click_callback = click_callback
        self.double_click_callback = double_click_callback
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setZValue(10)

        self.name_text = QGraphicsTextItem(Path(path).name, self)
        name_font = QFont()
        name_font.setPointSizeF(9.4)
        name_font.setBold(True)
        self.name_text.setFont(name_font)
        self.name_text.setDefaultTextColor(QColor("#f1f3f8"))
        self.name_text.setPos(11, 5)
        self.name_text.setTextWidth(self.WIDTH - 22)

        description = _shorten(str(entry.get("description", "")).strip(), 112)
        if not description:
            description = "No description yet."
        self.description_text = QGraphicsTextItem(description, self)
        description_font = QFont()
        description_font.setPointSizeF(7.5)
        self.description_text.setFont(description_font)
        self.description_text.setDefaultTextColor(QColor("#a9b0c0") if entry.get("description") else QColor("#737c90"))
        self.description_text.setPos(11, 27)
        self.description_text.setTextWidth(self.WIDTH - 22)

        self.subtitle_text = QGraphicsTextItem(subtitle, self)
        subtitle_font = QFont()
        subtitle_font.setPointSizeF(7.5)
        subtitle_font.setBold(True)
        self.subtitle_text.setFont(subtitle_font)
        self.subtitle_text.setDefaultTextColor(QColor("#8f97aa"))
        self.subtitle_text.setPos(11, 68)
        self.subtitle_text.setTextWidth(self.WIDTH - 22)

        full_description = str(entry.get("description", "")).strip()
        self.setToolTip(path + (f"\n\n{full_description}" if full_description else "\n\nNo description yet."))
        self._selected = False
        self._hovered = False
        self._apply_style()

    def _apply_style(self) -> None:
        status = entry_status(self.entry)
        status_color = STATUS_COLORS.get(status, QColor("#7e8596"))
        if self._selected:
            pen = QPen(QColor("#8b7dff"), 2.0)
            brush = QBrush(QColor("#242038"))
        elif self._hovered:
            pen = QPen(QColor("#565070"), 1.4)
            brush = QBrush(QColor("#1b1f2b"))
        else:
            pen = QPen(QColor("#303646"), 1.0)
            brush = QBrush(QColor("#151923"))
        self.setPen(pen)
        self.setBrush(brush)

        if not hasattr(self, "status_rail"):
            self.status_rail = QGraphicsRectItem(0, 0, 3, self.HEIGHT, self)
            self.status_rail.setPen(QPen(Qt.PenStyle.NoPen))
        self.status_rail.setBrush(QBrush(status_color))

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_style()

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self._apply_style()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self._apply_style()
        super().hoverLeaveEvent(event)


class ArchitectureGroupNode(QGraphicsRectItem):
    WIDTH = 278.0
    HEIGHT = 198.0

    def __init__(
        self,
        group: str,
        directory_key: str,
        file_paths: list[str],
        entries: dict,
        incoming_count: int,
        outgoing_count: int,
        click_callback,
        *,
        total_file_count: int | None = None,
    ):
        super().__init__(0, 0, self.WIDTH, self.HEIGHT)
        self.group = group
        self.directory_key = directory_key
        self.file_paths = file_paths
        self.click_callback = click_callback
        self.total_file_count = total_file_count if total_file_count is not None else len(file_paths)
        self.summary_text = f"{self.total_file_count} files · {incoming_count} in · {outgoing_count} out"
        important = sorted(
            file_paths,
            key=lambda path: (
                -len(entries.get(path, {}).get("relationships", [])),
                Path(path).name.lower(),
            ),
        )[:4]
        self.file_lines = [f"• {Path(path).name}" for path in important]
        hidden = self.total_file_count - len(important)
        if hidden > 0:
            self.file_lines.append(f"Showing {len(important)} of {self.total_file_count} · click to open all")
        elif self.total_file_count == 0:
            self.file_lines.append("No mapped files in this package")

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)
        self._hovered = False

        if directory_key:
            directory_entry = entries.get(directory_key, {})
            description = str(directory_entry.get("description", "")).strip()
        else:
            description = "Files stored directly at the project root."
        self.description = description or "No package description yet."
        tooltip = f"{group}\n{self.total_file_count} mapped files\n\n{self.description}"
        self.setToolTip(tooltip)
        self._apply_style()

    def _apply_style(self) -> None:
        self.setPen(QPen(QColor("#625a83") if self._hovered else QColor("#343b4d"), 1.5 if self._hovered else 1.0))
        self.setBrush(QBrush(QColor("#1a1f2a") if self._hovered else QColor("#141922")))
        self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawRoundedRect(self.rect(), 9.0, 9.0)

        title_font = QFont()
        title_font.setPointSizeF(10.7)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#f3f4f8"))
        painter.drawText(QRectF(14, 10, self.WIDTH - 28, 24), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.group)

        description_font = QFont()
        description_font.setPointSizeF(7.7)
        painter.setFont(description_font)
        painter.setPen(QColor("#a8afbf"))
        painter.drawText(
            QRectF(14, 37, self.WIDTH - 28, 42),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            _shorten(self.description, 130),
        )

        summary_font = QFont()
        summary_font.setPointSizeF(7.7)
        summary_font.setBold(True)
        painter.setFont(summary_font)
        painter.setPen(QColor("#8f98aa"))
        painter.drawText(QRectF(14, 82, self.WIDTH - 28, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.summary_text)

        files_font = QFont()
        files_font.setPointSizeF(7.8)
        painter.setFont(files_font)
        painter.setPen(QColor("#cbd0dc"))
        y = 108.0
        for line in self.file_lines:
            if line.startswith("Showing") or line.startswith("No mapped"):
                painter.setPen(QColor("#8e96a8"))
            else:
                painter.setPen(QColor("#cbd0dc"))
            painter.drawText(QRectF(14, y, self.WIDTH - 28, 17), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
            y += 17.0

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self._apply_style()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self._apply_style()
        super().hoverLeaveEvent(event)


class ProjectRootFrame(QGraphicsRectItem):
    """Visual containment frame making top-level package hierarchy unambiguous."""

    def __init__(self, rect: QRectF, project_name: str, description: str):
        super().__init__(rect)
        self.project_name = project_name
        self.description = description.strip() or "Project root containing sibling top-level packages and root files."
        self.setPen(QPen(QColor("#303748"), 1.2))
        self.setBrush(QBrush(QColor("#10141c")))
        self.setZValue(-30)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawRoundedRect(self.rect(), 13.0, 13.0)

        title_font = QFont()
        title_font.setPointSizeF(12.2)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#f0f2f7"))
        painter.drawText(
            QRectF(self.rect().left() + 18, self.rect().top() + 12, self.rect().width() - 36, 26),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{self.project_name} · Project root",
        )
        desc_font = QFont()
        desc_font.setPointSizeF(8.0)
        painter.setFont(desc_font)
        painter.setPen(QColor("#8f97aa"))
        painter.drawText(
            QRectF(self.rect().left() + 18, self.rect().top() + 40, self.rect().width() - 36, 38),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            _shorten(self.description, 200),
        )


class ProjectMapGraph(QGraphicsView):
    file_requested = Signal(str)
    directory_requested = Signal(str)
    file_focus_requested = Signal(str)
    zoom_changed = Signal(int)
    layout_changed = Signal()

    MIN_ZOOM = 0.35
    MAX_ZOOM = 2.50
    PAN_MARGIN = 900.0
    DRAG_THRESHOLD = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProjectMapGraph")
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.data: dict = {"project": {"name": "", "description": ""}, "entries": {}}
        self.view_mode = "architecture"
        self.directory = ""
        self.focus_file: str | None = None
        self.query = ""
        self.show_support_files = True
        self.nodes: dict[str, ProjectMapNode] = {}
        self.group_nodes: dict[str, ArchitectureGroupNode] = {}
        self.root_frame: ProjectRootFrame | None = None
        self.edges: list[RelationshipEdge] = []
        self.outgoing: dict[str, list[dict]] = {}
        self.incoming: dict[str, list[dict]] = {}
        self._content_rect = QRectF(0, 0, 800, 500)

        self.layout_state: dict = {"format_version": 1, "contexts": {}}

        self._pan_active = False
        self._pan_start = None
        self._pan_last = None
        self._pan_moved = False

        self._drag_item: ProjectMapNode | ArchitectureGroupNode | None = None
        self._drag_start_view = None
        self._drag_start_scene: QPointF | None = None
        self._drag_item_start: QPointF | None = None
        self._drag_moved = False

        # Wheel events can arrive dozens of times per second on modern mice and
        # touchpads. Keep zoom itself purely visual, then persist the final camera
        # once scrolling settles instead of emitting/saving layout state per tick.
        self._camera_commit_timer = QTimer(self)
        self._camera_commit_timer.setSingleShot(True)
        self._camera_commit_timer.setInterval(180)
        self._camera_commit_timer.timeout.connect(self._finish_camera_interaction)

    # ----- persisted layout/camera state -----

    def set_layout_state(self, state: dict | None, *, rebuild: bool = True) -> None:
        if isinstance(state, dict):
            contexts = state.get("contexts", {})
            self.layout_state = {
                "format_version": 1,
                "contexts": contexts if isinstance(contexts, dict) else {},
            }
        else:
            self.layout_state = {"format_version": 1, "contexts": {}}
        if rebuild:
            self.rebuild()
            QTimer.singleShot(0, self._restore_camera_or_fit)

    def export_layout_state(self) -> dict:
        return {
            "format_version": 1,
            "contexts": self.layout_state.setdefault("contexts", {}),
        }

    def _layout_key(self) -> str:
        if self.view_mode == "directory":
            return f"directory:{self.directory or '__root__'}"
        if self.view_mode == "file":
            return f"file:{self.focus_file or '__none__'}"
        return "architecture"

    def _context_layout(self, *, create: bool = True) -> dict:
        contexts = self.layout_state.setdefault("contexts", {})
        key = self._layout_key()
        if create:
            context = contexts.setdefault(key, {})
            context.setdefault("positions", {})
            return context
        context = contexts.get(key, {})
        return context if isinstance(context, dict) else {}

    def _saved_position(self, item_id: str) -> QPointF | None:
        raw = self._context_layout(create=False).get("positions", {}).get(item_id)
        if isinstance(raw, list) and len(raw) == 2:
            try:
                return QPointF(float(raw[0]), float(raw[1]))
            except (TypeError, ValueError):
                return None
        return None

    def _position_item(self, item, item_id: str, x: float, y: float) -> None:
        saved = self._saved_position(item_id)
        item.setPos(saved if saved is not None else QPointF(x, y))

    def _item_layout_id(self, item) -> str:
        if isinstance(item, ArchitectureGroupNode):
            return f"group:{item.directory_key or '__root_files__'}"
        if isinstance(item, ProjectMapNode):
            return f"file:{item.path}"
        return ""

    def _remember_item_position(self, item) -> None:
        item_id = self._item_layout_id(item)
        if not item_id:
            return
        pos = item.pos()
        self._context_layout()["positions"][item_id] = [round(pos.x(), 2), round(pos.y(), 2)]
        self.layout_changed.emit()

    def _remember_camera(self) -> None:
        if not self.scene.items():
            return
        center = self.mapToScene(self.viewport().rect().center())
        context = self._context_layout()
        context["camera"] = {
            "zoom": round(max(self.MIN_ZOOM, min(self.MAX_ZOOM, self.transform().m11())), 5),
            "center": [round(center.x(), 2), round(center.y(), 2)],
        }
        self.layout_changed.emit()

    def _restore_camera_or_fit(self) -> None:
        camera = self._context_layout(create=False).get("camera")
        if not isinstance(camera, dict):
            self.fit_to_contents(remember=False)
            return
        try:
            zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, float(camera.get("zoom", 1.0))))
            center_raw = camera.get("center", [])
            center = QPointF(float(center_raw[0]), float(center_raw[1]))
        except (TypeError, ValueError, IndexError):
            self.fit_to_contents(remember=False)
            return
        self.resetTransform()
        self.scale(zoom, zoom)
        self.centerOn(center)
        self._emit_zoom()

    def auto_arrange_current(self) -> None:
        context = self._context_layout()
        context["positions"] = {}
        context.pop("camera", None)
        self.rebuild()
        QTimer.singleShot(0, lambda: self.fit_to_contents(remember=True))
        self.layout_changed.emit()

    def reset_all_layouts(self) -> None:
        self.layout_state = {"format_version": 1, "contexts": {}}
        self.rebuild()
        QTimer.singleShot(0, lambda: self.fit_to_contents(remember=True))
        self.layout_changed.emit()

    # ----- canvas interaction -----

    def _zoom_percent(self) -> int:
        return int(round(self.transform().m11() * 100))

    def _emit_zoom(self) -> None:
        self.zoom_changed.emit(self._zoom_percent())

    def _finish_camera_interaction(self) -> None:
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._remember_camera()
        self.viewport().update()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            event.accept()
            return
        current = max(0.001, self.transform().m11())
        step_factor = 1.15 ** (delta / 120.0)
        target = max(self.MIN_ZOOM, min(self.MAX_ZOOM, current * step_factor))
        factor = target / current
        if abs(factor - 1.0) > 0.0001:
            # Antialiasing is visually unnecessary while the scene is moving and
            # is expensive for the many card/edge primitives in the map.
            self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            self.scale(factor, factor)
            self._emit_zoom()
            self._camera_commit_timer.start()
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            point = event.position().toPoint()
            item = self._interactive_item_at(point)
            if item is not None:
                self._drag_item = item
                self._drag_start_view = point
                self._drag_start_scene = self.mapToScene(point)
                self._drag_item_start = item.pos()
                self._drag_moved = False
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return

            self._pan_active = True
            self._pan_start = point
            self._pan_last = point
            self._pan_moved = False
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_item is not None and event.buttons() & Qt.MouseButton.LeftButton:
            point = event.position().toPoint()
            if self._drag_start_view is not None:
                delta_view = point - self._drag_start_view
                if abs(delta_view.x()) + abs(delta_view.y()) >= self.DRAG_THRESHOLD:
                    self._drag_moved = True
            if self._drag_moved and self._drag_start_scene is not None and self._drag_item_start is not None:
                current_scene = self.mapToScene(point)
                delta_scene = current_scene - self._drag_start_scene
                self._drag_item.setPos(self._drag_item_start + delta_scene)
                if isinstance(self._drag_item, ArchitectureGroupNode):
                    self._refresh_root_frame_geometry()
                self._refresh_edge_geometry()
            event.accept()
            return

        if self._pan_active and event.buttons() & Qt.MouseButton.LeftButton:
            point = event.position().toPoint()
            if self._pan_start is not None:
                delta_from_start = point - self._pan_start
                if abs(delta_from_start.x()) + abs(delta_from_start.y()) >= self.DRAG_THRESHOLD:
                    self._pan_moved = True
            if self._pan_moved and self._pan_last is not None:
                delta = point - self._pan_last
                self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._pan_last = point
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_item is not None:
            point = event.position().toPoint()
            item = self._drag_item
            moved = self._drag_moved
            self._drag_item = None
            self._drag_start_view = None
            self._drag_start_scene = None
            self._drag_item_start = None
            self._drag_moved = False
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            if moved:
                self._remember_item_position(item)
                self._update_content_bounds()
            else:
                self._activate_item(item, double_click=False)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._pan_active:
            point = event.position().toPoint()
            was_click = not self._pan_moved
            self._pan_active = False
            self._pan_start = None
            self._pan_last = None
            self._pan_moved = False
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            if was_click:
                self._activate_item_at(point, double_click=False)
            else:
                self._remember_camera()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            item = self._interactive_item_at(event.position().toPoint())
            if item is not None:
                self._activate_item(item, double_click=True)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _interactive_item_at(self, viewport_point):
        item = self.itemAt(viewport_point)
        while item is not None:
            if isinstance(item, (ProjectMapNode, ArchitectureGroupNode)):
                return item
            item = item.parentItem()
        return None

    def _activate_item(self, item, *, double_click: bool) -> None:
        if isinstance(item, ArchitectureGroupNode):
            self.directory_requested.emit(item.directory_key)
        elif isinstance(item, ProjectMapNode):
            if double_click:
                self.file_requested.emit(item.path)
            else:
                self._activate_file(item.path)

    def _activate_item_at(self, viewport_point, *, double_click: bool) -> None:
        item = self._interactive_item_at(viewport_point)
        if item is not None:
            self._activate_item(item, double_click=double_click)

    def fit_to_contents(self, *, remember: bool = True) -> None:
        rect = self._content_rect
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            return
        self.resetTransform()
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        current = self.transform().m11()
        if current < self.MIN_ZOOM:
            self.scale(self.MIN_ZOOM / max(current, 0.001), self.MIN_ZOOM / max(current, 0.001))
        elif current > self.MAX_ZOOM:
            self.scale(self.MAX_ZOOM / current, self.MAX_ZOOM / current)
        self.centerOn(rect.center())
        self._emit_zoom()
        if remember:
            self._remember_camera()

    def reset_zoom(self) -> None:
        self.resetTransform()
        self.centerOn(self._content_rect.center())
        self._emit_zoom()
        self._remember_camera()

    # ----- data/view setup -----

    def set_data(self, data: dict) -> None:
        self.data = data
        self.outgoing, self.incoming = relationship_index(data)
        if self.focus_file not in data.get("entries", {}):
            self.focus_file = None
        self.rebuild()

    def set_view(self, mode: str, *, directory: str = "", file_path: str | None = None) -> None:
        normalized_directory = directory.strip("/")
        target_file = self.focus_file if file_path is None else file_path
        changed_view = (
            mode != self.view_mode
            or normalized_directory != self.directory
            or (mode == "file" and target_file != self.focus_file)
        )
        if changed_view and self.scene.items():
            self._remember_camera()
        self.view_mode = mode
        self.directory = normalized_directory
        if file_path is not None:
            self.focus_file = file_path
        if changed_view:
            self.rebuild()
            QTimer.singleShot(0, self._restore_camera_or_fit)

    def set_query(self, query: str) -> None:
        self.query = query.strip().lower()
        self._apply_query_focus()

    def set_show_support_files(self, visible: bool) -> None:
        if self.show_support_files == visible:
            return
        self.show_support_files = visible
        self.rebuild()
        QTimer.singleShot(0, lambda: self.fit_to_contents(remember=True))

    def _all_file_paths(self) -> list[str]:
        return [
            path
            for path, entry in self.data.get("entries", {}).items()
            if isinstance(entry, dict) and entry.get("kind") == "file"
        ]

    def _visible_file_paths(self) -> list[str]:
        paths = self._all_file_paths()
        if not self.show_support_files:
            paths = [path for path in paths if not _is_support_file(path)]
        return paths

    def _lane_priority(self, name: str) -> tuple[int, str]:
        lower = name.lower()
        if name == "Root files":
            return (0, lower)
        if lower in {"ui", "frontend", "views", "pages", "components", "client"}:
            return (10, lower)
        if lower in {"core", "domain", "service", "services", "backend", "server"}:
            return (20, lower)
        if lower in {"data", "storage", "db", "database", "models"}:
            return (30, lower)
        if lower in {"tests", "test", "spec", "specs"}:
            return (90, lower)
        return (50, lower)

    def rebuild(self) -> None:
        self.scene.clear()
        self.nodes.clear()
        self.group_nodes.clear()
        self.root_frame = None
        self.edges.clear()
        self.outgoing, self.incoming = relationship_index(self.data)

        if self.view_mode == "file":
            self._build_file_view()
        elif self.view_mode == "directory":
            self._build_directory_view()
        else:
            self._build_architecture_view()

        self._apply_query_focus()
        self._update_content_bounds()

    def _update_content_bounds(self) -> None:
        bounds = self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        if bounds.isNull() or bounds.width() <= 0 or bounds.height() <= 0:
            bounds = QRectF(0, 0, 800, 500)
        self._content_rect = bounds
        self.scene.setSceneRect(bounds.adjusted(-self.PAN_MARGIN, -self.PAN_MARGIN, self.PAN_MARGIN, self.PAN_MARGIN))

    def _place_file_node(self, path: str, x: float, y: float, *, subtitle: str = "") -> ProjectMapNode:
        entry = self.data.get("entries", {}).get(path, {})
        node = ProjectMapNode(path, entry, self._activate_file, self.file_requested.emit, subtitle=subtitle)
        self._position_item(node, f"file:{path}", x, y)
        self.scene.addItem(node)
        self.nodes[path] = node
        return node

    def _file_stats(self, path: str) -> str:
        return f"{len(self.incoming.get(path, []))} incoming · {len(self.outgoing.get(path, []))} outgoing"

    # ----- architecture view -----

    def _architecture_group_for_file(self, path: str) -> str:
        return path.split("/", 1)[0] if "/" in path else "Root files"

    def _top_level_directories(self) -> list[str]:
        entries = self.data.get("entries", {})
        directories = {
            path
            for path, entry in entries.items()
            if isinstance(entry, dict) and entry.get("kind") == "directory" and "/" not in path
        }
        for path in self._all_file_paths():
            if "/" in path:
                directories.add(path.split("/", 1)[0])
        return sorted(directories, key=self._lane_priority)

    def _build_architecture_view(self) -> None:
        entries = self.data.get("entries", {})
        all_files = set(self._all_file_paths())
        visible_files = set(self._visible_file_paths())

        total_groups: dict[str, list[str]] = defaultdict(list)
        visible_groups: dict[str, list[str]] = defaultdict(list)
        for path in sorted(all_files, key=str.lower):
            total_groups[self._architecture_group_for_file(path)].append(path)
        for path in sorted(visible_files, key=str.lower):
            visible_groups[self._architecture_group_for_file(path)].append(path)

        ordered_groups: list[str] = []
        if total_groups.get("Root files"):
            ordered_groups.append("Root files")
        ordered_groups.extend(self._top_level_directories())
        # Keep directory-only packages visible even when they contain no files.
        for directory in self._top_level_directories():
            total_groups.setdefault(directory, [])
            visible_groups.setdefault(directory, [])
        ordered_groups = list(dict.fromkeys(ordered_groups))

        if not ordered_groups:
            self._add_empty_message("No mapped packages or files are available in the Project Map.")
            return

        aggregated: dict[tuple[str, str], list[dict]] = defaultdict(list)
        incoming_counts: Counter[str] = Counter()
        outgoing_counts: Counter[str] = Counter()
        for source, relationships in self.outgoing.items():
            if source not in visible_files:
                continue
            source_group = self._architecture_group_for_file(source)
            for relationship in relationships:
                target = str(relationship.get("target", ""))
                if target not in visible_files:
                    continue
                target_group = self._architecture_group_for_file(target)
                if source_group == target_group:
                    continue
                aggregated[(source_group, target_group)].append(relationship)
                outgoing_counts[source_group] += 1
                incoming_counts[target_group] += 1

        columns = 3 if len(ordered_groups) >= 3 else max(1, len(ordered_groups))
        gap_x = 58.0
        gap_y = 58.0
        start_x = 70.0
        start_y = 128.0

        for index, group in enumerate(sorted(ordered_groups, key=self._lane_priority)):
            row = index // columns
            col = index % columns
            x = start_x + col * (ArchitectureGroupNode.WIDTH + gap_x)
            y = start_y + row * (ArchitectureGroupNode.HEIGHT + gap_y)
            directory_key = "" if group == "Root files" else group
            node = ArchitectureGroupNode(
                group,
                directory_key,
                visible_groups.get(group, []),
                entries,
                incoming_counts[group],
                outgoing_counts[group],
                self._activate_group,
                total_file_count=len(total_groups.get(group, [])),
            )
            self._position_item(node, f"group:{directory_key or '__root_files__'}", x, y)
            self.scene.addItem(node)
            self.group_nodes[group] = node

        # The root is a containment frame, not another dependency node. This makes
        # ui/core/tests/tools read as siblings under one project instead of a chain.
        group_rect: QRectF | None = None
        for node in self.group_nodes.values():
            rect = node.sceneBoundingRect()
            group_rect = rect if group_rect is None else group_rect.united(rect)
        if group_rect is not None:
            frame_rect = group_rect.adjusted(-38, -96, 38, 38)
            project = self.data.get("project", {})
            self.root_frame = ProjectRootFrame(
                frame_rect,
                str(project.get("name", "Project")) or "Project",
                str(project.get("description", "")),
            )
            self.scene.addItem(self.root_frame)

        for (source_group, target_group), relationships in aggregated.items():
            source_node = self.group_nodes.get(source_group)
            target_node = self.group_nodes.get(target_group)
            if not source_node or not target_node:
                continue
            source_rect = source_node.sceneBoundingRect()
            target_rect = target_node.sceneBoundingRect()
            start, end = self._edge_points(source_rect, target_rect)
            type_counts = Counter(str(rel.get("type", "link")) for rel in relationships)
            most_common = type_counts.most_common(1)[0][0] if type_counts else "links"
            label = f"{len(relationships)} {most_common}" if len(relationships) > 1 else most_common
            source_kind = "static" if all(rel.get("source") == "static" for rel in relationships) else "ai"
            aggregate_relation = {
                "type": most_common,
                "source": source_kind,
                "description": f"{len(relationships)} relationships between {source_group} and {target_group}.",
            }
            edge = RelationshipEdge(
                source_group,
                target_group,
                aggregate_relation,
                start,
                end,
                label=label,
                strong=True,
            )
            self.scene.addItem(edge)
            self.edges.append(edge)

    # ----- directory/file views -----

    def _build_directory_view(self) -> None:
        directory = self.directory.strip("/")
        prefix = f"{directory}/" if directory else ""
        visible_files = self._visible_file_paths()
        paths = [
            path
            for path in visible_files
            if (directory and path.startswith(prefix) and "/" not in path[len(prefix):])
            or (not directory and "/" not in path)
        ]
        if not paths and directory:
            paths = [path for path in visible_files if path.startswith(prefix)]
        paths.sort(key=lambda value: (-self._connection_degree(value), Path(value).name.lower()))

        directory_label = directory or "Project root files"
        title = self.scene.addText(directory_label)
        title_font = title.font()
        title_font.setPointSizeF(12.0)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setDefaultTextColor(QColor("#f0f2f7"))
        title.setPos(30, 18)

        directory_entry = self.data.get("entries", {}).get(directory, {}) if directory else {}
        description = str(directory_entry.get("description", "")).strip()
        if not description and not directory:
            description = "Files stored directly at the project root."
        if description:
            desc = self.scene.addText(_shorten(description, 210))
            desc_font = desc.font()
            desc_font.setPointSizeF(8.0)
            desc.setFont(desc_font)
            desc.setDefaultTextColor(QColor("#a4abba"))
            desc.setTextWidth(760)
            desc.setPos(30, 46)

        external_in, external_out = self._directory_external_counts(directory, set(paths))
        summary = self.scene.addText(
            f"{len(paths)} visible files · {external_in} external incoming · {external_out} external outgoing"
        )
        summary_font = summary.font()
        summary_font.setPointSizeF(8.0)
        summary.setFont(summary_font)
        summary.setDefaultTextColor(QColor("#8f97aa"))
        summary.setPos(30, 78)

        hint = self.scene.addText("Drag cards to arrange them. Click a file for its relationship neighborhood; double-click to open it.")
        hint_font = hint.font()
        hint_font.setPointSizeF(8.0)
        hint.setFont(hint_font)
        hint.setDefaultTextColor(QColor("#727b8f"))
        hint.setPos(30, 99)

        if not paths:
            self._add_empty_message("No visible files in this package.", y=138)
            return

        columns = 3 if len(paths) >= 7 else 2
        start_x = 30.0
        start_y = 142.0
        gap_x = 30.0
        gap_y = 20.0
        for index, path in enumerate(paths):
            col = index % columns
            row = index // columns
            x = start_x + col * (ProjectMapNode.WIDTH + gap_x)
            y = start_y + row * (ProjectMapNode.HEIGHT + gap_y)
            self._place_file_node(path, x, y, subtitle=self._file_stats(path))

    def _build_file_view(self) -> None:
        center = self.focus_file
        entries = self.data.get("entries", {})
        if not center or entries.get(center, {}).get("kind") != "file":
            self._add_empty_message("Choose a file from Architecture or Directory view to inspect its relationships.")
            return

        incoming_relations = list(self.incoming.get(center, []))
        outgoing_relations = list(self.outgoing.get(center, []))
        tests = [rel for rel in incoming_relations if rel.get("type") == "tests"]
        incoming_relations = [rel for rel in incoming_relations if rel.get("type") != "tests"]

        incoming_paths = sorted({str(rel.get("source_path", "")) for rel in incoming_relations if rel.get("source_path")}, key=str.lower)
        outgoing_paths = sorted({str(rel.get("target", "")) for rel in outgoing_relations if rel.get("target")}, key=str.lower)
        test_paths = sorted({str(rel.get("source_path", "")) for rel in tests if rel.get("source_path")}, key=str.lower)

        lane_gap = 66.0
        x_in = 30.0
        x_center = x_in + ProjectMapNode.WIDTH + lane_gap
        x_out = x_center + ProjectMapNode.WIDTH + lane_gap
        self._add_lane_header("Incoming", x_in, 66, ProjectMapNode.WIDTH)
        self._add_lane_header("Selected file", x_center, 66, ProjectMapNode.WIDTH)
        self._add_lane_header("Outgoing", x_out, 66, ProjectMapNode.WIDTH)

        start_y = 112.0
        row_step = ProjectMapNode.HEIGHT + 22.0
        center_node = self._place_file_node(center, x_center, start_y, subtitle=self._file_stats(center))
        center_node.set_selected(True)

        for index, path in enumerate(incoming_paths):
            relation = self._relation_between(path, center)
            self._place_file_node(path, x_in, start_y + index * row_step, subtitle=self._relation_subtitle(relation))
        for index, path in enumerate(outgoing_paths):
            relation = self._relation_between(center, path)
            self._place_file_node(path, x_out, start_y + index * row_step, subtitle=self._relation_subtitle(relation))

        primary_rows = max(len(incoming_paths), len(outgoing_paths), 1)
        if test_paths:
            tests_y = start_y + primary_rows * row_step + 26
            self._add_lane_header("Tests", x_center, tests_y, ProjectMapNode.WIDTH)
            for index, path in enumerate(test_paths):
                x = x_center + (index % 2) * (ProjectMapNode.WIDTH + 28)
                y = tests_y + 46 + (index // 2) * row_step
                self._place_file_node(path, x, y, subtitle="tests this file")

        title = self.scene.addText(Path(center).name)
        title_font = title.font()
        title_font.setPointSizeF(11.2)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setDefaultTextColor(QColor("#f0f2f7"))
        title.setPos(30, 14)
        description = str(entries.get(center, {}).get("description", "")).strip()
        if description:
            desc = self.scene.addText(_shorten(description, 190))
            font = desc.font()
            font.setPointSizeF(8.0)
            desc.setFont(font)
            desc.setDefaultTextColor(QColor("#9da5b6"))
            desc.setTextWidth(790)
            desc.setPos(30, 38)

        self._add_visible_file_edges(center)

    def _add_visible_file_edges(self, center: str) -> None:
        for source, relationships in self.outgoing.items():
            source_node = self.nodes.get(source)
            if not source_node:
                continue
            for relation in relationships:
                target = str(relation.get("target", ""))
                target_node = self.nodes.get(target)
                if not target_node:
                    continue
                if source != center and target != center:
                    continue
                start, end = self._edge_points(source_node.sceneBoundingRect(), target_node.sceneBoundingRect())
                edge = RelationshipEdge(source, target, relation, start, end, strong=True)
                self.scene.addItem(edge)
                self.edges.append(edge)

    def _refresh_root_frame_geometry(self) -> None:
        if self.root_frame is None or not self.group_nodes:
            return
        group_rect: QRectF | None = None
        for node in self.group_nodes.values():
            rect = node.sceneBoundingRect()
            group_rect = rect if group_rect is None else group_rect.united(rect)
        if group_rect is not None:
            self.root_frame.setRect(group_rect.adjusted(-38, -96, 38, 38))
            self.root_frame.update()

    def _refresh_edge_geometry(self) -> None:
        for edge in self.edges:
            source_item = self.group_nodes.get(edge.source_path) or self.nodes.get(edge.source_path)
            target_item = self.group_nodes.get(edge.target_path) or self.nodes.get(edge.target_path)
            if source_item is None or target_item is None:
                continue
            start, end = self._edge_points(source_item.sceneBoundingRect(), target_item.sceneBoundingRect())
            edge.update_geometry(start, end)

    def _edge_points(self, source_rect: QRectF, target_rect: QRectF) -> tuple[QPointF, QPointF]:
        dx = target_rect.center().x() - source_rect.center().x()
        dy = target_rect.center().y() - source_rect.center().y()
        if abs(dx) >= abs(dy):
            if dx >= 0:
                return (
                    QPointF(source_rect.right(), source_rect.center().y()),
                    QPointF(target_rect.left(), target_rect.center().y()),
                )
            return (
                QPointF(source_rect.left(), source_rect.center().y()),
                QPointF(target_rect.right(), target_rect.center().y()),
            )
        if dy >= 0:
            return (
                QPointF(source_rect.center().x(), source_rect.bottom()),
                QPointF(target_rect.center().x(), target_rect.top()),
            )
        return (
            QPointF(source_rect.center().x(), source_rect.top()),
            QPointF(target_rect.center().x(), target_rect.bottom()),
        )

    def _add_lane_header(self, title: str, x: float, y: float, width: float) -> None:
        rect = self.scene.addRect(QRectF(x, y, width, 30), QPen(QColor("#2b3140")), QBrush(QColor("#11151d")))
        rect.setZValue(1)
        label = self.scene.addText(title)
        label.setDefaultTextColor(QColor("#aeb5c5"))
        font = label.font()
        font.setPointSizeF(8.2)
        font.setBold(True)
        label.setFont(font)
        label.setPos(x + 9, y + 4)
        label.setZValue(2)

    def _add_empty_message(self, text: str, *, y: float = 80.0) -> None:
        label = self.scene.addText(text)
        label.setDefaultTextColor(QColor("#8f97aa"))
        font = label.font()
        font.setPointSizeF(9.0)
        label.setFont(font)
        label.setPos(30, y)

    def _connection_degree(self, path: str) -> int:
        return len(self.incoming.get(path, [])) + len(self.outgoing.get(path, []))

    def _directory_external_counts(self, directory: str, paths: set[str]) -> tuple[int, int]:
        incoming = 0
        outgoing = 0
        for path in paths:
            incoming += sum(1 for rel in self.incoming.get(path, []) if rel.get("source_path") not in paths)
            outgoing += sum(1 for rel in self.outgoing.get(path, []) if rel.get("target") not in paths)
        return incoming, outgoing

    def _relation_between(self, source: str, target: str) -> dict:
        matches = [rel for rel in self.outgoing.get(source, []) if rel.get("target") == target]
        return matches[0] if matches else {}

    def _relation_subtitle(self, relation: dict) -> str:
        if not relation:
            return "related"
        source = "static" if relation.get("source") == "static" else "authored"
        return f"{relation.get('type', 'related')} · {source}"

    def _activate_group(self, group: str) -> None:
        self.directory_requested.emit(group.strip("/"))

    def _activate_file(self, path: str) -> None:
        self.file_focus_requested.emit(path)

    # ----- search emphasis -----

    def _matches_query(self, path: str) -> bool:
        if not self.query:
            return True
        entry = self.data.get("entries", {}).get(path, {})
        haystack = [path, str(entry.get("description", ""))]
        for symbol in entry.get("important_symbols", []):
            haystack.extend([str(symbol.get("name", "")), str(symbol.get("description", ""))])
        return self.query in "\n".join(haystack).lower()

    def _group_matches_query(self, group: str, node: ArchitectureGroupNode) -> bool:
        if not self.query:
            return True
        directory_entry = self.data.get("entries", {}).get(node.directory_key, {}) if node.directory_key else {}
        group_text = f"{group}\n{directory_entry.get('description', '')}".lower()
        return self.query in group_text or any(self._matches_query(path) for path in node.file_paths)

    def _apply_query_focus(self) -> None:
        if not self.query:
            for node in self.nodes.values():
                node.setOpacity(1.0)
            for node in self.group_nodes.values():
                node.setOpacity(1.0)
            for edge in self.edges:
                edge.set_emphasis(False, False)
            return

        matches = {path for path in self.nodes if self._matches_query(path)}
        for path, node in self.nodes.items():
            node.setOpacity(1.0 if path in matches else 0.14)
        group_matches: dict[str, bool] = {}
        for group, node in self.group_nodes.items():
            matched = self._group_matches_query(group, node)
            group_matches[group] = matched
            node.setOpacity(1.0 if matched else 0.14)
        for edge in self.edges:
            if self.view_mode == "architecture":
                relevant = group_matches.get(edge.source_path, False) or group_matches.get(edge.target_path, False)
            else:
                relevant = edge.source_path in matches or edge.target_path in matches
            edge.set_emphasis(relevant, not relevant)


class ProjectMapWorkspace(QWidget):
    file_requested = Signal(str)
    overview_requested = Signal()
    map_saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model: ProjectModel | None = None
        self.data: dict = {"project": {"name": "", "description": ""}, "entries": {}}
        self.current_path: str | None = None
        self.current_directory = ""
        self.view_mode = "architecture"
        self._loading_detail = False
        self._dirty = False
        self._history: list[tuple[str, str, str | None]] = []
        self._history_index = -1
        self._applying_history = False
        self._graph_initialized = False
        self._pending_layout_state: dict = {}
        self._layout_save_timer = QTimer(self)
        self._layout_save_timer.setSingleShot(True)
        self._layout_save_timer.setInterval(250)
        self._layout_save_timer.timeout.connect(self._save_layout_state)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QFrame()
        toolbar.setObjectName("ProjectMapToolbar")
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 6, 8, 6)
        toolbar_layout.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(8)
        overview = QPushButton("Sync Overview")
        overview.setObjectName("TextButton")
        overview.clicked.connect(self.overview_requested.emit)
        title = QLabel("Project Map")
        title.setObjectName("ProjectMapWorkspaceTitle")
        top.addWidget(overview)
        top.addWidget(title)

        self.coverage = QLabel("")
        self.coverage.setObjectName("ProjectMapCoverage")
        top.addWidget(self.coverage)
        top.addStretch(1)

        self.search = QLineEdit()
        self.search.setObjectName("ProjectMapSearch")
        self.search.setPlaceholderText("Search map…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(230)
        self.search.textChanged.connect(self.graph_search_changed)
        top.addWidget(self.search)

        self.support_toggle = QCheckBox("Support files")
        self.support_toggle.setObjectName("ProjectMapSupportToggle")
        self.support_toggle.setToolTip("Show README, ignore, environment, launcher, and similar support files")
        self.support_toggle.setChecked(True)
        self.support_toggle.toggled.connect(self._toggle_support_files)
        top.addWidget(self.support_toggle)

        save = QPushButton("Save")
        save.setObjectName("Secondary")
        save.clicked.connect(self.save)
        top.addWidget(save)
        refresh = QPushButton("Refresh")
        refresh.setObjectName("Secondary")
        refresh.clicked.connect(self.refresh_index)
        top.addWidget(refresh)
        toolbar_layout.addLayout(top)

        navigation = QHBoxLayout()
        navigation.setSpacing(4)

        self.back_btn = QToolButton()
        self.back_btn.setObjectName("ProjectMapCanvasButton")
        self.back_btn.setText("←")
        self.back_btn.setToolTip("Back · Alt+Left")
        self.back_btn.clicked.connect(self.go_back)
        navigation.addWidget(self.back_btn)

        self.forward_btn = QToolButton()
        self.forward_btn.setObjectName("ProjectMapCanvasButton")
        self.forward_btn.setText("→")
        self.forward_btn.setToolTip("Forward · Alt+Right")
        self.forward_btn.clicked.connect(self.go_forward)
        navigation.addWidget(self.forward_btn)

        self.project_crumb = QToolButton()
        self.project_crumb.setObjectName("ProjectMapBreadcrumb")
        self.project_crumb.clicked.connect(self.show_architecture)
        navigation.addWidget(self.project_crumb)

        self.dir_separator = QLabel("/")
        self.dir_separator.setObjectName("ProjectMapBreadcrumbSeparator")
        self.directory_crumb = QToolButton()
        self.directory_crumb.setObjectName("ProjectMapBreadcrumb")
        self.directory_crumb.clicked.connect(lambda: self.show_directory(self.current_directory))
        navigation.addWidget(self.dir_separator)
        navigation.addWidget(self.directory_crumb)

        self.file_separator = QLabel("/")
        self.file_separator.setObjectName("ProjectMapBreadcrumbSeparator")
        self.file_crumb = QToolButton()
        self.file_crumb.setObjectName("ProjectMapBreadcrumb")
        self.file_crumb.clicked.connect(lambda: self.show_file(self.current_path or ""))
        navigation.addWidget(self.file_separator)
        navigation.addWidget(self.file_crumb)
        navigation.addStretch(1)

        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        self.architecture_btn = self._view_button("Architecture", "architecture", self.show_architecture)
        self.directory_btn = self._view_button("Directory", "directory", lambda: self.show_directory(self.current_directory))
        self.file_btn = self._view_button("File", "file", lambda: self.show_file(self.current_path or ""))
        for button in (self.architecture_btn, self.directory_btn, self.file_btn):
            self.view_group.addButton(button)
            navigation.addWidget(button)

        self.arrange_btn = QToolButton()
        self.arrange_btn.setObjectName("ProjectMapCanvasButton")
        self.arrange_btn.setText("Auto Arrange")
        self.arrange_btn.setToolTip("Restore automatic positions for the current view")
        navigation.addWidget(self.arrange_btn)

        self.reset_layout_btn = QToolButton()
        self.reset_layout_btn.setObjectName("ProjectMapCanvasButton")
        self.reset_layout_btn.setText("Reset Layout")
        self.reset_layout_btn.setToolTip("Clear saved card positions and canvas views for this project")
        navigation.addWidget(self.reset_layout_btn)

        self.fit_btn = QToolButton()
        self.fit_btn.setObjectName("ProjectMapCanvasButton")
        self.fit_btn.setText("Fit")
        self.fit_btn.setToolTip("Fit the current map to the canvas")
        self.fit_btn.clicked.connect(lambda: self.graph.fit_to_contents())
        navigation.addWidget(self.fit_btn)

        self.zoom_reset_btn = QToolButton()
        self.zoom_reset_btn.setObjectName("ProjectMapCanvasButton")
        self.zoom_reset_btn.setText("100%")
        self.zoom_reset_btn.setToolTip("Reset map zoom to 100%")
        self.zoom_reset_btn.clicked.connect(lambda: self.graph.reset_zoom())
        navigation.addWidget(self.zoom_reset_btn)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("ProjectMapZoomLabel")
        self.zoom_label.setMinimumWidth(42)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        navigation.addWidget(self.zoom_label)

        self.details_btn = QPushButton("Details")
        self.details_btn.setObjectName("TextButton")
        self.details_btn.setToolTip("Show or hide documentation and relationship details")
        self.details_btn.clicked.connect(self.toggle_inspector)
        navigation.addWidget(self.details_btn)
        toolbar_layout.addLayout(navigation)
        root.addWidget(toolbar)

        content = QSplitter(Qt.Orientation.Horizontal)
        self.graph = ProjectMapGraph()
        self.graph.directory_requested.connect(self.show_directory)
        self.graph.file_focus_requested.connect(self.show_file)
        self.graph.file_requested.connect(self._request_file)
        self.graph.zoom_changed.connect(lambda value: self.zoom_label.setText(f"{value}%"))
        self.graph.layout_changed.connect(self._schedule_layout_save)
        self.arrange_btn.clicked.connect(self.graph.auto_arrange_current)
        self.reset_layout_btn.clicked.connect(self.graph.reset_all_layouts)
        content.addWidget(self.graph)

        self.inspector = QFrame()
        self.inspector.setObjectName("ProjectMapInspector")
        self.inspector.setMinimumWidth(330)
        self.inspector.setMaximumWidth(460)
        il = QVBoxLayout(self.inspector)
        il.setContentsMargins(14, 12, 14, 12)
        il.setSpacing(9)

        head = QHBoxLayout()
        title_stack = QVBoxLayout()
        title_stack.setSpacing(1)
        self.path_title = QLabel("Select a file")
        self.path_title.setObjectName("ProjectMapPathTitle")
        self.path_title.setWordWrap(True)
        self.kind_label = QLabel("")
        self.kind_label.setObjectName("Muted")
        title_stack.addWidget(self.path_title)
        title_stack.addWidget(self.kind_label)
        head.addLayout(title_stack, 1)
        self.open_btn = QPushButton("Open in Editor")
        self.open_btn.setObjectName("Secondary")
        self.open_btn.clicked.connect(self.open_current_file)
        self.open_btn.setVisible(False)
        head.addWidget(self.open_btn)
        close_inspector = QToolButton()
        close_inspector.setObjectName("ProjectMapInspectorClose")
        close_inspector.setText("×")
        close_inspector.setToolTip("Close details")
        close_inspector.clicked.connect(lambda: self.set_inspector_visible(False))
        head.addWidget(close_inspector)
        il.addLayout(head)

        self.connection_summary = QLabel("")
        self.connection_summary.setObjectName("ProjectMapConnectionSummary")
        self.connection_summary.setWordWrap(True)
        il.addWidget(self.connection_summary)

        self.detail_tabs = QTabWidget()
        self.detail_tabs.setObjectName("ProjectMapDetailTabs")

        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        overview_layout.setContentsMargins(0, 10, 0, 0)
        desc_label = QLabel("Description")
        desc_label.setObjectName("FieldLabel")
        overview_layout.addWidget(desc_label)
        self.description = QTextEdit()
        self.description.setObjectName("ProjectMapDescription")
        self.description.setPlaceholderText("Describe what this part of the project is responsible for…")
        self.description.textChanged.connect(self.mark_dirty)
        overview_layout.addWidget(self.description, 1)
        self.status_label = QLabel("")
        self.status_label.setObjectName("HelpText")
        overview_layout.addWidget(self.status_label)
        self.detail_tabs.addTab(overview_tab, "Overview")

        relationships_tab = QWidget()
        relationship_layout = QVBoxLayout(relationships_tab)
        relationship_layout.setContentsMargins(0, 10, 0, 0)
        relation_actions = QHBoxLayout()
        relation_actions.addStretch(1)
        self.add_relation_btn = QPushButton("Add link")
        self.add_relation_btn.setObjectName("TextButton")
        self.add_relation_btn.clicked.connect(self.add_relationship)
        self.remove_relation_btn = QPushButton("Remove link")
        self.remove_relation_btn.setObjectName("TextButton")
        self.remove_relation_btn.clicked.connect(self.remove_relationship)
        relation_actions.addWidget(self.add_relation_btn)
        relation_actions.addWidget(self.remove_relation_btn)
        relationship_layout.addLayout(relation_actions)

        self.relationships = QTreeWidget()
        self.relationships.setObjectName("ProjectMapRelationships")
        self.relationships.setColumnCount(4)
        self.relationships.setHeaderLabels(["Direction", "Type", "File", "Source"])
        self.relationships.setRootIsDecorated(False)
        self.relationships.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.relationships.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.relationships.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.relationships.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.relationships.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.relationships.itemDoubleClicked.connect(self._relationship_double_clicked)
        relationship_layout.addWidget(self.relationships, 1)
        relation_hint = QLabel("Double-click a relationship to focus that file. Static links are read-only.")
        relation_hint.setObjectName("HelpText")
        relation_hint.setWordWrap(True)
        relationship_layout.addWidget(relation_hint)
        self.detail_tabs.addTab(relationships_tab, "Relationships")

        symbols_tab = QWidget()
        symbols_layout = QVBoxLayout(symbols_tab)
        symbols_layout.setContentsMargins(0, 10, 0, 0)
        symbol_actions = QHBoxLayout()
        symbol_actions.addStretch(1)
        add_symbol = QPushButton("Add symbol")
        add_symbol.setObjectName("TextButton")
        add_symbol.clicked.connect(self.add_symbol_row)
        remove_symbol = QPushButton("Remove")
        remove_symbol.setObjectName("TextButton")
        remove_symbol.clicked.connect(self.remove_selected_symbol)
        symbol_actions.addWidget(add_symbol)
        symbol_actions.addWidget(remove_symbol)
        symbols_layout.addLayout(symbol_actions)

        self.symbols = QTableWidget(0, 3)
        self.symbols.setObjectName("ProjectMapSymbols")
        self.symbols.setHorizontalHeaderLabels(["Type", "Name", "What it does"])
        self.symbols.verticalHeader().setVisible(False)
        self.symbols.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.symbols.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.symbols.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.symbols.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.symbols.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.symbols.itemChanged.connect(self.mark_dirty)
        symbols_layout.addWidget(self.symbols, 1)
        self.detail_tabs.addTab(symbols_tab, "Symbols")

        il.addWidget(self.detail_tabs, 1)
        content.addWidget(self.inspector)
        content.setSizes([1000, 380])
        content.setStretchFactor(0, 1)
        content.setStretchFactor(1, 0)
        self.content_splitter = content
        self.inspector.setVisible(False)
        root.addWidget(content, 1)

        self.back_shortcut = QShortcut(QKeySequence("Alt+Left"), self)
        self.back_shortcut.activated.connect(self.go_back)
        self.forward_shortcut = QShortcut(QKeySequence("Alt+Right"), self)
        self.forward_shortcut.activated.connect(self.go_forward)

        self._sync_navigation_controls()

    def _view_button(self, text: str, mode: str, callback) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("ProjectMapViewButton")
        button.setCheckable(True)
        button.setProperty("viewMode", mode)
        button.clicked.connect(callback)
        return button

    def set_model(self, model: ProjectModel) -> None:
        if self.model and self.model.root != model.root:
            self.save_if_dirty()
            if self._graph_initialized:
                self._save_layout_state()
        self.model = model
        # Load lightweight map JSON now, but do not construct a QGraphicsScene
        # while the user is merely opening a project. Large maps are initialized
        # lazily the first time Project Map is actually shown.
        self.data = load_project_map(model.root, model.state.name)
        layout_state = load_json(project_map_layout_path(model.root), {})
        self._pending_layout_state = layout_state if isinstance(layout_state, dict) else {}
        self._graph_initialized = False
        self.current_path = None
        self.current_directory = ""
        self.view_mode = "architecture"
        self._dirty = False
        self._history = [("architecture", "", None)]
        self._history_index = 0
        self.set_inspector_visible(False)
        self.update_coverage()
        self._sync_navigation_controls()

    def activate(self) -> None:
        """Initialize the expensive graphics scene only when the map is opened."""
        if not self.model or self._graph_initialized:
            return
        self.graph.set_layout_state(self._pending_layout_state, rebuild=False)
        self.graph.set_data(self.data)
        self.graph.set_show_support_files(self.support_toggle.isChecked())
        self._graph_initialized = True
        self._applying_history = True
        try:
            self._apply_navigation_state(self._navigation_state(), record=False)
        finally:
            self._applying_history = False
        QTimer.singleShot(0, self.graph._restore_camera_or_fit)
        self._sync_navigation_controls()

    def update_coverage(self) -> None:
        counts = coverage_summary(self.data)
        total = counts["total"]
        documented = counts["documented"]
        percent = int(round((documented / total) * 100)) if total else 100
        self.coverage.setText(f"{counts['files']} files · {percent}% documented")
        self.coverage.setToolTip(
            f"{counts['files']} files, {counts['directories']} folders; "
            f"{documented} documented, {counts['needs_review']} need review, {counts['missing']} missing descriptions"
        )

    def graph_search_changed(self, text: str) -> None:
        self.graph.set_query(text)

    def _toggle_support_files(self, checked: bool) -> None:
        self.graph.set_show_support_files(checked)

    def _schedule_layout_save(self) -> None:
        if self.model:
            self._layout_save_timer.start()

    def _save_layout_state(self) -> None:
        if not self.model or not self._graph_initialized:
            return
        save_json(project_map_layout_path(self.model.root), self.graph.export_layout_state())

    def _navigation_state(self) -> tuple[str, str, str | None]:
        return (self.view_mode, self.current_directory, self.current_path if self.view_mode == "file" else None)

    def _push_history(self, state: tuple[str, str, str | None]) -> None:
        if self._applying_history:
            return
        if self._history_index >= 0 and self._history[self._history_index] == state:
            return
        if self._history_index < len(self._history) - 1:
            self._history = self._history[: self._history_index + 1]
        self._history.append(state)
        self._history_index = len(self._history) - 1

    def _apply_navigation_state(
        self,
        state: tuple[str, str, str | None],
        *,
        record: bool = True,
    ) -> None:
        mode, directory, path = state
        self.commit_current()
        directory = directory.strip("/")

        if mode == "file":
            if not path or self.data.get("entries", {}).get(path, {}).get("kind") != "file":
                return
            self.view_mode = "file"
            self.current_path = path
            parent = str(Path(path).parent).replace("\\", "/")
            self.current_directory = "" if parent == "." else parent
            self.load_detail(path)
            self.set_inspector_visible(True)
            self.graph.set_view("file", directory=self.current_directory, file_path=path)
            state = ("file", self.current_directory, path)
        elif mode == "directory":
            self.view_mode = "directory"
            self.current_directory = directory
            directory_entry = self.data.get("entries", {}).get(directory) if directory else None
            self.current_path = directory if isinstance(directory_entry, dict) and directory_entry.get("kind") == "directory" else None
            self.set_inspector_visible(False)
            self.graph.set_view("directory", directory=directory)
            state = ("directory", directory, None)
        else:
            self.view_mode = "architecture"
            self.current_directory = ""
            self.current_path = None
            self.set_inspector_visible(False)
            self.graph.set_view("architecture")
            state = ("architecture", "", None)

        if record:
            self._push_history(state)
        self._sync_navigation_controls()

    def show_architecture(self) -> None:
        self._apply_navigation_state(("architecture", "", None))

    def show_directory(self, directory: str = "") -> None:
        self._apply_navigation_state(("directory", directory.strip("/"), None))

    def show_file(self, path: str) -> None:
        if not path or self.data.get("entries", {}).get(path, {}).get("kind") != "file":
            return
        parent = str(Path(path).parent).replace("\\", "/")
        directory = "" if parent == "." else parent
        self._apply_navigation_state(("file", directory, path))

    def go_back(self) -> None:
        # Back follows the map hierarchy first, regardless of how the current view
        # was reached: File -> containing Directory -> Architecture. Insert a
        # missing structural parent into history so Forward still returns to the
        # deeper view.
        structural_target: tuple[str, str, str | None] | None = None
        if self.view_mode == "file":
            structural_target = ("directory", self.current_directory, None)
        elif self.view_mode == "directory":
            structural_target = ("architecture", "", None)

        if structural_target is not None:
            if self._history_index > 0 and self._history[self._history_index - 1] == structural_target:
                self._history_index -= 1
            else:
                insert_at = max(0, self._history_index)
                self._history.insert(insert_at, structural_target)
                self._history_index = insert_at
            self._applying_history = True
            try:
                self._apply_navigation_state(structural_target, record=False)
            finally:
                self._applying_history = False
            self._sync_navigation_controls()
            return

        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._applying_history = True
        try:
            self._apply_navigation_state(self._history[self._history_index], record=False)
        finally:
            self._applying_history = False
        self._sync_navigation_controls()

    def go_forward(self) -> None:
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        self._applying_history = True
        try:
            self._apply_navigation_state(self._history[self._history_index], record=False)
        finally:
            self._applying_history = False
        self._sync_navigation_controls()

    def _sync_navigation_controls(self) -> None:
        project_name = str(self.data.get("project", {}).get("name", "")).strip() or "Project"
        self.project_crumb.setText(project_name)
        self.project_crumb.setToolTip("Project architecture")

        has_directory = self.view_mode in {"directory", "file"}
        self.dir_separator.setVisible(has_directory)
        self.directory_crumb.setVisible(has_directory)
        self.directory_crumb.setText(self.current_directory or "Root files")
        self.directory_crumb.setToolTip("Open package view")

        has_file = self.view_mode == "file" and bool(self.current_path)
        self.file_separator.setVisible(has_file)
        self.file_crumb.setVisible(has_file)
        self.file_crumb.setText(Path(self.current_path).name if self.current_path else "")
        self.file_crumb.setToolTip("Focused file neighborhood")

        self.architecture_btn.setChecked(self.view_mode == "architecture")
        self.directory_btn.setChecked(self.view_mode == "directory")
        self.file_btn.setChecked(self.view_mode == "file")
        self.directory_btn.setEnabled(has_directory or bool(self.current_directory))
        self.file_btn.setEnabled(bool(self.current_path and self.data.get("entries", {}).get(self.current_path, {}).get("kind") == "file"))
        self.details_btn.setEnabled(bool(self.current_path))
        self.back_btn.setEnabled(self._history_index > 0 or self.view_mode in {"directory", "file"})
        self.forward_btn.setEnabled(0 <= self._history_index < len(self._history) - 1)
    def toggle_inspector(self) -> None:
        if not self.current_path:
            return
        if not self.inspector.isVisible():
            self.load_detail(self.current_path)
        self.set_inspector_visible(not self.inspector.isVisible())

    def set_inspector_visible(self, visible: bool) -> None:
        self.inspector.setVisible(visible and bool(self.current_path))
        if self.inspector.isVisible():
            available = max(760, self.content_splitter.width())
            width = min(390, max(340, available // 3))
            self.content_splitter.setSizes([max(420, available - width), width])

    def mark_dirty(self, *_args) -> None:
        if not self._loading_detail:
            self._dirty = True
            self.status_label.setText("Unsaved map changes")

    def commit_current(self) -> None:
        if not self.current_path or self._loading_detail:
            return
        entry = self.data.get("entries", {}).get(self.current_path)
        if not isinstance(entry, dict):
            return
        description = self.description.toPlainText().strip()
        symbols = []
        if entry.get("kind") == "file":
            for row in range(self.symbols.rowCount()):
                kind_item = self.symbols.item(row, 0)
                name_item = self.symbols.item(row, 1)
                desc_item = self.symbols.item(row, 2)
                kind = kind_item.text().strip() if kind_item else ""
                name = name_item.text().strip() if name_item else ""
                symbol_description = desc_item.text().strip() if desc_item else ""
                if name or symbol_description:
                    symbols.append(
                        {
                            "kind": kind or "symbol",
                            "name": name,
                            "description": symbol_description,
                        }
                    )
        if entry.get("description", "") != description or entry.get("important_symbols", []) != symbols:
            entry["description"] = description
            entry["important_symbols"] = symbols
            self._dirty = True

    def load_detail(self, path: str) -> None:
        self._loading_detail = True
        entry = self.data.get("entries", {}).get(path, {})
        kind = entry.get("kind", "file")
        self.path_title.setText(path or "Project root")
        self.kind_label.setText("Directory" if kind == "directory" else "File")
        self.description.setPlainText(str(entry.get("description", "")))
        self.open_btn.setVisible(kind == "file" and bool(self.model and (self.model.root / path).is_file()))
        self.symbols.setRowCount(0)
        if kind == "file":
            for symbol in entry.get("important_symbols", []):
                self._append_symbol(
                    str(symbol.get("kind", "symbol")),
                    str(symbol.get("name", "")),
                    str(symbol.get("description", "")),
                )
        self.detail_tabs.setTabEnabled(1, kind == "file")
        self.detail_tabs.setTabEnabled(2, kind == "file")
        if kind != "file" and self.detail_tabs.currentIndex() in {1, 2}:
            self.detail_tabs.setCurrentIndex(0)
        self.add_relation_btn.setVisible(kind == "file")
        self.remove_relation_btn.setVisible(kind == "file")
        self._load_relationships(path)
        self.status_label.setText(STATUS_LABELS.get(entry_status(entry), ""))
        self._loading_detail = False

    def _append_symbol(self, kind: str = "function", name: str = "", description: str = "") -> None:
        row = self.symbols.rowCount()
        self.symbols.insertRow(row)
        self.symbols.setItem(row, 0, QTableWidgetItem(kind))
        self.symbols.setItem(row, 1, QTableWidgetItem(name))
        self.symbols.setItem(row, 2, QTableWidgetItem(description))

    def add_symbol_row(self) -> None:
        if not self.current_path:
            return
        self._append_symbol()
        self.mark_dirty()
        self.symbols.editItem(self.symbols.item(self.symbols.rowCount() - 1, 1))

    def remove_selected_symbol(self) -> None:
        row = self.symbols.currentRow()
        if row < 0:
            return
        self.symbols.removeRow(row)
        self.mark_dirty()

    def _load_relationships(self, path: str) -> None:
        self.relationships.clear()
        outgoing, incoming = relationship_index(self.data)
        for relation in incoming.get(path, []):
            item = QTreeWidgetItem(
                [
                    "Incoming",
                    str(relation.get("type", "depends_on")),
                    str(relation.get("source_path", "")),
                    str(relation.get("source", "")),
                ]
            )
            item.setToolTip(2, str(relation.get("description", "")))
            item.setData(0, ROLE_RELATION, {"direction": "in", **relation})
            self.relationships.addTopLevelItem(item)
        for relation in outgoing.get(path, []):
            item = QTreeWidgetItem(
                [
                    "Outgoing",
                    str(relation.get("type", "depends_on")),
                    str(relation.get("target", "")),
                    str(relation.get("source", "")),
                ]
            )
            item.setToolTip(2, str(relation.get("description", "")))
            item.setData(0, ROLE_RELATION, {"direction": "out", **relation})
            self.relationships.addTopLevelItem(item)

        incoming_count = len(incoming.get(path, []))
        outgoing_count = len(outgoing.get(path, []))
        static_count = sum(1 for rel in outgoing.get(path, []) if rel.get("source") == "static")
        authored_count = outgoing_count - static_count
        if self.data.get("entries", {}).get(path, {}).get("kind") == "file":
            self.connection_summary.setText(
                f"{incoming_count} incoming · {outgoing_count} outgoing · "
                f"{static_count} static · {authored_count} authored"
            )
        else:
            descendants = sum(1 for rel in self.data.get("entries", {}) if path and rel.startswith(path + "/"))
            self.connection_summary.setText(f"{descendants} indexed descendants")

    def add_relationship(self) -> None:
        if not self.current_path:
            return
        entry = self.data.get("entries", {}).get(self.current_path, {})
        if entry.get("kind") != "file":
            return
        targets = sorted(
            path
            for path, candidate in self.data.get("entries", {}).items()
            if candidate.get("kind") == "file" and path != self.current_path
        )
        if not targets:
            return
        target, ok = QInputDialog.getItem(self, "Add Project Map link", "Target file:", targets, 0, False)
        if not ok or not target:
            return
        types = sorted(RELATIONSHIP_TYPES)
        default_index = types.index("uses") if "uses" in types else 0
        relation_type, ok = QInputDialog.getItem(self, "Relationship type", "Type:", types, default_index, False)
        if not ok or not relation_type:
            return
        note, ok = QInputDialog.getText(self, "Relationship note", "What connects these files?")
        if not ok:
            return
        entry.setdefault("relationships", []).append(
            {
                "target": target,
                "type": relation_type,
                "source": "user",
                "description": note.strip(),
            }
        )
        self._dirty = True
        self.graph.set_data(self.data)
        self.load_detail(self.current_path)
        self.status_label.setText("Unsaved map changes")

    def remove_relationship(self) -> None:
        item = self.relationships.currentItem()
        if not item or not self.current_path:
            return
        relation = item.data(0, ROLE_RELATION) or {}
        if relation.get("direction") != "out" or relation.get("source") == "static":
            self.status_label.setText("Static and incoming links are read-only")
            return
        entry = self.data.get("entries", {}).get(self.current_path, {})
        relationships = entry.get("relationships", [])
        for index, candidate in enumerate(relationships):
            if (
                candidate.get("target") == relation.get("target")
                and candidate.get("type") == relation.get("type")
                and candidate.get("source") == relation.get("source")
                and candidate.get("description", "") == relation.get("description", "")
            ):
                relationships.pop(index)
                self._dirty = True
                break
        self.graph.set_data(self.data)
        self.load_detail(self.current_path)
        self.status_label.setText("Unsaved map changes")

    def _relationship_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        relation = item.data(0, ROLE_RELATION) or {}
        target = relation.get("target") if relation.get("direction") == "out" else relation.get("source_path")
        if target in self.data.get("entries", {}):
            self.show_file(str(target))

    def save(self) -> None:
        if not self.model:
            return
        self.commit_current()
        state = self._navigation_state()
        save_project_map(self.model.root, self.data)
        self._dirty = False
        self.data = load_project_map(self.model.root, self.model.state.name)
        self.graph.set_data(self.data)
        self.update_coverage()
        self._applying_history = True
        try:
            self._apply_navigation_state(state, record=False)
        finally:
            self._applying_history = False
        if self.current_path:
            self.status_label.setText("Project map saved")
        self._sync_navigation_controls()
        self.map_saved.emit()

    def save_if_dirty(self) -> None:
        if self._dirty:
            self.save()
        if self._layout_save_timer.isActive():
            self._layout_save_timer.stop()
            self._save_layout_state()

    def refresh_index(self) -> None:
        if not self.model:
            return
        self.save_if_dirty()
        state = self._navigation_state()
        sync_project_map_managed(self.model)
        self.data = load_project_map(self.model.root, self.model.state.name)
        mode, directory, path = state
        if path and self.data.get("entries", {}).get(path, {}).get("kind") != "file":
            state = ("directory", directory, None) if directory else ("architecture", "", None)
        if not self._graph_initialized:
            self.activate()
        else:
            self.graph.set_data(self.data)
        self.update_coverage()
        self._applying_history = True
        try:
            self._apply_navigation_state(state, record=False)
        finally:
            self._applying_history = False
        if self.inspector.isVisible() and self.current_path:
            self.load_detail(self.current_path)
            self.status_label.setText("Project map refreshed")
        # Managed refresh can advance PROJECT_MAP.json in the sync baseline.
        # Refresh the project tree/status immediately so a stale "changed" badge
        # does not linger after TransferLoop accepted its own generated rewrite.
        self.map_saved.emit()

    def refresh_from_disk(self) -> None:
        """Reload the existing map file without regenerating static relationships."""
        if not self.model:
            return
        self.save_if_dirty()
        state = self._navigation_state()
        self.data = load_project_map(self.model.root, self.model.state.name)
        self.update_coverage()
        if not self._graph_initialized:
            return
        self.graph.set_data(self.data)
        mode, directory, path = state
        if path and self.data.get("entries", {}).get(path, {}).get("kind") != "file":
            state = ("directory", directory, None) if directory else ("architecture", "", None)
        self._applying_history = True
        try:
            self._apply_navigation_state(state, record=False)
        finally:
            self._applying_history = False
        self._sync_navigation_controls()

    def open_current_file(self) -> None:
        if self.current_path and self.data.get("entries", {}).get(self.current_path, {}).get("kind") == "file":
            self.save_if_dirty()
            self.file_requested.emit(self.current_path)

    def _request_file(self, path: str) -> None:
        self.save_if_dirty()
        self.file_requested.emit(path)
