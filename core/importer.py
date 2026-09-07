from __future__ import annotations

import copy
import difflib
import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Optional

from .memory import (
    MEMORY_FILENAME,
    append_import_memory,
    append_undo_memory,
    apply_memory_updates,
    merge_incoming_memory_preserving_history,
)
from .project import ProjectModel, likely_text_file, sha256_file
from .storage import create_backup_folder, history_dir, save_json

META_FILES = {
    ".ai-response.json", "ai-response.json", "MANIFEST.json",
    "AI_CONTEXT.md", "AI_INSTRUCTIONS.md", "PROJECT_TREE.txt",
}
VALID_ACTIONS = {"modified", "added", "deleted"}
MEMORY_UPDATE_KEYS = {"current_direction", "decisions", "constraints", "open_work", "project_notes"}
_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:[/\\]")


class ApplyChangesError(RuntimeError):
    """Raised when an apply operation fails after rollback has been attempted."""


@dataclass
class ChangeItem:
    path: str
    action: str
    summary: str = ""
    details: list[str] = field(default_factory=list)
    staged_path: str = ""
    conflict: bool = False
    unexpected: bool = False
    accepted: bool = False
    rejected: bool = False


@dataclass
class ImportInspection:
    zip_path: str
    root_prefix: str
    session_id: str
    export_id: str
    overall_summary: str
    changes: list[ChangeItem]
    confidence: int
    temp_dir: str
    memory_updates: dict[str, list[str]] = field(default_factory=dict)
    stale_export: bool = False
    warnings: list[str] = field(default_factory=list)

    def cleanup(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)


def zip_signature(path: Path) -> str:
    """Return a stable content fingerprint for an AI response ZIP.

    The response watcher must treat renamed/copied ZIPs and timestamp-only changes
    as the same response.  Using the archive bytes rather than path/mtime prevents
    an already-reviewed response from being rediscovered under a different name.
    """
    return f"sha256:{sha256_file(path)}"


def normalize_response_path(raw: object) -> str | None:
    """Return a safe project-relative response path, or None when unsafe/invalid."""
    value = str(raw or "").strip().replace("\\", "/")
    if not value or value.startswith("/") or value.startswith("//") or _DRIVE_PATH_RE.match(value):
        return None
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in {"", ".", ".."} for part in p.parts):
        return None
    normalized = p.as_posix().strip("/")
    if not normalized or ":" in p.parts[0]:
        return None
    return normalized


def _project_target(model: ProjectModel, rel: str) -> Path:
    safe = normalize_response_path(rel)
    if safe is None:
        raise ValueError(f"Unsafe project path in AI response: {rel!r}")
    root = model.root.resolve()
    target = (root / Path(*PurePosixPath(safe).parts)).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"AI response path escapes the project root: {rel!r}")
    return target


def _safe_members(zf: zipfile.ZipFile) -> tuple[list[str], list[str]]:
    safe: list[str] = []
    unsafe: list[str] = []
    for name in zf.namelist():
        if name.endswith("/"):
            continue
        normalized = normalize_response_path(name)
        if normalized is None:
            unsafe.append(name)
        else:
            safe.append(normalized)
    return safe, unsafe


def _read_response_manifest(zf: zipfile.ZipFile, members: list[str]) -> tuple[dict, str, str]:
    candidates = [m for m in members if PurePosixPath(m).name.lower() in {".ai-response.json", "ai-response.json"}]
    if not candidates:
        return {}, "", ""
    member = sorted(candidates, key=lambda x: x.count("/"))[0]
    try:
        data = json.loads(zf.read(member).decode("utf-8"))
    except Exception as exc:
        return {}, member, f"The response manifest is not valid UTF-8 JSON: {exc}"
    if not isinstance(data, dict):
        return {}, member, "The response manifest must contain a JSON object."
    return data, member, ""


