from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable, TYPE_CHECKING

from .storage import app_data_dir, project_store_dir

if TYPE_CHECKING:
    from .project import ProjectModel


BASE_INSTRUCTIONS_TEMPLATE = r"""# TransferLoop Instructions

## What This Workflow Is

You are working with a local software project through **TransferLoop**. You do not have direct access to the user's computer. The user manually uploads project context to this conversation and later downloads the files you return. TransferLoop then stages your response, compares it with the authoritative local project, shows the user the actual changes, and merges only the changes the user accepts.

The conversation may continue for several rounds before implementation is complete. Discuss requirements, ask questions, propose approaches, and revise plans normally. Do **not** assume every user message requires an immediate ZIP response. When the user asks you to provide implemented project changes, follow the response protocol below.

## How To Read Incoming Project Context

- Treat files supplied by the user through TransferLoop as authoritative current local versions.
- If a newly supplied file differs from a version you saw earlier in the conversation, the newly supplied file wins.
- A full/new-session export represents the current project state for a new AI conversation.
- An incremental export may contain only files that changed locally or files the user intentionally selected. Replace your previous understanding of those paths with the newly supplied versions.
- Read `.aimemory` when it is present. It contains the project's purpose, important context, and recent **accepted** changes from prior TransferLoop imports.
- If `.aimemory` conflicts with the actual project files, the current project files are authoritative.
- Do not modify `.aimemory` as part of normal implementation work unless the user explicitly asks you to. TransferLoop maintains it after accepted imports.
- If durable project knowledge changed, you may propose concise memory updates in `.ai-response.json` using the optional `memory_updates` object described below. Do not use it as a chat transcript.
- If the user explicitly asks you to edit `.aimemory`, preserve its existing `## Accepted Change History` section exactly. TransferLoop owns that section and appends accepted/reverted events itself.
- `.aiignore`, when present, describes local files that should not normally be sent through TransferLoop. Do not infer that ignored files should be created, deleted, or modified.

## Development Rules

- Preserve existing functionality unless the user explicitly asks to remove or replace it.
- Do not make unrelated changes.
- Prefer targeted edits over unnecessary rewrites.
- Follow the project's existing architecture, naming, and style where practical.
- Return complete resulting files, not patches, snippets, or instructions telling the user what to paste.
- Do not silently remove features to simplify implementation.
- Avoid adding new dependencies unless they are needed. If you add one, clearly mention it in the response notes.
- Do not include generated binaries, virtual environments, caches, credentials, secrets, or unrelated build output in your response.

## AI Response ZIP Protocol

When implementation is ready and the user asks for the changed files, return **one ZIP** containing only the project files that were added or modified, plus a response manifest named `.ai-response.json`.

### Project-relative paths

Preserve each file's project-relative path exactly.

For example, if the project file is:

```text
ui/project_page.py
```

the returned ZIP should contain:

```text
ui/project_page.py
```

Do not intentionally return absolute paths such as `C:/Users/...`, and never use `..` path traversal. Prefer placing the project-relative files directly at the ZIP root. If your execution environment automatically adds one or more wrapper folders, TransferLoop will attempt to locate the actual project root, but clean project-relative ZIP structure is preferred.

### Which files to include

- Include every project file you actually modified.
- Include every newly created project file.
- Do not include unchanged project files merely for completeness.
- Return the complete final contents of each included file.
- Do not include `.aimemory` unless the user explicitly requested a change to that file.
- A file is **not** considered deleted merely because it is absent from your ZIP. Deletions must be explicitly declared in `.ai-response.json`.

### `.ai-response.json`

The manifest must be valid UTF-8 JSON and use this shape:

```json
{
  "format_version": 1,
  "session_id": "SESSION_ID",
  "export_id": "EXPORT_ID",
  "summary": "Concise overall summary of the completed change",
  "files": [
    {
      "path": "relative/path/to/file.py",
      "action": "modified",
      "summary": "What changed in this file",
      "details": [
        "Optional additional detail",
        "Another useful review note"
      ]
    }
  ]
}
```

Rules for the manifest:

- `format_version` must be `1`.
- `session_id` must match the TransferLoop session ID supplied below.
- `export_id` should match the exact TransferLoop export ID supplied below. It lets TransferLoop compare your response with the precise project baseline you received.
- `summary` should describe the completed update in plain language.
- `files` must contain one entry for every modified, added, or deleted project file.
- `path` must be the project-relative path using forward slashes.
- `action` must be one of: `modified`, `added`, or `deleted`.
- `summary` should briefly explain what changed in that specific file.
- `details` should be a JSON array of concise review notes. It may be empty.
- Every modified or added file listed in the manifest must also be present in the ZIP.
- Every modified or added project file present in the ZIP must have a corresponding manifest entry.
- For `deleted` files, list the path in the manifest but do not create a placeholder file in the ZIP.

TransferLoop independently verifies the ZIP contents and does not blindly trust the manifest. The notes are for explaining intent; the application determines what actually changed.

### Optional durable memory updates

When implementation establishes durable project knowledge that will help a future AI conversation, `.ai-response.json` may include a `memory_updates` object with any of these arrays: `current_direction`, `decisions`, `constraints`, `open_work`, and `project_notes`. Keep entries concise and factual. Do not include temporary discussion, rejected ideas, or a turn-by-turn transcript. TransferLoop presents these separately from file changes so the user can choose whether to keep them.

## After You Return A ZIP

TransferLoop may allow the user to accept some changes and reject others. If the user later supplies newer versions of any files, those newly supplied versions are authoritative even when they differ from the ZIP you previously returned. Continue from the newest supplied project state rather than assuming all earlier proposed changes were accepted.
"""


