APP_STYLE = r"""
* {
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: 10.5pt;
}
QMainWindow, QWidget {
    background: #0d0f15;
    color: #e8ebf2;
}
QLabel {
    background: transparent;
    border: 0;
}
QFrame#Panel {
    background: #161922;
    border: 1px solid #262b38;
    border-radius: 15px;
}
QFrame#SidebarPanel {
    background: #12151c;
    border: 1px solid #232836;
    border-radius: 15px;
}
QFrame#WorkspaceCard {
    background: #171a24;
    border: 1px solid #282d3b;
    border-radius: 15px;
}
QFrame#Card, QFrame#SoftCard {
    background: #141720;
    border: 1px solid #242836;
    border-radius: 12px;
}
QFrame#InlineCard {
    background: #13161e;
    border: 1px solid #252a37;
    border-radius: 10px;
}
QFrame#StatusBar {
    background: transparent;
    border: 0;
}
QFrame#BottomStatusBar {
    background: transparent;
    border: 0;
    border-top: 1px solid #202532;
}
QLabel#Title {
    font-size: 23pt;
    font-weight: 700;
    color: #f7f7fb;
}
QLabel#SectionTitle {
    font-size: 11pt;
    font-weight: 700;
    color: #f4f5fa;
}
QLabel#FieldLabel {
    color: #c9cedb;
    font-size: 9.5pt;
    font-weight: 600;
}
QLabel#Muted, QLabel#StatusMuted, QLabel#HelpText {
    color: #9299aa;
}
QLabel#HelpText {
    font-size: 9.2pt;
}
QLabel#PathValue {
    color: #c7ccda;
    background: #13161e;
    border: 1px solid #252b39;
    border-radius: 9px;
    padding: 8px 10px;
    min-height: 20px;
}
QLabel#SessionValue {
    color: #b8b1ff;
    background: rgba(111, 93, 247, 0.08);
    border: 1px solid rgba(126, 109, 255, 0.20);
    border-radius: 8px;
    padding: 5px 9px;
    min-height: 18px;
    font-size: 9.2pt;
    font-weight: 650;
}
QLabel#LatestExportName {
    color: #dfe3ed;
    font-weight: 600;
    min-height: 18px;
}
QLabel#Good, QPushButton#Good {
    color: #79dda0;
    background: rgba(62, 171, 104, 0.12);
    border: 1px solid rgba(90, 207, 134, 0.32);
    border-radius: 10px;
    padding: 6px 10px;
    min-height: 18px;
    font-weight: 650;
}
QPushButton#Good:hover, QPushButton#Good:pressed {
    color: #79dda0;
    background: rgba(62, 171, 104, 0.12);
    border-color: rgba(90, 207, 134, 0.32);
}
QLabel#Warn, QPushButton#Warn {
    color: #f1c978;
    background: rgba(205, 153, 56, 0.10);
    border: 1px solid rgba(229, 180, 76, 0.30);
    border-radius: 10px;
    padding: 6px 10px;
    min-height: 18px;
    font-weight: 650;
}
QPushButton#Warn:hover {
    color: #ffe0a0;
    background: rgba(205, 153, 56, 0.17);
    border-color: rgba(241, 196, 98, 0.58);
}
QPushButton#Warn:pressed {
    background: rgba(205, 153, 56, 0.22);
}
QLabel#AcceptedState {
    color: #79dda0;
    font-weight: 700;
}
QLabel#NeedsContextState {
    color: #ff9292;
    font-weight: 700;
}
QLabel#WorkflowBadgeActive {
    color: #d9d4ff;
    background: rgba(111, 93, 247, 0.10);
    border: 1px solid rgba(126, 109, 255, 0.26);
    border-radius: 10px;
    padding: 4px 10px;
    min-height: 16px;
    font-size: 9.0pt;
    font-weight: 650;
}
QLabel#WorkflowBadgeInactive {
    color: #9aa2b5;
    background: #141821;
    border: 1px solid #2b3040;
    border-radius: 10px;
    padding: 4px 10px;
    min-height: 16px;
    font-size: 9.0pt;
    font-weight: 600;
}
QLabel#Watching {
    color: #a9a1ff;
    font-weight: 650;
}
QPushButton {
    background: #202431;
    border: 1px solid #313747;
    border-radius: 9px;
    padding: 8px 13px;
    min-height: 18px;
    color: #eef0f6;
}
QPushButton:hover {
    background: #292e3d;
    border-color: #474f64;
}
QPushButton:pressed {
    background: #1c202b;
}
QPushButton:disabled {
    color: #5e6472;
    background: #12151c;
    border-color: #202532;
}
QPushButton#Secondary:disabled {
    color: #5e6472;
    background: transparent;
    border-color: #272c39;
}
QPushButton#Primary {
    background: #6f5df7;
    border-color: #7e6dff;
    color: white;
    font-weight: 650;
}
QPushButton#Primary:hover {
    background: #7d6cff;
    border-color: #9488ff;
}
QPushButton#ApplyPrimary {
    background: #6f5df7;
    border-color: #7e6dff;
    color: white;
    font-weight: 650;
}
QPushButton#ApplyPrimary:hover {
    background: #7d6cff;
    border-color: #9488ff;
}
QPushButton#ApplyPrimary:disabled {
    color: #646a78;
    background: #171a22;
    border-color: #292e3b;
}
QPushButton#Secondary {
    background: transparent;
    border: 1px solid #4d466c;
    color: #d8d4ff;
    font-weight: 600;
}
QPushButton#Secondary:hover {
    background: rgba(111, 93, 247, 0.10);
    border-color: #7f72ff;
    color: #f0edff;
}
QPushButton#TextButton {
    background: transparent;
    border: 0;
    color: #aaa2ff;
    padding: 5px 7px;
}
QPushButton#TextButton:hover {
    background: rgba(111, 93, 247, 0.08);
    color: #d8d3ff;
}
QPushButton#Danger {
    color: #ff9c9c;
}
QToolButton {
    background: transparent;
    border: 0;
    border-radius: 8px;
    padding: 7px;
    color: #cdd2df;
}
QToolButton:hover {
    background: #222633;
}
QToolButton#IconButton, QToolButton#WireIconButton {
    min-width: 30px;
    min-height: 30px;
    max-width: 30px;
    max-height: 30px;
    padding: 1px;
    background: transparent;
    border: 1px solid #4d466c;
    border-radius: 8px;
}
QToolButton#IconButton:hover, QToolButton#WireIconButton:hover {
    background: rgba(111, 93, 247, 0.12);
    border-color: #8276ff;
}
QToolButton#IconButton:pressed, QToolButton#WireIconButton:pressed {
    background: rgba(111, 93, 247, 0.18);
}
QToolButton#IconButton:disabled, QToolButton#WireIconButton:disabled {
    border-color: #292e3b;
    background: transparent;
}
QToolButton#DangerIconButton {
    min-width: 32px;
    min-height: 32px;
    max-width: 32px;
    max-height: 32px;
    padding: 0;
    background: #151821;
    border: 1px solid #3b3038;
    border-radius: 9px;
}
QToolButton#DangerIconButton:hover {
    background: rgba(255, 92, 102, 0.09);
    border-color: #8d4850;
}
QToolButton#DangerIconButton:pressed {
    background: rgba(255, 92, 102, 0.16);
    border-color: #b2525c;
}
QToolButton#TreeMenuButton {
    min-width: 32px;
    min-height: 32px;
    max-width: 32px;
    max-height: 32px;
    padding: 0;
    color: #aaa3ff;
    font-size: 15pt;
    font-weight: 700;
    background: #151821;
    border: 1px solid #2b3040;
    border-radius: 9px;
}
QToolButton#TreeMenuButton:hover {
    color: #e1ddff;
    background: rgba(111, 93, 247, 0.10);
    border-color: #5f56a0;
}
QTreeWidget, QListWidget, QTextEdit, QTextBrowser, QLineEdit, QPlainTextEdit {
    background: #11141b;
    border: 1px solid #242a37;
    border-radius: 10px;
    color: #e8ebf2;
    selection-background-color: #3a315d;
    selection-color: #ffffff;
    outline: 0;
}
QLineEdit {
    padding: 8px 10px;
}
QLineEdit#TreeSearch {
    min-height: 16px;
    background: #151821;
    border: 1px solid #292e3c;
    color: #dfe3ed;
    padding: 7px 10px;
}
QLineEdit#TreeSearch:focus {
    border-color: #6257a8;
    background: #171a23;
}
QTreeWidget::item, QListWidget::item {
    padding: 6px 5px;
    border-radius: 6px;
}
QTreeWidget::item:hover, QListWidget::item:hover {
    background: rgba(111, 93, 247, 0.08);
}
QTreeWidget::item:selected, QListWidget::item:selected {
    background: #352e57;
    color: #ffffff;
}
QListWidget#RecentProjectList {
    background: transparent;
    border: 0;
    border-radius: 0;
}
QListWidget#RecentProjectList::item {
    padding: 0;
    margin: 0;
    background: transparent;
    border: 0;
}
QListWidget#RecentProjectList::item:hover {
    background: transparent;
}
QFrame#RecentProjectCard {
    background: #171a23;
    border: 1px solid #292e3b;
    border-radius: 14px;
}
QFrame#RecentProjectCard:hover {
    background: #1b1e29;
    border-color: #514a73;
}
QLabel#RecentProjectName {
    color: #f5f6fb;
    font-size: 12pt;
    font-weight: 680;
}
QLabel#RecentProjectPath {
    color: #9097a8;
    font-size: 9.5pt;
}
QHeaderView::section {
    background: #171a23;
    color: #9aa2b5;
    border: none;
    padding: 6px;
}
/* VS Code-like scrollbars: low-profile track with a readable thumb. */
QScrollBar:vertical {
    background: #0f1219;
    width: 14px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: rgba(121, 121, 121, 145);
    min-height: 32px;
    border: 3px solid #0f1219;
    border-radius: 6px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(150, 150, 150, 190);
}
QScrollBar::handle:vertical:pressed {
    background: rgba(180, 180, 180, 220);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    background: transparent;
    height: 0;
    border: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: #0f1219;
    height: 14px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: rgba(121, 121, 121, 145);
    min-width: 32px;
    border: 3px solid #0f1219;
    border-radius: 6px;
}
QScrollBar::handle:horizontal:hover {
    background: rgba(150, 150, 150, 190);
}
QScrollBar::handle:horizontal:pressed {
    background: rgba(180, 180, 180, 220);
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    background: transparent;
    width: 0;
    border: 0;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}
QAbstractScrollArea::corner {
    background: #0f1219;
}
QSplitter::handle {
    background: transparent;
    width: 10px;
}
QSplitter::handle:hover {
    background: rgba(111, 93, 247, 0.06);
}
QCheckBox {
    spacing: 8px;
    background: transparent;
}
QDialog {
    background: #11141b;
}
QDialog#LocalChangesDialog {
    background: #11141b;
}
QLabel#LocalChangesTitle {
    color: #f6f7fb;
    font-size: 15pt;
    font-weight: 700;
}
QLabel#LocalChangeSummaryBadge {
    background: #171a23;
    border: 1px solid #2d3240;
    border-radius: 9px;
    padding: 5px 9px;
    min-height: 17px;
    font-size: 9.2pt;
    font-weight: 650;
}
QFrame#LocalChangesListFrame {
    background: #10131a;
    border: 1px solid #292e3b;
    border-radius: 11px;
}
QTreeWidget#LocalChangesTree {
    background: transparent;
    border: 0;
    border-radius: 11px;
}
QTreeWidget#LocalChangesTree::item {
    padding: 8px 7px;
}
QFrame#LocalChangeDetailFrame {
    background: #10131a;
    border: 1px solid #292e3b;
    border-radius: 11px;
}
QLabel#LocalChangeDetailTitle {
    color: #eef0f6;
    font-size: 10.5pt;
    font-weight: 700;
}
QTextBrowser#LocalChangeDiff {
    background: #0f1218;
    border: 1px solid #232936;
    border-radius: 8px;
    padding: 0;
}
QTabWidget::pane {
    border: 1px solid #272c39;
    border-radius: 10px;
    top: -1px;
    background: #151821;
}
QTabBar::tab {
    background: transparent;
    color: #969dae;
    padding: 9px 14px;
}
QTabBar::tab:selected {
    color: white;
    border-bottom: 2px solid #7566ff;
}
QMenuBar {
    background: #0d0f15;
    color: #cfd4df;
    border-bottom: 1px solid #1d212c;
    padding: 2px 8px;
}
QMenuBar::item {
    background: transparent;
    border-radius: 6px;
    padding: 5px 9px;
}
QMenuBar::item:selected {
    background: #202431;
    color: #ffffff;
}
QMenu {
    background: #171a23;
    color: #e8ebf2;
    border: 1px solid #303647;
    border-radius: 9px;
    padding: 5px;
}
QMenu::item {
    padding: 7px 28px 7px 10px;
    border-radius: 6px;
}
QMenu::item:selected {
    background: #292e3d;
}
QMenu::separator {
    height: 1px;
    background: #303647;
    margin: 5px 7px;
}
QMessageBox {
    background: #151821;
}
"""

