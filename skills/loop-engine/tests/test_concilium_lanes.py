#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium_lanes.py"
spec = importlib.util.spec_from_file_location("concilium_lanes", MODULE)
concilium_lanes = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(concilium_lanes)


class ConciliumLanesTests(unittest.TestCase):
    def _successful_process(self, *args, **kwargs):
        return {"returncode": 0, "output": "", "timed_out": False, "duration_seconds": 0.0}

    def test_seat_timeout_env_maps_configured_slow_review_seats(self):
        config = {
            "timeouts": {
                "seat_mode_seconds": {
                    "claude": {"plan": 600, "review": 600},
                    "codex": {"review": 600},
                }
            }
        }

        env = concilium_lanes._seat_timeout_env(300, config)

        self.assertEqual(env["LOOP_SEAT_TIMEOUT"], "300")
        self.assertEqual(env["LOOP_SEAT_TIMEOUT_CLAUDE_PLAN"], "600")
        self.assertEqual(env["LOOP_SEAT_TIMEOUT_CLAUDE_REVIEW"], "600")
        self.assertEqual(env["LOOP_SEAT_TIMEOUT_CODEX_REVIEW"], "600")

    def test_roundtable_lane_passes_seat_models_to_conductor(self):
        config = {
            "seat_models": {
                "claude": {"provider": "anthropic", "model": "claude-opus"},
                "kimi": {"model": "kimi-k2"},
            },
            "lanes": {
                "roundtable": {
                    "commander": "claude",
                    "reviewer": "hermes",
                    "seats": ["claude", "kimi"],
                    "max_iters": 2,
                }
            },
        }
        with tempfile.TemporaryDirectory() as td, mock.patch.object(concilium_lanes.conductor, "run", return_value=0) as run:
            result = concilium_lanes.run_roundtable_lane(td, "Design the adapter.", "true", config, timeout=12)

        self.assertEqual(result, {"status": "ran", "lane": "roundtable", "returncode": 0})
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["seat_models"], config["seat_models"])

    def test_fast_lane_roster_write_uses_fast_session_and_restores_environment(self):
        captured_env = {}

        def capture_roster_env(*args, **kwargs):
            captured_env["LOOP_SESSION"] = os.environ.get("LOOP_SESSION")
            captured_env["LOOP_SEAT_TIMEOUT"] = os.environ.get("LOOP_SEAT_TIMEOUT")
            captured_env["LOOP_ARCHIVE"] = os.environ.get("LOOP_ARCHIVE")
            return ["kimi"]

        with tempfile.TemporaryDirectory() as td, \
                mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(concilium_lanes.process_runner, "run_process_group", side_effect=self._successful_process), \
                mock.patch.object(concilium_lanes.conductor, "write_roster", side_effect=capture_roster_env):
            result = concilium_lanes.run_fast_lane(td, "Design the adapter.", "true", "kimi", timeout=12)

            self.assertNotIn("LOOP_SESSION", os.environ)
            self.assertNotIn("LOOP_SEAT_TIMEOUT", os.environ)
            self.assertNotIn("LOOP_ARCHIVE", os.environ)

        self.assertEqual(result["status"], "ran")
        self.assertEqual(captured_env["LOOP_SESSION"], "fast-Design-the-adapter")
        self.assertEqual(captured_env["LOOP_SEAT_TIMEOUT"], "12")
        self.assertEqual(captured_env["LOOP_ARCHIVE"], "0")


if __name__ == "__main__":
    unittest.main()
