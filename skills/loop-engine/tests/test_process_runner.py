#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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

    def test_empty_env_does_not_inherit_parent_path(self):
        with tempfile.TemporaryDirectory() as td:
            result = process_runner.run_process_group(
                [sys.executable, "-c", "import os; print('PATH' in os.environ)"],
                cwd=pathlib.Path(td),
                env={},
                timeout=5,
            )

        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["output"].strip(), "False")
        self.assertFalse(result["timed_out"])

    def test_killpg_permission_error_still_returns_timeout(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(process_runner.os, "killpg", side_effect=PermissionError):
            result = process_runner.run_process_group(
                [sys.executable, "-c", "import time; time.sleep(2)"],
                cwd=pathlib.Path(td),
                env={},
                timeout=1,
            )

        self.assertEqual(result["returncode"], 124)
        self.assertTrue(result["timed_out"])
        self.assertIn("timeout after 1s", result["output"])

    def test_sigkill_output_collection_remains_bounded(self):
        class FakeProc:
            pid = 123
            returncode = None

            def __init__(self):
                self.timeouts: list[int] = []

            def communicate(self, timeout=None):
                self.timeouts.append(timeout)
                if timeout is None:
                    raise AssertionError("final communicate must be bounded")
                raise subprocess.TimeoutExpired(["fake"], timeout, output=f"partial-{len(self.timeouts)}")

        fake_proc = FakeProc()
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(process_runner.subprocess, "Popen", return_value=fake_proc), \
                mock.patch.object(process_runner.os, "getpgid", return_value=456), \
                mock.patch.object(process_runner.os, "killpg") as killpg:
            result = process_runner.run_process_group(
                [sys.executable, "-c", "pass"],
                cwd=pathlib.Path(td),
                env={},
                timeout=1,
            )

        self.assertEqual(result["returncode"], 124)
        self.assertTrue(result["timed_out"])
        self.assertIn("timeout after 1s", result["output"])
        self.assertEqual(fake_proc.timeouts, [1, 2, 2])
        killpg.assert_has_calls([
            mock.call(456, signal.SIGTERM),
            mock.call(456, signal.SIGKILL),
        ])


if __name__ == "__main__":
    unittest.main()
