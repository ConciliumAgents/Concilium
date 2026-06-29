#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium-run.py"
spec = importlib.util.spec_from_file_location("concilium_run", MODULE)
concilium_run = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(concilium_run)


class ConciliumRunTests(unittest.TestCase):
    def test_print_route_does_not_run_agents(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run, "run_fast_lane") as fast:
            result = concilium_run.run_concilium(
                repo=td,
                task="Fix one typo in docs/example.md.",
                test_cmd="true",
                dry_run=True,
                print_route=True,
                signals={"risk": "low", "file_count": 1, "security_sensitive": False, "ambiguous": False},
            )

        self.assertEqual(result["route"]["lane"], "fast")
        self.assertEqual(result["status"], "preview")
        fast.assert_not_called()

    def test_blocked_preflight_stops_before_agent_call(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run, "collect_capacity", return_value=[
                    {"seat": "kimi", "status": "ok", "blocking": False, "reason": ""},
                    {"seat": "hermes", "status": "hard_exhausted", "blocking": True, "reason": "0 percent remaining"},
                ]), \
                mock.patch.object(concilium_run, "run_review_lane") as review:
            result = concilium_run.run_concilium(
                repo=td,
                task="Change config routing behavior.",
                test_cmd="true",
                dry_run=False,
                print_route=False,
                signals={"risk": "medium", "file_count": 2, "security_sensitive": False, "ambiguous": False},
            )

        self.assertEqual(result["status"], "blocked")
        review.assert_not_called()


if __name__ == "__main__":
    unittest.main()
