from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from .instructions import write_exported_instructions
from .memory import MEMORY_FILENAME, ensure_memory, refresh_memory_overview
from .project import ProjectModel


@dataclass(frozen=True)
class ExportArtifacts:
    zip_path: Path
    instructions_path: Path
    mode: str
    exported_paths: tuple[str, ...]


def export_package(model: ProjectModel, relative_paths: list[str], destination: Path, mode: str) -> ExportArtifacts:
    """Create the project ZIP plus a separate AI instructions Markdown file.

    Generated AI workflow/context files are intentionally not inserted into the project ZIP. The ZIP contains
    project files only (including project-owned `.aiignore`/`.aimemory` when selected). The companion Markdown
    file tells the AI how TransferLoop works and how response ZIPs must be formatted.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    model.state.ensure_session()

    if mode == "all":
        refresh_memory_overview(model)
        ensure_memory(model)
        if MEMORY_FILENAME not in relative_paths:
            relative_paths = [*relative_paths, MEMORY_FILENAME]

    # Export only paths that are still part of the current AI-visible project.
    # This matters when .aiignore changes after a previous synchronization: stale
    # tracked paths must not leak back into a changed export just because the files
    # still exist on disk.
    existing_paths = sorted({
        rel.replace("\\", "/").strip("/")
        for rel in relative_paths
        if rel
        and not model.is_ignored_path(rel)
        and (model.root / rel).is_file()
    })

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in existing_paths:
            zf.write(model.root / rel, arcname=rel)

    instructions_path = write_exported_instructions(model, destination, mode, existing_paths)
    model.mark_synced(existing_paths, initialize=(mode == "all"))
    return ExportArtifacts(
        zip_path=destination,
        instructions_path=instructions_path,
        mode=mode,
        exported_paths=tuple(existing_paths),
    )
