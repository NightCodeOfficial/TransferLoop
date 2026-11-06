from __future__ import annotations

import ast
import copy
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .ignore import is_ignored
from .storage import snapshots_dir

if TYPE_CHECKING:
    from .project import ProjectModel

PROJECT_MAP_FILENAME = "PROJECT_MAP.json"
PROJECT_MAP_VERSION = 2

RELATIONSHIP_TYPES = {
    "imports",
    "uses",
    "calls",
    "tests",
    "opens",
    "reads",
    "writes",
    "signal",
    "depends_on",
}
RELATIONSHIP_SOURCES = {"static", "ai", "user", "heuristic"}


def project_map_path(project_root: Path) -> Path:
    return project_root / PROJECT_MAP_FILENAME


def _empty_map(project_name: str) -> dict[str, Any]:
    return {
        "format_version": PROJECT_MAP_VERSION,
        "project": {
            "name": project_name,
            "description": "",
        },
        "entries": {},
    }


def _normalize_symbol(symbol: Any) -> dict[str, str] | None:
    if not isinstance(symbol, dict):
        return None
    name = str(symbol.get("name", "")).strip()
    description = str(symbol.get("description", "")).strip()
    kind = str(symbol.get("kind", "symbol")).strip() or "symbol"
    if not name and not description:
        return None
    return {
        "name": name,
        "kind": kind,
        "description": description,
    }


def _normalize_relationship(relationship: Any) -> dict[str, Any] | None:
    if not isinstance(relationship, dict):
        return None
    target = str(relationship.get("target", "")).replace("\\", "/").strip("/")
    if not target:
        return None
    relation_type = str(relationship.get("type", "depends_on")).strip().lower() or "depends_on"
    source = str(relationship.get("source", "ai")).strip().lower() or "ai"
    if source not in RELATIONSHIP_SOURCES:
        source = "ai"
    description = str(relationship.get("description", "")).strip()
    symbols_raw = relationship.get("symbols", [])
    symbols = []
    if isinstance(symbols_raw, list):
        symbols = [str(value).strip() for value in symbols_raw if str(value).strip()]
    normalized: dict[str, Any] = {
        "target": target,
        "type": relation_type,
        "source": source,
        "description": description,
    }
    if symbols:
        normalized["symbols"] = symbols
    return normalized


def _normalize_entry(path: str, raw: Any, *, kind: str | None = None) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    resolved_kind = kind or str(source.get("kind", "file")).strip() or "file"
    symbols: list[dict[str, str]] = []
    relationships: list[dict[str, Any]] = []
    if resolved_kind == "file":
        raw_symbols = source.get("important_symbols", [])
        if isinstance(raw_symbols, list):
            for symbol in raw_symbols:
                normalized = _normalize_symbol(symbol)
                if normalized:
                    symbols.append(normalized)
        raw_relationships = source.get("relationships", [])
        if isinstance(raw_relationships, list):
            for relationship in raw_relationships:
                normalized = _normalize_relationship(relationship)
                if normalized:
                    relationships.append(normalized)
    return {
        "kind": resolved_kind,
        "description": str(source.get("description", "")).strip(),
        "important_symbols": symbols,
        "relationships": relationships,
    }




def _map_from_raw(raw: Any, fallback_name: str) -> dict[str, Any]:
    result = _empty_map(fallback_name)
    if not isinstance(raw, dict):
        return result
    project = raw.get("project", {})
    if isinstance(project, dict):
        result["project"]["name"] = str(project.get("name", fallback_name)).strip() or fallback_name
        result["project"]["description"] = str(project.get("description", "")).strip()
    raw_entries = raw.get("entries", {})
    if isinstance(raw_entries, dict):
        for rel, entry in raw_entries.items():
            normalized_rel = str(rel).replace("\\", "/").strip("/")
            if not normalized_rel:
                continue
            result["entries"][normalized_rel] = _normalize_entry(normalized_rel, entry)
    return result


