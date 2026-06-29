#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "benchmark-roundtable.py"
spec = importlib.util.spec_from_file_location("benchmark_roundtable", MODULE)
benchmark = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(benchmark)


def sample_task() -> dict:
    return {
        "id": "sample",
        "category": "repo-local",
        "prompt": "Make a small doc change.",
        "allowed_paths": ["docs/example.md"],
        "verify_cmds": ["python3 -c 'print(1)'"],
        "quality_checks": ["Report exists."],
        "expected_artifacts": ["report.md", "diff.patch", "test-results.txt", "result.json"],
    }


class BenchmarkRoundtableTests(unittest.TestCase):
    def test_load_tasks_requires_phase2_schema(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "tasks.json"
            path.write_text(json.dumps([{"id": "x"}]), encoding="utf-8")
            with self.assertRaises(ValueError):
                benchmark.load_tasks(path)

    def test_load_tasks_accepts_valid_task(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "tasks.json"
            path.write_text(json.dumps([sample_task()]), encoding="utf-8")
            tasks = benchmark.load_tasks(path)
        self.assertEqual(tasks[0]["id"], "sample")

    def test_dry_lane_writes_comparable_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = pathlib.Path(td)
            task = sample_task()
            record = benchmark.run_dry_lane(
                task=task,
                lane="baseline-kimi",
                lane_dir=run_dir / "task-sample" / "baseline-kimi",
                harness_commit="harness",
                task_base_commit="base",
            )

            self.assertEqual(record["lane"], "baseline-kimi")
            self.assertEqual(record["task_id"], "sample")
            self.assertEqual(record["status"], "PASS")
            self.assertTrue((run_dir / "task-sample" / "baseline-kimi" / "result.json").is_file())
            self.assertTrue((run_dir / "task-sample" / "baseline-kimi" / "report.md").is_file())
            self.assertTrue((run_dir / "task-sample" / "baseline-kimi" / "diff.patch").is_file())
            self.assertTrue((run_dir / "task-sample" / "baseline-kimi" / "test-results.txt").is_file())

    def test_run_verify_cmds_marks_failure(self):
        with tempfile.TemporaryDirectory() as td:
            result = benchmark.run_verify_cmds(
                pathlib.Path(td),
                ["python3 -c 'import sys; sys.exit(3)'"],
                timeout=30,
            )
        self.assertFalse(result["passed"])
        self.assertEqual(result["commands"][0]["returncode"], 3)

    def test_refuse_dirty_repo_without_force(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (repo / "dirty.txt").write_text("dirty", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                benchmark.ensure_clean_repo(repo, force=False)

    def test_lane_worktree_path_is_under_phase2_worktrees(self):
        path = benchmark.lane_worktree_path("run-1", "baseline-kimi", "sample")
        self.assertIn("evals/loop-engine/phase2/worktrees", str(path))
        self.assertTrue(str(path).endswith("run-1/baseline-kimi/sample"))

    def test_write_summary_creates_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = pathlib.Path(td)
            task = sample_task()
            records = [
                benchmark.run_dry_lane(task, "baseline-kimi", run_dir / "task-sample" / "baseline-kimi", "h", "b"),
                benchmark.run_dry_lane(task, "review", run_dir / "task-sample" / "review", "h", "b"),
                benchmark.run_dry_lane(task, "roundtable", run_dir / "task-sample" / "roundtable", "h", "b"),
            ]
            benchmark.write_records(run_dir / "records.jsonl", records)
            benchmark.write_summary(run_dir)
            summary = (run_dir / "summary.md").read_text(encoding="utf-8")
        self.assertIn("# Loop Engine Benchmark Summary", summary)
        self.assertIn("| sample | PASS | PASS | PASS | tie |", summary)

    def test_dry_batch_includes_review_lane(self):
        with tempfile.TemporaryDirectory() as td:
            records = benchmark.run_dry_batch([sample_task()], pathlib.Path(td), "harness", "base")

        self.assertEqual(
            sorted(record["lane"] for record in records),
            ["baseline-kimi", "review", "roundtable"],
        )

    def test_lane_record_uses_original_base_after_lane_commits(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            (repo / "tracked.txt").write_text("base\nchanged\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "lane change"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
            )

            task = sample_task()
            record = benchmark.lane_record(
                task=task,
                lane="roundtable",
                status="PASS",
                verify={"passed": True},
                repo=repo,
                lane_dir=pathlib.Path(td) / "lane",
                started=0,
                returncode=0,
                harness_commit="harness",
                task_base_commit=base,
            )

        self.assertEqual(record["task_base_commit"], base)
        self.assertIn("tracked.txt", record["changed_files"])
        self.assertIn("tracked.txt", record["diff_summary"])

    def test_resolve_commit_dereferences_annotated_tags(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "tag", "-a", "v1", "-m", "tag"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            tag_object = subprocess.check_output(["git", "rev-parse", "v1"], cwd=repo, text=True).strip()

            self.assertNotEqual(tag_object, commit)
            self.assertEqual(benchmark.resolve_commit("v1", cwd=repo), commit)

    def test_path_violations_ignore_lane_report_but_block_other_paths(self):
        task = sample_task()
        task["allowed_paths"] = ["docs/example.md"]
        violations = benchmark.path_violations(
            task,
            ["BENCHMARK-REPORT.md", "docs/example.md", "roundtable-memory/LESSONS.md"],
        )
        self.assertEqual(violations, ["roundtable-memory/LESSONS.md"])

    def test_allowed_target_changes_exclude_lane_report(self):
        task = sample_task()
        result = benchmark.classify_changed_files(task, ["BENCHMARK-REPORT.md", "docs/example.md"])
        self.assertEqual(result["allowed_target_changes"], ["docs/example.md"])
        self.assertEqual(result["violations"], [])

    def test_lane_record_blocks_when_only_lane_report_changed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (repo / "base.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "base.txt"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            (repo / "BENCHMARK-REPORT.md").write_text("report\n", encoding="utf-8")

            record = benchmark.lane_record(
                task=sample_task(),
                lane="roundtable",
                status="PASS",
                verify={"passed": True},
                repo=repo,
                lane_dir=pathlib.Path(td) / "lane",
                started=0,
                returncode=0,
                harness_commit="harness",
                task_base_commit=base,
            )

        self.assertEqual(record["status"], "ERR")
        self.assertIn("no changed files inside allowed_paths", record["blocking_findings"])

    def test_lane_record_warns_but_passes_on_nonzero_returncode_with_verified_target_diff(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (repo / "docs").mkdir()
            (repo / "docs" / "example.md").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "docs/example.md"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            (repo / "docs" / "example.md").write_text("base\nchanged\n", encoding="utf-8")

            record = benchmark.lane_record(
                task=sample_task(),
                lane="roundtable",
                status="ERR",
                verify={"passed": True},
                repo=repo,
                lane_dir=pathlib.Path(td) / "lane",
                started=0,
                returncode=1,
                harness_commit="harness",
                task_base_commit=base,
            )

        self.assertEqual(record["status"], "PASS")
        self.assertEqual(record["lane_returncode"], 1)
        self.assertEqual(record["allowed_target_changes"], ["docs/example.md"])
        self.assertIn("lane returncode 1", record["warnings"])

    def test_lane_record_blocks_when_review_verdict_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (repo / "docs").mkdir()
            (repo / "docs" / "example.md").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "docs/example.md"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            (repo / "docs" / "example.md").write_text("base\nchanged\n", encoding="utf-8")

            record = benchmark.lane_record(
                task=sample_task(),
                lane="review",
                status="PASS",
                verify={"passed": True},
                repo=repo,
                lane_dir=pathlib.Path(td) / "lane",
                started=0,
                returncode=2,
                harness_commit="harness",
                task_base_commit=base,
                review_verdict="BLOCK",
            )

        self.assertEqual(record["status"], "ERR")
        self.assertEqual(record["review_verdict"], "BLOCK")
        self.assertIn("review blocked", record["blocking_findings"])

    def test_run_review_lane_delegates_to_review_runner(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            lane_dir = pathlib.Path(td) / "lane"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (repo / "docs").mkdir()
            (repo / "docs" / "example.md").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "docs/example.md"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

            def fake_review_runner(repo_arg, task_arg, **kwargs):
                self.assertEqual(pathlib.Path(repo_arg), repo)
                self.assertEqual(task_arg, sample_task()["prompt"])
                (repo / "docs" / "example.md").write_text("base\nchanged\n", encoding="utf-8")
                session = repo / ".roundtable" / "sessions" / "review-sample"
                (session / "KB").mkdir(parents=True)
                (session / "KB" / "report.md").write_text("# report\n", encoding="utf-8")
                return {
                    "returncode": 0,
                    "review_verdict": "PASS",
                    "retries": 1,
                    "agent_calls": 4,
                    "session_path": str(session),
                }

            with mock.patch.object(benchmark.review_lane, "run_review_lane", side_effect=fake_review_runner):
                record = benchmark.run_review_lane(
                    sample_task(),
                    repo,
                    lane_dir,
                    timeout=30,
                    harness_commit="harness",
                    task_base_commit=base,
                )

            self.assertEqual(record["lane"], "review")
            self.assertEqual(record["status"], "PASS")
            self.assertEqual(record["review_verdict"], "PASS")
            self.assertEqual(record["retries"], 1)
            self.assertEqual(record["agent_calls"], 4)
            self.assertTrue((lane_dir / "result.json").is_file())
            self.assertTrue((lane_dir / "report.md").is_file())

    def test_roundtable_env_disables_archive_for_benchmark(self):
        env = benchmark.roundtable_env(timeout=123, session="phase2-sample")
        self.assertEqual(env["LOOP_SESSION"], "phase2-sample")
        self.assertEqual(env["LOOP_SEAT_TIMEOUT"], "123")
        self.assertEqual(env["LOOP_ARCHIVE"], "0")


if __name__ == "__main__":
    unittest.main()
