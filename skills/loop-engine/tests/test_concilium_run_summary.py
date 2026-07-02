#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium_run_summary.py"
spec = importlib.util.spec_from_file_location("concilium_run_summary", MODULE)
concilium_run_summary = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(concilium_run_summary)


def base_result() -> dict:
    return {
        "status": "ran",
        "mode": "live_run",
        "request_fingerprint": "abc123",
        "request": {"repo": "/repo", "task": "Audit.", "mode": "live_run"},
        "route": {"lane": "audit", "required_seats": ["claude", "hermes", "kimi"]},
        "preflight": {"status": "warn", "warnings": ["capacity unknown"], "blocking_seats": []},
        "guard": {"status": "allowed", "requires_confirmation": False},
        "capacity": [
            {"seat": "claude", "provider": "anthropic", "model": "opus", "status": "unknown", "source": "not_checked"},
            {"seat": "hermes", "provider": "DeepSeek", "model": "deepseek-v4-flash", "status": "unknown", "source": "not_checked"},
            {"seat": "kimi", "provider": "moonshot", "model": "kimi-code/kimi-for-coding", "status": "unknown", "source": "not_checked"},
        ],
        "seat_results": [
            {"seat": "claude", "mode": "review", "backend_type": "external_cli", "status": "invoked", "rc": 0, "verdict": "PASS"},
            {"seat": "hermes", "mode": "review", "backend_type": "external_cli", "status": "invoked", "rc": 0, "verdict": "PASS"},
            {"seat": "kimi", "mode": "review", "backend_type": "external_cli", "status": "invoked", "rc": 0, "verdict": "PASS"},
        ],
        "verify": {"returncode": 0, "output": "OK"},
        "artifact_gate": {"status": "passed", "disallowed_delta": []},
        "events": [],
        "returncode": 0,
    }


class RunSummaryTests(unittest.TestCase):
    def test_build_summary_records_launcher_guard_seats_and_artifact_gate(self):
        summary = concilium_run_summary.build_run_summary(
            base_result(),
            launcher={"entrypoint": "/usr/local/bin/roundtable", "repo": "/tmp/concilium", "branch": "main", "commit": "abc"},
        )

        self.assertEqual(summary["schema_version"], "concilium.run_summary.v1")
        self.assertEqual(summary["launcher"]["commit"], "abc")
        self.assertEqual(summary["route"]["lane"], "audit")
        self.assertEqual(summary["budget_guard"]["status"], "allowed")
        self.assertEqual(summary["final_verdict"], "pass")
        self.assertEqual([seat["seat"] for seat in summary["seats"]], ["claude", "hermes", "kimi"])
        self.assertTrue(all(seat["backend_type"] == "external_cli" for seat in summary["seats"]))
        self.assertEqual(summary["artifact_gate"]["status"], "passed")

    def test_quota_error_becomes_retry_required_not_block(self):
        result = base_result()
        result["returncode"] = 1
        result["seat_results"][2] = {
            "seat": "kimi",
            "mode": "review",
            "backend_type": "external_cli",
            "status": "invoked",
            "rc": 1,
            "verdict": "ERR",
            "output_tail": "provider.rate_limit: 429 You've reached your usage limit for this period. Your quota will be refreshed in the next period.",
        }

        summary = concilium_run_summary.build_run_summary(result, launcher={"commit": "abc"})

        self.assertEqual(summary["seats"][2]["outcome"], "quota_exhausted")
        self.assertEqual(summary["final_verdict"], "retry_required")
        self.assertIn("kimi", summary["retry_required_seats"])
        self.assertEqual(summary["blocking_seats"], [])

    def test_blocking_review_remains_block(self):
        result = base_result()
        result["returncode"] = 2
        result["seat_results"][1]["rc"] = 2
        result["seat_results"][1]["verdict"] = "BLOCK"

        summary = concilium_run_summary.build_run_summary(result, launcher={"commit": "abc"})

        self.assertEqual(summary["final_verdict"], "block")
        self.assertEqual(summary["blocking_seats"], ["hermes"])

    def test_blocking_review_with_quota_text_still_blocks(self):
        result = base_result()
        result["returncode"] = 2
        result["seat_results"][1] = {
            "seat": "hermes",
            "mode": "review",
            "backend_type": "external_cli",
            "status": "invoked",
            "rc": 2,
            "verdict": "BLOCK",
            "output_tail": "This quota classifier can mis-handle 429 errors and weaken reviewer authority.",
        }

        summary = concilium_run_summary.build_run_summary(result, launcher={"commit": "abc"})

        self.assertEqual(summary["seats"][1]["outcome"], "block")
        self.assertEqual(summary["final_verdict"], "block")
        self.assertEqual(summary["blocking_seats"], ["hermes"])

    def test_roundtable_state_fills_seats_when_lane_has_no_seat_results(self):
        result = base_result()
        result.pop("seat_results")
        result["roundtable_state"] = {
            "participants": ["claude", "hermes"],
            "seat_verdicts": [
                {"iter": 1, "seat": "claude", "mode": "review", "rc": 0, "verdict": "PASS"},
                {"iter": 1, "seat": "hermes", "mode": "review", "rc": 2, "verdict": "BLOCK"},
            ],
            "seat_timings": [
                {"iter": 1, "seat": "claude", "mode": "review", "rc": 0, "duration_seconds": 10.5},
                {"iter": 1, "seat": "hermes", "mode": "review", "rc": 2, "duration_seconds": 8.25},
            ],
        }

        summary = concilium_run_summary.build_run_summary(result, launcher={"commit": "abc"})

        self.assertEqual([seat["seat"] for seat in summary["seats"]], ["claude", "hermes"])
        self.assertEqual(summary["seats"][1]["duration_seconds"], 8.25)
        self.assertEqual(summary["final_verdict"], "block")

    def test_roundtable_state_uses_latest_iter_per_seat_mode(self):
        result = base_result()
        result.pop("seat_results")
        result["roundtable_state"] = {
            "participants": ["claude", "hermes"],
            "seat_verdicts": [
                {"iter": 1, "seat": "claude", "mode": "review", "rc": 0, "verdict": "PASS"},
                {"iter": 1, "seat": "hermes", "mode": "review", "rc": 2, "verdict": "BLOCK"},
                {"iter": 2, "seat": "claude", "mode": "review", "rc": 0, "verdict": "PASS"},
                {"iter": 2, "seat": "hermes", "mode": "review", "rc": 0, "verdict": "PASS"},
            ],
            "seat_timings": [
                {"iter": 1, "seat": "claude", "mode": "review", "rc": 0, "duration_seconds": 10.5},
                {"iter": 1, "seat": "hermes", "mode": "review", "rc": 2, "duration_seconds": 8.25},
                {"iter": 2, "seat": "claude", "mode": "review", "rc": 0, "duration_seconds": 6.5},
                {"iter": 2, "seat": "hermes", "mode": "review", "rc": 0, "duration_seconds": 7.25},
            ],
        }

        summary = concilium_run_summary.build_run_summary(result, launcher={"commit": "abc"})

        self.assertEqual(summary["final_verdict"], "pass")
        self.assertEqual(summary["blocking_seats"], [])
        self.assertEqual(summary["seats"][1]["duration_seconds"], 7.25)

    def test_write_summary_persists_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "run-summary.json"
            summary = concilium_run_summary.write_run_summary(path, base_result(), launcher={"commit": "abc"})

            self.assertTrue(path.is_file())
            self.assertEqual(summary["schema_version"], "concilium.run_summary.v1")
            self.assertIn('"final_verdict": "pass"', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
