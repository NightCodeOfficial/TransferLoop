from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


LANGUAGE_BY_SUFFIX = {
    ".py": "Python", ".pyw": "Python",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".json": "JSON", ".jsonc": "JSON",
    ".html": "HTML", ".htm": "HTML", ".xml": "XML", ".svg": "XML",
    ".css": "CSS", ".scss": "CSS", ".sass": "CSS",
    ".md": "Markdown", ".markdown": "Markdown",
    ".yaml": "YAML", ".yml": "YAML",
    ".toml": "TOML", ".ini": "Config", ".cfg": "Config", ".conf": "Config", ".properties": "Config",
    ".sql": "SQL",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".ps1": "PowerShell", ".psm1": "PowerShell", ".psd1": "PowerShell",
    ".bat": "Batch", ".cmd": "Batch",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++",
    ".cs": "C#", ".java": "Java", ".go": "Go", ".rs": "Rust",
    ".php": "PHP", ".rb": "Ruby", ".swift": "Swift", ".kt": "Kotlin", ".kts": "Kotlin",
    ".r": "R", ".vue": "Vue", ".svelte": "Svelte",
}


def detect_language(path: Path) -> str:
    name = path.name.lower()
    if name == "dockerfile":
        return "Dockerfile"
    if name in {"makefile", "gnumakefile"}:
        return "Makefile"
    if name in {".aiignore", ".gitignore"}:
        return "Ignore"
    if name == ".aimemory":
        return "Markdown"
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "Plain Text")


def comment_prefix(language: str) -> str | None:
    if language in {"Python", "Shell", "PowerShell", "YAML", "TOML", "Config", "Ruby", "R", "Makefile", "Dockerfile", "Ignore"}:
        return "#"
    if language in {"JavaScript", "TypeScript", "C", "C++", "C#", "Java", "Go", "Rust", "Swift", "Kotlin", "PHP", "Vue", "Svelte"}:
        return "//"
    if language == "SQL":
        return "--"
    if language == "Batch":
        return "REM "
    return None


