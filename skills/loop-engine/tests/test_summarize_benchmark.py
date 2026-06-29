#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "summarize-benchmark.py"
spec = importlib.util.spec_from_file_location("summarize_benchmark", MODULE)
summary = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(summary)


def record(task_id: str, lane: str, status: str, seconds: float) -> dict:
    return {
        "task_id": task_id,
        "category": "repo-local",
        "lane": lane,
        "status": status,
        "verify_passed": status == "PASS",
        "review_verdict": "",
        "blocking_findings": [] if status == "PASS" else ["failed verify"],
        "wall_seconds": seconds,
    }


class SummarizeBenchmarkTests(unittest.TestCase):
    def test_classify_roundtable_better_when_only_roundtable_passes(self):
        kimi = record("x", "baseline-kimi", "ERR", 10)
        rt = record("x", "roundtable", "PASS", 20)
        outcome, reason = summary.classify_pair(kimi, rt)
        self.assertEqual(outcome, "roundtable_better")
        self.assertIn("roundtable passed", reason)

    def test_classify_kimi_better_when_only_kimi_passes(self):
        kimi = record("x", "baseline-kimi", "PASS", 10)
        rt = record("x", "roundtable", "ERR", 20)
        outcome, reason = summary.classify_pair(kimi, rt)
        self.assertEqual(outcome, "kimi_better")
        self.assertIn("kimi passed", reason)

    def test_classify_tie_when_both_pass(self):
        kimi = record("x", "baseline-kimi", "PASS", 10)
        rt = record("x", "roundtable", "PASS", 20)
        outcome, reason = summary.classify_pair(kimi, rt)
        self.assertEqual(outcome, "tie")
        self.assertIn("both passed", reason)

    def test_build_summary_groups_records_by_task(self):
        records = [
            record("x", "baseline-kimi", "PASS", 10),
            record("x", "roundtable", "PASS", 20),
        ]
        report = summary.build_summary(records)
        self.assertIn("# Loop Engine Phase 2 Benchmark Summary", report)
        self.assertIn("| x | PASS | PASS | tie |", report)

    def test_main_writes_summary_file(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = pathlib.Path(td)
            records_path = run_dir / "records.jsonl"
            records_path.write_text(
                "\n".join(json.dumps(r) for r in [
                    record("x", "baseline-kimi", "PASS", 10),
                    record("x", "roundtable", "PASS", 20),
                ]) + "\n",
                encoding="utf-8",
            )
            rc = summary.main(["--records", str(records_path), "--out", str(run_dir / "summary.md")])
            self.assertEqual(rc, 0)
            self.assertTrue((run_dir / "summary.md").is_file())


if __name__ == "__main__":
    unittest.main()
