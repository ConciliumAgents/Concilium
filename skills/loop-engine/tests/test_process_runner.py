#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "process_runner.py"
spec = importlib.util.spec_from_file_location("process_runner", MODULE)
process_runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(process_runner)


class ProcessRunnerTests(unittest.TestCase):
    def test_timeout_returns_124_and_marks_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            result = process_runner.run_process_group(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                cwd=pathlib.Path(td),
                env={},
                timeout=1,
            )

        self.assertEqual(result["returncode"], 124)
        self.assertTrue(result["timed_out"])
        self.assertIn("timeout after 1s", result["output"])


if __name__ == "__main__":
    unittest.main()
