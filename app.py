from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.icons import app_icon
from ui.styles import APP_STYLE
from core.version import APP_VERSION
from core.logging_utils import configure_logging
from core.storage import ensure_app_data_migrated


def _set_windows_app_identity() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TransferLoop.Desktop")
    except Exception:
        # AppUserModelID improves taskbar grouping, but must never block startup.
        pass


def main() -> int:
    # Legacy profile migration is intentionally a one-time startup task. Keep
    # it out of storage path helpers so routine saves, project opens, imports,
    # and Project Map camera updates never recurse through old project history.
    ensure_app_data_migrated()
    configure_logging()
    _set_windows_app_identity()
    app = QApplication(sys.argv)
    app.setApplicationName("TransferLoop")
    app.setApplicationDisplayName("TransferLoop")
    app.setOrganizationName("TransferLoop")
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(app_icon())
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
