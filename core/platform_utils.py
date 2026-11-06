from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable


_FILE_MANAGER_DESTINATION = "org.freedesktop.FileManager1"
_FILE_MANAGER_OBJECT = "/org/freedesktop/FileManager1"
_FILE_MANAGER_SHOW_ITEMS = "org.freedesktop.FileManager1.ShowItems"


def _gvariant_string(value: str) -> str:
    """Quote a string for a GVariant command-line literal."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def linux_file_manager_show_items_argument(paths: Iterable[Path]) -> str:
    """Build the GVariant array consumed by FileManager1.ShowItems."""
    uris = [Path(path).resolve().as_uri() for path in paths]
    return "[" + ", ".join(_gvariant_string(uri) for uri in uris) + "]"


def show_items_in_linux_file_manager(paths: Iterable[Path]) -> bool:
    """Ask the desktop file manager to reveal/select paths using FileManager1.

    The freedesktop FileManager1 D-Bus interface is supported by common Linux
    file managers.  This helper deliberately has no Python D-Bus dependency;
    it uses ``gdbus`` when a graphical session bus is available.  Callers
    should fall back to opening the containing folder when this returns False.
    """
    items = [Path(path).resolve() for path in paths]
    if not items:
        return False
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return False

    gdbus = shutil.which("gdbus")
    if not gdbus:
        return False

    command = [
        gdbus,
        "call",
        "--session",
        "--dest",
        _FILE_MANAGER_DESTINATION,
        "--object-path",
        _FILE_MANAGER_OBJECT,
        "--method",
        _FILE_MANAGER_SHOW_ITEMS,
        linux_file_manager_show_items_argument(items),
        "",
    ]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0
