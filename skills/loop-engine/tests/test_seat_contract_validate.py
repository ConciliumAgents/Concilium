#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / "bin" / "seat-contract-validate.py"
spec = importlib.util.spec_from_file_location("seat_contract_validate", MODULE)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


class SeatContractValidateTests(unittest.TestCase):
    def test_extract_valid_plan(self):
        text = '```json\n[{"agent":"kimi","subtask":"Do the work."}]\n```'
        self.assertEqual(
            validator.extract_plan(text),
            [{"agent": "kimi", "subtask": "Do the work."}],
        )

    def test_invalid_plan_has_error(self):
        self.assertTrue(validator.validate_plan("no json here"))

    def test_exec_requires_lessons(self):
        self.assertEqual(
            validator.validate_exec("done\n## Lessons\n### General\n- None.\n### agents\n- None."),
            [],
        )
        self.assertIn("## Lessons", validator.validate_exec("done")[0])

    def test_exec_requires_project_lesson_subsection_beyond_general(self):
        errors = validator.validate_exec("done\n## Lessons\n### General\n- None.")
        self.assertIn("project lesson subsection", errors[0])

    def test_exec_ignores_project_like_headings_outside_lessons(self):
        text = "### unrelated\nnotes\n## Lessons\n### General\n- None."
        errors = validator.validate_exec(text)
        self.assertIn("project lesson subsection", errors[0])

    def test_review_requires_exactly_one_verdict(self):
        self.assertEqual(validator.validate_review("Looks fine\nVERDICT: PASS\n"), [])
        self.assertEqual(validator.validate_review("Looks fine\n**VERDICT: PASS**\n"), [])
        self.assertTrue(validator.validate_review("VERDICT: PASS\nVERDICT: BLOCK\n"))
        self.assertTrue(validator.validate_review("no verdict"))

    def test_review_blocks_high_or_critical_findings(self):
        self.assertTrue(validator.validate_review("[HIGH] bad\nVERDICT: PASS\n"))
        self.assertEqual(validator.validate_review("[HIGH] bad\nVERDICT: BLOCK\n"), [])
        self.assertEqual(validator.validate_review("[HIGH] bad\n**VERDICT: BLOCK**\n"), [])
        self.assertEqual(validator.validate_review("[MEDIUM] note\nVERDICT: PASS\n"), [])

    def test_infers_mode_from_minute_filename(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "iter-1-kimi-review.md"
            path.write_text("Looks fine\nVERDICT: BLOCK\n", encoding="utf-8")
            self.assertEqual(validator.validate_file(path), [])


if __name__ == "__main__":
    unittest.main()
