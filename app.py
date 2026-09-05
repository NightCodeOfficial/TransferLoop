from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.styles import APP_STYLE
from core.version import APP_VERSION


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("TransferLoop")
    app.setApplicationVersion(APP_VERSION)
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
