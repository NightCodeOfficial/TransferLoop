from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from .importer import ChangeItem, ImportInspection
    from .project import ProjectModel

MEMORY_FILENAME = ".aimemory"
ENTRY_MARKER = "<!-- TL:MEMORY-ENTRY -->"
MEMORY_ENTRY_RE = re.compile(r"<!-- (?:TL|APS):MEMORY-ENTRY -->")
MAX_DETAILED_ENTRIES = 12
HISTORY_HEADING = "## Accepted Change History"
STRUCTURED_MEMORY_SECTIONS = {
    "current_direction": ("## Current Direction", "- No durable direction has been recorded yet."),
    "decisions": ("## Architecture & Important Decisions", "- No durable decisions have been recorded yet."),
    "constraints": ("## Constraints & Conventions", "- No durable constraints have been recorded yet."),
    "open_work": ("## Open Work", "- No open work has been recorded yet."),
    "project_notes": ("## Project Notes", "- No additional durable project notes have been recorded yet."),
}


def memory_path(project_root: Path) -> Path:
    return project_root / MEMORY_FILENAME


def _migrate_memory_branding(path: Path) -> None:
    """Update current memory metadata while preserving accepted history verbatim."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    before_history, separator, history = text.partition(HISTORY_HEADING)
    migrated = before_history.replace("AI Project Sync", "TransferLoop")
    if migrated == before_history:
        return
    updated = migrated + (separator + history if separator else "")
    path.write_text(updated, encoding="utf-8")


def _detect_technical_snapshot(model: "ProjectModel") -> list[str]:
    extensions: dict[str, int] = {}
    folders: list[str] = []
    try:
        for child in sorted(model.root.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir() and not child.name.startswith("."):
                folders.append(child.name)
    except OSError:
        pass

    for rel, path, ignored in model.iter_files():
        if ignored or rel == MEMORY_FILENAME:
            continue
        suffix = path.suffix.lower()
        if suffix:
            extensions[suffix] = extensions.get(suffix, 0) + 1

    language_map = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript/React",
        ".jsx": "JavaScript/React", ".cs": "C#", ".java": "Java", ".cpp": "C++", ".c": "C",
        ".go": "Go", ".rs": "Rust", ".php": "PHP", ".rb": "Ruby", ".swift": "Swift",
    }
    ranked = sorted(extensions.items(), key=lambda kv: (-kv[1], kv[0]))
    languages = []
    for ext, _count in ranked:
        name = language_map.get(ext)
        if name and name not in languages:
            languages.append(name)
        if len(languages) >= 3:
            break

    lines = []
    if languages:
        lines.append(f"- Primary technologies detected: {', '.join(languages)}")
    if folders:
        shown = folders[:10]
        suffix = f" (+{len(folders) - len(shown)} more)" if len(folders) > len(shown) else ""
        lines.append(f"- Top-level folders: {', '.join(shown)}{suffix}")
    if (model.root / "requirements.txt").exists():
        try:
            requirements = (model.root / "requirements.txt").read_text(encoding="utf-8", errors="replace").lower()
            if "pyside6" in requirements:
                lines.append("- UI framework detected: PySide6 / Qt")
            elif "pyqt" in requirements:
                lines.append("- UI framework detected: PyQt / Qt")
        except OSError:
            pass
    return lines or ["- Technical details will be inferred from the current project files."]


def _section_bounds(text: str, heading: str) -> tuple[int, int] | None:
    start = text.find(heading)
    if start == -1:
        return None
    search_from = start + len(heading)
    next_heading = re.search(r"^## ", text[search_from:], flags=re.MULTILINE)
    end = search_from + next_heading.start() if next_heading else len(text)
    return start, end


def _ensure_structured_sections(path: Path) -> None:
    """Add durable project-memory sections to older .aimemory files in place."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    if all(heading in text for heading, _placeholder in STRUCTURED_MEMORY_SECTIONS.values()):
        return

    insert_at = text.find("## Important Memory Rules")
    if insert_at == -1:
        insert_at = text.find(HISTORY_HEADING)
    if insert_at == -1:
        insert_at = len(text)

    missing = []
    for heading, placeholder in STRUCTURED_MEMORY_SECTIONS.values():
        if heading not in text:
            missing.append(f"{heading}\n\n{placeholder}\n")
    if not missing:
        return

    prefix = text[:insert_at].rstrip()
    suffix = text[insert_at:].lstrip()
    updated = prefix + "\n\n" + "\n".join(missing).rstrip() + "\n\n" + suffix
    path.write_text(updated.rstrip() + "\n", encoding="utf-8")


