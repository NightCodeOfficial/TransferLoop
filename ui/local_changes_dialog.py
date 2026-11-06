from __future__ import annotations

import html
from collections import Counter

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from core.project import LocalChange, ProjectModel

ROLE_PATH = Qt.UserRole
ROLE_KIND = Qt.UserRole + 1

_CHANGE_PRESENTATION = {
    "modified": ("Modified", "#c4b5ff", "File contents differ from the last AI sync baseline."),
    "added": ("Added", "#79dda0", "This file was added locally after the last AI sync."),
    "deleted": ("Deleted", "#ff9292", "This file existed at the last AI sync but has been removed locally."),
    "context": (
        "Refresh context",
        "#f1c978",
        "This path was deliberately left divergent and should be exported again to refresh AI context.",
    ),
}


class LocalChangesDialog(QDialog):
    """Focused review of local paths that are newer than the current AI context."""

    file_requested = Signal(str)
    export_requested = Signal()

    def __init__(self, model: ProjectModel, changes: list[LocalChange], parent=None):
        super().__init__(parent)
        self.model = model
        self.changes = changes
        self.changes_by_path = {change.path: change for change in changes}
        self.setWindowTitle("Local changes")
        self.setObjectName("LocalChangesDialog")
        self.resize(980, 610)
        self.setMinimumSize(760, 480)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        title = QLabel(self._headline())
        title.setObjectName("LocalChangesTitle")
        root.addWidget(title)

        explanation = QLabel(
            "These files are newer than the project state currently supplied to the AI. "
            "Select a file to see the exact local diff against TransferLoop's sync snapshot."
        )
        explanation.setObjectName("HelpText")
        explanation.setWordWrap(True)
        root.addWidget(explanation)

        summary_row = QHBoxLayout()
        summary_row.setContentsMargins(0, 0, 0, 0)
        summary_row.setSpacing(8)
        counts = Counter(change.kind for change in changes)
        for kind in ("modified", "added", "deleted", "context"):
            count = counts.get(kind, 0)
            if not count:
                continue
            label, color, _ = _CHANGE_PRESENTATION[kind]
            badge = QLabel(f"{label}  {count}")
            badge.setObjectName("LocalChangeSummaryBadge")
            badge.setStyleSheet(f"color: {color};")
            summary_row.addWidget(badge)
        summary_row.addStretch(1)
        root.addLayout(summary_row)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("LocalChangesSplitter")

        list_frame = QFrame()
        list_frame.setObjectName("LocalChangesListFrame")
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)

        self.tree = QTreeWidget()
        self.tree.setObjectName("LocalChangesTree")
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Change", "File"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.itemActivated.connect(self._activate_item)
        list_layout.addWidget(self.tree)
        splitter.addWidget(list_frame)

        detail_frame = QFrame()
        detail_frame.setObjectName("LocalChangeDetailFrame")
        detail_layout = QVBoxLayout(detail_frame)
        detail_layout.setContentsMargins(14, 12, 14, 14)
        detail_layout.setSpacing(8)

        self.detail_title = QLabel("Select a changed file")
        self.detail_title.setObjectName("LocalChangeDetailTitle")
        self.detail_title.setWordWrap(True)
        detail_layout.addWidget(self.detail_title)

        self.detail_meta = QLabel("")
        self.detail_meta.setObjectName("HelpText")
        self.detail_meta.setWordWrap(True)
        detail_layout.addWidget(self.detail_meta)

        self.diff_view = QTextBrowser()
        self.diff_view.setObjectName("LocalChangeDiff")
        self.diff_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.diff_view.setOpenExternalLinks(False)
        detail_layout.addWidget(self.diff_view, 1)
        splitter.addWidget(detail_frame)

        splitter.setSizes([390, 570])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self._populate()

        hint = QLabel(
            "Double-click a current file to open it in TransferLoop. Deleted files remain visible here so the removal is reviewable."
        )
        hint.setObjectName("HelpText")
        hint.setWordWrap(True)
        root.addWidget(hint)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(9)

        self.open_btn = QPushButton("Open Selected")
        self.open_btn.setObjectName("Secondary")
        self.open_btn.clicked.connect(self._open_selected)
        self.open_btn.setEnabled(False)
        actions.addWidget(self.open_btn)

        actions.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        actions.addWidget(close_btn)

        export_btn = QPushButton(f"Export Changed ({len(changes)})")
        export_btn.setObjectName("Primary")
        export_btn.setToolTip("Create an incremental export containing these local changes")
        export_btn.clicked.connect(self._request_export)
        actions.addWidget(export_btn)
        root.addLayout(actions)

        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _headline(self) -> str:
        count = len(self.changes)
        noun = "change" if count == 1 else "changes"
        return f"{count} local {noun} since the last AI sync"

    def _populate(self) -> None:
        for change in self.changes:
            label, color, tooltip = _CHANGE_PRESENTATION.get(
                change.kind,
                (change.kind.capitalize(), "#dfe3ed", "Local state differs from the AI sync baseline."),
            )
            item = QTreeWidgetItem([label, change.path])
            item.setData(0, ROLE_PATH, change.path)
            item.setData(0, ROLE_KIND, change.kind)
            item.setForeground(0, QColor(color))
            item.setToolTip(0, tooltip)
            item.setToolTip(1, tooltip)
            self.tree.addTopLevelItem(item)

    def _selected(self) -> tuple[str, str] | None:
        item = self.tree.currentItem()
        if not item:
            return None
        path = str(item.data(0, ROLE_PATH) or "")
        kind = str(item.data(0, ROLE_KIND) or "")
        return (path, kind) if path else None

    def _selection_changed(self) -> None:
        selected = self._selected()
        if not selected:
            self.open_btn.setEnabled(False)
            self.detail_title.setText("Select a changed file")
            self.detail_meta.clear()
            self.diff_view.clear()
            return

        rel, kind = selected
        change = self.changes_by_path.get(rel)
        if not change:
            return
        label, color, tooltip = _CHANGE_PRESENTATION.get(
            kind,
            (kind.capitalize(), "#dfe3ed", "Local state differs from the AI sync baseline."),
        )
        self.detail_title.setText(rel)
        self.detail_meta.setText(f"{label} · {tooltip}")
        self.detail_meta.setStyleSheet(f"color: {color};")
        self.diff_view.setHtml(self._diff_html(self.model.local_change_diff(change).text))
        can_open = kind != "deleted" and (self.model.root / rel).is_file()
        self.open_btn.setEnabled(can_open)

    @staticmethod
    def _diff_html(diff_text: str) -> str:
        rows: list[str] = []
        for line in diff_text.splitlines() or [""]:
            escaped = html.escape(line)
            style = "color:#cfd4df;"
            if line.startswith("@@"):
                style = "color:#b9afff;background:#211d35;"
            elif line.startswith("+++") or line.startswith("---"):
                style = "color:#aeb5c5;background:#171b24;font-weight:600;"
            elif line.startswith("+"):
                style = "color:#8fe2ad;background:#13241b;"
            elif line.startswith("-"):
                style = "color:#ffaaaa;background:#291719;"
            rows.append(f'<span style="display:block;{style}">{escaped or "&nbsp;"}</span>')
        return (
            '<html><body style="margin:0;background:#0f1218;">'
            '<pre style="margin:0;padding:10px;font-family:Consolas,monospace;font-size:9.5pt;line-height:1.35;">'
            + "".join(rows)
            + "</pre></body></html>"
        )

    def _activate_item(self, _item: QTreeWidgetItem, _column: int) -> None:
        if self.open_btn.isEnabled():
            self._open_selected()

    def _open_selected(self) -> None:
        selected = self._selected()
        if not selected:
            return
        rel, kind = selected
        if kind == "deleted" or not (self.model.root / rel).is_file():
            return
        self.accept()
        self.file_requested.emit(rel)

    def _request_export(self) -> None:
        self.accept()
        self.export_requested.emit()
