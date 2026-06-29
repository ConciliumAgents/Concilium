#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "benchmark-roundtable.py"
spec = importlib.util.spec_from_file_location("benchmark_roundtable", MODULE)
benchmark = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(benchmark)


def sample_task() -> dict:
    return {
        "id": "sample",
        "category": "repo-local",
        "prompt": "Make a small doc change.",
        "allowed_paths": ["docs/example.md"],
        "verify_cmds": ["python3 -c 'print(1)'"],
        "quality_checks": ["Report exists."],
        "expected_artifacts": ["report.md", "diff.patch", "test-results.txt", "result.json"],
    }


class BenchmarkRoundtableTests(unittest.TestCase):
    def test_load_tasks_requires_phase2_schema(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "tasks.json"
            path.write_text(json.dumps([{"id": "x"}]), encoding="utf-8")
            with self.assertRaises(ValueError):
                benchmark.load_tasks(path)

    def test_load_tasks_accepts_valid_task(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "tasks.json"
            path.write_text(json.dumps([sample_task()]), encoding="utf-8")
            tasks = benchmark.load_tasks(path)
        self.assertEqual(tasks[0]["id"], "sample")

    def test_dry_lane_writes_comparable_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = pathlib.Path(td)
            task = sample_task()
            record = benchmark.run_dry_lane(
                task=task,
                lane="baseline-kimi",
                lane_dir=run_dir / "task-sample" / "baseline-kimi",
                harness_commit="harness",
                task_base_commit="base",
            )

            self.assertEqual(record["lane"], "baseline-kimi")
            self.assertEqual(record["task_id"], "sample")
            self.assertEqual(record["status"], "PASS")
            self.assertTrue((run_dir / "task-sample" / "baseline-kimi" / "result.json").is_file())
            self.assertTrue((run_dir / "task-sample" / "baseline-kimi" / "report.md").is_file())
            self.assertTrue((run_dir / "task-sample" / "baseline-kimi" / "diff.patch").is_file())
            self.assertTrue((run_dir / "task-sample" / "baseline-kimi" / "test-results.txt").is_file())


if __name__ == "__main__":
    unittest.main()
