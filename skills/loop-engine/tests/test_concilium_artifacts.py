#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium_artifacts.py"
spec = importlib.util.spec_from_file_location("concilium_artifacts", MODULE)
concilium_artifacts = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(concilium_artifacts)


class ConciliumArtifactTests(unittest.TestCase):
    def init_repo(self, repo: Path) -> None:
        subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (repo / ".gitignore").write_text(".roundtable/\n__pycache__/\nevals/\n", encoding="utf-8")
        (repo / "tracked.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore", "tracked.md"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base"],
            cwd=repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_artifact_gate_default_allows_delta_when_allowed_paths_omitted(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.init_repo(repo)
            (repo / "docs").mkdir()
            (repo / "docs" / "extra.md").write_text("extra\n", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(repo)

        self.assertEqual(result["status"], "passed")
        self.assertIn("docs/extra.md", result["new_delta_paths"])
        self.assertEqual(result["disallowed_delta"], [])

    def test_artifact_gate_strict_empty_allowed_paths_blocks_any_new_delta(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.init_repo(repo)
            (repo / "docs").mkdir()
            (repo / "docs" / "extra.md").write_text("extra\n", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                allowed_write_paths=[],
                allow_unlisted_delta=False,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["disallowed_delta"], ["docs/extra.md"])

    def test_artifact_gate_strict_empty_allowed_paths_blocks_required_report(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.init_repo(repo)
            report = repo / "docs" / "audits" / "report.md"
            report.parent.mkdir(parents=True)
            report.write_text("# Report\n", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                required_artifact_paths=["docs/audits/report.md"],
                allowed_write_paths=[],
                baseline_delta_paths=concilium_artifacts.collect_delta(repo).get("delta_paths", []),
                allow_unlisted_required=False,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["disallowed"], ["docs/audits/report.md"])

    def test_artifact_gate_rejects_paths_that_escape_repo(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.init_repo(repo)

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                required_artifact_paths=["../outside.md", "/tmp/outside.md"],
                allowed_write_paths=["../*.md", "docs/audits/*.md"],
                allow_unlisted_required=False,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["invalid"], ["../*.md", "../outside.md", "/tmp/outside.md"])

    def test_artifact_snapshot_detects_existing_dirty_file_hash_change(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.init_repo(repo)
            tracked = repo / "tracked.md"
            tracked.write_text("dirty before review\n", encoding="utf-8")
            before = concilium_artifacts.hash_delta_snapshot(repo)

            tracked.write_text("dirty during review\n", encoding="utf-8")
            after = concilium_artifacts.hash_delta_snapshot(repo)

        self.assertEqual(
            concilium_artifacts.changed_snapshot_paths(before, after, allowed_paths=[]),
            ["tracked.md"],
        )

    def test_artifact_gate_glob_does_not_cross_directory_segments(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.init_repo(repo)
            review_dir = repo / "docs" / "audits" / "review"
            review_dir.mkdir(parents=True)
            (review_dir / "extra.md").write_text("extra\n", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                allowed_write_paths=["docs/audits/*.md"],
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["disallowed_delta"], ["docs/audits/review/extra.md"])

    def test_artifact_gate_glob_is_anchored_to_repo_relative_path(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.init_repo(repo)
            nested = repo / "tmp" / "docs" / "audits"
            nested.mkdir(parents=True)
            (nested / "report.md").write_text("wrong root\n", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                allowed_write_paths=["docs/audits/*.md"],
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["disallowed_delta"], ["tmp/docs/audits/report.md"])

    def test_required_artifact_gate_passes_existing_allowed_report(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            report = repo / "docs" / "audits" / "report.md"
            report.parent.mkdir(parents=True)
            report.write_text("# Report\n\n## Findings\n", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                required_artifact_paths=["docs/audits/report.md"],
                allowed_write_paths=["docs/audits/*.md"],
            )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["disallowed"], [])

    def test_required_artifact_gate_fails_missing_report(self):
        with tempfile.TemporaryDirectory() as td:
            result = concilium_artifacts.evaluate_artifact_gate(
                pathlib.Path(td),
                required_artifact_paths=["docs/audits/report.md"],
                allowed_write_paths=["docs/audits/*.md"],
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["missing"], ["docs/audits/report.md"])

    def test_required_artifact_gate_fails_disallowed_report_path(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            report = repo / "tmp" / "report.md"
            report.parent.mkdir(parents=True)
            report.write_text("# Report\n", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                required_artifact_paths=["tmp/report.md"],
                allowed_write_paths=["docs/audits/*.md"],
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["disallowed"], ["tmp/report.md"])

    def test_required_artifact_gate_fails_empty_report(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            report = repo / "docs" / "audits" / "report.md"
            report.parent.mkdir(parents=True)
            report.write_text("", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                required_artifact_paths=["docs/audits/report.md"],
                allowed_write_paths=["docs/audits/*.md"],
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["empty"], ["docs/audits/report.md"])

    def test_required_artifact_gate_fails_unchanged_committed_report(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            report = repo / "docs" / "audits" / "report.md"
            report.parent.mkdir(parents=True)
            report.write_text("# Old Report\n", encoding="utf-8")
            subprocess.run(["git", "add", "docs/audits/report.md"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(
                ["git", "-c", "user.email=test@example.test", "-c", "user.name=Test", "commit", "-m", "add report"],
                cwd=repo,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                required_artifact_paths=["docs/audits/report.md"],
                allowed_write_paths=["docs/audits/*.md"],
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["unchanged_required"], ["docs/audits/report.md"])

    def test_artifact_gate_fails_disallowed_git_delta(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            report = repo / "docs" / "audits" / "report.md"
            report.parent.mkdir(parents=True)
            report.write_text("# Report\n", encoding="utf-8")
            source = repo / "src" / "app.py"
            source.parent.mkdir(parents=True)
            source.write_text("print('changed')\n", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                required_artifact_paths=["docs/audits/report.md"],
                allowed_write_paths=["docs/audits/*.md"],
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["disallowed_delta"], ["src/app.py"])

    def test_artifact_gate_ignores_baseline_delta(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            source = repo / "src" / "app.py"
            source.parent.mkdir(parents=True)
            source.write_text("print('already dirty')\n", encoding="utf-8")
            baseline = concilium_artifacts.collect_delta(repo)["delta_paths"]
            report = repo / "docs" / "audits" / "report.md"
            report.parent.mkdir(parents=True)
            report.write_text("# Report\n", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                required_artifact_paths=["docs/audits/report.md"],
                allowed_write_paths=["docs/audits/*.md"],
                baseline_delta_paths=baseline,
            )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["baseline_delta_paths"], ["src/app.py"])
        self.assertEqual(result["new_delta_paths"], ["docs/audits/report.md"])
        self.assertEqual(result["disallowed_delta"], [])

    def test_run_bundle_redacts_secret_bearing_payloads(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = concilium_artifacts.write_run_bundle(
                pathlib.Path(td),
                "run-123",
                {
                    "request": {"task": "audit", "secret": "sk-secret123"},
                    "events": [
                        {
                            "type": "seat",
                            "seat": "codex",
                            "output": "SORFTIME_MCP_URL=https://example.test?key=abc123 user@example.com",
                        }
                    ],
                },
            )

            text = (bundle / "manifest.json").read_text(encoding="utf-8")

        self.assertIn("[REDACTED]", text)
        self.assertNotIn("sk-secret123", text)
        self.assertNotIn("abc123", text)
        self.assertNotIn("user@example.com", text)


if __name__ == "__main__":
    unittest.main()
