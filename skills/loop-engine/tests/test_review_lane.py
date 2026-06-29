#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "review-lane.py"
spec = importlib.util.spec_from_file_location("review_lane", MODULE)
review_lane = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(review_lane)


class ReviewLaneTests(unittest.TestCase):
    def test_requires_distinct_executor_and_reviewer(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                review_lane.run_review_lane(td, "Do the work", executor="kimi", reviewer="kimi")

    def test_pass_finishes_without_repair(self):
        calls = []

        def fake_run_seat(repo, seat, mode, brief, env, timeout):
            calls.append((seat, mode, brief))
            if mode == "exec":
                return 0, "edited"
            if mode == "review":
                return 0, "VERDICT: PASS\n"
            self.fail(f"unexpected mode: {mode}")

        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(review_lane, "init_session"), \
                mock.patch.object(review_lane, "refresh_kb"), \
                mock.patch.object(review_lane, "set_iteration") as set_iteration, \
                mock.patch.object(review_lane, "run_seat", side_effect=fake_run_seat):
            result = review_lane.run_review_lane(
                td,
                "Add docs",
                executor="kimi",
                reviewer="hermes",
                repair_limit=1,
                session="unit-review",
            )

        self.assertEqual(result["review_verdict"], "PASS")
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["retries"], 0)
        self.assertEqual(result["agent_calls"], 2)
        self.assertEqual([(seat, mode) for seat, mode, _ in calls], [("kimi", "exec"), ("hermes", "review")])
        set_iteration.assert_called_once()

    def test_init_session_overwrites_default_participants_with_lane_seats(self):
        def fake_run_cmd(args, cwd, env, timeout):
            if "roundtable-init.sh" in str(args[0]):
                state_path = pathlib.Path(td) / ".roundtable" / "sessions" / "unit-review" / "roundtable.json"
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(
                    json.dumps({"iter": 1, "participants": ["claude", "codex", "hermes"]}),
                    encoding="utf-8",
                )
            return 0, "ok"

        with tempfile.TemporaryDirectory() as td, \
                review_lane.scoped_loop_session("unit-review"), \
                mock.patch.object(review_lane, "run_cmd", side_effect=fake_run_cmd), \
                mock.patch.object(review_lane.conductor, "write_roster", return_value=["hermes", "kimi"]):
            review_lane.init_session(
                td,
                "Add docs",
                "true",
                review_lane.review_lane_env(30, "unit-review"),
                30,
                ["kimi", "hermes"],
            )

            state = json.loads(
                (pathlib.Path(td) / ".roundtable" / "sessions" / "unit-review" / "roundtable.json")
                .read_text(encoding="utf-8")
            )

        self.assertEqual(state["participants"], ["kimi", "hermes"])

    def test_block_triggers_one_repair_pass(self):
        calls = []
        review_count = {"n": 0}

        def fake_run_seat(repo, seat, mode, brief, env, timeout):
            calls.append((seat, mode, brief))
            if mode == "exec":
                return 0, "edited"
            if mode == "review":
                review_count["n"] += 1
                if review_count["n"] == 1:
                    return 2, "[HIGH] missing detail\nVERDICT: BLOCK\n"
                return 0, "fixed\nVERDICT: PASS\n"
            self.fail(f"unexpected mode: {mode}")

        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(review_lane, "init_session"), \
                mock.patch.object(review_lane, "refresh_kb"), \
                mock.patch.object(review_lane, "set_iteration") as set_iteration, \
                mock.patch.object(review_lane, "run_seat", side_effect=fake_run_seat):
            result = review_lane.run_review_lane(
                td,
                "Add docs",
                executor="kimi",
                reviewer="hermes",
                repair_limit=1,
                session="unit-review",
            )

        self.assertEqual(result["review_verdict"], "PASS")
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["retries"], 1)
        self.assertEqual(result["agent_calls"], 4)
        self.assertEqual([(seat, mode) for seat, mode, _ in calls], [
            ("kimi", "exec"),
            ("hermes", "review"),
            ("kimi", "exec"),
            ("hermes", "review"),
        ])
        repair_brief = calls[2][2]
        self.assertIn("Previous review blocked", repair_brief)
        self.assertIn("VERDICT: BLOCK", repair_brief)
        resolved_td = str(pathlib.Path(td).resolve())
        set_iteration.assert_has_calls([mock.call(resolved_td, 1), mock.call(resolved_td, 2)])

    def test_final_block_is_returned_after_repair_limit(self):
        def fake_run_seat(repo, seat, mode, brief, env, timeout):
            if mode == "exec":
                return 0, "edited"
            if mode == "review":
                return 2, "still bad\nVERDICT: BLOCK\n"
            self.fail(f"unexpected mode: {mode}")

        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(review_lane, "init_session"), \
                mock.patch.object(review_lane, "refresh_kb"), \
                mock.patch.object(review_lane, "set_iteration"), \
                mock.patch.object(review_lane, "run_seat", side_effect=fake_run_seat):
            result = review_lane.run_review_lane(
                td,
                "Add docs",
                executor="kimi",
                reviewer="hermes",
                repair_limit=1,
                session="unit-review",
            )

        self.assertEqual(result["review_verdict"], "BLOCK")
        self.assertEqual(result["returncode"], 2)
        self.assertEqual(result["retries"], 1)
        self.assertEqual(result["agent_calls"], 4)


if __name__ == "__main__":
    unittest.main()
