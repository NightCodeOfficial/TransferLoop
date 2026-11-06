from __future__ import annotations

import difflib
import hashlib
import json
import os
import secrets
import shutil
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .ignore import is_ignored, load_patterns
from .storage import (
    backups_dir, copy_into_snapshot, export_baselines_dir, history_dir, load_json,
    project_state_path, save_json, snapshots_dir,
)
from .instructions import ensure_project_instructions

TEXT_EXTENSIONS = {
    ".py", ".pyw", ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css", ".scss", ".sass",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".md", ".txt", ".csv", ".xml",
    ".sql", ".sh", ".bat", ".cmd", ".ps1", ".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".go",
    ".rs", ".php", ".rb", ".swift", ".kt", ".kts", ".r", ".vue", ".svelte", ".gradle", ".properties",
}

BASELINE_TEXT_SNAPSHOT_MAX_BYTES = 4 * 1024 * 1024
ACCEPTED_AI_DELETED = "<deleted>"

# These files are useful TransferLoop metadata, but changes to them do not mean
# the AI is missing project source context. .aimemory is app-maintained and
# .aiignore only changes what future exports should include. Keep their stored
# hashes intact so an AI response that tries to overwrite either file can still
# be checked against the export/sync baseline.
CONTEXT_NEUTRAL_SYNC_FILES = {".aimemory", ".aiignore"}


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


def materially_equal_files(first: Path, second: Path) -> bool:
    """Return whether two files have the same meaningful content.

    SHA-256 equality remains the fast/authoritative path. For UTF-8 text, line
    ending-only differences are treated as equivalent so CRLF/LF normalization
    cannot manufacture a stale-context warning or local-change marker.
    """
    try:
        if sha256_file(first) == sha256_file(second):
            return True
        if not likely_text_file(first) or not likely_text_file(second):
            return False
        if max(first.stat().st_size, second.stat().st_size) > BASELINE_TEXT_SNAPSHOT_MAX_BYTES:
            return False
        first_text = first.read_text(encoding="utf-8")
        second_text = second.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    normalize = lambda text: text.replace("\r\n", "\n").replace("\r", "\n")
    return normalize(first_text) == normalize(second_text)


@dataclass(frozen=True)
class LocalChange:
    """A project path whose local state is newer than the AI sync baseline."""

    path: str
    kind: str


