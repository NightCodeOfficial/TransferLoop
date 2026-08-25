from __future__ import annotations

import unittest

from ui.markdown_preview import MARKDOWN_DOCUMENT_STYLE, markdown_preview_source


class MarkdownPreviewTests(unittest.TestCase):
    def test_mermaid_flowchart_gets_readable_text_fallback(self) -> None:
        source = """```mermaid
flowchart LR
    A[Local project] -->|Select and export context| B[TransferLoop]
    B -->|Manual upload: project ZIP + AI instructions| C[Browser-based AI]
    C -->|Manual download: response ZIP| B
    B -->|Stage, diff, accept or reject| A
```"""

        rendered = markdown_preview_source(source)

        self.assertNotIn("flowchart LR", rendered)
        self.assertIn("**Local project** — Select and export context → **TransferLoop**", rendered)
        self.assertIn("**TransferLoop** — Manual upload: project ZIP + AI instructions → **Browser-based AI**", rendered)
        self.assertEqual(4, sum(line.startswith("- ") for line in rendered.splitlines()))
        self.assertNotIn("Diagram", rendered)
        self.assertNotIn("Mermaid is shown", rendered)


    def test_unrecognized_mermaid_fallback_has_no_added_explanation(self) -> None:
        source = """```mermaid\nsequenceDiagram\n    Alice->>Bob: Hello\n```"""

        rendered = markdown_preview_source(source)

        self.assertEqual("```text\nsequenceDiagram\n    Alice->>Bob: Hello\n```", rendered)
        self.assertNotIn("Mermaid diagram", rendered)
        self.assertNotIn("not available", rendered)

    def test_plain_markdown_with_single_blank_lines_is_left_unchanged(self) -> None:
        source = "# Heading\n\n- one\n- two\n"
        self.assertEqual(source, markdown_preview_source(source))

    def test_extra_blank_lines_are_preserved_for_reader_spacing(self) -> None:
        source = "# Heading\n\n\nParagraph\n\n\n\nNext\n"
        rendered = markdown_preview_source(source)

        self.assertEqual("# Heading\n\n\u00a0\nParagraph\n\n\u00a0\n\u00a0\nNext\n", rendered)

    def test_blank_lines_inside_fenced_code_are_not_rewritten(self) -> None:
        source = "```python\nprint('one')\n\n\nprint('two')\n```\n"
        self.assertEqual(source, markdown_preview_source(source))

    def test_reader_style_contains_spacing_for_lists_and_paragraphs(self) -> None:
        self.assertIn("p {", MARKDOWN_DOCUMENT_STYLE)
        self.assertIn("ul, ol {", MARKDOWN_DOCUMENT_STYLE)
        self.assertIn("li {", MARKDOWN_DOCUMENT_STYLE)
        self.assertIn("margin-bottom: 12px", MARKDOWN_DOCUMENT_STYLE)


if __name__ == "__main__":
    unittest.main()
