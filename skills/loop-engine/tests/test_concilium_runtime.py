#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium_runtime.py"
spec = importlib.util.spec_from_file_location("concilium_runtime", MODULE)
concilium_runtime = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(concilium_runtime)


BASE_CONFIG = {
    "version": 1,
    "lanes": {
        "fast": {"default_single_agent": "kimi", "verify_required": True},
        "review": {
            "default_review_executor": "kimi",
            "default_review_reviewer": "hermes",
            "review_repair_limit": 1,
        },
        "roundtable": {
            "commander": "claude",
            "reviewer": "",
            "seats": ["claude", "hermes", "kimi"],
            "max_iters": 5,
        },
    },
    "routing": {
        "risk_posture": "balanced",
        "allow_auto_escalation": True,
        "allow_auto_downgrade": False,
    },
    "capacity": {"warn_below_percent": 20, "block_below_percent": 5, "max_status_age_seconds": 300},
    "privacy": {"redact_account_identifiers": True, "redact_credentials": True},
}


def capacity_record(seat: str, status: str) -> dict:
    return {
        "seat": seat,
        "provider": "fixture",
        "model": seat,
        "status": status,
        "source": "test",
        "reason": status,
        "checked_at": "2026-06-29T00:00:00Z",
        "reset_at": "",
        "stale_after_seconds": 300,
        "blocking": status in {"hard_exhausted", "unavailable"},
    }


