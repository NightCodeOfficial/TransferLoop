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
APP_DATA_MIGRATION_MARKER = ".flat-layout-migrated-v1"


def _app_data_root() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg_data_home:
        return Path(xdg_data_home).expanduser()
    return Path.home() / ".local" / "share"


def _migrate_legacy_app_data(root: Path, destination: Path) -> bool:
    """Copy an existing pre-TransferLoop profile without overwriting newer state.

    Returns ``True`` when there was nothing to migrate or all missing files were
    copied successfully. Migration failures are intentionally non-fatal so a
    damaged legacy profile can never prevent TransferLoop from starting.
    """
    for legacy_name in LEGACY_APP_NAMES:
        legacy = root / legacy_name
        if not legacy.exists() or not legacy.is_dir():
            continue
        try:
            _copy_missing_tree(legacy, destination)
        except OSError:
            return False
        return True
    return True


def app_base_dir() -> Path:
    """Return the product root used by the packaged desktop application."""
    return _app_data_root() / APP_NAME


def _copy_missing_tree(source: Path, target: Path) -> None:
    """Copy legacy profile files without overwriting newer Data/ state."""
    if not source.exists() or not source.is_dir():
        return
    for child in source.rglob("*"):
        relative = child.relative_to(source)
        destination = target / relative
        if child.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(child, destination)


def _migrate_flat_transferloop_data(base: Path, destination: Path) -> bool:
    """Migrate the original LocalAppData/TransferLoop flat state into Data/.

    The installer creates ``Data`` before the application starts, so the mere
    existence of that directory cannot be treated as proof that migration has
    already happened. Copy only missing legacy state and never overwrite newer
    files in ``Data``.
    """
    legacy_settings = base / "settings.json"
    legacy_projects = base / "projects"
    if not legacy_settings.exists() and not legacy_projects.exists():
        return True

    destination.mkdir(parents=True, exist_ok=True)
    target_settings = destination / "settings.json"
    success = True
    if legacy_settings.exists():
        try:
            if not target_settings.exists():
                shutil.copy2(legacy_settings, target_settings)
            else:
                # Recover the most visible casualty of a previously skipped
                # migration without overwriting newer settings. A first run of
                # the new layout can create an otherwise valid settings file
                # with an empty recent-project list before the user notices.
                legacy_data = json.loads(legacy_settings.read_text(encoding="utf-8"))
                current_data = json.loads(target_settings.read_text(encoding="utf-8"))
                if isinstance(legacy_data, dict) and isinstance(current_data, dict):
                    legacy_recent = legacy_data.get("recent_projects", [])
                    current_recent = current_data.get("recent_projects", [])
                    changed = False
                    if isinstance(legacy_recent, list) and legacy_recent and not current_recent:
                        current_data["recent_projects"] = legacy_recent
                        changed = True
                    for key, value in legacy_data.items():
                        if key not in current_data:
                            current_data[key] = value
                            changed = True
                    if changed:
                        tmp = target_settings.with_suffix(target_settings.suffix + ".migration.tmp")
                        tmp.write_text(json.dumps(current_data, indent=2, ensure_ascii=False), encoding="utf-8")
                        tmp.replace(target_settings)
        except (OSError, json.JSONDecodeError):
            success = False

    try:
        _copy_missing_tree(legacy_projects, destination / "projects")
    except OSError:
        success = False
    return success


def ensure_app_data_migrated() -> Path:
    """Perform legacy application-data migration once, outside hot path helpers.

    Older TransferLoop builds stored settings and project state directly under
    ``.../TransferLoop``. Packaged builds use ``.../TransferLoop/Data``. A prior
    implementation re-walked the complete legacy ``projects`` tree every time a
    storage path was requested, which made otherwise unrelated UI operations
    progressively slower as history/snapshot data accumulated.

    This explicit startup step writes a durable marker after a successful
    migration. Normal path helpers such as :func:`app_data_dir` and
    :func:`project_store_dir` never perform migration work.
    """
    root = _app_data_root()
    base = root / APP_NAME
    destination = base / "Data"
    destination.mkdir(parents=True, exist_ok=True)

    marker = destination / APP_DATA_MIGRATION_MARKER
    if marker.exists():
        return destination

    flat_ok = _migrate_flat_transferloop_data(base, destination)
    legacy_ok = _migrate_legacy_app_data(root, destination)
    if flat_ok and legacy_ok:
        try:
            marker.write_text("1\n", encoding="utf-8")
        except OSError:
            # Marker failure should not block startup. The next launch will
            # retry migration rather than risk silently losing legacy state.
            pass
    return destination


def app_data_dir() -> Path:
    """Return the current application-data directory without migration work."""
    path = app_base_dir() / "Data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
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
    confirm_recent_project_removal: bool = True
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
            confirm_recent_project_removal=bool(data.get("confirm_recent_project_removal", True)),
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

    def remove_recent(self, project_path: str) -> None:
        """Remove a project from the start-screen recent list without deleting project data."""
        normalized = str(Path(project_path).resolve())
        self.recent_projects = [
            path for path in self.recent_projects
            if str(Path(path).resolve()) != normalized
        ]
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


def project_map_layout_path(project_path: Path) -> Path:
    """UI-only Project Map layout state, stored outside the mapped project."""
    return project_store_dir(project_path) / "project_map_layout.json"


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


def export_baselines_dir(project_path: Path) -> Path:
    path = project_store_dir(project_path) / "export_baselines"
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
