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
    export_id: str
    exported_paths: tuple[str, ...]
    deleted_paths: tuple[str, ...]


def export_package(model: ProjectModel, relative_paths: list[str], destination: Path, mode: str) -> ExportArtifacts:
    """Create a project ZIP plus a separate AI instructions Markdown file.

    Generated workflow/context metadata stays in the companion Markdown file instead
    of being inserted into the source ZIP. Changed exports explicitly record paths
    deleted since the previous export so deletion state is not silently lost.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    model.state.ensure_session()

    if mode == "all":
        refresh_memory_overview(model)
        ensure_memory(model)
        if MEMORY_FILENAME not in relative_paths:
            relative_paths = [*relative_paths, MEMORY_FILENAME]

    normalized = sorted({
        rel.replace("\\", "/").strip("/")
        for rel in relative_paths
        if rel and not model.is_ignored_path(rel)
    })
    existing_paths = tuple(
        rel for rel in normalized
        if (model.root / rel).is_file()
    )
    deleted_paths = tuple(
        rel for rel in normalized
        if not (model.root / rel).exists() and rel in model.state.synced_hashes
    )

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in existing_paths:
            zf.write(model.root / rel, arcname=rel)

    # Mark both present and deleted paths synchronized. Previously only files that
    # still existed were marked, causing a deletion to remain permanently "changed".
    model.mark_synced([*existing_paths, *deleted_paths], initialize=(mode == "all"))
    export_id = model.state.next_export_id()
    model.record_export_baseline(export_id)

    instructions_path = write_exported_instructions(
        model,
        destination,
        mode,
        existing_paths,
        deleted_paths=deleted_paths,
        export_id=export_id,
    )
    return ExportArtifacts(
        zip_path=destination,
        instructions_path=instructions_path,
        mode=mode,
        export_id=export_id,
        exported_paths=existing_paths,
        deleted_paths=deleted_paths,
    )
