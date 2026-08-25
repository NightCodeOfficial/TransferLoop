from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .ignore import is_ignored, load_patterns
from .storage import load_json, save_json, project_state_path, copy_into_snapshot
from .instructions import ensure_project_instructions

TEXT_EXTENSIONS = {
    ".py", ".pyw", ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css", ".scss", ".sass",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".md", ".txt", ".csv", ".xml",
    ".sql", ".sh", ".bat", ".cmd", ".ps1", ".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".go",
    ".rs", ".php", ".rb", ".swift", ".kt", ".kts", ".r", ".vue", ".svelte", ".gradle", ".properties",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def likely_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS or path.name.lower() in {"dockerfile", "makefile", "license"}:
        return True
    try:
        chunk = path.read_bytes()[:4096]
        if b"\x00" in chunk:
            return False
        chunk.decode("utf-8")
        return True
    except Exception:
        return False


@dataclass(frozen=True)
class ProjectDiskSnapshot:
    """Cheap on-disk project state used by the live external-change watcher.

    ``tracked_files`` stores only metadata for files that participate in sync.
    ``tree_entries`` stores the visible project-tree structure, including ignored
    items at the point where traversal stops. Comparing these snapshots lets the
    UI notice IDE saves, additions, removals, renames, and .aiignore changes
    without hashing every project file on every polling interval.
    """

    tracked_files: dict[str, tuple[int, int]]
    tree_entries: tuple[tuple[str, bool, bool], ...]


@dataclass
class ProjectState:
    path: str
    name: str
    session_id: str = ""
    initialized: bool = False
    synced_hashes: dict[str, str] = field(default_factory=dict)
    project_context: str = ""
    project_instructions: str = ""
    last_backup: str = ""
    seen_zip_signatures: list[str] = field(default_factory=list)
    diverged_paths: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, project_path: Path) -> "ProjectState":
        state_path = project_state_path(project_path)
        data = load_json(state_path, {})
        return cls(
            path=str(project_path.resolve()),
            name=data.get("name", project_path.name),
            session_id=data.get("session_id", ""),
            initialized=bool(data.get("initialized", False)),
            synced_hashes=dict(data.get("synced_hashes", {})),
            project_context=data.get("project_context", ""),
            project_instructions=data.get("project_instructions", ""),
            last_backup=data.get("last_backup", ""),
            seen_zip_signatures=list(data.get("seen_zip_signatures", []))[-100:],
            diverged_paths=list(data.get("diverged_paths", [])),
        )

    def save(self) -> None:
        save_json(project_state_path(Path(self.path)), self.__dict__)

    def ensure_session(self) -> str:
        if not self.session_id:
            self.session_id = "TL-" + secrets.token_hex(3).upper()
            self.save()
        return self.session_id