def _validate_manifest(model: ProjectModel, manifest: dict) -> tuple[list[dict], dict[str, list[str]], str]:
    if not manifest:
        return [], {}, ""
    if manifest.get("format_version") != 1:
        return [], {}, "Unsupported or missing .ai-response.json format_version; expected 1."

    session_id = str(manifest.get("session_id", "")).strip()
    if not session_id:
        return [], {}, "The response manifest is missing session_id."
    if model.state.session_id and session_id != model.state.session_id:
        return [], {}, (
            f"This response belongs to session {session_id}, but the open project uses "
            f"session {model.state.session_id}."
        )

    raw_entries = manifest.get("files")
    if not isinstance(raw_entries, list):
        return [], {}, "The response manifest 'files' field must be a JSON array."

    entries: list[dict] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_entries, start=1):
        if not isinstance(raw, dict):
            return [], {}, f"Manifest file entry {index} must be a JSON object."
        rel = normalize_response_path(raw.get("path"))
        if rel is None:
            return [], {}, f"Manifest file entry {index} contains an unsafe or invalid project path."
        key = rel.casefold()
        if key in seen:
            return [], {}, f"Manifest contains duplicate/case-colliding path: {rel}"
        seen.add(key)
        action = str(raw.get("action", "")).strip().lower()
        if action not in VALID_ACTIONS:
            return [], {}, f"Manifest entry {rel} has invalid action {action!r}."
        entries.append({
            "path": rel,
            "action": action,
            "summary": str(raw.get("summary", "")),
            "details": list(raw.get("details", [])) if isinstance(raw.get("details", []), list) else [],
        })

    memory_updates: dict[str, list[str]] = {}
    raw_updates = manifest.get("memory_updates", {})
    if raw_updates not in ({}, None):
        if not isinstance(raw_updates, dict):
            return [], {}, "memory_updates must be a JSON object when provided."
        for key, values in raw_updates.items():
            if key not in MEMORY_UPDATE_KEYS:
                continue
            if not isinstance(values, list):
                return [], {}, f"memory_updates.{key} must be an array of strings."
            cleaned = []
            for value in values[:30]:
                item = " ".join(str(value).strip().split())
                if item:
                    cleaned.append(item[:600])
            if cleaned:
                memory_updates[key] = cleaned
    return entries, memory_updates, ""


def _infer_root(members: list[str], known_paths: set[str], manifest_paths: set[str]) -> tuple[str, int]:
    scores: dict[str, int] = {}
    anchors = known_paths | manifest_paths
    for member in members:
        member_parts = PurePosixPath(member).parts
        for anchor in anchors:
            anchor_parts = PurePosixPath(anchor).parts
            if len(anchor_parts) > len(member_parts):
                continue
            if tuple(member_parts[-len(anchor_parts):]) == tuple(anchor_parts):
                prefix_parts = member_parts[:-len(anchor_parts)]
                prefix = "/".join(prefix_parts)
                if prefix:
                    prefix += "/"
                scores[prefix] = scores.get(prefix, 0) + 1

    if scores:
        best = sorted(scores.items(), key=lambda kv: (-kv[1], len(kv[0])))[0]
        return best[0], best[1]

    payload = [m for m in members if PurePosixPath(m).name not in META_FILES]
    if not payload:
        return "", 0
    split = [PurePosixPath(m).parts for m in payload]
    common = []
    for parts in zip(*split):
        if len(set(parts)) == 1:
            common.append(parts[0])
        else:
            break
    if common and len(common) < min(len(p) for p in split):
        prefix = "/".join(common)
        return (prefix + "/" if prefix else ""), 0
    return "", 0


def _path_differs_from_sync(
    model: ProjectModel,
    rel: str,
    local: Path,
    action: str,
    *,
    include_diverged: bool = True,
) -> bool:
    """Return whether the current local path differs from TransferLoop's synchronized state.

    This is intentionally the same source of truth as the project page's
    "locally changed" count. If the UI says a project has zero local changes,
    review must not independently manufacture file conflicts from an older or
    malformed export-baseline record.
    """
    if include_diverged and rel in model.state.diverged_paths:
        return True

    synced_hash = model.state.synced_hashes.get(rel)
    if action == "added":
        return local.exists()
    if not local.exists():
        return action == "modified" and synced_hash is not None
    if not local.is_file():
        return True
    if synced_hash is None:
        return True
    try:
        return sha256_file(local) != synced_hash
    except OSError:
        return True


def _path_differs_from_export_baseline(
    rel: str,
    local: Path,
    action: str,
    baseline_hashes: dict[str, str],
) -> bool:
    baseline_hash = baseline_hashes.get(rel)
    if action == "added":
        return local.exists()
    if not local.exists():
        return action == "modified" and baseline_hash is not None
    if not local.is_file():
        return True
    if baseline_hash is None:
        return True
    try:
        return sha256_file(local) != baseline_hash
    except OSError:
        return True


