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
        self.assertEqual(result["seat_results"], [{
            "seat": "kimi",
            "mode": "exec",
            "backend_type": "external_cli",
            "status": "invoked",
            "rc": 0,
        }])
        self.assertTrue(captured_env["LOOP_SESSION"].startswith("fast-"))
        self.assertEqual(captured_env["LOOP_SEAT_TIMEOUT"], "12")
        self.assertEqual(captured_env["LOOP_ARCHIVE"], "0")

    def test_audit_lane_sets_participants_to_actual_seated_reviewers(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_lanes.process_runner, "run_process_group", side_effect=self._successful_process), \
                mock.patch.object(concilium_lanes.conductor, "write_roster", return_value=["claude", "kimi"]) as write_roster, \
                mock.patch.object(concilium_lanes.conductor, "set_participants") as set_participants, \
                mock.patch.object(
                    concilium_lanes.conductor,
                    "timed_run_seat",
                    side_effect=[(0, "VERDICT: PASS"), (0, "VERDICT: PASS")],
                ) as timed_run:
            config = {"lanes": {"audit": {"seats": ["claude", "hermes", "kimi"]}}, "seat_models": {}}
            result = concilium_lanes.run_audit_lane(td, "Read-only audit.", "", config, timeout=12)

        write_roster.assert_called_once()
        set_participants.assert_called_once_with(str(pathlib.Path(td).resolve()), ["claude", "kimi"])
        self.assertEqual([call.args[2:4] for call in timed_run.call_args_list], [("claude", "review"), ("kimi", "review")])
        self.assertEqual([row["seat"] for row in result["seat_results"]], ["claude", "kimi"])
        self.assertEqual([row["verdict"] for row in result["seat_results"]], ["PASS", "PASS"])

    def test_audit_lane_ignores_inherited_loop_session_by_default(self):
        observed = {}

        def capture_roster_env(*args, **kwargs):
            observed["loop_session"] = os.environ.get("LOOP_SESSION")
            observed["loop_seat_timeout"] = os.environ.get("LOOP_SEAT_TIMEOUT")
            return ["claude", "hermes", "kimi"]

        config = {
            "lanes": {"audit": {"seats": ["claude", "hermes", "kimi"]}},
            "seat_models": {},
        }
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.dict(os.environ, {"LOOP_SESSION": "stale-session"}, clear=False), \
                mock.patch.object(concilium_lanes.process_runner, "run_process_group", side_effect=self._successful_process), \
                mock.patch.object(concilium_lanes.conductor, "write_roster", side_effect=capture_roster_env), \
                mock.patch.object(concilium_lanes.conductor, "set_participants"), \
                mock.patch.object(
                    concilium_lanes.conductor,
                    "timed_run_seat",
                    side_effect=[(0, "VERDICT: PASS"), (0, "VERDICT: PASS"), (0, "VERDICT: PASS")],
                ):
            result = concilium_lanes.run_audit_lane(
                td,
                "Read-only audit the architecture.",
                "",
                config,
                timeout=12,
            )
            self.assertEqual(os.environ.get("LOOP_SESSION"), "stale-session")

        self.assertEqual(result["status"], "ran")
        self.assertNotEqual(observed["loop_session"], "stale-session")
        self.assertTrue(observed["loop_session"].startswith("audit-"))
        self.assertEqual(observed["loop_seat_timeout"], "12")

    def test_plan_review_lane_initializes_session_and_sets_actual_participants(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            plan = repo / "docs" / "superpowers" / "plans" / "example.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# Example Plan\n", encoding="utf-8")
            config = {
                "lanes": {"plan_review": {"seats": ["claude", "hermes", "kimi"], "plan_path": str(plan.relative_to(repo))}},
                "seat_models": {},
            }
            with mock.patch.object(concilium_lanes.process_runner, "run_process_group", side_effect=self._successful_process) as runner, \
                    mock.patch.object(concilium_lanes.conductor, "write_roster", return_value=["claude", "hermes", "kimi"]) as write_roster, \
                    mock.patch.object(concilium_lanes.conductor, "set_participants") as set_participants, \
                    mock.patch.object(
                        concilium_lanes.conductor,
                        "timed_run_seat",
                        side_effect=[(0, "VERDICT: PASS"), (0, "VERDICT: PASS"), (0, "VERDICT: PASS")],
                    ) as timed_run:
                result = concilium_lanes.run_plan_review_lane(repo, "Review the plan.", "", config, timeout=12)

        called_bins = [pathlib.Path(call.args[0][0]).name for call in runner.call_args_list]
        self.assertIn("roundtable-init.sh", called_bins)
        self.assertIn("kb-refresh.sh", called_bins)
        write_roster.assert_called_once()
        set_participants.assert_called_once_with(str(repo.resolve()), ["claude", "hermes", "kimi"])
        self.assertEqual(result["status"], "passed")
        self.assertEqual(
            [call.args[2:4] for call in timed_run.call_args_list],
            [("claude", "review"), ("hermes", "review"), ("kimi", "review")],
        )
        self.assertEqual([row["verdict"] for row in result["seat_results"]], ["PASS", "PASS", "PASS"])

    def test_plan_review_lane_ignores_inherited_loop_session_by_default(self):
        observed = {}

        def capture_roster_env(*args, **kwargs):
            observed["loop_session"] = os.environ.get("LOOP_SESSION")
            observed["loop_seat_timeout"] = os.environ.get("LOOP_SEAT_TIMEOUT")
            return ["claude", "hermes", "kimi"]

        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            plan = repo / "docs" / "superpowers" / "plans" / "example.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# Example Plan\n", encoding="utf-8")
            config = {
                "lanes": {"plan_review": {"seats": ["claude", "hermes", "kimi"], "plan_path": str(plan.relative_to(repo))}},
                "seat_models": {},
            }
            with mock.patch.dict(os.environ, {"LOOP_SESSION": "stale-session"}, clear=False), \
                    mock.patch.object(concilium_lanes.process_runner, "run_process_group", side_effect=self._successful_process), \
                    mock.patch.object(concilium_lanes.conductor, "write_roster", side_effect=capture_roster_env), \
                    mock.patch.object(concilium_lanes.conductor, "set_participants"), \
                    mock.patch.object(
                        concilium_lanes.conductor,
                        "timed_run_seat",
                        side_effect=[(0, "VERDICT: PASS"), (0, "VERDICT: PASS"), (0, "VERDICT: PASS")],
                    ):
                result = concilium_lanes.run_plan_review_lane(repo, "方案评审，只评不改。", "", config, timeout=12)
                self.assertEqual(os.environ.get("LOOP_SESSION"), "stale-session")

        self.assertEqual(result["status"], "passed")
        self.assertNotEqual(observed["loop_session"], "stale-session")
        self.assertTrue(observed["loop_session"].startswith("plan-review-"))
        self.assertEqual(observed["loop_seat_timeout"], "12")


if __name__ == "__main__":
    unittest.main()