# Extended editor/artifact styling is appended to the main stylesheet below.
APP_STYLE += r"""
QLabel#ArtifactKind {
    color: #9389ff;
    font-size: 8.8pt;
    font-weight: 700;
    letter-spacing: 0.3px;
    min-height: 16px;
}
QLabel#EditorTitle {
    color: #f6f7fb;
    font-size: 17pt;
    font-weight: 700;
}
QPlainTextEdit#MarkdownEditor {
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 10pt;
    background: #10131a;
    border: 1px solid #282e3c;
    border-radius: 11px;
    padding: 10px;
    selection-background-color: #433873;
}
QTextBrowser#MarkdownPreview {
    background: #151821;
    border: 1px solid #282e3c;
    border-radius: 11px;
    padding: 12px;
}

QFrame#EditorSyncSidebar {
    background: #10131a;
    border: 1px solid #242938;
    border-radius: 12px;
}
QScrollArea#EditorSidebarScroll, QScrollArea#EditorSidebarScroll > QWidget > QWidget {
    background: transparent;
    border: 0;
}
QFrame#EditorToolbar {
    background: #11141b;
    border: 0;
    border-bottom: 1px solid #252a37;
}
QLabel#EditorPath {
    color: #8f97aa;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 9.5pt;
}
QTabWidget#EditorTabs::pane {
    border: 0;
    border-radius: 0;
    background: #0f1219;
}
QTabWidget#EditorTabs QTabBar::tab {
    background: #141821;
    color: #9ba3b6;
    border-right: 1px solid #252a37;
    border-bottom: 1px solid #252a37;
    padding: 8px 13px;
    min-width: 110px;
}
QTabWidget#EditorTabs QTabBar::tab:selected {
    background: #11151d;
    color: #f3f4f8;
    border-bottom: 2px solid #7566ff;
}
QPlainTextEdit#CodeEditor {
    background: #0f1219;
    color: #dfe3ed;
    border: 0;
    border-radius: 0;
    selection-background-color: #3b3261;
}
QFrame#EditorFindBar {
    background: #151923;
    border: 0;
    border-top: 1px solid #272d3b;
}
QPushButton#EditorMiniButton {
    min-width: 28px;
    padding: 5px 8px;
    background: transparent;
    border: 1px solid #343a4b;
    color: #d6daE5;
}
QPushButton#EditorMiniButton:hover {
    background: rgba(111, 93, 247, 0.10);
    border-color: #6960a9;
}
QFrame#EditorStatusBar {
    background: #11141b;
    border: 0;
    border-top: 1px solid #252a37;
}
QLabel#EditorStatusValue {
    color: #a6adbd;
    font-size: 9pt;
}
"""

