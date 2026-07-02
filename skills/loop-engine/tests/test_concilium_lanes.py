#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess
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

        self.assertEqual(result["status"], "ran")
        self.assertEqual(result["lane"], "roundtable")
        self.assertEqual(result["returncode"], 0)
        self.assertTrue(result["session_path"])
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["seat_models"], config["seat_models"])

    def test_roundtable_lane_returns_runtime_session_path(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td).resolve()
            captured = {}

            def fake_run(repo_arg, task_arg, **kwargs):
                del repo_arg, task_arg, kwargs
                captured["session"] = os.environ.get("LOOP_SESSION", "")
                return 0

            with mock.patch.object(concilium_lanes.conductor, "run", side_effect=fake_run):
                result = concilium_lanes.run_roundtable_lane(
                    repo,
                    "Complex task.",
                    "",
                    {"lanes": {"roundtable": {"seats": ["claude", "hermes", "kimi"], "max_iters": 2}}},
                    timeout=30,
                )

        self.assertTrue(captured["session"].startswith("roundtable-"))
        self.assertEqual(result["session_path"], str(repo / ".roundtable" / "sessions" / captured["session"]))

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

    def test_audit_lane_returns_session_path(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_lanes.process_runner, "run_process_group", side_effect=self._successful_process), \
                mock.patch.object(concilium_lanes.conductor, "write_roster", return_value=["claude"]), \
                mock.patch.object(concilium_lanes.conductor, "set_participants"), \
                mock.patch.object(concilium_lanes.conductor, "timed_run_seat", return_value=(0, "VERDICT: PASS")):
            repo = pathlib.Path(td).resolve()
            result = concilium_lanes.run_audit_lane(
                repo,
                "Read-only audit.",
                "",
                {"lanes": {"audit": {"seats": ["claude"]}}, "seat_models": {}},
                timeout=12,
            )

        self.assertEqual(result["status"], "ran")
        self.assertIn("/.roundtable/sessions/audit-", result["session_path"])

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

    def test_audit_lane_inner_gate_rejects_disallowed_seat_delta(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            def rogue_review(repo_arg, iteration, seat, mode, brief="", provider="", model=""):
                del iteration, seat, mode, brief, provider, model
                pathlib.Path(repo_arg, "unexpected.txt").write_text("bad\n", encoding="utf-8")
                return 0, "VERDICT: PASS\n"

            config = {
                "lanes": {
                    "audit": {
                        "seats": ["claude"],
                        "required_artifact_paths": ["docs/audits/report.md"],
                        "allowed_write_paths": ["docs/audits/report.md"],
                    }
                },
                "seat_models": {},
            }

            with mock.patch.object(concilium_lanes.process_runner, "run_process_group", side_effect=self._successful_process), \
                    mock.patch.object(concilium_lanes.conductor, "write_roster", return_value=["claude"]), \
                    mock.patch.object(concilium_lanes.conductor, "set_participants"), \
                    mock.patch.object(concilium_lanes.conductor, "timed_run_seat", side_effect=rogue_review):
                result = concilium_lanes.run_audit_lane(repo, "Read-only audit.", "", config, timeout=12)

        self.assertEqual(result["status"], "artifact_failed")
        self.assertEqual(result["returncode"], 2)
        self.assertIn("unexpected.txt", result["artifact_gate"]["disallowed_delta"])

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

    def test_plan_review_lane_returns_session_path_on_retry_required(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td).resolve()
            plan = repo / "docs" / "superpowers" / "plans" / "example.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# Example Plan\n", encoding="utf-8")
            config = {
                "lanes": {"plan_review": {"seats": ["kimi"], "plan_path": str(plan.relative_to(repo))}},
                "seat_models": {},
            }
            with mock.patch.object(concilium_lanes.process_runner, "run_process_group", side_effect=self._successful_process), \
                    mock.patch.object(concilium_lanes.conductor, "write_roster", return_value=["kimi"]), \
                    mock.patch.object(concilium_lanes.conductor, "set_participants"), \
                    mock.patch.object(concilium_lanes.conductor, "timed_run_seat", return_value=(1, "provider.rate_limit: 429 quota")):
                result = concilium_lanes.run_plan_review_lane(repo, "Review plan.", "", config, timeout=12)

        self.assertEqual(result["status"], "retry_required")
        self.assertIn("/.roundtable/sessions/plan-review-", result["session_path"])

    def test_plan_review_bad_plan_path_returns_blocked_without_session_path(self):
        result = concilium_lanes.run_plan_review_lane(
            "/tmp/repo",
            "Review plan.",
            "",
            {"lanes": {"plan_review": {"seats": ["kimi"], "plan_path": "../escape.md"}}, "seat_models": {}},
            timeout=12,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("session_path", result)

    def test_review_lane_preserves_delegated_session_path_without_summary_attachment(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td).resolve()
            session = repo / ".roundtable" / "sessions" / "review-unit"
            delegated = {
                "status": "done",
                "returncode": 0,
                "session_path": str(session),
            }
            with mock.patch.object(concilium_lanes.review_lane_module, "run_review_lane", return_value=delegated):
                result = concilium_lanes.run_review_lane(
                    repo,
                    "Review and repair.",
                    "",
                    {"lanes": {"review": {}}, "seat_models": {}},
                    timeout=12,
                )

        self.assertEqual(result["status"], "ran")
        self.assertEqual(result["lane"], "review")
        self.assertEqual(result["session_path"], str(session))
        self.assertNotIn("run_summary", result)

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
