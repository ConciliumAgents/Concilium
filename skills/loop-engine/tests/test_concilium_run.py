#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import importlib.util
import io
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
    def test_print_route_dry_preview_routes_through_adapter(self):
        preview = {
            "status": "preview",
            "route": {"lane": "fast", "required_seats": ["kimi"]},
        }
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run.concilium_runtime, "run_concilium_adapter", return_value=preview) as adapter:
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
        adapter.assert_called_once()
        params = adapter.call_args.args[0]
        self.assertEqual(params["mode"], "preview")
        self.assertTrue(params["dry_run"])
        self.assertTrue(params["print_route"])

    def test_confirmation_required_cli_exits_three(self):
        result = {"status": "confirmation_required", "guard": {"status": "confirmation_required"}}
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run.concilium_runtime, "run_concilium_adapter", return_value=result), \
                contextlib.redirect_stdout(io.StringIO()):
            rc = concilium_run.main(
                [
                    "--repo", td,
                    "--task", "Change config routing behavior.",
                    "--test-cmd", "true",
                    "--live",
                    "--signals-json", '{"risk":"medium","file_count":2,"security_sensitive":false,"ambiguous":false}',
                ]
            )

        self.assertEqual(rc, 3)

    def test_blocked_cli_exits_three(self):
        result = {"status": "blocked", "guard": {"status": "blocked"}}
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run.concilium_runtime, "run_concilium_adapter", return_value=result), \
                contextlib.redirect_stdout(io.StringIO()):
            rc = concilium_run.main(["--repo", td, "--task", "Change config routing behavior."])

        self.assertEqual(rc, 3)


if __name__ == "__main__":
    unittest.main()
