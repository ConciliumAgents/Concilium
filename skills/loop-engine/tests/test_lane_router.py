#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "lane_router.py"
spec = importlib.util.spec_from_file_location("lane_router", MODULE)
lane_router = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(lane_router)


class LaneRouterTests(unittest.TestCase):
    def base_config(self):
        return {
            "lanes": {
                "fast": {"default_single_agent": "kimi"},
                "review": {
                    "default_review_executor": "kimi",
                    "default_review_reviewer": "hermes",
                    "review_repair_limit": 1,
                },
                "audit": {
                    "default_reviewer": "claude",
                    "seats": ["claude", "hermes", "kimi"],
                    "allowed_report_paths": ["docs/audits/*.md"],
                },
                "plan_review": {"seats": ["claude", "hermes", "kimi"], "max_rounds": 3},
                "roundtable": {"commander": "claude", "reviewer": "", "seats": ["claude", "hermes", "kimi"]},
            },
            "routing": {"risk_posture": "balanced", "allow_auto_escalation": True, "allow_auto_downgrade": False},
        }

    def test_clear_small_task_routes_fast(self):
        result = lane_router.route_task(
            task="Fix one typo in docs/example.md.",
            signals={"file_count": 1, "risk": "low", "security_sensitive": False, "ambiguous": False},
            config=self.base_config(),
        )
        self.assertEqual(result["lane"], "fast")
        self.assertEqual(result["required_seats"], ["kimi"])

    def test_semantic_edge_routes_review(self):
        result = lane_router.route_task(
            task="Change config routing behavior and update tests.",
            signals={"file_count": 2, "risk": "medium", "security_sensitive": False, "ambiguous": False},
            config=self.base_config(),
        )
        self.assertEqual(result["lane"], "review")
        self.assertEqual(result["required_seats"], ["kimi", "hermes"])

    def test_ambiguous_or_security_routes_roundtable(self):
        result = lane_router.route_task(
            task="Redesign auth routing.",
            signals={"file_count": 4, "risk": "high", "security_sensitive": True, "ambiguous": True},
            config=self.base_config(),
        )
        self.assertEqual(result["lane"], "roundtable")
        self.assertIn("claude", result["required_seats"])

    def test_read_only_audit_routes_to_audit_lane(self):
        result = lane_router.route_task(
            task=(
                "Use Roundtable to audit architecture and memory. "
                "Read-only review; do not modify code; only write docs/audits/report.md."
            ),
            signals={
                "file_count": 20,
                "risk": "high",
                "security_sensitive": False,
                "ambiguous": True,
                "read_only": True,
                "allowed_write_paths": ["docs/audits/report.md"],
            },
            config=self.base_config(),
        )

        self.assertEqual(result["lane"], "audit")
        self.assertEqual(result["required_seats"], ["claude", "hermes", "kimi"])
        self.assertNotIn("codex", result["required_seats"])
        self.assertIn("read-only", result["reason"])

    def test_execution_plan_review_routes_to_plan_review_lane(self):
        result = lane_router.route_task(
            "Review implementation plan docs/plans/example.md; revise the plan after a member BLOCK and review again",
            {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
            self.base_config(),
        )

        self.assertEqual(result["lane"], "plan_review")
        self.assertEqual(result["required_seats"], ["claude", "hermes", "kimi"])
        self.assertNotIn("codex", result["required_seats"])
        self.assertIn("review", result["reason"])

    def test_plan_review_defaults_to_native_heterogeneous_seats_without_codex(self):
        result = lane_router.route_task(
            "Review implementation plan docs/plans/example.md; revise the plan after a member BLOCK and review again",
            {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
            self.base_config(),
        )

        self.assertEqual(result["lane"], "plan_review")
        self.assertEqual(result["required_seats"], ["claude", "hermes", "kimi"])
        self.assertNotIn("codex", result["required_seats"])

    def test_preflight_block_does_not_silent_downgrade(self):
        result = lane_router.apply_preflight(
            route={"lane": "review", "required_seats": ["kimi", "hermes"], "reason": "medium risk"},
            preflight={"status": "blocked", "blocking_seats": ["hermes"], "warnings": []},
            config=self.base_config(),
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["lane"], "review")
        self.assertIn("no silent downgrade", result["reason"])


if __name__ == "__main__":
    unittest.main()