class ProjectModel:
    def __init__(self, project_path: Path):
        self.root = project_path.resolve()
        self.state = ProjectState.load(self.root)
        self._hash_cache: dict[str, tuple[int, int, str]] = {}
        ensure_project_instructions(self.root, self.state.project_instructions)
        # Ignore rules can change after a project has already been synchronized.
        # Paths that are ignored now are outside the AI-visible project state and
        # must not remain in the synchronization baseline as phantom deletions.
        self.prune_ignored_sync_state()

    @property
    def patterns(self) -> list[str]:
        return load_patterns(self.root)

    @staticmethod
    def _normalize_relative_path(relative_path: str) -> str:
        return relative_path.replace("\\", "/").strip("/")

    def is_ignored_path(self, relative_path: str, patterns: list[str] | None = None) -> bool:
        rel = self._normalize_relative_path(relative_path)
        if not rel:
            return False
        return is_ignored(rel, patterns if patterns is not None else self.patterns, False)

    def prune_ignored_sync_state(self, save: bool = True) -> tuple[str, ...]:
        """Remove currently ignored paths from persistent synchronization tracking.

        A path can legitimately become ignored after it was synchronized in an
        earlier AI session (for example, adding ``runtime/`` to ``.aiignore``).
        Those paths are no longer part of the AI-visible project state, so keeping
        their old hashes would make them look deleted forever. Diverged paths must
        be pruned for the same reason.
        """
        patterns = self.patterns
        ignored_synced = {
            rel for rel in self.state.synced_hashes
            if self.is_ignored_path(rel, patterns)
        }
        ignored_diverged = {
            rel for rel in self.state.diverged_paths
            if self.is_ignored_path(rel, patterns)
        }
        removed = ignored_synced | ignored_diverged
        if not removed:
            return ()

        for rel in ignored_synced:
            self.state.synced_hashes.pop(rel, None)
        if ignored_diverged:
            self.state.diverged_paths = [
                rel for rel in self.state.diverged_paths
                if rel not in ignored_diverged
            ]
        if save:
            self.state.save()
        return tuple(sorted(removed))

    def iter_files(self, include_ignored: bool = False) -> Iterable[tuple[str, Path, bool]]:
        patterns = self.patterns
        for base, dirs, files in os.walk(self.root):
            base_path = Path(base)
            rel_base = base_path.relative_to(self.root)
            rel_base_str = "" if str(rel_base) == "." else rel_base.as_posix()

            # Keep ignored dirs visible to the GUI scan if requested, but skip descent when exporting.
            if not include_ignored:
                dirs[:] = [
                    d for d in dirs
                    if not is_ignored(f"{rel_base_str}/{d}".strip("/"), patterns, True)
                ]

            for filename in files:
                path = base_path / filename
                rel = path.relative_to(self.root).as_posix()
                ignored = is_ignored(rel, patterns, False)
                if ignored and not include_ignored:
                    continue
                yield rel, path, ignored

    def disk_snapshot(self) -> ProjectDiskSnapshot:
        """Return a metadata-only snapshot of the current project.

        This deliberately uses ``stat`` metadata instead of content hashes so it
        is inexpensive enough to run periodically while a project is open.
        Content hashes are calculated only after the metadata snapshot reports a
        real change.
        """
        patterns = self.patterns
        tracked_files: dict[str, tuple[int, int]] = {}
        tree_entries: list[tuple[str, bool, bool]] = []

        for base, dirs, files in os.walk(self.root):
            base_path = Path(base)
            rel_base = base_path.relative_to(self.root)
            rel_base_str = "" if str(rel_base) == "." else rel_base.as_posix()

            kept_dirs: list[str] = []
            for dirname in sorted(dirs, key=str.lower):
                rel = f"{rel_base_str}/{dirname}".strip("/")
                ignored = is_ignored(rel, patterns, True)
                tree_entries.append((rel, True, ignored))
                if not ignored:
                    kept_dirs.append(dirname)
            dirs[:] = kept_dirs

            for filename in sorted(files, key=str.lower):
                path = base_path / filename
                rel = path.relative_to(self.root).as_posix()
                ignored = is_ignored(rel, patterns, False)
                tree_entries.append((rel, False, ignored))
                if ignored or rel == ".aimemory":
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                tracked_files[rel] = (stat.st_mtime_ns, stat.st_size)

        return ProjectDiskSnapshot(
            tracked_files=tracked_files,
            tree_entries=tuple(tree_entries),
        )

    def all_hashes(self, include_ignored: bool = False) -> dict[str, str]:
        """Hash the current project while reusing hashes for unchanged files."""
        hashes: dict[str, str] = {}
        next_cache: dict[str, tuple[int, int, str]] = {}

        for rel, path, ignored in self.iter_files(include_ignored=include_ignored):
            if ignored:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue

            marker = (stat.st_mtime_ns, stat.st_size)
            cached = self._hash_cache.get(rel)
            if cached and cached[:2] == marker:
                digest = cached[2]
            else:
                try:
                    digest = sha256_file(path)
                except OSError:
                    continue

            hashes[rel] = digest
            next_cache[rel] = (marker[0], marker[1], digest)

        self._hash_cache = next_cache
        return hashes

    def changed_since_sync(self) -> list[str]:
        # Persistently discard paths that became ignored after an earlier sync.
        # Otherwise they appear as local deletions even though .aiignore explicitly
        # removed them from the AI-visible project context.
        self.prune_ignored_sync_state()
        current = self.all_hashes()
        synced = self.state.synced_hashes
        memory_file = ".aimemory"
        changed = [rel for rel, digest in current.items() if rel != memory_file and synced.get(rel) != digest]
        changed.extend(rel for rel in synced if rel != memory_file and rel not in current)
        changed.extend(rel for rel in self.state.diverged_paths if rel != memory_file)
        return sorted(set(changed))

    def mark_synced(self, relative_paths: Iterable[str], initialize: bool = False) -> None:
        patterns = self.patterns
        self.prune_ignored_sync_state(save=False)

        # A full export is an exact new baseline for the current AI-visible project.
        # Do not carry hashes/divergence for files that belonged to an older baseline.
        if initialize:
            self.state.synced_hashes = {}
            self.state.diverged_paths = []

        paths = sorted({
            self._normalize_relative_path(rel)
            for rel in relative_paths
            if rel and not self.is_ignored_path(rel, patterns)
        })
        for rel in paths:
            if rel in self.state.diverged_paths:
                self.state.diverged_paths.remove(rel)
            path = self.root / rel
            if path.exists() and path.is_file():
                try:
                    digest = sha256_file(path)
                except OSError:
                    continue
                self.state.synced_hashes[rel] = digest
                copy_into_snapshot(self.root, rel)
            else:
                self.state.synced_hashes.pop(rel, None)
                copy_into_snapshot(self.root, rel)
        if initialize:
            self.state.initialized = True
            self.state.ensure_session()
        self.state.save()