def _migrate_legacy_branding(text: str) -> str:
    """Update the former product name without changing user-authored workflow content."""
    return text.replace("AI Project Sync", "TransferLoop")


def _migrate_protocol_additions(text: str) -> str:
    """Add newer protocol fields to stored/custom instructions without replacing user text."""
    migrated = text
    if '"export_id": "EXPORT_ID"' not in migrated:
        migrated = migrated.replace(
            '"session_id": "SESSION_ID",',
            '"session_id": "SESSION_ID",\n  "export_id": "EXPORT_ID",',
        )
    export_rule = '- `export_id` should match the exact TransferLoop export ID supplied below.'
    if export_rule not in migrated:
        migrated = migrated.replace(
            '- `session_id` must match the TransferLoop session ID supplied below.',
            '- `session_id` must match the TransferLoop session ID supplied below.\n'
            + export_rule
            + ' It lets TransferLoop compare your response with the precise project baseline you received.',
        )
    memory_rule = '- If durable project knowledge changed, you may propose concise memory updates in `.ai-response.json` using the optional `memory_updates` object described below. Do not use it as a chat transcript.'
    if memory_rule not in migrated:
        migrated = migrated.replace(
            '- Do not modify `.aimemory` as part of normal implementation work unless the user explicitly asks you to. TransferLoop maintains it after accepted imports.',
            '- Do not modify `.aimemory` as part of normal implementation work unless the user explicitly asks you to. TransferLoop maintains it after accepted imports.\n' + memory_rule,
        )
    if '### Optional durable memory updates' not in migrated:
        anchor = 'TransferLoop independently verifies the ZIP contents and does not blindly trust the manifest. The notes are for explaining intent; the application determines what actually changed.'
        addition = (
            anchor
            + '\n\n### Optional durable memory updates\n\n'
            + 'When implementation establishes durable project knowledge that will help a future AI conversation, `.ai-response.json` may include a `memory_updates` object with any of these arrays: `current_direction`, `decisions`, `constraints`, `open_work`, and `project_notes`. Keep entries concise and factual. Do not include temporary discussion, rejected ideas, or a turn-by-turn transcript. TransferLoop presents these separately from file changes so the user can choose whether to keep them.'
        )
        migrated = migrated.replace(anchor, addition)
    return migrated


