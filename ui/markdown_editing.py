from __future__ import annotations

from dataclasses import dataclass
import re


_LIST_RE = re.compile(
    r"^(?P<indent>[ \t]*)"
    r"(?P<quote>(?:>[ \t]*)*)"
    r"(?P<marker>(?:(?P<number>\d+)(?P<delimiter>[.)])|[-+*]))"
    r"(?P<space>[ \t]+)"
    r"(?P<task>\[[ xX]\][ \t]+)?"
    r"(?P<body>.*)$"
)
_QUOTE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<quote>(?:>[ \t]*)+)(?P<body>.*)$")
_URL_RE = re.compile(r"^(?:https?://|mailto:)[^\s]+$", re.IGNORECASE)


@dataclass(frozen=True)
class MarkdownEnterAction:
    next_prefix: str | None = None
    replace_current_with: str | None = None


def enter_action(line: str, cursor_column: int) -> MarkdownEnterAction | None:
    """Return the Markdown continuation action for Enter on *line*.

    The function intentionally stays independent of Qt so continuation behavior
    can be unit-tested without a GUI runtime.
    """
    cursor_column = max(0, min(len(line), cursor_column))

    match = _LIST_RE.match(line)
    if match:
        body = match.group("body")
        body_start = match.start("body")
        before_body = line[body_start:cursor_column] if cursor_column >= body_start else ""
        after_body = line[cursor_column:] if cursor_column >= body_start else body

        # Enter on an empty list/task item exits the list. If the list is inside
        # a blockquote, keep the quote so one more Enter can exit the quote.
        if not body.strip() and not before_body.strip() and not after_body.strip():
            base = match.group("indent") + match.group("quote")
            return MarkdownEnterAction(replace_current_with=base)

        marker = match.group("marker")
        if match.group("number"):
            marker = f"{int(match.group('number')) + 1}{match.group('delimiter')}"
        task = "[ ] " if match.group("task") else ""
        prefix = (
            match.group("indent")
            + match.group("quote")
            + marker
            + match.group("space")
            + task
        )
        return MarkdownEnterAction(next_prefix=prefix)

    quote_match = _QUOTE_RE.match(line)
    if quote_match:
        body = quote_match.group("body")
        if not body.strip():
            return MarkdownEnterAction(replace_current_with=quote_match.group("indent"))
        return MarkdownEnterAction(
            next_prefix=quote_match.group("indent") + quote_match.group("quote")
        )

    return None


def is_markdown_url(text: str) -> bool:
    return bool(_URL_RE.fullmatch(text.strip()))


def is_list_or_quote_line(line: str) -> bool:
    return bool(_LIST_RE.match(line) or _QUOTE_RE.match(line))
