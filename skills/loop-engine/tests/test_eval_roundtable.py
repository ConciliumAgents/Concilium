#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
import datetime


ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "eval-roundtable.py"
spec = importlib.util.spec_from_file_location("eval_roundtable", MODULE)
eval_roundtable = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(eval_roundtable)


class EvalRoundtableTests(unittest.TestCase):
    def test_find_repo_root_from_script_path(self):
        self.assertEqual(eval_roundtable.ROOT, ROOT)

    def test_load_tasks_requires_core_keys(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "tasks.json"
            path.write_text(json.dumps([{"id": "x"}]), encoding="utf-8")
            with self.assertRaises(ValueError):
                eval_roundtable.load_tasks(path)

    def test_eval_task_runs_from_repo_root(self):
        cmd = (
            f"{sys.executable} -c "
            "'import pathlib; assert pathlib.Path(\"skills/loop-engine\").is_dir()'"
        )
        result = eval_roundtable.eval_task(
            {"id": "root_check", "task": "Check cwd", "expected_status": "PASS", "test_cmd": cmd},
            timeout=30,
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["status"], "PASS")

    def test_select_tasks_skips_optional_by_default(self):
        tasks = [
            {"id": "required", "task": "Required", "expected_status": "PASS"},
            {"id": "optional", "task": "Optional", "expected_status": "PASS", "optional": True},
        ]
        self.assertEqual([task["id"] for task in eval_roundtable.select_tasks(tasks, False)], ["required"])
        self.assertEqual(
            [task["id"] for task in eval_roundtable.select_tasks(tasks, True)],
            ["required", "optional"],
        )

    def test_doc_drift_eval_runs_doc_drift_test(self):
        tasks = eval_roundtable.load_tasks(eval_roundtable.DEFAULT_TASKS)
        task = next(item for item in tasks if item["id"] == "doc_drift_lessons_archive")
        self.assertIn("test_lessons_archive_docs.py", task["test_cmd"])

    def test_output_path_includes_microseconds(self):
        now = datetime.datetime(2026, 1, 2, 3, 4, 5, 6789)
        self.assertEqual(
            eval_roundtable.output_path_for(now).name,
            "20260102-030405-006789.jsonl",
        )


if __name__ == "__main__":
    unittest.main()
