#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "report-session.py"
spec = importlib.util.spec_from_file_location("report_session", MODULE)
report_session = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(report_session)


class ReportSessionTests(unittest.TestCase):
    def test_build_report_includes_session_sections_and_minutes(self):
        with tempfile.TemporaryDirectory() as td:
            session = pathlib.Path(td) / "session-1"
            kb = session / "KB"
            minutes = session / "minutes"
            kb.mkdir(parents=True)
            minutes.mkdir()
            (session / "roundtable.json").write_text(
                json.dumps({"participants": ["claude", "kimi"], "iter": 2}),
                encoding="utf-8",
            )
            (kb / "conclusion.md").write_text("Final conclusion", encoding="utf-8")
            (kb / "task.md").write_text("Task body", encoding="utf-8")
            (kb / "test-results.txt").write_text("Tests passed", encoding="utf-8")
            (minutes / "iter-1-kimi-review.md").write_text("Looks fine\n**VERDICT: PASS**\n", encoding="utf-8")

            report = report_session.build_report(session)

        self.assertIn("# Roundtable Session Report: session-1", report)
        self.assertIn("## Minute Index", report)
        self.assertIn("## Latest Test Output", report)
        self.assertIn("| 1 | kimi | review | PASS |", report)

    def test_build_report_includes_seat_timing_when_available(self):
        with tempfile.TemporaryDirectory() as td:
            session = pathlib.Path(td) / "session-1"
            kb = session / "KB"
            minutes = session / "minutes"
            kb.mkdir(parents=True)
            minutes.mkdir()
            (session / "roundtable.json").write_text(
                json.dumps(
                    {
                        "participants": ["claude", "kimi"],
                        "iter": 2,
                        "seat_timings": [
                            {
                                "iter": 1,
                                "seat": "kimi",
                                "mode": "exec",
                                "rc": 0,
                                "duration_seconds": 12.345,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (minutes / "iter-1-kimi-exec.md").write_text("Edited file\n", encoding="utf-8")

            report = report_session.build_report(session)

        self.assertIn("| Iter | Seat | Mode | Verdict | Duration(s) | Bytes | File |", report)
        self.assertIn("| 1 | kimi | exec | - | 12.345 |", report)


if __name__ == "__main__":
    unittest.main()
