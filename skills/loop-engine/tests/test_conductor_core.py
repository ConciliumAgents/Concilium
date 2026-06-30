#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "conductor.py"
spec = importlib.util.spec_from_file_location("conductor", MODULE)
conductor = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(conductor)


class QuietReporter(conductor.Reporter):
    def __init__(self):
        self.events = []

    def start(self, repo, task, commander, reviewer, max_iters):
        self.events.append(("start", reviewer))

    def round(self, it):
        self.events.append(("round", it))

    def plan(self, plan):
        self.events.append(("plan", plan))

    def seat(self, agent, mode, subtask="", rc=None, phase="start"):
        self.events.append(("seat", phase, agent, mode, subtask, rc))

    def verdict(self, reviewer, v):
        self.events.append(("verdict", reviewer, v))

    def finish(self, status, it):
        self.events.append(("finish", status, it))

    def log(self, msg):
        self.events.append(("log", msg))

    def transcript(self, agent, mode, text):
        self.events.append(("transcript", agent, mode, text))


def init_repo(repo: pathlib.Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    (repo / ".gitignore").write_text(".roundtable/\n", encoding="utf-8")
    (repo / "tracked.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore", "tracked.md"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base"],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )


class ConductorPatch:
    def __init__(self, test: unittest.TestCase, repo: pathlib.Path, run_seat):
        self.test = test
        self.repo = repo
        self.run_seat = run_seat
        self.originals = {}
        self.env_original = os.environ.get("LOOP_SESSION")

    def __enter__(self):
        for name in ("write_roster", "run_seat", "sh_capture", "import_memory", "write_conclusion", "archive_to_memory"):
            self.originals[name] = getattr(conductor, name)
        conductor.write_roster = lambda repo, seats=None, seat_models=None: ["claude", "hermes", "kimi"]
        conductor.run_seat = self.run_seat
        conductor.sh_capture = self.sh_capture
        conductor.import_memory = lambda repo: 0
        conductor.write_conclusion = lambda *args, **kwargs: None
        conductor.archive_to_memory = lambda *args, **kwargs: None
        os.environ["LOOP_SESSION"] = "unit-session"
        return self

    def __exit__(self, exc_type, exc, tb):
        for name, value in self.originals.items():
            setattr(conductor, name, value)
        if self.env_original is None:
            os.environ.pop("LOOP_SESSION", None)
        else:
            os.environ["LOOP_SESSION"] = self.env_original

    def sh_capture(self, script: str, *args: str):
        session = self.repo / ".roundtable" / "sessions" / os.environ["LOOP_SESSION"]
        (session / "KB").mkdir(parents=True, exist_ok=True)
        (session / "minutes").mkdir(parents=True, exist_ok=True)
        if script == "roundtable-init.sh":
            (session / "roundtable.json").write_text(json.dumps({"iter": 1}), encoding="utf-8")
        return 0, ""


class ConductorCoreTests(unittest.TestCase):
    def test_split_path_list_accepts_commas_and_colons(self):
        self.assertEqual(
            conductor.split_path_list("docs/a.md,docs/b.md:reports/c.md"),
            ["docs/a.md", "docs/b.md", "reports/c.md"],
        )

    def test_review_err_falls_back_to_alternate_reviewer(self):
        calls = []
        reporter = QuietReporter()
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)

            def fake_run_seat(agent, mode, repo_arg, brief="", extra=None, provider="", model=""):
                calls.append((agent, mode, brief))
                if mode == "plan":
                    return 0, '```json\n[{"agent":"kimi","subtask":"edit tracked.md"}]\n```'
                if mode == "exec":
                    pathlib.Path(repo_arg, "tracked.md").write_text("base\nchanged\n", encoding="utf-8")
                    return 0, "edited"
                if agent == "hermes" and mode == "review":
                    return 1, "API call failed after 3 retries: HTTP 429: Error"
                if agent == "claude" and mode == "review":
                    return 0, "VERDICT: PASS\n"
                return self.fail(f"unexpected call: {agent} {mode}")

            with ConductorPatch(self, repo, fake_run_seat):
                rc = conductor.run(str(repo), "Edit tracked.md", max_iters=1, reporter=reporter)

        self.assertEqual(rc, 0)
        self.assertIn(("hermes", "review", ""), calls)
        self.assertIn(("claude", "review", ""), calls)
        self.assertIn(("verdict", "claude", "PASS"), reporter.events)

    def test_review_block_does_not_fall_back_to_alternate_reviewer(self):
        calls = []
        reporter = QuietReporter()
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)

            def fake_run_seat(agent, mode, repo_arg, brief="", extra=None, provider="", model=""):
                calls.append((agent, mode, brief))
                if mode == "plan":
                    return 0, '```json\n[{"agent":"kimi","subtask":"edit tracked.md"}]\n```'
                if mode == "exec":
                    pathlib.Path(repo_arg, "tracked.md").write_text("base\nchanged\n", encoding="utf-8")
                    return 0, "edited"
                if agent == "hermes" and mode == "review":
                    return 2, "VERDICT: BLOCK\n"
                if agent == "claude" and mode == "review":
                    return self.fail("BLOCK must not trigger reviewer fallback")
                return self.fail(f"unexpected call: {agent} {mode}")

            with ConductorPatch(self, repo, fake_run_seat):
                rc = conductor.run(str(repo), "Edit tracked.md", max_iters=1, reporter=reporter)

        self.assertEqual(rc, 2)
        self.assertIn(("hermes", "review", ""), calls)
        self.assertNotIn(("claude", "review", ""), calls)
        self.assertIn(("verdict", "hermes", "BLOCK"), reporter.events)

    def test_plan_prompt_names_execution_pool_and_excludes_reviewer(self):
        plan_briefs = []
        reporter = QuietReporter()
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)

            def fake_run_seat(agent, mode, repo_arg, brief="", extra=None, provider="", model=""):
                if mode == "plan":
                    plan_briefs.append(brief)
                    return 0, '```json\n[{"agent":"kimi","subtask":"edit tracked.md"}]\n```'
                if mode == "exec":
                    pathlib.Path(repo_arg, "tracked.md").write_text("base\nchanged\n", encoding="utf-8")
                    return 0, "exec ok"
                if mode == "review":
                    return 0, "VERDICT: PASS\n"
                return self.fail(f"unexpected call: {agent} {mode}")

            with ConductorPatch(self, repo, fake_run_seat):
                rc = conductor.run(str(repo), "Edit tracked.md", max_iters=1, reporter=reporter)

        self.assertEqual(rc, 0)
        self.assertEqual(len(plan_briefs), 1)
        self.assertIn("执行池: kimi", plan_briefs[0])
        self.assertIn("验证席: hermes", plan_briefs[0])
        self.assertIn("不要输出只读复审子任务", plan_briefs[0])
        self.assertIn(("verdict", "hermes", "PASS"), reporter.events)

    def test_run_records_seat_timings_in_roundtable_state(self):
        reporter = QuietReporter()
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)

            def fake_run_seat(agent, mode, repo_arg, brief="", extra=None, provider="", model=""):
                if mode == "plan":
                    return 0, '```json\n[{"agent":"kimi","subtask":"edit tracked.md"}]\n```'
                if mode == "exec":
                    pathlib.Path(repo_arg, "tracked.md").write_text("base\nchanged\n", encoding="utf-8")
                    return 0, "edited"
                if mode == "review":
                    return 0, "VERDICT: PASS\n"
                return self.fail(f"unexpected call: {agent} {mode}")

            with ConductorPatch(self, repo, fake_run_seat):
                rc = conductor.run(str(repo), "Edit tracked.md", max_iters=1, reporter=reporter)

            state = json.loads(
                (repo / ".roundtable" / "sessions" / "unit-session" / "roundtable.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(rc, 0)
        timings = state["seat_timings"]
        observed = {(row["seat"], row["mode"], row["rc"]) for row in timings}
        self.assertIn(("claude", "plan", 0), observed)
        self.assertIn(("kimi", "exec", 0), observed)
        self.assertIn(("hermes", "review", 0), observed)
        for row in timings:
            self.assertEqual(row["iter"], 1)
            self.assertIsInstance(row["duration_seconds"], float)
            self.assertGreaterEqual(row["duration_seconds"], 0.0)

    def test_read_only_audit_task_routes_only_reviewers(self):
        calls = []
        reporter = QuietReporter()
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)

            def fake_run_seat(agent, mode, repo_arg, brief="", extra=None, provider="", model=""):
                calls.append((agent, mode, brief))
                if mode in {"plan", "exec"}:
                    return self.fail(f"read-only audit must not call {mode}")
                if mode == "review":
                    return 0, "VERDICT: PASS\n"
                return self.fail(f"unexpected call: {agent} {mode}")

            with ConductorPatch(self, repo, fake_run_seat):
                rc = conductor.run(
                    str(repo),
                    "Read-only audit the architecture and memory system.",
                    max_iters=2,
                    reporter=reporter,
                )

        self.assertEqual(rc, 0)
        self.assertTrue(calls)
        self.assertEqual({mode for _agent, mode, _brief in calls}, {"review"})
        self.assertIn(("finish", "PASS", 1), reporter.events)

    def test_audit_only_flag_routes_only_reviewers_even_without_keywords(self):
        calls = []
        reporter = QuietReporter()
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)

            def fake_run_seat(agent, mode, repo_arg, brief="", extra=None, provider="", model=""):
                calls.append((agent, mode))
                if mode in {"plan", "exec"}:
                    return self.fail(f"audit_only must not call {mode}")
                return 0, "VERDICT: PASS\n"

            with ConductorPatch(self, repo, fake_run_seat):
                rc = conductor.run(
                    str(repo),
                    "Inspect architecture.",
                    max_iters=2,
                    reporter=reporter,
                    audit_only=True,
                )

        self.assertEqual(rc, 0)
        self.assertEqual({mode for _agent, mode in calls}, {"review"})

    def test_read_only_audit_blocks_disallowed_delta(self):
        reporter = QuietReporter()
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)

            def fake_run_seat(agent, mode, repo_arg, brief="", extra=None, provider="", model=""):
                if mode != "review":
                    return self.fail(f"read-only audit must not call {mode}")
                pathlib.Path(repo_arg, "leak.md").write_text("modified by reviewer\n", encoding="utf-8")
                return 0, "VERDICT: PASS\n"

            with ConductorPatch(self, repo, fake_run_seat):
                rc = conductor.run(
                    str(repo),
                    "Read-only audit the architecture.",
                    max_iters=1,
                    reporter=reporter,
                    allowed_write_paths=[],
                )

            self.assertTrue((repo / "leak.md").exists())

        self.assertEqual(rc, 2)
        self.assertIn(("finish", "BLOCK", 1), reporter.events)


if __name__ == "__main__":
    unittest.main()
