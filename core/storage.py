from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any

APP_NAME = "TransferLoop"
LEGACY_APP_NAMES = ("AIProjectSync",)


def _app_data_root() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return Path.home() / ".local" / "share"


def _migrate_legacy_app_data(root: Path, destination: Path) -> None:
    """Copy an existing pre-TransferLoop profile into the new app-data namespace once."""
    if destination.exists():
        return
    for legacy_name in LEGACY_APP_NAMES:
        legacy = root / legacy_name
        if not legacy.exists() or not legacy.is_dir():
            continue
        try:
            shutil.copytree(legacy, destination)
        except OSError:
            # A failed migration should not prevent TransferLoop from starting.
            destination.mkdir(parents=True, exist_ok=True)
        return


def app_data_dir() -> Path:
    root = _app_data_root()
    path = root / APP_NAME
    _migrate_legacy_app_data(root, path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


@dataclass
class AppSettings:
    download_folder: str = str(Path.home() / "Downloads")
    export_folder: str = str(Path.home() / "Downloads")
    delete_import_zip_after_apply: bool = True
    monitor_downloads: bool = True
    recent_projects: list[str] = field(default_factory=list)
    theme: str = "dark"

    @classmethod
    def load(cls) -> "AppSettings":
        data = load_json(settings_path(), {})
        return cls(
            download_folder=data.get("download_folder", str(Path.home() / "Downloads")),
            export_folder=data.get("export_folder", str(Path.home() / "Downloads")),
            delete_import_zip_after_apply=bool(data.get("delete_import_zip_after_apply", True)),
            monitor_downloads=bool(data.get("monitor_downloads", True)),
            recent_projects=list(data.get("recent_projects", [])),
            theme=data.get("theme", "dark"),
        )

    def save(self) -> None:
        save_json(settings_path(), asdict(self))

    def touch_recent(self, project_path: str) -> None:
        normalized = str(Path(project_path).resolve())
        self.recent_projects = [p for p in self.recent_projects if p != normalized]
        self.recent_projects.insert(0, normalized)
        self.recent_projects = self.recent_projects[:12]
        self.save()


def project_id(project_path: Path) -> str:
    import hashlib
    return hashlib.sha1(str(project_path.resolve()).encode("utf-8")).hexdigest()[:12]


def project_store_dir(project_path: Path) -> Path:
    path = app_data_dir() / "projects" / project_id(project_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_state_path(project_path: Path) -> Path:
    return project_store_dir(project_path) / "state.json"


def snapshots_dir(project_path: Path) -> Path:
    path = project_store_dir(project_path) / "snapshot"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backups_dir(project_path: Path) -> Path:
    path = project_store_dir(project_path) / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def history_dir(project_path: Path) -> Path:
    path = project_store_dir(project_path) / "history"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_backup_folder(project_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    folder = backups_dir(project_path) / stamp
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def copy_into_snapshot(project_path: Path, relative_path: str) -> None:
    src = project_path / relative_path
    dst = snapshots_dir(project_path) / relative_path
    if src.exists() and src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    elif dst.exists():
        dst.unlink()
