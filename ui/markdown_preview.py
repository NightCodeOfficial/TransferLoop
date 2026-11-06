from __future__ import annotations

import re


MARKDOWN_DOCUMENT_STYLE = """
body {
    color: #dfe3ed;
    font-family: 'Segoe UI', sans-serif;
    font-size: 15px;
    line-height: 1.55;
}
p {
    margin-top: 0;
    margin-bottom: 12px;
}
h1, h2, h3, h4, h5, h6 {
    color: #f4f5f8;
    font-weight: 600;
    margin-top: 24px;
    margin-bottom: 10px;
}
h1 {
    font-size: 28px;
    margin-top: 0;
    padding-bottom: 8px;
    border-bottom: 1px solid #2b3140;
}
h2 {
    font-size: 22px;
    padding-bottom: 6px;
    border-bottom: 1px solid #252b38;
}
h3 { font-size: 18px; }
h4, h5, h6 { font-size: 16px; }
ul, ol {
    margin-top: 6px;
    margin-bottom: 14px;
    margin-left: 22px;
}
li {
    margin-top: 3px;
    margin-bottom: 5px;
}
a { color: #a99cff; text-decoration: none; }
pre {
    background-color: #0b0e14;
    color: #e4e7ef;
    margin-top: 10px;
    margin-bottom: 14px;
    padding: 12px 14px;
    border: 1px solid #252b38;
}
code {
    font-family: 'Cascadia Code', 'Consolas', monospace;
    background-color: #171b24;
    color: #e4e7ef;
}
blockquote {
    color: #b3b9c7;
    margin: 10px 0 14px 4px;
    padding-left: 12px;
    border-left: 3px solid #6f5df7;
}
hr { color: #303647; background-color: #303647; margin: 18px 0; }
table { border-collapse: collapse; margin: 8px 0 16px 0; }
th, td { border: 1px solid #343a4b; padding: 7px 10px; }
th { background-color: #171b24; color: #f0f2f7; font-weight: 600; }
"""


_MERMAID_FENCE_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)
_MERMAID_NODE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\[([^\]]+)\]")
_MERMAID_EDGE_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)(?:\[[^\]]+\])?\s*"
    r"-->(?:\|([^|]+)\|)?\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)(?:\[[^\]]+\])?\s*$"
)


_FENCE_START_RE = re.compile(r"^\s*(`{3,}|~{3,})")


def _preserve_extra_blank_lines(markdown: str) -> str:
    """Keep extra source blank lines visible without changing the Markdown file itself.

    One blank line is left untouched for normal Markdown block separation. Additional
    consecutive blank lines become non-breaking-space paragraphs so QTextDocument
    does not collapse them all into the same block gap.
    """
    lines = markdown.splitlines()
    had_trailing_newline = markdown.endswith("\n")
    output: list[str] = []
    in_fence = False
    fence_char = ""
    fence_length = 0
    blank_run = 0

    def flush_blank_run() -> None:
        nonlocal blank_run
        if blank_run <= 0:
            return
        output.append("")
        output.extend("\u00a0" for _ in range(blank_run - 1))
        blank_run = 0

    for line in lines:
        fence = _FENCE_START_RE.match(line)
        if in_fence:
            output.append(line)
            if fence and fence.group(1)[0] == fence_char and len(fence.group(1)) >= fence_length:
                in_fence = False
                fence_char = ""
                fence_length = 0
            continue

        if fence:
            flush_blank_run()
            token = fence.group(1)
            in_fence = True
            fence_char = token[0]
            fence_length = len(token)
            output.append(line)
            continue

        if not line.strip():
            blank_run += 1
            continue

        flush_blank_run()
        output.append(line)

    flush_blank_run()
    rendered = "\n".join(output)
    if had_trailing_newline:
        rendered += "\n"
    return rendered


def markdown_preview_source(markdown: str) -> str:
    """Prepare Markdown for Qt read mode while keeping the source file untouched."""

    def replace_mermaid(match: re.Match[str]) -> str:
        source = match.group(1).strip()
        nodes = {node_id: label.strip() for node_id, label in _MERMAID_NODE_RE.findall(source)}
        edges: list[tuple[str, str, str]] = []
        for line in source.splitlines():
            edge = _MERMAID_EDGE_RE.match(line)
            if edge:
                start, label, end = edge.groups()
                edges.append((start, (label or "").strip(), end))

        if edges:
            rendered: list[str] = []
            for start, label, end in edges:
                start_label = nodes.get(start, start)
                end_label = nodes.get(end, end)
                arrow = f" — {label} → " if label else " → "
                rendered.append(f"- **{start_label}**{arrow}**{end_label}**")
            return "\n".join(rendered)

        return "```text\n" + source + "\n```"

    rendered = _MERMAID_FENCE_RE.sub(replace_mermaid, markdown)
    return _preserve_extra_blank_lines(rendered)
