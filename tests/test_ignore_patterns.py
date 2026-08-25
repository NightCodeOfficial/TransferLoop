from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.ignore import add_pattern, is_ignored, load_patterns


class IgnorePatternTests(unittest.TestCase):
    def test_add_folder_pattern_ignores_folder_and_descendants(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            add_pattern(project, "runtime/cache", is_dir=True)

            patterns = load_patterns(project)

            self.assertIn("runtime/cache/", patterns)
            self.assertTrue(is_ignored("runtime/cache", patterns, is_dir=True))
            self.assertTrue(is_ignored("runtime/cache/state.json", patterns, is_dir=False))
            self.assertFalse(is_ignored("runtime/cache-other/state.json", patterns, is_dir=False))


if __name__ == "__main__":
    unittest.main()