class ConciliumRuntimeRequestTests(unittest.TestCase):
    def test_normalize_request_resolves_repo_and_defaults_mode(self):
        with tempfile.TemporaryDirectory() as td:
            request = concilium_runtime.normalize_request({
                "repo": td,
                "task": "Fix one typo.",
                "dry_run": True,
                "test_cmd": "python3 -m unittest",
            })

        self.assertEqual(request["mode"], "preview")
        self.assertEqual(request["task"], "Fix one typo.")
        self.assertEqual(request["test_cmd"], "python3 -m unittest")
        self.assertEqual(request["timeout"], 300)
        self.assertEqual(request["intent"], "task")
        self.assertTrue(pathlib.Path(request["repo"]).is_absolute())

    def test_invalid_mode_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "unknown execution mode"):
                concilium_runtime.normalize_request({"repo": td, "task": "x", "mode": "dry-ish"})

    def test_zero_timeout_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            cases = (
                {"repo": td, "task": "x", "timeout": 0},
                {"repo": td, "task": "x", "seat_timeout": 0},
            )
            for params in cases:
                with self.subTest(params=params):
                    with self.assertRaisesRegex(ValueError, "timeout must be positive"):
                        concilium_runtime.normalize_request(params)

    def test_live_false_with_whitespace_defaults_to_preview(self):
        with tempfile.TemporaryDirectory() as td:
            request = concilium_runtime.normalize_request({"repo": td, "task": "x", "live": " false "})

        self.assertEqual(request["mode"], "preview")

    def test_request_overlay_does_not_mutate_base_config(self):
        request = concilium_runtime.normalize_request({
            "repo": ".",
            "task": "Change routing.",
            "mode": "live_run",
            "seats": ["claude", "codex"],
            "seat_models": {
                "codex": "gpt-5-codex-high",
                "kimi": {"provider": "moonshot", "model": "kimi-k2"},
            },
            "fast_agent": "codex",
            "review_executor": "codex",
            "review_reviewer": "claude",
            "commander": "codex",
            "reviewer": "claude",
            "max_iters": 2,
            "timeout": 77,
        })

        effective = concilium_runtime.apply_request_overlay(BASE_CONFIG, request)

        self.assertEqual(request["timeout"], 77)
        self.assertEqual(request["overlay"]["seat_models"]["codex"], {"model": "gpt-5-codex-high"})
        self.assertEqual(
            request["overlay"]["seat_models"]["kimi"],
            {"provider": "moonshot", "model": "kimi-k2"},
        )
        self.assertEqual(BASE_CONFIG["lanes"]["fast"]["default_single_agent"], "kimi")
        self.assertEqual(effective["lanes"]["fast"]["default_single_agent"], "codex")
        self.assertEqual(effective["lanes"]["review"]["default_review_executor"], "codex")
        self.assertEqual(effective["lanes"]["review"]["default_review_reviewer"], "claude")
        self.assertEqual(effective["lanes"]["roundtable"]["commander"], "codex")
        self.assertEqual(effective["lanes"]["roundtable"]["reviewer"], "claude")
        self.assertEqual(effective["lanes"]["roundtable"]["seats"], ["claude", "codex"])
        self.assertEqual(effective["lanes"]["roundtable"]["max_iters"], 2)
        self.assertEqual(effective["seat_models"]["codex"], {"model": "gpt-5-codex-high"})
        self.assertEqual(effective["seat_models"]["kimi"], {"provider": "moonshot", "model": "kimi-k2"})

    def test_fingerprint_changes_when_decision_input_changes(self):
        with tempfile.TemporaryDirectory() as td:
            base = concilium_runtime.normalize_request({"repo": td, "task": "Fix docs.", "mode": "stub_run"})
            changed = concilium_runtime.normalize_request({"repo": td, "task": "Fix docs.", "mode": "live_run"})

        self.assertNotEqual(
            concilium_runtime.request_fingerprint(base),
            concilium_runtime.request_fingerprint(changed),
        )

    def test_fingerprint_changes_for_each_declared_key(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as other:
            base = concilium_runtime.normalize_request({
                "repo": td,
                "task": "Fix docs.",
                "test_cmd": "python3 -m unittest",
                "mode": "stub_run",
                "timeout": 30,
                "intent": "task",
                "signals": {"risk": "low"},
                "fast_agent": "kimi",
            })

            variants = {
                "repo": {"repo": other},
                "task": {"task": "Fix docs and tests."},
                "test_cmd": {"test_cmd": "python3 -m pytest"},
                "mode": {"mode": "preview"},
                "timeout": {"timeout": 31},
                "intent": {"intent": "tiny_smoke"},
                "signals": {"signals": {"risk": "medium"}},
                "overlay": {"fast_agent": "codex"},
            }
            base_fingerprint = concilium_runtime.request_fingerprint(base)
            for key, updates in variants.items():
                params = {
                    "repo": td,
                    "task": "Fix docs.",
                    "test_cmd": "python3 -m unittest",
                    "mode": "stub_run",
                    "timeout": 30,
                    "intent": "task",
                    "signals": {"risk": "low"},
                    "fast_agent": "kimi",
                }
                params.update(copy.deepcopy(updates))
                with self.subTest(key=key):
                    changed = concilium_runtime.normalize_request(params)
                    self.assertNotEqual(
                        base_fingerprint,
                        concilium_runtime.request_fingerprint(changed),
                    )


class ConciliumRuntimeAdapterTests(unittest.TestCase):
    def test_preview_builds_route_without_executor_call(self):
        with tempfile.TemporaryDirectory() as td:
            executor = mock.Mock(side_effect=AssertionError("executor must not run for preview"))

            result = concilium_runtime.run_concilium_adapter(
                {
                    "repo": td,
                    "task": "Fix one typo in docs/example.md.",
                    "test_cmd": "true",
                    "mode": "preview",
                    "signals": {"risk": "low", "file_count": 1, "security_sensitive": False, "ambiguous": False},
                },
                config=BASE_CONFIG,
                capacity=[capacity_record("kimi", "ok")],
                lane_executor=executor,
            )

        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["route"]["lane"], "fast")
        self.assertEqual(result["guard"]["status"], "allowed")
        self.assertTrue(result["request_fingerprint"])
        executor.assert_not_called()

    def test_stub_run_emits_done_without_live_executor(self):
        with tempfile.TemporaryDirectory() as td:
            sink = concilium_runtime.concilium_events.ListEventSink()
            executor = mock.Mock(side_effect=AssertionError("executor must not run for stub_run"))

            result = concilium_runtime.run_concilium_adapter(
                {
                    "repo": td,
                    "task": "Change config routing behavior.",
                    "test_cmd": "true",
                    "mode": "stub_run",
                    "signals": {"risk": "medium", "file_count": 2, "security_sensitive": False, "ambiguous": False},
                },
                event_sink=sink,
                config=BASE_CONFIG,
                capacity=[capacity_record("kimi", "ok"), capacity_record("hermes", "ok")],
                lane_executor=executor,
            )

        self.assertEqual(result["status"], "stubbed")
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["route"]["lane"], "review")
        self.assertEqual(
            [event["type"] for event in sink.events],
            ["start", "preflight", "guard", "seat", "seat", "finish", "done"],
        )
        self.assertEqual([event["seat"] for event in sink.events if event["type"] == "seat"], ["kimi", "hermes"])
        executor.assert_not_called()

    def test_live_run_warning_requires_confirmation_without_executor_call(self):
        with tempfile.TemporaryDirectory() as td:
            sink = concilium_runtime.concilium_events.ListEventSink()
            executor = mock.Mock(side_effect=AssertionError("executor must not run without guard allowance"))

            result = concilium_runtime.run_concilium_adapter(
                {
                    "repo": td,
                    "task": "Change config routing behavior.",
                    "test_cmd": "true",
                    "mode": "live_run",
                    "signals": {"risk": "medium", "file_count": 2, "security_sensitive": False, "ambiguous": False},
                },
                event_sink=sink,
                config=BASE_CONFIG,
                capacity=[capacity_record("kimi", "ok"), capacity_record("hermes", "unknown")],
                lane_executor=executor,
            )

        self.assertEqual(result["status"], "confirmation_required")
        self.assertEqual(result["guard"]["status"], "confirmation_required")
        self.assertTrue(result["guard"]["confirmation_payload"]["request_fingerprint"])
        self.assertEqual([event["type"] for event in sink.events], ["start", "preflight", "guard", "finish", "done"])
        self.assertEqual(sink.events[-2]["rc"], 3)
        self.assertEqual(sink.events[-1]["rc"], 3)
        executor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
