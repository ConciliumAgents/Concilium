#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]


class LessonsArchiveDocsTests(unittest.TestCase):
    def test_lessons_write_instruction_matches_conductor_archive_glob(self):
        lessons = (ROOT / "roundtable-memory" / "LESSONS.md").read_text(encoding="utf-8")
        conductor = (ROOT / "skills" / "loop-engine" / "bin" / "conductor.py").read_text(encoding="utf-8")

        self.assertIn("minutes/iter-*-*-exec.md", lessons)
        self.assertNotIn("minutes/iter-*-claude-exec.md", lessons)
        self.assertIn('glob("iter-*-*-exec.md")', conductor)


if __name__ == "__main__":
    unittest.main()
