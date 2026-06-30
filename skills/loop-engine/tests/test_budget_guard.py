#!/usr/bin/env python3
from __future__ import annotations

import datetime
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "budget_guard.py"
RUNTIME_MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium_runtime.py"
spec = importlib.util.spec_from_file_location("budget_guard", MODULE)
budget_guard = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(budget_guard)


def record(seat: str, status: str, *, checked_at: str = "2026-06-29T00:00:00Z", stale_after: int = 300) -> dict:
    return {
        "seat": seat,
        "provider": "local",
        "model": seat,
        "status": status,
        "source": "fixture",
        "reason": status,
        "checked_at": checked_at,
        "reset_at": "",
        "stale_after_seconds": stale_after,
        "blocking": status in {"hard_exhausted", "unavailable"},
    }


BASE_PREVIEW = {
    "request_fingerprint": "abc123",
    "route": {"lane": "review", "reason": "medium task", "required_seats": ["kimi", "hermes"]},
    "preflight": {"status": "ok", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": []},
    "capacity": [record("kimi", "ok"), record("hermes", "ok")],
}


class BudgetGuardTests(unittest.TestCase):
    def test_preview_allows_without_confirmation(self):
        result = budget_guard.evaluate_budget_guard(BASE_PREVIEW, mode="preview")

        self.assertEqual(result["status"], "allowed")
        self.assertFalse(result["requires_confirmation"])

    def test_preview_retains_hard_block_details_without_blocking(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "hard_exhausted")]
        preview["preflight"] = {
            "status": "blocked",
            "required_seats": ["kimi", "hermes"],
            "blocking_seats": ["hermes"],
            "warnings": ["preview warning"],
        }

        result = budget_guard.evaluate_budget_guard(preview, mode="preview")

        self.assertEqual(result["status"], "allowed")
        self.assertFalse(result["requires_confirmation"])
        self.assertIn("hermes", result["blocking_seats"])
        self.assertIn("preview warning", result["warnings"])

    def test_stub_run_retains_unresolved_details_without_blocking(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok")]
        preview["preflight"] = {
            "status": "blocked",
            "required_seats": ["kimi", "hermes"],
            "blocking_seats": ["hermes"],
            "warnings": ["stub warning"],
        }

        result = budget_guard.evaluate_budget_guard(preview, mode="stub_run")

        self.assertEqual(result["status"], "allowed")
        self.assertFalse(result["requires_confirmation"])
        self.assertIn("hermes", result["unresolved_seats"])
        self.assertIn("stub warning", result["warnings"])

    def test_live_unknown_requires_per_run_confirmation(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "unknown")]
        preview["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": ["hermes unknown"]}

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertEqual(result["status"], "confirmation_required")
        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(result["confirmation_payload"]["selected_lane"], "review")
        self.assertEqual(result["confirmation_payload"]["request_fingerprint"], "abc123")
        self.assertIn("confirmation_fingerprint", result["confirmation_payload"])
        self.assertEqual(result["confirmation_payload"]["seats"][1]["reason"], "unknown")

    def test_malformed_capacity_status_requires_confirmation(self):
        cases = (None, "", "   ", "weird")
        for status in cases:
            with self.subTest(status=status):
                preview = dict(BASE_PREVIEW)
                preview["capacity"] = [record("kimi", "ok"), record("hermes", status)]
                preview["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": []}

                result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

                self.assertEqual(result["status"], "confirmation_required")
                self.assertTrue(result["requires_confirmation"])
                self.assertEqual(result["reason"], "live run requires confirmation for limited capacity")
                self.assertEqual(result["confirmation_payload"]["seats"][1]["capacity_status"], "unknown")

    def test_live_confirmation_payload_defaults_files_may_be_modified(self):
        preview = dict(BASE_PREVIEW)
        preview["mode"] = "live_run"
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "unknown")]
        preview["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": ["hermes unknown"]}

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertTrue(result["confirmation_payload"]["files_may_be_modified"])

    def test_live_guard_mode_defaults_files_may_be_modified_without_preview_mode(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "unknown")]
        preview["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": ["hermes unknown"]}

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertTrue(result["confirmation_payload"]["files_may_be_modified"])

    def test_read_only_audit_confirmation_payload_marks_target_files_not_modified(self):
        preview = {
            "request_fingerprint": "audit123",
            "mode": "live_run",
            "route": {
                "lane": "audit",
                "reason": "read-only audit uses reviewer-only lane with artifact gate",
                "required_seats": ["claude", "hermes", "kimi"],
            },
            "request": {
                "mode": "live_run",
                "signals": {
                    "read_only": True,
                    "allowed_write_paths": ["docs/audits/report.md"],
                    "required_artifact_paths": ["docs/audits/report.md"],
                },
            },
            "signals": {
                "read_only": True,
                "allowed_write_paths": ["docs/audits/report.md"],
                "required_artifact_paths": ["docs/audits/report.md"],
            },
            "capacity": [record("claude", "unknown"), record("hermes", "unknown"), record("kimi", "unknown")],
            "preflight": {
                "status": "warn",
                "required_seats": ["claude", "hermes", "kimi"],
                "blocking_seats": [],
                "warnings": ["capacity unknown"],
            },
        }

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        payload = result["confirmation_payload"]
        self.assertFalse(payload["files_may_be_modified"])
        self.assertTrue(payload["read_only_task"])
        self.assertEqual(payload["allowed_write_paths"], ["docs/audits/report.md"])
        self.assertEqual(payload["required_artifact_paths"], ["docs/audits/report.md"])

    def test_explicit_files_may_be_modified_override_wins_for_read_only_payload(self):
        preview = {
            "request_fingerprint": "audit124",
            "mode": "live_run",
            "route": {"lane": "audit", "required_seats": ["claude"]},
            "request": {"mode": "live_run", "signals": {"read_only": True}},
            "signals": {"read_only": True},
            "files_may_be_modified": True,
            "capacity": [record("claude", "unknown")],
            "preflight": {"status": "warn", "required_seats": ["claude"], "blocking_seats": [], "warnings": []},
        }

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertTrue(result["confirmation_payload"]["files_may_be_modified"])
        self.assertTrue(result["confirmation_payload"]["read_only_task"])

    def test_inferred_audit_lane_without_read_only_signal_is_read_only_in_payload(self):
        preview = {
            "request_fingerprint": "audit125",
            "mode": "live_run",
            "route": {"lane": "audit", "required_seats": ["claude"]},
            "request": {"mode": "live_run"},
            "capacity": [record("claude", "unknown")],
            "preflight": {"status": "warn", "required_seats": ["claude"], "blocking_seats": [], "warnings": []},
        }

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertFalse(result["confirmation_payload"]["files_may_be_modified"])
        self.assertTrue(result["confirmation_payload"]["read_only_task"])

    def test_matching_confirmation_allows_warn_live_run(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "soft_limited")]
        preview["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": ["hermes soft"]}

        required = budget_guard.evaluate_budget_guard(preview, mode="live_run")
        confirmed = budget_guard.evaluate_budget_guard(
            preview,
            mode="live_run",
            confirmation={
                "accepted": True,
                "request_fingerprint": required["confirmation_payload"]["request_fingerprint"],
                "confirmation_fingerprint": required["confirmation_payload"]["confirmation_fingerprint"],
            },
        )

        self.assertEqual(confirmed["status"], "allowed")

    def test_string_false_confirmation_is_rejected(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "unknown")]
        preview["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": ["hermes unknown"]}
        required = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        result = budget_guard.evaluate_budget_guard(
            preview,
            mode="live_run",
            confirmation={
                "accepted": "false",
                "request_fingerprint": required["confirmation_payload"]["request_fingerprint"],
                "confirmation_fingerprint": required["confirmation_payload"]["confirmation_fingerprint"],
            },
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "confirmation does not match current preflight")

    def test_missing_request_fingerprint_confirmation_is_rejected(self):
        preview = dict(BASE_PREVIEW)
        preview.pop("request_fingerprint")
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "unknown")]
        preview["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": ["hermes unknown"]}
        payload = budget_guard.confirmation_payload(preview)

        result = budget_guard.evaluate_budget_guard(
            preview,
            mode="live_run",
            confirmation={
                "accepted": True,
                "request_fingerprint": "",
                "confirmation_fingerprint": payload["confirmation_fingerprint"],
            },
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "confirmation does not match current preflight")

    def test_missing_request_fingerprint_blocks_initial_confirmation_flow(self):
        preview = dict(BASE_PREVIEW)
        preview.pop("request_fingerprint")
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "unknown")]
        preview["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": ["hermes unknown"]}

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["requires_confirmation"])
        self.assertEqual(result["reason"], "missing request fingerprint for confirmation")

    def test_blank_request_fingerprint_values_fail_closed(self):
        cases = (None, "   ")
        for request_fingerprint in cases:
            with self.subTest(request_fingerprint=request_fingerprint):
                preview = dict(BASE_PREVIEW)
                preview["request_fingerprint"] = request_fingerprint
                preview["capacity"] = [record("kimi", "ok"), record("hermes", "unknown")]
                preview["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": ["hermes unknown"]}

                initial = budget_guard.evaluate_budget_guard(preview, mode="live_run")

                self.assertEqual(initial["status"], "blocked")
                self.assertFalse(initial["requires_confirmation"])
                self.assertEqual(initial["reason"], "missing request fingerprint for confirmation")

                payload = budget_guard.confirmation_payload(preview)
                confirmed = budget_guard.evaluate_budget_guard(
                    preview,
                    mode="live_run",
                    confirmation={
                        "accepted": True,
                        "request_fingerprint": payload["request_fingerprint"],
                        "confirmation_fingerprint": payload["confirmation_fingerprint"],
                    },
                )

                self.assertEqual(confirmed["status"], "blocked")
                self.assertEqual(confirmed["reason"], "confirmation does not match current preflight")

    def test_mismatched_confirmation_blocks(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "unknown")]
        preview["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": ["hermes unknown"]}

        result = budget_guard.evaluate_budget_guard(
            preview,
            mode="live_run",
            confirmation={"accepted": True, "request_fingerprint": "old"},
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "confirmation does not match current preflight")

    def test_confirmation_fingerprint_must_match_current_payload(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "unknown")]
        preview["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": ["hermes unknown"]}
        required = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        changed_record = record("hermes", "soft_limited")
        changed_record["source"] = "fresh-fixture"
        changed_record["reason"] = "soft now"
        changed = dict(BASE_PREVIEW)
        changed["capacity"] = [record("kimi", "ok"), changed_record]
        changed["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": ["hermes soft"]}

        result = budget_guard.evaluate_budget_guard(
            changed,
            mode="live_run",
            confirmation={
                "accepted": True,
                "request_fingerprint": required["confirmation_payload"]["request_fingerprint"],
                "confirmation_fingerprint": required["confirmation_payload"]["confirmation_fingerprint"],
            },
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "confirmation does not match current preflight")

    def test_fresh_hard_exhausted_blocks(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "hard_exhausted")]
        preview["preflight"] = {"status": "blocked", "required_seats": ["kimi", "hermes"], "blocking_seats": ["hermes"], "warnings": []}

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertEqual(result["status"], "blocked")
        self.assertIn("hermes", result["blocking_seats"])

    def test_route_required_seats_are_authoritative(self):
        preview = dict(BASE_PREVIEW)
        preview["route"] = {"lane": "review", "reason": "medium task", "required_seats": ["kimi", "hermes"]}
        preview["preflight"] = {"status": "ok", "required_seats": ["kimi"], "blocking_seats": [], "warnings": []}
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "unavailable")]

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertEqual(result["status"], "blocked")
        self.assertIn("hermes", result["blocking_seats"])
        payload = budget_guard.confirmation_payload(preview, mode="live_run")
        self.assertEqual(payload["required_seats"], ["kimi", "hermes"])

    def test_route_required_missing_seat_blocks_as_unresolved(self):
        preview = dict(BASE_PREVIEW)
        preview["route"] = {"lane": "review", "reason": "medium task", "required_seats": ["kimi", "hermes"]}
        preview["preflight"] = {"status": "ok", "required_seats": ["kimi"], "blocking_seats": [], "warnings": []}
        preview["capacity"] = [record("kimi", "ok")]

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertEqual(result["status"], "blocked")
        self.assertIn("hermes", result["unresolved_seats"])

    def test_stale_hard_exhausted_tiny_smoke_requires_confirmation(self):
        old = "2026-06-28T00:00:00Z"
        preview = dict(BASE_PREVIEW)
        preview["request"] = {"intent": "tiny_smoke"}
        preview["capacity"] = [record("kimi", "hard_exhausted", checked_at=old, stale_after=10)]
        preview["route"] = {"lane": "fast", "reason": "tiny smoke", "required_seats": ["kimi"]}
        preview["preflight"] = {"status": "blocked", "required_seats": ["kimi"], "blocking_seats": ["kimi"], "warnings": []}

        result = budget_guard.evaluate_budget_guard(
            preview,
            mode="live_run",
            now=datetime.datetime(2026, 6, 29, tzinfo=datetime.UTC),
        )

        self.assertEqual(result["status"], "confirmation_required")
        self.assertIn("stale hard_exhausted", result["reason"])

    def test_stale_boundary_is_inclusive(self):
        stale_record = record("kimi", "ok", checked_at="2026-06-29T00:00:00Z", stale_after=300)

        result = budget_guard.is_stale(
            stale_record,
            now=datetime.datetime(2026, 6, 29, 0, 5, tzinfo=datetime.UTC),
        )

        self.assertTrue(result)

    def test_missing_required_seat_blocks_as_unresolved(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok")]
        preview["preflight"] = {"status": "blocked", "required_seats": ["kimi", "hermes"], "blocking_seats": ["hermes"], "warnings": []}

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertEqual(result["status"], "blocked")
        self.assertIn("hermes", result["unresolved_seats"])

    def test_runtime_attach_guard_imports_local_guard_module(self):
        runtime_spec = importlib.util.spec_from_file_location("concilium_runtime", RUNTIME_MODULE)
        concilium_runtime = importlib.util.module_from_spec(runtime_spec)
        assert runtime_spec.loader is not None
        runtime_spec.loader.exec_module(concilium_runtime)

        result = concilium_runtime.attach_guard(BASE_PREVIEW)

        self.assertEqual(result["guard"]["status"], "allowed")

    def test_runtime_attach_guard_ignores_shadowed_budget_guard_module(self):
        class ShadowedBudgetGuard:
            @staticmethod
            def evaluate_budget_guard(*args, **kwargs):
                raise AssertionError("shadowed module was used")

        sentinel = object()
        original = sys.modules.get("budget_guard", sentinel)
        sys.modules["budget_guard"] = ShadowedBudgetGuard
        try:
            runtime_spec = importlib.util.spec_from_file_location("concilium_runtime", RUNTIME_MODULE)
            concilium_runtime = importlib.util.module_from_spec(runtime_spec)
            assert runtime_spec.loader is not None
            runtime_spec.loader.exec_module(concilium_runtime)

            result = concilium_runtime.attach_guard(BASE_PREVIEW)
        finally:
            if original is sentinel:
                sys.modules.pop("budget_guard", None)
            else:
                sys.modules["budget_guard"] = original

        self.assertEqual(result["guard"]["status"], "allowed")


if __name__ == "__main__":
    unittest.main()
