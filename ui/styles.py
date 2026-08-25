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
}
QLabel#SessionValue {
    color: #b8b1ff;
    background: rgba(111, 93, 247, 0.08);
    border: 1px solid rgba(126, 109, 255, 0.20);
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 9.2pt;
    font-weight: 650;
}
QLabel#LatestExportName {
    color: #dfe3ed;
    font-weight: 600;
}
QLabel#Good {
    color: #79dda0;
    background: rgba(62, 171, 104, 0.12);
    border: 1px solid rgba(90, 207, 134, 0.32);
    border-radius: 10px;
    padding: 5px 9px;
    font-weight: 650;
}
QLabel#Warn {
    color: #f1c978;
    background: rgba(205, 153, 56, 0.10);
    border: 1px solid rgba(229, 180, 76, 0.30);
    border-radius: 10px;
    padding: 5px 9px;
    font-weight: 650;
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
QPushButton#Secondary {
    background: transparent;
    border: 1px solid #4d466c;
    color: #d8d4ff;
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
