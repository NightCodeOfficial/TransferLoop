from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Optional

from .project import ProjectModel, likely_text_file, sha256_file
from .memory import (
    MEMORY_FILENAME, append_import_memory, append_undo_memory,
    merge_incoming_memory_preserving_history,
)
from .storage import create_backup_folder, history_dir, save_json

META_FILES = {".ai-response.json", "ai-response.json", "MANIFEST.json", "AI_CONTEXT.md", "AI_INSTRUCTIONS.md", "PROJECT_TREE.txt"}


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


@dataclass
class ImportInspection:
    zip_path: str
    root_prefix: str
    session_id: str
    overall_summary: str
    changes: list[ChangeItem]
    confidence: int
    temp_dir: str

    def cleanup(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)


def zip_signature(path: Path) -> str:
    st = path.stat()
    return f"{path.resolve()}::{st.st_size}::{st.st_mtime_ns}"


def _safe_members(zf: zipfile.ZipFile) -> list[str]:
    result = []
    for name in zf.namelist():
        p = PurePosixPath(name.replace("\\", "/"))
        if p.is_absolute() or ".." in p.parts:
            continue
        if name.endswith("/"):
            continue
        result.append(p.as_posix())
    return result


def _read_response_manifest(zf: zipfile.ZipFile, members: list[str]) -> tuple[dict, str]:
    candidates = [m for m in members if PurePosixPath(m).name.lower() in {".ai-response.json", "ai-response.json"}]
    for member in sorted(candidates, key=lambda x: x.count("/")):
        try:
            data = json.loads(zf.read(member).decode("utf-8"))
            if isinstance(data, dict):
                return data, member
        except Exception:
            continue
    return {}, ""


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

    # Fallback: strip a common wrapper directory if every payload file shares one.
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
    # Keep at least the last directory containing files as project content, not wrapper.
    if common and len(common) < min(len(p) for p in split):
        prefix = "/".join(common)
        return (prefix + "/" if prefix else ""), 0
    return "", 0


def inspect_zip(model: ProjectModel, zip_path: Path) -> Optional[ImportInspection]:
    if not zip_path.exists() or zip_path.suffix.lower() != ".zip":
        return None

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = _safe_members(zf)
            if not members:
                return None
            manifest, manifest_member = _read_response_manifest(zf, members)
            manifest_entries = manifest.get("files", []) if isinstance(manifest.get("files", []), list) else []
            manifest_paths = {
                str(entry.get("path", "")).replace("\\", "/").strip("/")
                for entry in manifest_entries if isinstance(entry, dict) and entry.get("path")
            }
            known_paths = {rel for rel, _, _ in model.iter_files()}
            root_prefix, confidence = _infer_root(members, known_paths, manifest_paths)

            # A ZIP with neither known project path matches nor a response manifest is not treated as this project's response.
            if confidence == 0 and not manifest_paths:
                return None

            temp_dir = Path(tempfile.mkdtemp(prefix="transferloop_import_"))
            stage_root = temp_dir / "stage"
            stage_root.mkdir(parents=True, exist_ok=True)

            for member in members:
                if root_prefix and not member.startswith(root_prefix):
                    continue
                rel = member[len(root_prefix):] if root_prefix else member
                rel = rel.strip("/")
                if not rel or PurePosixPath(rel).name in META_FILES:
                    continue
                target = stage_root / Path(*PurePosixPath(rel).parts)
                target_resolved = target.resolve()
                if stage_root.resolve() not in target_resolved.parents:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

            notes_by_path: dict[str, dict] = {}
            for entry in manifest_entries:
                if isinstance(entry, dict) and entry.get("path"):
                    notes_by_path[str(entry["path"]).replace("\\", "/").strip("/")] = entry

            changes: list[ChangeItem] = []
            staged_files: set[str] = set()
            for path in stage_root.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(stage_root).as_posix()
                staged_files.add(rel)
                local = model.root / rel
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
                expected_action = str(entry.get("action", action)).lower()
                synced_hash = model.state.synced_hashes.get(rel)
                conflict = False
                if rel in model.state.diverged_paths:
                    conflict = True
                elif local.exists() and synced_hash:
                    try:
                        conflict = sha256_file(local) != synced_hash
                    except OSError:
                        conflict = True
                elif action == "added" and rel in model.state.synced_hashes:
                    conflict = True

                changes.append(ChangeItem(
                    path=rel,
                    action=action,
                    summary=str(entry.get("summary", "")),
                    details=list(entry.get("details", [])) if isinstance(entry.get("details", []), list) else [],
                    staged_path=str(path),
                    conflict=conflict,
                    unexpected=bool(notes_by_path) and rel not in notes_by_path,
                ))

            # Support explicit deletions from manifest.
            for rel, entry in notes_by_path.items():
                if str(entry.get("action", "")).lower() != "deleted":
                    continue
                local = model.root / rel
                if not local.exists():
                    continue
                synced_hash = model.state.synced_hashes.get(rel)
                conflict = False
                if rel in model.state.diverged_paths:
                    conflict = True
                elif synced_hash and local.is_file():
                    try:
                        conflict = sha256_file(local) != synced_hash
                    except OSError:
                        conflict = True
                changes.append(ChangeItem(
                    path=rel,
                    action="deleted",
                    summary=str(entry.get("summary", "")),
                    details=list(entry.get("details", [])) if isinstance(entry.get("details", []), list) else [],
                    staged_path="",
                    conflict=conflict,
                ))

            if not changes:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

            return ImportInspection(
                zip_path=str(zip_path),
                root_prefix=root_prefix,
                session_id=str(manifest.get("session_id", "")),
                overall_summary=str(manifest.get("summary", "")),
                changes=sorted(changes, key=lambda c: c.path.lower()),
                confidence=confidence,
                temp_dir=str(temp_dir),
            )
    except (zipfile.BadZipFile, OSError):
        return None