def _conflict_for_path(
    model: ProjectModel,
    rel: str,
    local: Path,
    action: str,
    baseline_hashes: dict[str, str] | None,
    export_id: str = "",
) -> bool:
    # First use the same synchronized-state check shown to the user as
    # "locally changed". A genuine unsynchronized local edit is always a
    # conflict because the AI did not receive that current file state.
    #
    # When an exact baseline exists for the *latest* export, an old diverged
    # marker alone is not enough to create a conflict; the current bytes are
    # authoritative. This preserves the earlier false-positive fix.
    latest_exact_export = bool(
        export_id
        and baseline_hashes is not None
        and export_id == model.state.last_export_id
    )
    if _path_differs_from_sync(
        model, rel, local, action, include_diverged=not latest_exact_export
    ):
        return True

    # If this response is for the latest export and the current file still
    # matches TransferLoop's synchronized state, it is safe to review/apply.
    # Older TransferLoop versions could persist an export-baseline snapshot
    # that later disagreed with the synchronized state even though the user had
    # made no local edits. Trusting that legacy snapshot produced the "0 locally
    # changed" / "Needs updated context" contradiction.
    if latest_exact_export:
        return False

    # For a response based on an older export, keep the exact-baseline check.
    # This protects against applying a genuinely stale response after a newer
    # project export established different context.
    if baseline_hashes is not None:
        return _path_differs_from_export_baseline(rel, local, action, baseline_hashes)

    return False


def inspect_zip_detailed(model: ProjectModel, zip_path: Path) -> tuple[Optional[ImportInspection], str]:
    if not zip_path.exists() or zip_path.suffix.lower() != ".zip":
        return None, "Choose an existing ZIP file."

    temp_dir: Path | None = None
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members, unsafe_members = _safe_members(zf)
            if unsafe_members:
                return None, "The ZIP contains unsafe absolute or parent-traversal paths and was rejected."
            if not members:
                return None, "The ZIP does not contain any files."

            manifest, _manifest_member, manifest_error = _read_response_manifest(zf, members)
            if manifest_error:
                return None, manifest_error
            manifest_entries, memory_updates, validation_error = _validate_manifest(model, manifest)
            if validation_error:
                return None, validation_error

            notes_by_path = {entry["path"]: entry for entry in manifest_entries}
            manifest_paths = set(notes_by_path)
            known_paths = {rel for rel, _, _ in model.iter_files()}
            root_prefix, confidence = _infer_root(members, known_paths, manifest_paths)

            if confidence == 0 and not manifest_paths and not memory_updates:
                return None, (
                    "The ZIP could not be confidently mapped to this project. Include .ai-response.json "
                    "and preserve project-relative paths."
                )

            export_id = str(manifest.get("export_id", "")).strip() if manifest else ""
            baseline_hashes = model.baseline_hashes_for_export(export_id) if export_id else None
            warnings: list[str] = []
            stale_export = bool(export_id and model.state.last_export_id and export_id != model.state.last_export_id)
            if stale_export:
                warnings.append(
                    f"Response is based on {export_id}; the most recent export is {model.state.last_export_id}."
                )
            if export_id and baseline_hashes is None:
                warnings.append(
                    f"The exact baseline for {export_id} is no longer available; conflict checks use the current sync baseline."
                )

            temp_dir = Path(tempfile.mkdtemp(prefix="transferloop_import_"))
            stage_root = temp_dir / "stage"
            stage_root.mkdir(parents=True, exist_ok=True)

            for member in members:
                if root_prefix and not member.startswith(root_prefix):
                    continue
                rel_raw = member[len(root_prefix):] if root_prefix else member
                rel = normalize_response_path(rel_raw)
                if rel is None or PurePosixPath(rel).name in META_FILES:
                    continue
                target = stage_root / Path(*PurePosixPath(rel).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

            changes: list[ChangeItem] = []
            staged_files: set[str] = set()
            for path in stage_root.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(stage_root).as_posix()
                staged_files.add(rel)
                local = _project_target(model, rel)
                if local.exists() and local.is_file():
                    try:
                        if sha256_file(local) == sha256_file(path):
                            continue
                    except OSError:
                        pass
                    action = "modified"
                else:
                    action = "added"

                entry = notes_by_path.get(rel, {})
                if entry.get("action") == "deleted":
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    return None, f"Manifest says {rel} is deleted, but the ZIP also contains that file."

                conflict = _conflict_for_path(model, rel, local, action, baseline_hashes, export_id)
                changes.append(ChangeItem(
                    path=rel,
                    action=action,
                    summary=str(entry.get("summary", "")),
                    details=list(entry.get("details", [])),
                    staged_path=str(path),
                    conflict=conflict,
                    unexpected=bool(notes_by_path) and rel not in notes_by_path,
                ))

            for rel, entry in notes_by_path.items():
                expected_action = entry["action"]
                if expected_action != "deleted":
                    if rel not in staged_files:
                        local = _project_target(model, rel)
                        if expected_action == "modified" and local.exists() and local.is_file():
                            # A manifest can list a file that is byte-identical and therefore
                            # absent from changes, but it must still be physically in the ZIP.
                            shutil.rmtree(temp_dir, ignore_errors=True)
                            return None, f"Manifest lists {rel} as {expected_action}, but the file is missing from the ZIP."
                        if expected_action == "added":
                            shutil.rmtree(temp_dir, ignore_errors=True)
                            return None, f"Manifest lists {rel} as added, but the file is missing from the ZIP."
                    continue

                local = _project_target(model, rel)
                if not local.exists():
                    continue
                conflict = _conflict_for_path(model, rel, local, "deleted", baseline_hashes, export_id)
                changes.append(ChangeItem(
                    path=rel,
                    action="deleted",
                    summary=str(entry.get("summary", "")),
                    details=list(entry.get("details", [])),
                    staged_path="",
                    conflict=conflict,
                ))

            if not changes and not memory_updates:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None, "The response does not contain any project changes."

            return ImportInspection(
                zip_path=str(zip_path),
                root_prefix=root_prefix,
                session_id=str(manifest.get("session_id", "")) if manifest else "",
                export_id=export_id,
                overall_summary=str(manifest.get("summary", "")) if manifest else "",
                changes=sorted(changes, key=lambda c: c.path.lower()),
                confidence=confidence,
                temp_dir=str(temp_dir),
                memory_updates=memory_updates,
                stale_export=stale_export,
                warnings=warnings,
            ), ""
    except zipfile.BadZipFile:
        return None, "The selected file is not a valid ZIP archive."
    except OSError as exc:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return None, f"Could not inspect the ZIP: {exc}"


def inspect_zip(model: ProjectModel, zip_path: Path) -> Optional[ImportInspection]:
    inspection, _error = inspect_zip_detailed(model, zip_path)
    return inspection


def build_text_diff(model: ProjectModel, change: ChangeItem) -> str:
    if change.action == "deleted":
        local = _project_target(model, change.path)
        if not local.exists() or not likely_text_file(local):
            return "Binary or unavailable file will be deleted."
        before = local.read_text(encoding="utf-8", errors="replace").splitlines()
        after: list[str] = []
    else:
        staged = Path(change.staged_path)
        local = _project_target(model, change.path)
        if not likely_text_file(staged) or (local.exists() and not likely_text_file(local)):
            old_size = local.stat().st_size if local.exists() else 0
            new_size = staged.stat().st_size if staged.exists() else 0
            return f"Binary / non-text comparison unavailable.\n\nLocal size: {old_size:,} bytes\nAI version: {new_size:,} bytes"
        before = local.read_text(encoding="utf-8", errors="replace").splitlines() if local.exists() else []
        after = staged.read_text(encoding="utf-8", errors="replace").splitlines()

    return "\n".join(difflib.unified_diff(
        before,
        after,
        fromfile=f"local/{change.path}",
        tofile=f"ai/{change.path}",
        lineterm="",
    )) or "No textual differences detected."


def _restore_project_files(model: ProjectModel, backup: Path, manifest: dict) -> list[str]:
    errors: list[str] = []
    for entry in reversed(manifest.get("files", [])):
        rel = entry.get("path")
        if not rel:
            continue
        try:
            target = _project_target(model, rel)
            backup_file = backup / Path(*PurePosixPath(rel).parts)
            if entry.get("existed"):
                if not backup_file.exists():
                    raise OSError("backup copy is missing")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_file, target)
            elif target.exists() and target.is_file():
                target.unlink()
        except Exception as exc:
            errors.append(f"{rel}: {exc}")
    return errors


