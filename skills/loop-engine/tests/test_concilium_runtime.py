#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest

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

    def test_request_overlay_does_not_mutate_base_config(self):
        request = concilium_runtime.normalize_request({
            "repo": ".",
            "task": "Change routing.",
            "mode": "live_run",
            "seats": ["claude", "codex"],
            "seat_models": {"codex": "gpt-5-codex-high"},
            "fast_agent": "codex",
            "review_executor": "codex",
            "review_reviewer": "claude",
            "commander": "codex",
            "reviewer": "claude",
            "max_iters": 2,
            "timeout": 77,
        })

        effective = concilium_runtime.apply_request_overlay(BASE_CONFIG, request)

        self.assertEqual(BASE_CONFIG["lanes"]["fast"]["default_single_agent"], "kimi")
        self.assertEqual(effective["lanes"]["fast"]["default_single_agent"], "codex")
        self.assertEqual(effective["lanes"]["review"]["default_review_executor"], "codex")
        self.assertEqual(effective["lanes"]["review"]["default_review_reviewer"], "claude")
        self.assertEqual(effective["lanes"]["roundtable"]["commander"], "codex")
        self.assertEqual(effective["lanes"]["roundtable"]["reviewer"], "claude")
        self.assertEqual(effective["lanes"]["roundtable"]["seats"], ["claude", "codex"])
        self.assertEqual(effective["lanes"]["roundtable"]["max_iters"], 2)
        self.assertEqual(effective["seat_models"]["codex"], "gpt-5-codex-high")

    def test_fingerprint_changes_when_decision_input_changes(self):
        with tempfile.TemporaryDirectory() as td:
            base = concilium_runtime.normalize_request({"repo": td, "task": "Fix docs.", "mode": "stub_run"})
            changed = concilium_runtime.normalize_request({"repo": td, "task": "Fix docs.", "mode": "live_run"})

        self.assertNotEqual(
            concilium_runtime.request_fingerprint(base),
            concilium_runtime.request_fingerprint(changed),
        )


if __name__ == "__main__":
    unittest.main()