def _load_map_file(path: Path, fallback_name: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        raw = {}
    return _map_from_raw(raw, fallback_name)


def _authored_projection(data: dict[str, Any]) -> dict[str, Any]:
    """Return only user/AI-authored map content, excluding generated structure/static links."""
    projected_entries: dict[str, Any] = {}
    for path, entry in data.get("entries", {}).items():
        if not isinstance(entry, dict):
            continue
        description = str(entry.get("description", "")).strip()
        symbols = entry.get("important_symbols", []) if entry.get("kind") == "file" else []
        authored_relationships = [
            rel
            for rel in entry.get("relationships", [])
            if isinstance(rel, dict) and rel.get("source") != "static"
        ]
        if not description and not symbols and not authored_relationships:
            continue
        projected_entries[path] = {
            "kind": entry.get("kind", "file"),
            "description": description,
            "important_symbols": symbols,
            "relationships": authored_relationships,
        }
    return {
        "project_description": str(data.get("project", {}).get("description", "")).strip(),
        "entries": projected_entries,
    }

def load_project_map(project_root: Path, project_name: str | None = None) -> dict[str, Any]:
    path = project_map_path(project_root)
    fallback_name = project_name or project_root.name
    return _load_map_file(path, fallback_name)


def save_project_map(project_root: Path, data: dict[str, Any]) -> Path:
    path = project_map_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = copy.deepcopy(data)
    normalized["format_version"] = PROJECT_MAP_VERSION
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def _discover_entries(model: "ProjectModel") -> dict[str, str]:
    """Return AI-visible project paths and their kinds without interpreting code."""
    patterns = model.patterns
    discovered: dict[str, str] = {}

    for base, dirs, files in os.walk(model.root):
        base_path = Path(base)
        try:
            rel_base = base_path.relative_to(model.root)
        except ValueError:
            continue
        rel_base_str = "" if str(rel_base) == "." else rel_base.as_posix()

        kept_dirs: list[str] = []
        for dirname in sorted(dirs, key=str.lower):
            rel = f"{rel_base_str}/{dirname}".strip("/")
            if dirname == "__pycache__" or is_ignored(rel, patterns, True):
                continue
            discovered[rel] = "directory"
            kept_dirs.append(dirname)
        dirs[:] = kept_dirs

        for filename in sorted(files, key=str.lower):
            rel = f"{rel_base_str}/{filename}".strip("/")
            if rel == PROJECT_MAP_FILENAME:
                # The map is navigation metadata; indexing itself adds noise and can
                # cause unnecessary self-rewrites when the structure changes.
                continue
            if is_ignored(rel, patterns, False):
                continue
            discovered[rel] = "file"

    return discovered


def _python_module_map(discovered: dict[str, str]) -> dict[str, str]:
    modules: dict[str, str] = {}
    for rel, kind in discovered.items():
        if kind != "file" or not rel.endswith(".py"):
            continue
        parts = rel[:-3].split("/")
        if parts[-1] == "__init__":
            module = ".".join(parts[:-1])
        else:
            module = ".".join(parts)
        if module:
            modules[module] = rel
    return modules


def _resolve_module(module: str, module_map: dict[str, str]) -> str | None:
    candidate = module.strip(".")
    while candidate:
        if candidate in module_map:
            return module_map[candidate]
        if "." not in candidate:
            break
        candidate = candidate.rsplit(".", 1)[0]
    return None


def _relative_import_base(source_rel: str, level: int, module: str | None) -> str:
    source_module = source_rel[:-3].replace("/", ".")
    if source_module.endswith(".__init__"):
        package_parts = source_module[: -len(".__init__")].split(".")
    else:
        package_parts = source_module.split(".")[:-1]
    if level > 0:
        trim = max(0, level - 1)
        if trim:
            package_parts = package_parts[: max(0, len(package_parts) - trim)]
    elif level == 0:
        package_parts = []
    module_parts = module.split(".") if module else []
    return ".".join([*package_parts, *module_parts])


def _static_python_relationships(
    project_root: Path,
    discovered: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    """Infer deterministic file relationships from project-local Python imports."""
    module_map = _python_module_map(discovered)
    result: dict[str, list[dict[str, Any]]] = {}

    for source_rel, kind in discovered.items():
        if kind != "file" or not source_rel.endswith(".py"):
            continue
        try:
            source_text = (project_root / source_rel).read_text(encoding="utf-8")
            tree = ast.parse(source_text, filename=source_rel)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue

        targets: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _resolve_module(alias.name, module_map)
                    if target and target != source_rel:
                        targets.add(target)
            elif isinstance(node, ast.ImportFrom):
                base = _relative_import_base(source_rel, node.level, node.module)
                candidates = []
                for alias in node.names:
                    if alias.name != "*":
                        candidates.append(".".join(part for part in (base, alias.name) if part))
                if base:
                    candidates.append(base)
                for candidate in candidates:
                    target = _resolve_module(candidate, module_map)
                    if target and target != source_rel:
                        targets.add(target)
                        # An ImportFrom statement belongs to one module in the usual
                        # case. Stop after the first project-local resolution.
                        break

        if not targets:
            continue
        is_test_source = source_rel.startswith("tests/") or Path(source_rel).name.startswith("test_")
        relationships = []
        for target in sorted(targets, key=str.lower):
            relation_type = "tests" if is_test_source and not target.startswith("tests/") else "imports"
            description = (
                f"Tests functionality from {target}."
                if relation_type == "tests"
                else f"Imports project module {target}."
            )
            relationships.append(
                {
                    "target": target,
                    "type": relation_type,
                    "source": "static",
                    "description": description,
                }
            )
        result[source_rel] = relationships

    return result


def sync_project_map(model: "ProjectModel") -> tuple[Path, bool]:
    """Synchronize paths and static relationships while preserving authored map notes.

    TransferLoop owns the structural index and statically verified relationships.
    Descriptions, important-symbol notes, and non-static architectural relationships
    remain authored by an AI or the user.
    """
    path = project_map_path(model.root)
    existing = load_project_map(model.root, model.state.name)
    updated = copy.deepcopy(existing)
    updated["format_version"] = PROJECT_MAP_VERSION
    updated["project"]["name"] = model.state.name

    discovered = _discover_entries(model)
    static_relationships = _static_python_relationships(model.root, discovered)
    previous_entries = existing.get("entries", {})
    entries: dict[str, dict[str, Any]] = {}
    for rel in sorted(discovered, key=lambda value: (value.count("/"), value.lower())):
        kind = discovered[rel]
        entry = _normalize_entry(rel, previous_entries.get(rel, {}), kind=kind)
        if kind == "file":
            authored_relationships = [
                relation
                for relation in entry.get("relationships", [])
                if relation.get("source") != "static" and relation.get("target") in discovered
            ]
            entry["relationships"] = [*static_relationships.get(rel, []), *authored_relationships]
        entries[rel] = entry
    updated["entries"] = entries

    changed = updated != existing or not path.exists()
    if changed:
        save_project_map(model.root, updated)
    return path, changed


def sync_project_map_managed(model: "ProjectModel") -> tuple[Path, bool, bool]:
    """Synchronize the generated map without reporting TransferLoop's own rewrite as a user edit.

    If the existing map matched the current AI sync baseline before the refresh (or the
    map did not exist yet), a structural/static rewrite is app-managed metadata. In that
    case TransferLoop advances only PROJECT_MAP.json in the current sync baseline after
    regenerating it. If the map was already locally modified, its authored edits remain
    divergent and are never auto-accepted.

    Returns ``(path, changed, baseline_advanced)``.
    """
    path = project_map_path(model.root)
    existed_before = path.is_file()
    baseline_hash = model.state.synced_hashes.get(PROJECT_MAP_FILENAME)

    before_hash: str | None = None
    if existed_before:
        try:
            from .project import sha256_file

            before_hash = sha256_file(path)
        except OSError:
            before_hash = None

    was_clean = bool(baseline_hash and before_hash == baseline_hash)
    if baseline_hash and existed_before and not was_clean:
        # A Project Map can differ from its baseline solely because TransferLoop
        # regenerated paths/static relationships after source changes. Treat that
        # as clean when all authored descriptions, symbols, and non-static links
        # still match the stored sync snapshot.
        baseline_snapshot = snapshots_dir(model.root) / PROJECT_MAP_FILENAME
        if baseline_snapshot.is_file():
            existing_map = load_project_map(model.root, model.state.name)
            baseline_map = _load_map_file(baseline_snapshot, model.state.name)
            was_clean = _authored_projection(existing_map) == _authored_projection(baseline_map)
    generated_new = not existed_before and baseline_hash is None

    path, changed = sync_project_map(model)
    baseline_advanced = False
    after_hash: str | None = None
    if path.is_file():
        try:
            from .project import sha256_file

            after_hash = sha256_file(path)
        except OSError:
            after_hash = None
    needs_baseline_advance = bool(after_hash and after_hash != baseline_hash)
    if model.state.initialized and (was_clean or generated_new) and needs_baseline_advance:
        model.mark_synced([PROJECT_MAP_FILENAME])
        baseline_advanced = True
    return path, changed, baseline_advanced


def entry_status(entry: dict[str, Any]) -> str:
    """Return a documentation status suitable for both the GUI and coverage counts."""
    if not str(entry.get("description", "")).strip():
        return "missing"
    if entry.get("kind") == "file":
        for symbol in entry.get("important_symbols", []):
            if not str(symbol.get("name", "")).strip() or not str(symbol.get("description", "")).strip():
                return "needs_review"
        for relationship in entry.get("relationships", []):
            if relationship.get("source") == "static":
                continue
            if not str(relationship.get("target", "")).strip() or not str(relationship.get("type", "")).strip():
                return "needs_review"
    return "documented"


def coverage_summary(data: dict[str, Any]) -> dict[str, int]:
    entries = data.get("entries", {}) if isinstance(data, dict) else {}
    counts = {"total": 0, "documented": 0, "needs_review": 0, "missing": 0, "files": 0, "directories": 0}
    if not isinstance(entries, dict):
        return counts
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        counts["total"] += 1
        if entry.get("kind") == "directory":
            counts["directories"] += 1
        else:
            counts["files"] += 1
        status = entry_status(entry)
        counts[status] += 1
    return counts


def relationship_index(data: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    """Return outgoing/incoming relationship indexes keyed by project-relative path."""
    entries = data.get("entries", {}) if isinstance(data, dict) else {}
    outgoing: dict[str, list[dict[str, Any]]] = {}
    incoming: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(entries, dict):
        return outgoing, incoming
    for source, entry in entries.items():
        if not isinstance(entry, dict) or entry.get("kind") != "file":
            continue
        for relation in entry.get("relationships", []):
            normalized = _normalize_relationship(relation)
            if not normalized:
                continue
            target = normalized["target"]
            if target not in entries:
                continue
            outgoing.setdefault(source, []).append(normalized)
            incoming.setdefault(target, []).append({**normalized, "source_path": source})
    return outgoing, incoming