def apply_memory_updates(model: "ProjectModel", updates: dict[str, list[str]]) -> Path:
    """Merge user-approved durable AI memory suggestions into managed sections."""
    path = ensure_memory(model)
    text = path.read_text(encoding="utf-8", errors="replace")

    for key, values in updates.items():
        if key not in STRUCTURED_MEMORY_SECTIONS or not isinstance(values, list):
            continue
        clean_values = []
        seen = set()
        for value in values:
            item = " ".join(str(value).strip().split())
            if not item or item.casefold() in seen:
                continue
            seen.add(item.casefold())
            clean_values.append(item[:600])
        if not clean_values:
            continue

        heading, placeholder = STRUCTURED_MEMORY_SECTIONS[key]
        bounds = _section_bounds(text, heading)
        if not bounds:
            continue
        start, end = bounds
        section = text[start:end]
        existing = []
        for line in section.splitlines()[1:]:
            stripped = line.strip()
            if stripped.startswith("- ") and stripped != placeholder:
                existing.append(stripped[2:].strip())
        merged = []
        merged_seen = set()
        for item in [*existing, *clean_values]:
            if item.casefold() in merged_seen:
                continue
            merged_seen.add(item.casefold())
            merged.append(item)
        replacement = heading + "\n\n" + "\n".join(f"- {item}" for item in merged) + "\n\n"
        text = text[:start] + replacement + text[end:].lstrip("\n")

    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path


def ensure_memory(model: "ProjectModel") -> Path:
    path = memory_path(model.root)
    if path.exists():
        _migrate_memory_branding(path)
        _ensure_structured_sections(path)
        return path

    context = model.state.project_context.strip() or (
        f"{model.state.name} is a software project managed with TransferLoop. "
        "No custom project description has been entered yet; inspect the current files for authoritative implementation details."
    )
    snapshot = "\n".join(_detect_technical_snapshot(model))
    text = f"""# AI Project Memory

> This file is maintained by TransferLoop. It gives a new AI conversation durable project context plus a short recent history of changes actually accepted into the local project.

## Project Overview

**Project:** {model.state.name}

{context}

## Technical Snapshot

{snapshot}

## Current Direction

- No durable direction has been recorded yet.

## Architecture & Important Decisions

- No durable decisions have been recorded yet.

## Constraints & Conventions

- No durable constraints have been recorded yet.

## Open Work

- No open work has been recorded yet.

## Project Notes

- No additional durable project notes have been recorded yet.

## Important Memory Rules

- Current project files are authoritative if this memory ever becomes stale.
- Change-history entries below describe changes accepted through TransferLoop, not merely changes an AI proposed.
- AI assistants should not modify this file during normal implementation work unless the user explicitly asks them to.

## Accepted Change History

No TransferLoop imports have been accepted yet.
"""
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path


def refresh_memory_overview(model: "ProjectModel") -> Path:
    """Refresh a newly-created/default overview without destroying existing history."""
    path = ensure_memory(model)
    text = path.read_text(encoding="utf-8", errors="replace")
    start = text.find("## Project Overview")
    end = text.find("## Technical Snapshot")
    if start == -1 or end == -1 or end <= start:
        return path
    context = model.state.project_context.strip() or (
        f"{model.state.name} is a software project managed with TransferLoop. "
        "No custom project description has been entered yet; inspect the current files for authoritative implementation details."
    )
    replacement = f"## Project Overview\n\n**Project:** {model.state.name}\n\n{context}\n\n"
    updated = text[:start] + replacement + text[end:]
    path.write_text(updated.rstrip() + "\n", encoding="utf-8")
    return path