@dataclass(frozen=True)
class LocalChangeDiff:
    """Renderable text diff for one local change."""

    text: str
    truncated: bool = False
    preview_available: bool = True


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
    accepted_ai_hashes: dict[str, str] = field(default_factory=dict)
    project_context: str = ""
    project_instructions: str = ""
    last_backup: str = ""
    seen_zip_signatures: list[str] = field(default_factory=list)
    diverged_paths: list[str] = field(default_factory=list)
    export_counter: int = 0
    last_export_id: str = ""
    pending_response_zip: str = ""
    recovery_warning: str = field(default="", repr=False, compare=False)

    @classmethod
    def load(cls, project_path: Path) -> "ProjectState":
        state_path = project_state_path(project_path)
        recovery_warning = ""
        if state_path.exists():
            try:
                data = json.loads(state_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("state root is not a JSON object")
            except Exception as exc:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                recovery_copy = state_path.with_name(f"state.corrupt_{stamp}.json")
                try:
                    shutil.copy2(state_path, recovery_copy)
                    recovery_warning = (
                        f"TransferLoop could not read this project's saved state ({exc}). "
                        f"The unreadable file was preserved as {recovery_copy.name}, and a fresh state was loaded."
                    )
                except OSError:
                    recovery_warning = (
                        f"TransferLoop could not read this project's saved state ({exc}). "
                        "A fresh state was loaded; the corrupt file could not be copied."
                    )
                data = {}
        else:
            data = {}
        return cls(
            path=str(project_path.resolve()),
            name=data.get("name", project_path.name),
            session_id=data.get("session_id", ""),
            initialized=bool(data.get("initialized", False)),
            synced_hashes=dict(data.get("synced_hashes", {})),
            accepted_ai_hashes=dict(data.get("accepted_ai_hashes", {})),
            project_context=data.get("project_context", ""),
            project_instructions=data.get("project_instructions", ""),
            last_backup=data.get("last_backup", ""),
            seen_zip_signatures=list(data.get("seen_zip_signatures", []))[-100:],
            diverged_paths=list(data.get("diverged_paths", [])),
            export_counter=int(data.get("export_counter", 0) or 0),
            last_export_id=data.get("last_export_id", ""),
            pending_response_zip=data.get("pending_response_zip", ""),
            recovery_warning=recovery_warning,
        )

    def save(self) -> None:
        payload = {key: value for key, value in self.__dict__.items() if key != "recovery_warning"}
        save_json(project_state_path(Path(self.path)), payload)

    def ensure_session(self) -> str:
        if not self.session_id:
            self.session_id = "TL-" + secrets.token_hex(3).upper()
            self.save()
        return self.session_id

    def next_export_id(self) -> str:
        session = self.ensure_session()
        self.export_counter += 1
        self.last_export_id = f"{session}-E{self.export_counter:04d}"
        self.save()
        return self.last_export_id


class ProjectModel:
    def __init__(self, project_path: Path):
        self.root = project_path.resolve()
        self.state = ProjectState.load(self.root)
        self._hash_cache: dict[str, tuple[int, int, str]] = {}
        self._local_changes_cache: tuple[tuple, tuple[LocalChange, ...]] | None = None
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
        ignored_ai = {
            rel for rel in self.state.accepted_ai_hashes
            if self.is_ignored_path(rel, patterns)
        }
        removed = ignored_synced | ignored_diverged | ignored_ai
        if not removed:
            return ()

        for rel in ignored_synced:
            self.state.synced_hashes.pop(rel, None)
        if ignored_diverged:
            self.state.diverged_paths = [
                rel for rel in self.state.diverged_paths
                if rel not in ignored_diverged
            ]
        for rel in ignored_ai:
            self.state.accepted_ai_hashes.pop(rel, None)
        self.invalidate_local_change_cache()
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


    def record_export_baseline(self, export_id: str) -> None:
        """Persist the immutable AI-visible file baseline associated with an export.

        Format 3 keeps the hash snapshot plus deduplicated UTF-8 text blobs for
        recent exports. The hashes preserve exact lineage while the text blobs let
        the importer perform a real three-way merge (export baseline vs current
        local vs incoming AI) instead of treating any whole-file mismatch as a
        conflict.
        """
        if not export_id:
            return
        context_hashes = dict(self.state.synced_hashes)
        folder = export_baselines_dir(self.root)
        blob_folder = folder / "_blobs"
        blob_folder.mkdir(parents=True, exist_ok=True)
        snapshot_root = snapshots_dir(self.root)
        content_blobs: dict[str, str] = {}
        for rel, digest in context_hashes.items():
            source = snapshot_root / rel
            try:
                if (
                    not source.is_file()
                    or source.stat().st_size > BASELINE_TEXT_SNAPSHOT_MAX_BYTES
                    or not likely_text_file(source)
                    or sha256_file(source) != digest
                ):
                    continue
                blob = blob_folder / digest
                if not blob.exists():
                    shutil.copy2(source, blob)
                content_blobs[rel] = digest
            except OSError:
                continue

        payload = {
            "format_version": 3,
            "export_id": export_id,
            "session_id": self.state.session_id,
            "context_hashes": context_hashes,
            "content_blobs": content_blobs,
            # Retain the old key so older TransferLoop builds can still read a
            # baseline created by this version if the project is opened there.
            "synced_hashes": context_hashes,
        }
        save_json(folder / f"{export_id}.json", payload)

        # Keep a bounded lineage history. The response workflow only needs recent
        # exports, while older accepted responses remain in the normal history store.
        baseline_files = sorted(
            folder.glob("*.json"),
            key=lambda path: path.stat().st_mtime_ns if path.exists() else 0,
            reverse=True,
        )
        for stale in baseline_files[30:]:
            try:
                stale.unlink()
            except OSError:
                pass

        # Garbage-collect deduplicated text blobs no longer referenced by one of
        # the retained recent baselines.
        retained_hashes: set[str] = set()
        for baseline_file in baseline_files[:30]:
            data = load_json(baseline_file, {})
            if not isinstance(data, dict):
                continue
            blobs = data.get("content_blobs", {})
            if isinstance(blobs, dict):
                retained_hashes.update(str(value) for value in blobs.values() if value)
        for blob in blob_folder.iterdir():
            if blob.is_file() and blob.name not in retained_hashes:
                try:
                    blob.unlink()
                except OSError:
                    pass

    def export_baseline_for_export(self, export_id: str) -> tuple[dict[str, str] | None, bool]:
        """Return ``(hashes, is_exact)`` for one export-lineage record.

        ``is_exact`` is true only for format-2+ records created from an immutable
        export-time context snapshot. Legacy records remain readable, but import
        conflict detection uses the conservative compatibility path for them.
        """
        if not export_id:
            return None, False
        data = load_json(export_baselines_dir(self.root) / f"{export_id}.json", {})
        if not isinstance(data, dict):
            return None, False
        version = data.get("format_version", 0)
        if isinstance(version, int) and version >= 2:
            hashes = data.get("context_hashes")
            if isinstance(hashes, dict):
                return dict(hashes), True
        hashes = data.get("synced_hashes")
        return (dict(hashes), False) if isinstance(hashes, dict) else (None, False)

    def export_baseline_content_path(self, export_id: str, relative_path: str) -> Path | None:
        """Return/recover the retained exact text snapshot for one export/path.

        Format-2 baselines created by older TransferLoop versions stored only
        hashes. When possible, recover their exact text bytes from the current
        sync snapshot, project file, or transactional backups by requiring a
        SHA-256 match to the immutable export hash. This makes the three-way merge
        upgrade useful immediately after installation instead of requiring a new
        full export solely to seed text snapshots.
        """
        if not export_id:
            return None
        folder = export_baselines_dir(self.root)
        baseline_file = folder / f"{export_id}.json"
        data = load_json(baseline_file, {})
        if not isinstance(data, dict) or int(data.get("format_version", 0) or 0) < 2:
            return None
        blobs = data.get("content_blobs", {})
        if not isinstance(blobs, dict):
            blobs = {}
        rel = self._normalize_relative_path(relative_path)
        hashes = data.get("context_hashes", {})
        if not isinstance(hashes, dict):
            hashes = {}
        digest = str(blobs.get(rel) or hashes.get(rel) or "").strip()
        if not digest:
            return None
        blob = folder / "_blobs" / digest
        if blob.is_file():
            try:
                if sha256_file(blob) == digest:
                    return blob
            except OSError:
                pass

        candidates = [snapshots_dir(self.root) / rel, self.root / rel]
        try:
            backup_folders = sorted(
                (path for path in backups_dir(self.root).iterdir() if path.is_dir()),
                key=lambda path: path.name,
                reverse=True,
            )
        except OSError:
            backup_folders = []
        candidates.extend(backup / rel for backup in backup_folders)

        for candidate in candidates:
            try:
                if (
                    not candidate.is_file()
                    or candidate.stat().st_size > BASELINE_TEXT_SNAPSHOT_MAX_BYTES
                    or not likely_text_file(candidate)
                    or sha256_file(candidate) != digest
                ):
                    continue
                blob.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, blob)
                blobs[rel] = digest
                data["content_blobs"] = blobs
                data["format_version"] = max(3, int(data.get("format_version", 0) or 0))
                save_json(baseline_file, data)
                return blob
            except OSError:
                continue
        return None

    def current_matches_accepted_ai_state(self, relative_path: str) -> bool:
        """Return whether the current path matches an accepted AI response state.

        New applies record this directly in ``accepted_ai_hashes``. The history
        fallback recovers provenance for responses accepted by older builds before
        this field existed, then caches the result in project state.
        """
        rel = self._normalize_relative_path(relative_path)
        target = self.root / rel
        if target.is_file():
            try:
                current_digest = sha256_file(target)
            except OSError:
                return False
            if self.state.accepted_ai_hashes.get(rel) == current_digest:
                return True
        else:
            current_digest = ACCEPTED_AI_DELETED
            if self.state.accepted_ai_hashes.get(rel) == ACCEPTED_AI_DELETED:
                return True

        try:
            history_folders = sorted(
                (path for path in history_dir(self.root).iterdir() if path.is_dir()),
                key=lambda path: path.name,
                reverse=True,
            )
        except OSError:
            return False

        for folder in history_folders[:100]:
            data = load_json(folder / "history.json", {})
            if not isinstance(data, dict) or rel not in set(data.get("accepted", [])):
                continue
            if target.is_file():
                response_file = folder / "response_files" / rel
                try:
                    if response_file.is_file() and sha256_file(response_file) == current_digest:
                        self.state.accepted_ai_hashes[rel] = current_digest
                        self.state.save()
                        return True
                except OSError:
                    continue
            else:
                changes = data.get("changes", [])
                if any(
                    isinstance(change, dict)
                    and change.get("path") == rel
                    and change.get("action") == "deleted"
                    for change in changes
                ):
                    self.state.accepted_ai_hashes[rel] = ACCEPTED_AI_DELETED
                    self.state.save()
                    return True
        return False

    def baseline_hashes_for_export(self, export_id: str) -> dict[str, str] | None:
        hashes, _is_exact = self.export_baseline_for_export(export_id)
        return hashes

    def invalidate_local_change_cache(self) -> None:
        """Discard the UI-oriented local-change cache after known disk/state changes."""
        self._local_changes_cache = None

    def _local_change_state_key(self) -> tuple:
        """Return the small in-memory state portion that affects local-change classification."""
        return (
            bool(self.state.initialized),
            tuple(sorted(self.state.synced_hashes.items())),
            tuple(sorted(self.state.diverged_paths)),
        )

    def cached_local_changes_since_sync(self) -> list[LocalChange]:
        """Return local changes while reusing the last scan until the UI invalidates it.

        TransferLoop's project page can ask for the same local-change set several times
        while rebuilding the tree, status header, and export summary. Rewalking the entire
        project for each consumer made routine UI work noticeably slower. External-change
        monitoring and app-managed writes explicitly invalidate this cache.
        """
        state_key = self._local_change_state_key()
        cached = self._local_changes_cache
        if cached is not None and cached[0] == state_key:
            return list(cached[1])
        changes = self.local_changes_since_sync()
        self._local_changes_cache = (self._local_change_state_key(), tuple(changes))
        return list(changes)

    def local_changes_since_sync(self) -> list[LocalChange]:
        """Describe paths that need to be refreshed in the AI-visible context.

        The classification is intentionally based on the same sync baseline used by
        ``changed_since_sync`` so the header count, project tree, Export Changed, and
        local-change review all agree. Historical ``diverged_paths`` markers are
        intentionally not treated as content changes: a file that is byte-identical
        to the synchronized baseline must not be reported as outdated.
        """
        # Persistently discard paths that became ignored after an earlier sync.
        # Otherwise they appear as local deletions even though .aiignore explicitly
        # removed them from the AI-visible project context.
        self.prune_ignored_sync_state()
        current = self.all_hashes()
        synced = self.state.synced_hashes
        neutral = CONTEXT_NEUTRAL_SYNC_FILES
        changes: dict[str, LocalChange] = {}
        for rel, digest in current.items():
            if rel in neutral:
                continue
            if rel not in synced:
                changes[rel] = LocalChange(rel, "added")
            elif synced.get(rel) != digest:
                baseline_path = snapshots_dir(self.root) / rel
                if not baseline_path.is_file() or not materially_equal_files(self.root / rel, baseline_path):
                    changes[rel] = LocalChange(rel, "modified")

        for rel in synced:
            if rel not in neutral and rel not in current:
                changes[rel] = LocalChange(rel, "deleted")

        return [changes[rel] for rel in sorted(changes)]

    def changed_since_sync(self) -> list[str]:
        return [change.path for change in self.local_changes_since_sync()]

    def local_change_diff(self, change: LocalChange, max_lines: int = 500) -> LocalChangeDiff:
        """Build a bounded unified diff against the stored sync snapshot.

        The snapshot is the exact file copy maintained alongside ``synced_hashes``.
        This makes the UI able to show what changed without altering the project or
        requiring a source-control repository.
        """
        current_path = self.root / change.path
        baseline_path = snapshots_dir(self.root) / change.path

        if change.kind == "context":
            return LocalChangeDiff(
                "No file-content difference is required for this status.\n\n"
                "This path is marked as context-diverged (for example, an AI-proposed "
                "change was not applied). Export it again so the next AI response is based "
                "on the local version you kept."
            )

        preview_paths = [path for path in (baseline_path, current_path) if path.exists() and path.is_file()]
        for path in preview_paths:
            try:
                if path.stat().st_size > 2 * 1024 * 1024:
                    return LocalChangeDiff(
                        "Inline diff preview is unavailable because this file is larger than 2 MB. "
                        "Use Open Selected to inspect the local file.",
                        preview_available=False,
                    )
            except OSError:
                return LocalChangeDiff("The file could not be read for an inline diff preview.", preview_available=False)
            if not likely_text_file(path):
                return LocalChangeDiff(
                    "Binary or unsupported file — TransferLoop can track that it changed, but cannot show a text diff.",
                    preview_available=False,
                )

        def read_lines(path: Path) -> list[str] | None:
            try:
                return path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                return None

        before = read_lines(baseline_path) if baseline_path.exists() else []
        after = read_lines(current_path) if current_path.exists() else []
        if before is None or after is None:
            return LocalChangeDiff("The file could not be read for an inline diff preview.", preview_available=False)

        if change.kind == "added":
            lines = [f"+++ {change.path} (local new file)", *[f"+{line}" for line in after]]
        elif change.kind == "deleted":
            lines = [f"--- {change.path} (AI sync baseline)", *[f"-{line}" for line in before]]
        else:
            lines = list(
                difflib.unified_diff(
                    before,
                    after,
                    fromfile=f"{change.path} (AI sync baseline)",
                    tofile=f"{change.path} (local)",
                    lineterm="",
                    n=3,
                )
            )

        if not lines:
            return LocalChangeDiff("No textual line differences were found.")

        truncated = len(lines) > max_lines
        if truncated:
            lines = lines[:max_lines]
            lines.extend(["", f"… diff truncated after {max_lines} lines …"])
        return LocalChangeDiff("\n".join(lines), truncated=truncated)

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
        self.invalidate_local_change_cache()
        self.state.save()

    def mark_ai_applied(self, relative_paths: Iterable[str]) -> None:
        """Record the exact current states produced by an accepted AI response.

        This provenance is deliberately separate from ``synced_hashes`` because a
        later export may synchronize user/external edits. Keeping the last accepted
        AI state lets stale-response review explain whether current bytes came from
        an accepted TransferLoop merge or from another source.
        """
        for rel in {
            self._normalize_relative_path(path)
            for path in relative_paths
            if path
        }:
            target = self.root / rel
            if target.is_file():
                try:
                    self.state.accepted_ai_hashes[rel] = sha256_file(target)
                except OSError:
                    self.state.accepted_ai_hashes.pop(rel, None)
            else:
                self.state.accepted_ai_hashes[rel] = ACCEPTED_AI_DELETED
        self.state.save()
