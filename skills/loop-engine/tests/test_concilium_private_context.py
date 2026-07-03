#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
BIN = ROOT / "skills" / "loop-engine" / "bin"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


concilium_config = load_module("concilium_config", BIN / "concilium_config.py")
conductor = load_module("conductor", BIN / "conductor.py")
concilium_lanes = load_module("concilium_lanes", BIN / "concilium_lanes.py")
review_lane_module = load_module("review_lane_module", BIN / "review-lane.py")


class PrivateContextTests(unittest.TestCase):
    def test_config_accepts_private_context_dirs_list(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            private_dir = pathlib.Path(td) / "private"
            private_dir.mkdir()
            defaults = pathlib.Path(td) / "defaults.json"
            user = pathlib.Path(td) / "user.json"
            defaults.write_text(
                json.dumps({
                    "version": 1,
                    "lanes": {"fast": {}, "review": {}},
                    "routing": {"risk_posture": "balanced"},
                    "capacity": {"warn_below_percent": 20, "block_below_percent": 5},
                    "timeouts": {"seat_mode_seconds": {}},
                    "memory": {
                        "private_context_dirs": [],
                        "private_context_max_file_bytes": 20000,
                        "private_context_max_total_bytes": 200000,
                        "private_archive_dir": "",
                    },
                }),
                encoding="utf-8",
            )
            user.write_text(json.dumps({"memory": {"private_context_dirs": [str(private_dir)]}}), encoding="utf-8")

            config = concilium_config.load_config(repo, user_config=user, default_config=defaults)

        self.assertEqual(config["memory"]["private_context_dirs"], [str(private_dir)])

    def test_project_config_cannot_select_private_context_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            private_dir = pathlib.Path(td) / "private"
            private_dir.mkdir()
            defaults = pathlib.Path(td) / "defaults.json"
            user = pathlib.Path(td) / "user.json"
            defaults.write_text(
                json.dumps({
                    "version": 1,
                    "lanes": {"fast": {}, "review": {}},
                    "routing": {"risk_posture": "balanced"},
                    "capacity": {"warn_below_percent": 20, "block_below_percent": 5},
                    "timeouts": {"seat_mode_seconds": {}},
                    "memory": {
                        "private_context_dirs": [],
                        "private_context_max_file_bytes": 20000,
                        "private_context_max_total_bytes": 200000,
                        "private_archive_dir": "",
                    },
                }),
                encoding="utf-8",
            )
            user.write_text(json.dumps({}), encoding="utf-8")
            (repo / ".concilium.json").write_text(
                json.dumps({
                    "memory": {
                        "private_context_dirs": [str(private_dir)],
                        "private_context_max_file_bytes": 999999,
                        "private_context_max_total_bytes": 999999,
                        "private_archive_dir": "/tmp/attacker-controlled-archive",
                    }
                }),
                encoding="utf-8",
            )

            config = concilium_config.load_config(repo, user_config=user, default_config=defaults)

        self.assertEqual(config["memory"]["private_context_dirs"], [])
        self.assertEqual(config["memory"]["private_context_max_file_bytes"], 20000)
        self.assertEqual(config["memory"]["private_context_max_total_bytes"], 200000)
        self.assertEqual(config["memory"]["private_archive_dir"], "")

    def test_import_memory_reads_explicit_private_context_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            subprocess_session = "test-session"
            session = repo / ".roundtable" / "sessions" / subprocess_session / "KB"
            session.mkdir(parents=True)
            private_dir = pathlib.Path(td) / "private"
            private_dir.mkdir()
            (private_dir / "lesson.md").write_text("# Private Lesson\nKeep local context explicit.\n", encoding="utf-8")
            old_session = os.environ.get("LOOP_SESSION")
            os.environ["LOOP_SESSION"] = subprocess_session
            try:
                count = conductor.import_memory(str(repo), private_context_dirs=[str(private_dir)])
            finally:
                if old_session is None:
                    os.environ.pop("LOOP_SESSION", None)
                else:
                    os.environ["LOOP_SESSION"] = old_session
            imported = (session / "imported-memory.md").read_text(encoding="utf-8")

        self.assertEqual(count, 1)
        self.assertIn("Private context", imported)
        self.assertIn("lesson.md", imported)
        self.assertNotIn(str(private_dir), imported)
        self.assertIn("Private Lesson", imported)
        self.assertIn("Keep local context explicit.", imported)

    def test_import_memory_reads_only_markdown_files(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            session = repo / ".roundtable" / "sessions" / "test-session" / "KB"
            session.mkdir(parents=True)
            private_dir = pathlib.Path(td) / "private"
            private_dir.mkdir()
            (private_dir / ".env").write_text("API_KEY=secret\n", encoding="utf-8")
            (private_dir / "credentials.json").write_text('{"token":"secret"}\n', encoding="utf-8")
            (private_dir / "notes.md").write_text("safe note\n", encoding="utf-8")
            old_session = os.environ.get("LOOP_SESSION")
            os.environ["LOOP_SESSION"] = "test-session"
            try:
                count = conductor.import_memory(str(repo), private_context_dirs=[str(private_dir)])
            finally:
                if old_session is None:
                    os.environ.pop("LOOP_SESSION", None)
                else:
                    os.environ["LOOP_SESSION"] = old_session
            imported = (session / "imported-memory.md").read_text(encoding="utf-8")

        self.assertEqual(count, 1)
        self.assertIn("safe note", imported)
        self.assertNotIn("API_KEY", imported)
        self.assertNotIn("token", imported)

    def test_import_memory_marks_total_truncation(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            session = repo / ".roundtable" / "sessions" / "test-session" / "KB"
            session.mkdir(parents=True)
            private_dir = pathlib.Path(td) / "private"
            private_dir.mkdir()
            (private_dir / "one.md").write_text("1234567890\n", encoding="utf-8")
            (private_dir / "two.md").write_text("abcdefghij\n", encoding="utf-8")
            old_session = os.environ.get("LOOP_SESSION")
            os.environ["LOOP_SESSION"] = "test-session"
            try:
                conductor.import_memory(
                    str(repo),
                    private_context_dirs=[str(private_dir)],
                    memory_config={"private_context_max_total_bytes": 12},
                )
            finally:
                if old_session is None:
                    os.environ.pop("LOOP_SESSION", None)
                else:
                    os.environ["LOOP_SESSION"] = old_session
            imported = (session / "imported-memory.md").read_text(encoding="utf-8")

        self.assertIn("Private context truncated", imported)

    def test_archive_to_memory_uses_private_archive_dir(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            overlay_archive = pathlib.Path(td) / "overlay" / "roundtable-memory"
            overlay_archive.mkdir(parents=True)
            old_archive = os.environ.get("LOOP_ARCHIVE")
            old_session = os.environ.get("LOOP_SESSION")
            os.environ["LOOP_ARCHIVE"] = "1"
            os.environ["LOOP_SESSION"] = "20260703-test"
            try:
                conductor.archive_to_memory(
                    str(repo),
                    "Archive private memory",
                    "PASS",
                    1,
                    ["PASS"],
                    memory_config={"private_archive_dir": str(overlay_archive)},
                )
            finally:
                if old_archive is None:
                    os.environ.pop("LOOP_ARCHIVE", None)
                else:
                    os.environ["LOOP_ARCHIVE"] = old_archive
                if old_session is None:
                    os.environ.pop("LOOP_SESSION", None)
                else:
                    os.environ["LOOP_SESSION"] = old_session

            self.assertTrue(list((overlay_archive / repo.name).glob("*.md")))
            self.assertFalse((repo / "roundtable-memory").exists())

    def test_audit_lane_imports_private_context_before_reviewer_runs(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            imported = []
            config = {
                "memory": {"private_context_dirs": ["/private/overlay"]},
                "lanes": {"audit": {"seats": ["hermes"]}},
                "seat_models": {},
                "timeouts": {"seat_mode_seconds": {}},
            }
            with mock.patch.object(concilium_lanes, "_run_bin", return_value=(0, "")), \
                 mock.patch.object(concilium_lanes.conductor, "write_roster", return_value=["hermes"]), \
                 mock.patch.object(concilium_lanes.conductor, "set_participants"), \
                 mock.patch.object(concilium_lanes.conductor, "timed_run_seat", return_value=(0, "VERDICT: PASS")), \
                 mock.patch.object(concilium_lanes, "_run_shell", return_value=(0, "")), \
                 mock.patch.object(concilium_lanes.conductor, "import_memory", side_effect=lambda repo_arg, memory_config=None: imported.append(memory_config) or 1):
                result = concilium_lanes.run_audit_lane(repo, "Review only.", "", config, timeout=5)

        self.assertEqual(result["returncode"], 0)
        self.assertEqual(imported, [{"private_context_dirs": ["/private/overlay"]}])

    def test_review_lane_passes_memory_config_to_review_lane_module(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            config = {
                "memory": {"private_context_dirs": ["/private/overlay"]},
                "lanes": {"review": {"default_review_executor": "hermes", "default_review_reviewer": "codex"}},
                "seat_models": {},
                "timeouts": {"seat_mode_seconds": {}},
            }
            with mock.patch.object(
                concilium_lanes.review_lane_module,
                "run_review_lane",
                return_value={"returncode": 0, "status": "ran"},
            ) as run:
                result = concilium_lanes.run_review_lane(repo, "Review this.", "", config, timeout=5)

        self.assertEqual(result["returncode"], 0)
        self.assertEqual(run.call_args.kwargs["memory_config"], {"private_context_dirs": ["/private/overlay"]})

    def test_review_lane_module_imports_private_context_before_roster(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            events = []
            with mock.patch.object(review_lane_module, "run_cmd", return_value=(0, "")), \
                 mock.patch.object(
                     review_lane_module.conductor,
                     "import_memory",
                     side_effect=lambda repo_arg, memory_config=None: events.append(("import", memory_config)) or 1,
                 ), \
                 mock.patch.object(
                     review_lane_module.conductor,
                     "write_roster",
                     side_effect=lambda repo_arg, seats, seat_models=None: events.append(("roster", seats)) or seats,
                 ), \
                 mock.patch.object(review_lane_module.conductor, "set_participants"), \
                 mock.patch.object(review_lane_module, "refresh_kb"):
                review_lane_module.init_session(
                    repo,
                    "Review this.",
                    "",
                    {},
                    5,
                    ["hermes"],
                    memory_config={"private_context_dirs": ["/private/overlay"]},
                )

        self.assertEqual(events[0], ("import", {"private_context_dirs": ["/private/overlay"]}))
        self.assertEqual(events[1], ("roster", ["hermes"]))

    def test_roundtable_lane_passes_memory_config_to_conductor_run(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            archive_env = []
            config = {
                "memory": {
                    "private_context_dirs": ["/private/overlay"],
                    "private_archive_dir": "/private/overlay/roundtable-memory",
                },
                "lanes": {"roundtable": {"seats": ["hermes"], "commander": "claude", "reviewer": ""}},
                "seat_models": {},
                "timeouts": {"seat_mode_seconds": {}},
            }

            def fake_run(*args, **kwargs):
                archive_env.append(os.environ.get("LOOP_ARCHIVE"))
                return 0

            with mock.patch.object(concilium_lanes.conductor, "run", side_effect=fake_run) as run:
                result = concilium_lanes.run_roundtable_lane(repo, "Review only.", "", config, timeout=5)

        self.assertEqual(result["returncode"], 0)
        self.assertEqual(
            run.call_args.kwargs["memory_config"],
            {
                "private_context_dirs": ["/private/overlay"],
                "private_archive_dir": "/private/overlay/roundtable-memory",
            },
        )
        self.assertEqual(archive_env, ["1"])


if __name__ == "__main__":
    unittest.main()
