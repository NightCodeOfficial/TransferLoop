from __future__ import annotations

import fnmatch
from pathlib import Path

DEFAULT_AIIGNORE = """# TransferLoop recommended exclusions
# Edit this file manually or use the app's project tree.

.git/
.venv/
venv/
__pycache__/
*.pyc
*.pyo
*.log
*.tmp
.cache/
build/
dist/
node_modules/
.env
.env.*
*.pem
*.key
"""


def load_patterns(project_path: Path) -> list[str]:
    path = project_path / ".aiignore"
    if not path.exists():
        return []
    patterns: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line.replace("\\", "/"))
    return patterns


def _matches_pattern(rel: str, pattern: str, is_dir: bool) -> bool:
    rel = rel.replace("\\", "/").strip("/")
    pat = pattern.strip().replace("\\", "/")
    if not pat:
        return False

    # Negation is deliberately not supported in v1; keep behavior predictable.
    if pat.startswith("!"):
        return False

    dir_only = pat.endswith("/")
    pat = pat.rstrip("/")

    if dir_only:
        return rel == pat or rel.startswith(pat + "/")

    if "/" not in pat:
        parts = rel.split("/")
        return any(fnmatch.fnmatchcase(part, pat) for part in parts)

    return fnmatch.fnmatchcase(rel, pat) or rel.startswith(pat + "/")


def is_ignored(relative_path: str, patterns: list[str], is_dir: bool = False) -> bool:
    rel = relative_path.replace("\\", "/").strip("/")
    return any(_matches_pattern(rel, pattern, is_dir) for pattern in patterns)


def add_pattern(project_path: Path, relative_path: str, is_dir: bool = False) -> None:
    path = project_path / ".aiignore"
    if not path.exists():
        path.write_text(DEFAULT_AIIGNORE, encoding="utf-8")
    rel = relative_path.replace("\\", "/").strip("/")
    pattern = rel + ("/" if is_dir else "")
    existing = load_patterns(project_path)
    if pattern in existing:
        return
    with path.open("a", encoding="utf-8") as f:
        if path.stat().st_size > 0:
            f.write("\n")
        f.write(pattern + "\n")