def merge_incoming_memory_preserving_history(local_path: Path, incoming_path: Path) -> None:
    """Apply an AI-authored .aimemory update without allowing it to rewrite TransferLoop history.

    TransferLoop owns the Accepted Change History section. The AI may update the
    project context around it when the user explicitly requests that, but the
    existing local history must survive verbatim.
    """
    incoming = incoming_path.read_text(encoding="utf-8", errors="replace")
    if not local_path.exists():
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(incoming.rstrip() + "\n", encoding="utf-8")
        return

    local = local_path.read_text(encoding="utf-8", errors="replace")
    local_start = local.find(HISTORY_HEADING)
    if local_start == -1:
        local_path.write_text(incoming.rstrip() + "\n", encoding="utf-8")
        return

    # Accepted Change History is intentionally the final managed section today. If
    # the incoming file also contains the heading, replace that incoming section with
    # the authoritative local one. If it omits the heading entirely, append the local
    # managed history after the AI-authored context.
    local_history = local[local_start:].rstrip()
    incoming_start = incoming.find(HISTORY_HEADING)
    if incoming_start == -1:
        merged = incoming.rstrip() + "\n\n" + local_history + "\n"
    else:
        merged = incoming[:incoming_start].rstrip() + "\n\n" + local_history + "\n"

    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(merged, encoding="utf-8")


def _entry_for_change(change: "ChangeItem") -> list[str]:
    action = change.action.capitalize()
    lines = [f"- **{action}:** `{change.path}`"]
    if change.summary:
        lines.append(f"  - {change.summary.strip()}")
    for detail in change.details:
        if str(detail).strip():
            lines.append(f"  - {str(detail).strip()}")
    return lines


def append_import_memory(
    model: "ProjectModel",
    inspection: "ImportInspection",
    accepted_paths: set[str],
    rejected_paths: set[str],
) -> Path:
    path = ensure_memory(model)
    text = path.read_text(encoding="utf-8", errors="replace")
    text = text.replace("\nNo TransferLoop imports have been accepted yet.\n", "\n")
    text = text.replace("\nNo AI Project Sync imports have been accepted yet.\n", "\n")

    accepted_changes = [c for c in inspection.changes if c.path in accepted_paths]
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = inspection.overall_summary.strip() or "TransferLoop import"
    lines = [ENTRY_MARKER, f"### {stamp} — {title}", ""]
    if accepted_changes:
        lines.append("**Accepted changes**")
        lines.append("")
        for change in accepted_changes:
            lines.extend(_entry_for_change(change))
    else:
        lines.extend(["No proposed project-file changes were accepted."])

    if rejected_paths:
        lines.extend(["", "**Rejected / not applied**", ""])
        for rel in sorted(rejected_paths):
            lines.append(f"- `{rel}`")
    lines.append("")
    entry = "\n".join(lines)

    history_heading = HISTORY_HEADING
    heading_index = text.find(history_heading)
    if heading_index == -1:
        text = text.rstrip() + f"\n\n{history_heading}\n\n"
    text = text.rstrip() + "\n\n" + entry

    # Keep the memory useful as AI context rather than allowing an unbounded detailed log.
    # Legacy APS markers remain readable so existing projects do not lose history after rebranding.
    markers = list(MEMORY_ENTRY_RE.finditer(text))
    if len(markers) > MAX_DETAILED_ENTRIES:
        intro = text[:markers[0].start()].rstrip()
        recent_start = markers[-MAX_DETAILED_ENTRIES].start()
        note = (
            "\n\n> Older detailed TransferLoop history was compacted from `.aimemory`. "
            "The application's own history retains the full audit trail.\n\n"
        )
        text = intro + note + text[recent_start:].lstrip()

    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path


def append_undo_memory(model: "ProjectModel", affected_paths: Iterable[str]) -> Path:
    path = ensure_memory(model)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        ENTRY_MARKER,
        f"### {stamp} — Reverted previous AI merge",
        "",
        "The user used TransferLoop's undo operation to restore the pre-merge versions of:",
        "",
    ]
    for rel in sorted(set(affected_paths)):
        lines.append(f"- `{rel}`")
    with path.open("a", encoding="utf-8") as f:
        f.write("\n" + "\n".join(lines).rstrip() + "\n")
    return path