class ProjectSyntaxHighlighter(QSyntaxHighlighter):
    """Built-in syntax colorer for the text formats TransferLoop commonly handles."""

    def __init__(self, document, language: str):
        super().__init__(document)
        self.language = language
        self.rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        self._build_rules()

    @staticmethod
    def _format(color: str, *, bold: bool = False, italic: bool = False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.DemiBold)
        fmt.setFontItalic(italic)
        return fmt

    def _add(self, pattern: str, fmt: QTextCharFormat) -> None:
        self.rules.append((QRegularExpression(pattern), fmt))

    def _keywords(self, words: list[str]) -> None:
        if words:
            escaped = "|".join(QRegularExpression.escape(word) for word in words)
            self._add(r"\b(?:" + escaped + r")\b", self._format("#a99cff", bold=True))

    def _common_literals(self) -> None:
        self._add(r"\b(?:true|false|null|none|nil|undefined)\b", self._format("#d19aef", bold=True))
        self._add(r"(?<![\w.])(?:0x[0-9A-Fa-f]+|\d+(?:\.\d+)?)\b", self._format("#e6b673"))
        self._add(r'"(?:\\.|[^"\\])*"', self._format("#8fd6a3"))
        self._add(r"'(?:\\.|[^'\\])*'", self._format("#8fd6a3"))

    def _build_rules(self) -> None:
        lang = self.language
        keywords = {
            "Python": "and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield True False None".split(),
            "JavaScript": "async await break case catch class const continue debugger default delete do else export extends finally for from function if import in instanceof let new of return static super switch this throw try typeof var void while yield".split(),
            "TypeScript": "abstract any as async await boolean break case catch class const continue declare default else enum export extends finally for from function if implements import in interface keyof let namespace new number of private protected public readonly return static string super switch this throw try type typeof unknown var void while".split(),
            "C": "auto break case char const continue default do double else enum extern float for goto if int long register return short signed sizeof static struct switch typedef union unsigned void volatile while".split(),
            "C++": "alignas auto bool break case catch char class const constexpr continue default delete do double else enum explicit extern false float for friend if inline int namespace new nullptr operator private protected public return sizeof static struct switch template this throw true try typedef typename using virtual void while".split(),
            "C#": "abstract as async await base bool break case catch class const continue decimal default delegate do double else enum event explicit extern false finally fixed float for foreach if implicit in int interface internal is lock long namespace new null object out override private protected public readonly ref return sealed short static string struct switch this throw true try typeof uint ulong unchecked unsafe ushort using virtual void volatile while".split(),
            "Java": "abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for if implements import instanceof int interface long native new package private protected public return short static strictfp super switch synchronized this throw throws transient try void volatile while".split(),
            "Go": "break case chan const continue default defer else fallthrough for func go goto if import interface map package range return select struct switch type var".split(),
            "Rust": "as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait true type unsafe use where while".split(),
            "SQL": "alter and as asc begin between by case create delete desc distinct drop else end exists from group having in index insert into is join left like limit not null on or order outer primary references right select set table then union unique update values when where".split(),
            "PowerShell": "begin break catch class continue data do dynamicparam else elseif end enum exit filter finally for foreach from function if in param process return switch throw trap try until using while".split(),
        }

        if lang in {"HTML", "XML", "Vue", "Svelte"}:
            self._add(r"</?[A-Za-z][^>]*>", self._format("#7cb7ff"))
            self._add(r"\b[A-Za-z_:][-A-Za-z0-9_:.]*(?=\s*=)", self._format("#d7a6ff"))
            self._add(r'"[^"\n]*"', self._format("#8fd6a3"))
            self._add(r"<!--.*-->", self._format("#737b8c", italic=True))
            return

        if lang == "Markdown":
            self._add(r"^#{1,6}\s+.*$", self._format("#b8aeff", bold=True))
            self._add(r"`[^`]+`", self._format("#e6b673"))
            self._add(r"\*\*[^*]+\*\*|__[^_]+__", self._format("#f1f3f8", bold=True))
            self._add(r"^>.*$", self._format("#8fd6a3"))
            self._add(r"^\s*[-*+]\s+", self._format("#a99cff", bold=True))
            self._add(r"\[[^]]+\]\([^)]+\)", self._format("#79b8ff"))
            self._add(r"<!--.*-->", self._format("#737b8c", italic=True))
            return

        if lang == "JSON":
            self._add(r'"(?:\\.|[^"\\])*"(?=\s*:)', self._format("#79b8ff"))
            self._common_literals()
            return

        if lang == "CSS":
            self._add(r"[.#]?[A-Za-z_-][A-Za-z0-9_-]*(?=\s*\{)", self._format("#79b8ff", bold=True))
            self._add(r"\b[-A-Za-z]+(?=\s*:)", self._format("#d7a6ff"))
            self._common_literals()
            self._add(r"/\*.*\*/", self._format("#737b8c", italic=True))
            return

        if lang in {"YAML", "TOML", "Config", "Ignore", "Makefile", "Dockerfile"}:
            self._add(r"^\s*[^#\s][^:=]*?(?=\s*[:=])", self._format("#79b8ff"))
            self._common_literals()
            self._add(r"#.*$", self._format("#737b8c", italic=True))
            return

        fallback = keywords["JavaScript"] if lang in {"PHP", "Swift", "Kotlin"} else []
        self._keywords(keywords.get(lang, fallback))
        self._common_literals()

        if lang == "Python":
            self._add(r"\b(?:def|class)\s+[A-Za-z_]\w*", self._format("#79b8ff", bold=True))
            self._add(r"#.*$", self._format("#737b8c", italic=True))
        elif lang in {"Shell", "PowerShell", "Ruby", "R"}:
            self._add(r"\$[A-Za-z_][A-Za-z0-9_:]*", self._format("#79b8ff"))
            self._add(r"#.*$", self._format("#737b8c", italic=True))
        elif lang == "Batch":
            self._add(r"(?i:^\s*(?:REM\b|::).*$)", self._format("#737b8c", italic=True))
            self._add(r"%[^%]+%", self._format("#79b8ff"))
        elif lang == "SQL":
            self._add(r"--.*$", self._format("#737b8c", italic=True))
        else:
            self._add(r"//.*$", self._format("#737b8c", italic=True))
            self._add(r"/\*.*\*/", self._format("#737b8c", italic=True))

    def highlightBlock(self, text: str) -> None:
        for expression, fmt in self.rules:
            iterator = expression.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                start = match.capturedStart()
                length = match.capturedLength()
                if start >= 0 and length > 0:
                    self.setFormat(start, length, fmt)
