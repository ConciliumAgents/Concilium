#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


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


if __name__ == "__main__":
    unittest.main()
