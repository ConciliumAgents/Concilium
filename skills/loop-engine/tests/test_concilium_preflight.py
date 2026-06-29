#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium_preflight.py"
spec = importlib.util.spec_from_file_location("concilium_preflight", MODULE)
concilium_preflight = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(concilium_preflight)


class ConciliumPreflightTests(unittest.TestCase):
    def test_hard_exhausted_required_seat_blocks(self):
        result = concilium_preflight.evaluate_preflight(
            required_seats=["kimi", "hermes"],
            capacity=[
                {"seat": "kimi", "status": "ok", "blocking": False, "reason": ""},
                {"seat": "hermes", "status": "hard_exhausted", "blocking": True, "reason": "0 percent remaining"},
            ],
            allow_auto_escalation=True,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("hermes", result["blocking_seats"])

    def test_unknown_capacity_warns_but_allows(self):
        result = concilium_preflight.evaluate_preflight(
            required_seats=["kimi"],
            capacity=[{"seat": "kimi", "status": "unknown", "blocking": False, "reason": "no quota source"}],
            allow_auto_escalation=True,
        )

        self.assertEqual(result["status"], "warn")
        self.assertIn("unknown", result["warnings"][0])

    def test_missing_required_seat_blocks(self):
        result = concilium_preflight.evaluate_preflight(
            required_seats=["claude"],
            capacity=[{"seat": "kimi", "status": "ok", "blocking": False, "reason": ""}],
            allow_auto_escalation=True,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("claude", result["blocking_seats"])


if __name__ == "__main__":
    unittest.main()
