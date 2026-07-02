#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "session_retention.py"
spec = importlib.util.spec_from_file_location("session_retention", MODULE)
session_retention = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(session_retention)


class SessionRetentionTests(unittest.TestCase):
    def test_scan_marks_sensitive_session_without_printing_secret(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            session = repo / ".roundtable" / "sessions" / "audit-1"
            (session / "KB").mkdir(parents=True)
            (session / "KB" / "task.md").write_text("see .codex/config.toml key=sk-live-secret\n", encoding="utf-8")

            report = session_retention.scan_repo(repo)

        self.assertEqual(report["sessions"][0]["sensitivity"], "sensitive_possible")
        self.assertIn(".codex/config.toml", report["sessions"][0]["indicators"])
        encoded = json.dumps(report)
        self.assertNotIn("sk-live-secret", encoded)

    def test_prune_requires_yes(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            session = repo / ".roundtable" / "sessions" / "audit-1"
            session.mkdir(parents=True)

            removed = session_retention.prune_repo(repo, yes=False)

            self.assertEqual(removed, [])
            self.assertTrue(session.exists())

    def test_prune_removes_matching_session_with_yes(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            session = repo / ".roundtable" / "sessions" / "audit-1"
            session.mkdir(parents=True)

            removed = session_retention.prune_repo(repo, yes=True)

            self.assertEqual(removed, [str(session.resolve())])
            self.assertFalse(session.exists())


if __name__ == "__main__":
    unittest.main()