def apply_changes(
    model: ProjectModel,
    inspection: ImportInspection,
    accepted_paths: set[str],
    *,
    accept_memory_updates: bool = False,
) -> tuple[int, Path]:
    selected_changes = [change for change in inspection.changes if change.path in accepted_paths]
    for change in selected_changes:
        _project_target(model, change.path)
        if change.action != "deleted" and (not change.staged_path or not Path(change.staged_path).is_file()):
            raise ApplyChangesError(f"Staged file is missing for {change.path}; no changes were applied.")

    state_before = copy.deepcopy(model.state.__dict__)
    memory_path = model.root / MEMORY_FILENAME
    memory_existed_before = memory_path.exists() and memory_path.is_file()
    try:
        backup = create_backup_folder(model.root)
        backup_manifest: dict = {"files": [], "source_zip": inspection.zip_path}

        # Save all originals before the first write so the apply can be rolled back as a unit.
        for change in selected_changes:
            target = _project_target(model, change.path)
            existed = target.exists() and target.is_file()
            if existed:
                backup_target = backup / Path(*PurePosixPath(change.path).parts)
                backup_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup_target)
            backup_manifest["files"].append({
                "path": change.path,
                "existed": existed,
                "action": change.action,
            })

        managed_memory_backup = backup / "_transferloop_managed" / MEMORY_FILENAME
        if memory_existed_before:
            managed_memory_backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(memory_path, managed_memory_backup)
        save_json(backup / "backup_manifest.json", backup_manifest)
    except Exception as exc:
        raise ApplyChangesError(f"Could not create a complete pre-apply backup: {exc}. No project files were changed.") from exc

    changed_count = 0
    rejected_paths = {change.path for change in inspection.changes if change.path not in accepted_paths}
    try:
        for change in selected_changes:
            target = _project_target(model, change.path)
            if change.action == "deleted":
                if change.path == MEMORY_FILENAME:
                    continue
                if target.exists() and target.is_file():
                    target.unlink()
            else:
                source = Path(change.staged_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                if change.path == MEMORY_FILENAME:
                    merge_incoming_memory_preserving_history(target, source)
                else:
                    shutil.copy2(source, target)
            changed_count += 1

        if accept_memory_updates and inspection.memory_updates:
            apply_memory_updates(model, inspection.memory_updates)

        model.state.last_backup = str(backup)
        model.state.pending_response_zip = ""
        for rel in rejected_paths:
            if rel not in model.state.diverged_paths:
                model.state.diverged_paths.append(rel)
        model.state.save()
        model.mark_synced(accepted_paths)
        append_import_memory(model, inspection, accepted_paths, rejected_paths)
        model.mark_synced({MEMORY_FILENAME})

        try:
            signature = zip_signature(Path(inspection.zip_path))
        except OSError:
            signature = ""
        if signature:
            seen = [sig for sig in model.state.seen_zip_signatures if sig != signature]
            seen.append(signature)
            model.state.seen_zip_signatures = seen[-100:]
            model.state.save()

        hist = {
            "summary": inspection.overall_summary,
            "session_id": inspection.session_id,
            "export_id": inspection.export_id,
            "zip": inspection.zip_path,
            "accepted": sorted(accepted_paths),
            "rejected_or_unapplied": sorted(rejected_paths),
            "memory_updates_accepted": bool(accept_memory_updates and inspection.memory_updates),
            "memory_updates": inspection.memory_updates,
            "changes": [change.__dict__ for change in inspection.changes],
        }
        import datetime
        history_root = history_dir(model.root) / datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        history_root.mkdir(parents=True, exist_ok=True)
        response_files = history_root / "response_files"
        response_files.mkdir(parents=True, exist_ok=True)
        for change in inspection.changes:
            if change.staged_path and Path(change.staged_path).exists():
                dst = response_files / Path(*PurePosixPath(change.path).parts)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(change.staged_path, dst)
        save_json(history_root / "history.json", hist)
        return changed_count, backup
    except Exception as exc:
        rollback_errors = _restore_project_files(model, backup, backup_manifest)
        try:
            if managed_memory_backup.exists():
                memory_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(managed_memory_backup, memory_path)
            elif not memory_existed_before and memory_path.exists() and memory_path.is_file():
                memory_path.unlink()
        except Exception as memory_exc:
            rollback_errors.append(f"{MEMORY_FILENAME}: {memory_exc}")

        model.state.__dict__.clear()
        model.state.__dict__.update(state_before)
        try:
            model.state.save()
        except Exception as state_exc:
            rollback_errors.append(f"state.json: {state_exc}")

        detail = f"Apply failed: {exc}. Project files were rolled back."
        if rollback_errors:
            detail += " Some rollback steps also failed: " + "; ".join(rollback_errors)
        raise ApplyChangesError(detail) from exc


def undo_last_apply(model: ProjectModel) -> int:
    if not model.state.last_backup:
        return 0
    backup = Path(model.state.last_backup)
    manifest_path = backup / "backup_manifest.json"
    if not manifest_path.exists():
        return 0
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    count = 0
    affected = []
    for entry in data.get("files", []):
        rel = normalize_response_path(entry.get("path"))
        if not rel:
            continue
        affected.append(rel)
        target = _project_target(model, rel)
        backup_file = backup / Path(*PurePosixPath(rel).parts)
        if entry.get("existed"):
            if backup_file.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_file, target)
                count += 1
        else:
            if target.exists() and target.is_file():
                target.unlink()
                count += 1
    model.mark_synced(affected)
    append_undo_memory(model, affected)
    model.mark_synced({MEMORY_FILENAME})
    model.state.last_backup = ""
    model.state.save()
    return count
