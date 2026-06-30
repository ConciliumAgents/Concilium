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

    def test_run_concilium_passes_explicit_seats_to_adapter(self):
        preview = {
            "status": "preview",
            "route": {"lane": "audit", "required_seats": ["claude", "hermes", "kimi"]},
        }
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run.concilium_runtime, "run_concilium_adapter", return_value=preview) as adapter:
            concilium_run.run_concilium(
                repo=td,
                task="Read-only audit the architecture.",
                dry_run=True,
                seats=["claude", "hermes", "kimi"],
            )

        self.assertEqual(adapter.call_args.args[0]["seats"], ["claude", "hermes", "kimi"])

    def test_cli_seats_comma_list_reaches_adapter(self):
        result = {
            "status": "preview",
            "route": {"lane": "audit", "required_seats": ["claude", "hermes", "kimi"]},
        }
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run.concilium_runtime, "run_concilium_adapter", return_value=result) as adapter, \
                contextlib.redirect_stdout(io.StringIO()):
            rc = concilium_run.main([
                "--repo", td,
                "--task", "Read-only audit the architecture.",
                "--print-route",
                "--seats", "claude,hermes,kimi",
            ])

        self.assertEqual(rc, 0)
        self.assertEqual(adapter.call_args.args[0]["seats"], ["claude", "hermes", "kimi"])

    def test_cli_legacy_roundtable_flags_reach_runtime_overlay(self):
        result = {
            "status": "preview",
            "route": {"lane": "roundtable", "required_seats": ["claude", "hermes", "kimi"]},
        }
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run.concilium_runtime, "run_concilium_adapter", return_value=result) as adapter, \
                contextlib.redirect_stdout(io.StringIO()):
            rc = concilium_run.main([
                "--repo", td,
                "--task", "Architecture decision with migration risk.",
                "--print-route",
                "--commander", "claude",
                "--reviewer", "hermes",
                "--max-iters", "2",
                "--review-executor", "kimi",
                "--review-reviewer", "hermes",
                "--fast-agent", "kimi",
            ])

        self.assertEqual(rc, 0)
        params = adapter.call_args.args[0]
        self.assertEqual(params["commander"], "claude")
        self.assertEqual(params["reviewer"], "hermes")
        self.assertEqual(params["max_iters"], 2)
        self.assertEqual(params["review_executor"], "kimi")
        self.assertEqual(params["review_reviewer"], "hermes")
        self.assertEqual(params["fast_agent"], "kimi")

    def test_cli_yes_reuses_single_capacity_snapshot_for_confirmation(self):
        capacity = [
            {
                "seat": "claude",
                "provider": "anthropic",
                "model": "opus",
                "status": "unknown",
                "source": "test",
                "reason": "unknown",
                "checked_at": "2026-06-30T00:00:00Z",
                "reset_at": "",
                "stale_after_seconds": 300,
            },
            {
                "seat": "hermes",
                "provider": "DeepSeek",
                "model": "deepseek-v4-flash",
                "status": "unknown",
                "source": "test",
                "reason": "unknown",
                "checked_at": "2026-06-30T00:00:00Z",
                "reset_at": "",
                "stale_after_seconds": 300,
            },
            {
                "seat": "kimi",
                "provider": "moonshot",
                "model": "kimi-code/kimi-for-coding",
                "status": "unknown",
                "source": "test",
                "reason": "unknown",
                "checked_at": "2026-06-30T00:00:00Z",
                "reset_at": "",
                "stale_after_seconds": 300,
            },
        ]
        config = {
            "routing": {"risk_posture": "balanced", "allow_auto_escalation": True},
            "lanes": {
                "audit": {"seats": ["claude", "hermes", "kimi"]},
                "plan_review": {"seats": ["claude", "hermes", "kimi"], "max_rounds": 3},
                "fast": {"default_single_agent": "kimi"},
                "review": {"default_review_executor": "kimi", "default_review_reviewer": "hermes"},
                "roundtable": {"commander": "claude", "seats": ["hermes", "kimi"], "reviewer": "hermes"},
            },
            "seat_models": {},
        }
        result = {"status": "blocked", "returncode": 2}
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run.concilium_config, "load_config", return_value=config), \
                mock.patch.object(concilium_run.concilium_lanes, "collect_capacity", return_value=capacity), \
                mock.patch.object(concilium_run.concilium_runtime, "run_concilium_adapter", return_value=result) as adapter, \
                contextlib.redirect_stdout(io.StringIO()):
            rc = concilium_run.main([
                "--repo", td,
                "--task", "Read-only audit the architecture and memory system. Do not modify files.",
                "--live",
                "--yes",
                "--signals-json", '{"read_only":true,"risk":"high","file_count":3}',
            ])

        self.assertEqual(rc, 3)
        self.assertIs(adapter.call_args.kwargs["capacity"], capacity)
        self.assertIs(adapter.call_args.kwargs["config"], config)
        confirmation = adapter.call_args.kwargs["confirmation"]
        self.assertTrue(confirmation["accepted"])
        self.assertTrue(confirmation["request_fingerprint"])
        self.assertTrue(confirmation["confirmation_fingerprint"])

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

    def test_print_route_live_forces_preview_mode(self):
        preview = {
            "status": "preview",
            "route": {"lane": "fast", "required_seats": ["kimi"]},
        }
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run.concilium_runtime, "run_concilium_adapter", return_value=preview) as adapter, \
                contextlib.redirect_stdout(io.StringIO()):
            rc = concilium_run.main(["--repo", td, "--task", "Fix one typo.", "--live", "--print-route"])

        self.assertEqual(rc, 0)
        adapter.assert_called_once()
        params = adapter.call_args.args[0]
        self.assertEqual(params["mode"], "preview")
        self.assertTrue(params["live"])
        self.assertTrue(params["print_route"])

    def test_blocked_cli_exits_three(self):
        result = {"status": "blocked", "guard": {"status": "blocked"}}
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run.concilium_runtime, "run_concilium_adapter", return_value=result), \
                contextlib.redirect_stdout(io.StringIO()):
            rc = concilium_run.main(["--repo", td, "--task", "Change config routing behavior."])

        self.assertEqual(rc, 3)


if __name__ == "__main__":
    unittest.main()
