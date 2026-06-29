#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "capacity_status.py"
spec = importlib.util.spec_from_file_location("capacity_status", MODULE)
capacity_status = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(capacity_status)

ROSTER_MODULE = ROOT / "skills" / "loop-engine" / "bin" / "roster-detect.py"
roster_spec = importlib.util.spec_from_file_location("roster_detect", ROSTER_MODULE)
roster_detect = importlib.util.module_from_spec(roster_spec)
assert roster_spec.loader is not None
roster_spec.loader.exec_module(roster_detect)


class CapacityStatusTests(unittest.TestCase):
    def test_status_classifies_thresholds(self):
        self.assertEqual(capacity_status.classify_percent(80, warn_below=20, block_below=5), "ok")
        self.assertEqual(capacity_status.classify_percent(15, warn_below=20, block_below=5), "soft_limited")
        self.assertEqual(capacity_status.classify_percent(4, warn_below=20, block_below=5), "hard_exhausted")
        self.assertEqual(capacity_status.classify_percent(None, warn_below=20, block_below=5), "unknown")

    def test_redaction_removes_credentials_and_account_ids(self):
        text = "token sk-live-secret email user@example.com cookie abc.def.ghi"
        redacted = capacity_status.redact(text)
        self.assertNotIn("sk-live-secret", redacted)
        self.assertNotIn("user@example.com", redacted)
        self.assertNotIn("abc.def.ghi", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_record_shape_is_stable(self):
        record = capacity_status.make_record(
            seat="kimi",
            provider="moonshot",
            model="kimi-code/kimi-for-coding",
            status="unknown",
            source="local",
            reason="quota endpoint unavailable",
        )

        self.assertEqual(record["seat"], "kimi")
        self.assertEqual(record["status"], "unknown")
        self.assertIn("checked_at", record)
        self.assertIn("blocking", record)

    def test_hard_exhausted_is_blocking(self):
        record = capacity_status.make_record(
            seat="claude",
            provider="anthropic",
            model="opus",
            status="hard_exhausted",
            source="fixture",
            reason="0 percent remaining",
        )

        self.assertTrue(record["blocking"])

    def test_summarize_blockers_names_blocking_seats(self):
        blockers = capacity_status.summarize_blockers([
            capacity_status.make_record("kimi", "moonshot", "kimi-code", "ok", "fixture", ""),
            capacity_status.make_record("hermes", "deepseek", "deepseek-v4", "unavailable", "fixture", "missing CLI"),
        ])

        self.assertEqual(blockers, ["hermes: missing CLI"])

    def test_roster_default_capacity_shape_is_unknown_and_non_blocking(self):
        seat = {"seat": "kimi", "available": True, "provider": "moonshot", "model": "kimi-code/kimi-for-coding"}

        enriched = roster_detect.attach_default_capacity(seat)

        self.assertEqual(enriched["capacity"]["status"], "unknown")
        self.assertEqual(enriched["capacity"]["source"], "not_checked")
        self.assertIsNone(enriched["capacity"]["percent_remaining"])
        self.assertFalse(enriched["capacity"]["blocking"])
        self.assertEqual(enriched["capacity"]["reason"], "capacity-status not requested")


if __name__ == "__main__":
    unittest.main()
