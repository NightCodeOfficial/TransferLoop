from __future__ import annotations

import unittest

from ui.markdown_editing import enter_action, is_markdown_url


class MarkdownEditingTests(unittest.TestCase):
    def test_unordered_list_continues(self) -> None:
        action = enter_action("  - item", len("  - item"))
        self.assertIsNotNone(action)
        self.assertEqual("  - ", action.next_prefix)

    def test_numbered_list_increments(self) -> None:
        action = enter_action("9. item", len("9. item"))
        self.assertEqual("10. ", action.next_prefix)

    def test_task_list_continues_unchecked(self) -> None:
        action = enter_action("- [x] done", len("- [x] done"))
        self.assertEqual("- [ ] ", action.next_prefix)

    def test_nested_blockquote_list_keeps_prefix(self) -> None:
        action = enter_action(">   - item", len(">   - item"))
        self.assertEqual(">   - ", action.next_prefix)

    def test_empty_list_exits_list(self) -> None:
        action = enter_action("    - ", len("    - "))
        self.assertEqual("    ", action.replace_current_with)

    def test_empty_list_inside_quote_keeps_quote(self) -> None:
        action = enter_action("> - ", len("> - "))
        self.assertEqual("> ", action.replace_current_with)

    def test_blockquote_continues_and_empty_quote_exits(self) -> None:
        self.assertEqual("> ", enter_action("> quote", len("> quote")).next_prefix)
        self.assertEqual("", enter_action("> ", len("> ")).replace_current_with)

    def test_url_detection(self) -> None:
        self.assertTrue(is_markdown_url("https://example.com/a"))
        self.assertTrue(is_markdown_url("mailto:test@example.com"))
        self.assertFalse(is_markdown_url("not a url"))


if __name__ == "__main__":
    unittest.main()