APP_STYLE += r"""
QToolButton#EditorModeButton {
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
    padding: 0;
    margin: 0;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
}
QToolButton#EditorModeButton:hover {
    background: #1b1f29;
    border-color: #303647;
}
QToolButton#EditorModeButton:pressed {
    background: #242938;
}
QStackedWidget#MarkdownDocumentStack {
    background: #0f1219;
    border: 0;
}
QTextBrowser#MarkdownReadView {
    background: #0f1219;
    color: #dfe3ed;
    border: 0;
    border-radius: 0;
    padding: 0;
    selection-background-color: #3b3261;
}
"""

APP_STYLE += r"""
QFrame#ProjectMapToolbar {
    background: #11141b;
    border: 0;
    border-bottom: 1px solid #252a37;
}
QLabel#ProjectMapWorkspaceTitle {
    color: #f3f4f8;
    font-size: 10.5pt;
    font-weight: 700;
}
QLabel#ProjectMapCoverage {
    color: #c9c4ff;
    background: rgba(111, 93, 247, 0.09);
    border: 1px solid rgba(126, 109, 255, 0.23);
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 8.8pt;
    font-weight: 650;
}
QLineEdit#ProjectMapSearch {
    min-height: 15px;
    padding: 6px 9px;
    background: #151821;
    border: 1px solid #292e3c;
}
QLineEdit#ProjectMapSearch:focus {
    border-color: #6257a8;
}
QCheckBox#ProjectMapSupportToggle {
    color: #9ca4b6;
    spacing: 6px;
}
QToolButton#ProjectMapBreadcrumb {
    color: #aeb5c5;
    background: transparent;
    border: 0;
    border-radius: 6px;
    padding: 4px 6px;
    font-weight: 650;
}
QToolButton#ProjectMapBreadcrumb:hover {
    color: #f0f2f7;
    background: #191d27;
}
QLabel#ProjectMapBreadcrumbSeparator {
    color: #555d70;
    padding: 0 1px;
}
QPushButton#ProjectMapViewButton {
    min-height: 24px;
    padding: 3px 9px;
    color: #9da5b6;
    background: transparent;
    border: 1px solid #2b3140;
    border-radius: 7px;
}
QPushButton#ProjectMapViewButton:hover {
    color: #e5e7ee;
    background: #181c26;
}
QPushButton#ProjectMapViewButton:checked {
    color: #dedaff;
    background: rgba(111, 93, 247, 0.14);
    border-color: #554b91;
}
QPushButton#ProjectMapViewButton:disabled {
    color: #555d70;
    border-color: #232834;
}
QToolButton#ProjectMapCanvasButton {
    min-height: 24px;
    padding: 3px 8px;
    color: #9da5b6;
    background: transparent;
    border: 1px solid #2b3140;
    border-radius: 7px;
}
QToolButton#ProjectMapCanvasButton:hover {
    color: #f0f2f7;
    background: #181c26;
    border-color: #41495d;
}
QLabel#ProjectMapZoomLabel {
    color: #747d90;
    font-size: 8pt;
    padding: 0 2px;
}
QGraphicsView#ProjectMapGraph {
    background: #0f1219;
    border: 0;
}
QFrame#ProjectMapInspector {
    background: #12151c;
    border: 0;
    border-left: 1px solid #252a37;
}
QToolButton#ProjectMapInspectorClose {
    min-width: 27px;
    max-width: 27px;
    min-height: 27px;
    max-height: 27px;
    padding: 0;
    color: #8991a3;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    font-size: 13pt;
}
QToolButton#ProjectMapInspectorClose:hover {
    color: #f1f3f8;
    background: #1b1f29;
    border-color: #303647;
}
QLabel#ProjectMapPathTitle {
    color: #f4f5fa;
    font-size: 11.5pt;
    font-weight: 700;
}
QLabel#ProjectMapConnectionSummary {
    color: #9ca4b6;
    background: #151923;
    border: 1px solid #292f3d;
    border-radius: 8px;
    padding: 7px 9px;
    font-size: 8.8pt;
}
QTabWidget#ProjectMapDetailTabs::pane {
    border: 0;
    background: transparent;
}
QTabWidget#ProjectMapDetailTabs QTabBar::tab {
    color: #8f97aa;
    background: transparent;
    border: 0;
    border-bottom: 2px solid transparent;
    padding: 7px 9px;
}
QTabWidget#ProjectMapDetailTabs QTabBar::tab:selected {
    color: #e9e7ff;
    border-bottom-color: #7467d6;
}
QTextEdit#ProjectMapDescription {
    background: #0f1219;
    border: 1px solid #282e3c;
    border-radius: 9px;
    padding: 8px;
}
QTableWidget#ProjectMapSymbols,
QTreeWidget#ProjectMapRelationships {
    background: #0f1219;
    border: 1px solid #282e3c;
    border-radius: 9px;
    gridline-color: #252b38;
    selection-background-color: #352e57;
}
QTableWidget#ProjectMapSymbols::item,
QTreeWidget#ProjectMapRelationships::item {
    padding: 5px;
}
"""