def _migrate_instruction_file(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    migrated = _migrate_protocol_additions(_migrate_legacy_branding(text))
    if migrated != text:
        path.write_text(migrated, encoding="utf-8")


def base_template_path() -> Path:
    return app_data_dir() / "base_ai_instructions.md"


def ensure_base_template() -> Path:
    path = base_template_path()
    if not path.exists():
        path.write_text(BASE_INSTRUCTIONS_TEMPLATE.strip() + "\n", encoding="utf-8")
    else:
        _migrate_instruction_file(path)
    return path


def read_base_template() -> str:
    path = ensure_base_template()
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return BASE_INSTRUCTIONS_TEMPLATE.strip() + "\n"


def save_base_template(text: str) -> None:
    path = ensure_base_template()
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def project_instructions_path(project_root: Path) -> Path:
    return project_store_dir(project_root) / "AI_PROJECT_INSTRUCTIONS.md"


def ensure_project_instructions(project_root: Path, legacy_project_instructions: str = "") -> Path:
    path = project_instructions_path(project_root)
    if not path.exists():
        shutil.copy2(ensure_base_template(), path)
        legacy = legacy_project_instructions.strip()
        if legacy:
            with path.open("a", encoding="utf-8") as f:
                f.write("\n## Project-Specific Instructions\n\n")
                f.write(_migrate_legacy_branding(legacy))
                f.write("\n")
    else:
        _migrate_instruction_file(path)
    return path


def read_project_instructions(project_root: Path, legacy_project_instructions: str = "") -> str:
    path = ensure_project_instructions(project_root, legacy_project_instructions)
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return read_base_template()


def save_project_instructions(project_root: Path, text: str) -> Path:
    path = ensure_project_instructions(project_root)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path


def reset_project_instructions_to_base(project_root: Path) -> str:
    text = read_base_template()
    save_project_instructions(project_root, text)
    return text


def _format_paths(paths: Iterable[str], limit: int = 120) -> str:
    ordered = sorted({p.replace("\\", "/") for p in paths if p})
    if not ordered:
        return "- No project files were included in this export."
    visible = ordered[:limit]
    lines = [f"- `{path}`" for path in visible]
    if len(ordered) > limit:
        lines.append(f"- …and {len(ordered) - limit} additional files")
    return "\n".join(lines)


def render_session_instructions(
    model: "ProjectModel",
    mode: str,
    exported_paths: Iterable[str],
    *,
    deleted_paths: Iterable[str] = (),
    export_id: str = "",
) -> str:
    base = read_project_instructions(model.root, model.state.project_instructions).rstrip()
    session_id = model.state.ensure_session()
    export_id = export_id or model.state.last_export_id
    context = model.state.project_context.strip() or (
        "No custom project description has been entered yet. Read `.aimemory` and inspect the supplied project files to establish context."
    )
    mode_explanation = {
        "all": "This is a full project-context export. Treat the accompanying ZIP as the current authoritative project state for this session.",
        "changed": "This is an incremental synchronization export. Supplied files replace older versions, and paths listed as deleted below no longer exist locally.",
        "selected": "This is a user-selected context export. The supplied paths are authoritative current versions and should update your working understanding of those files.",
    }.get(mode, "The accompanying ZIP contains authoritative current project files.")

    deleted = tuple(sorted({p.replace("\\", "/") for p in deleted_paths if p}))
    deleted_section = ""
    if deleted:
        deleted_section = f"""

### Paths deleted locally since the previous export

These paths are intentionally absent from the ZIP because they no longer exist in the local project. Update your working understanding accordingly. Do not recreate them unless the user asks for that.

{_format_paths(deleted)}
"""

    return f"""{base}

---

# Current TransferLoop Session

- **Project:** {model.state.name}
- **TransferLoop session ID:** `{session_id}`
- **TransferLoop export ID:** `{export_id or 'Unavailable'}`
- **Export type:** `{mode}`

## Current project description

{context}

## Context supplied with this export

{mode_explanation}

The project ZIP is a separate attachment. Read these instructions first, then inspect that ZIP and read `.aimemory` inside it when present.

### Files supplied in this export

{_format_paths(exported_paths)}{deleted_section}

When you later return implemented changes, use the `.ai-response.json` protocol above and preserve both the session ID `{session_id}` and export ID `{export_id}`.
"""

def exported_instructions_path(zip_path: Path) -> Path:
    return zip_path.with_name(f"{zip_path.stem}_AI_INSTRUCTIONS.md")


def write_exported_instructions(
    model: "ProjectModel",
    zip_path: Path,
    mode: str,
    exported_paths: Iterable[str],
    *,
    deleted_paths: Iterable[str] = (),
    export_id: str = "",
) -> Path:
    path = exported_instructions_path(zip_path)
    path.write_text(
        render_session_instructions(
            model, mode, exported_paths, deleted_paths=deleted_paths, export_id=export_id
        ).rstrip() + "\n",
        encoding="utf-8",
    )
    return path