def build_text_diff(model: ProjectModel, change: ChangeItem) -> str:
    if change.action == "deleted":
        local = model.root / change.path
        if not local.exists() or not likely_text_file(local):
            return "Binary or unavailable file will be deleted."
        before = local.read_text(encoding="utf-8", errors="replace").splitlines()
        after: list[str] = []
    else:
        staged = Path(change.staged_path)
        local = model.root / change.path
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


def apply_changes(model: ProjectModel, inspection: ImportInspection, accepted_paths: set[str]) -> tuple[int, Path]:
    backup = create_backup_folder(model.root)
    changed_count = 0
    backup_manifest: dict = {"files": [], "source_zip": inspection.zip_path}

    for change in inspection.changes:
        if change.path not in accepted_paths:
            continue
        target = model.root / change.path
        backup_target = backup / change.path
        existed = target.exists()
        if existed and target.is_file():
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_target)

        backup_manifest["files"].append({
            "path": change.path,
            "existed": existed,
            "action": change.action,
        })

        if change.action == "deleted":
            if change.path == MEMORY_FILENAME:
                # .aimemory is app-managed and should never be removed by an AI response.
                # Treat an accepted delete as a no-op; the subsequent history append keeps
                # the managed memory present and authoritative.
                pass
            elif target.exists() and target.is_file():
                target.unlink()
        else:
            source = Path(change.staged_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if change.path == MEMORY_FILENAME:
                merge_incoming_memory_preserving_history(target, source)
            else:
                shutil.copy2(source, target)
        changed_count += 1

    save_json(backup / "backup_manifest.json", backup_manifest)
    model.state.last_backup = str(backup)

    rejected_paths = {change.path for change in inspection.changes if change.path not in accepted_paths}
    for rel in rejected_paths:
        if rel not in model.state.diverged_paths:
            model.state.diverged_paths.append(rel)
    model.state.save()
    model.mark_synced(accepted_paths)
    append_import_memory(model, inspection, accepted_paths, rejected_paths)
    # append_import_memory changes .aimemory after the accepted files are marked
    # synchronized. Record the final app-managed version so a later response does not
    # see APS's own history entry as a local conflict.
    model.mark_synced({MEMORY_FILENAME})

    # Once a response has actually been applied, remember its exact ZIP signature.
    # This prevents the watcher from rediscovering the same manually imported ZIP and
    # presenting the old pre-acceptance .aimemory as a brand-new response.
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
        "zip": inspection.zip_path,
        "accepted": sorted(accepted_paths),
        "rejected_or_unapplied": sorted(rejected_paths),
        "changes": [change.__dict__ for change in inspection.changes],
    }
    import datetime
    history_root = history_dir(model.root) / datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    history_root.mkdir(parents=True, exist_ok=True)
    response_files = history_root / "response_files"
    response_files.mkdir(parents=True, exist_ok=True)
    for change in inspection.changes:
        if change.staged_path and Path(change.staged_path).exists():
            dst = response_files / change.path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(change.staged_path, dst)
    save_json(history_root / "history.json", hist)
    return changed_count, backup


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
        rel = entry.get("path")
        if not rel:
            continue
        affected.append(rel)
        target = model.root / rel
        backup_file = backup / rel
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
    # The undo entry is itself an app-managed .aimemory change; keep its synchronized
    # hash aligned with the final memory file for future conflict checks.
    model.mark_synced({MEMORY_FILENAME})
    model.state.last_backup = ""
    model.state.save()
    return count
