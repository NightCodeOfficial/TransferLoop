from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .storage import logs_dir

LOG_FILENAME = "transferloop.log"


def configure_logging() -> Path:
    """Configure a small rotating application log and capture uncaught exceptions."""
    path = logs_dir() / LOG_FILENAME
    root = logging.getLogger()
    if not any(isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", "") == str(path) for handler in root.handlers):
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    root.setLevel(logging.INFO)

    previous_hook = sys.excepthook

    def _log_uncaught(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            previous_hook(exc_type, exc_value, exc_traceback)
            return
        logging.getLogger("TransferLoop").critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        previous_hook(exc_type, exc_value, exc_traceback)

    if getattr(sys.excepthook, "__name__", "") != "_log_uncaught":
        sys.excepthook = _log_uncaught
    return path
