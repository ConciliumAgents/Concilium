#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import queue
import stat
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "web" / "server.py"
spec = importlib.util.spec_from_file_location("web_server", MODULE)
web_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(web_server)


def drain(q: "queue.Queue") -> list[dict]:
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    return events


class WebRuntimeAdapterTests(unittest.TestCase):
    def test_preflight_forces_preview_and_run_preserves_explicit_stub_mode(self):
        payload = {
            "repo": ".",
            "task": "Change routing.",
            "test_cmd": "python3 -m unittest",
            "mode": "stub_run",
            "seat_timeout": 42,
        }
        calls = []

        def fake_adapter(params, **kwargs):
            calls.append((dict(params), kwargs))
            sink = kwargs.get("event_sink")
            if sink is not None:
                web_server.concilium_events.emit_done(sink, 0)
            return {
                "route": {"lane": "fast"},
                "preflight": {"status": "ok"},
                "capacity": [],
                "signals": {},
                "guard": {"status": "allowed"},
                "returncode": 0,
            }

        q: queue.Queue = queue.Queue()
        with mock.patch.object(web_server.concilium_runtime, "run_concilium_adapter", side_effect=fake_adapter):
            web_server.preflight_response(payload)
            web_server._run_thread(payload, q)

        preflight_params, preflight_kwargs = calls[0]
        run_params, run_kwargs = calls[1]
        for key in ("repo", "task", "test_cmd"):
            self.assertEqual(preflight_params[key], payload[key])
            self.assertEqual(run_params[key], payload[key])
        self.assertEqual(preflight_params["timeout"], 42)
        self.assertEqual(run_params["timeout"], 42)
        self.assertEqual(preflight_params["mode"], "preview")
        self.assertEqual(run_params["mode"], "stub_run")
        self.assertNotIn("event_sink", preflight_kwargs)
        self.assertTrue(hasattr(run_kwargs["event_sink"], "emit"))
        self.assertTrue(hasattr(run_kwargs["event_sink"], "done_emitted"))

    def test_run_thread_blocked_result_emits_done_without_conductor_run(self):
        q: queue.Queue = queue.Queue()
        with mock.patch.object(web_server.conductor, "run", side_effect=AssertionError("must not call conductor.run")) as conductor_run, \
                mock.patch.object(web_server.concilium_runtime, "run_concilium_adapter", return_value={
                    "status": "blocked",
                    "returncode": 3,
                }):
            web_server._run_thread({"repo": ".", "task": "Change routing.", "mode": "stub_run"}, q)

        conductor_run.assert_not_called()
        self.assertEqual(drain(q), [{"rc": 3, "type": "done"}])

    def test_run_thread_confirmation_required_without_returncode_emits_block_rc(self):
        q: queue.Queue = queue.Queue()
        with mock.patch.object(web_server.concilium_runtime, "run_concilium_adapter", return_value={
            "status": "confirmation_required",
        }):
            web_server._run_thread({"repo": ".", "task": "Change routing.", "mode": "live_run"}, q)

        self.assertEqual(drain(q), [{"rc": 3, "type": "done"}])

    def test_run_thread_translates_adapter_events_for_existing_web_ui(self):
        q: queue.Queue = queue.Queue()

        def fake_adapter(params, **kwargs):
            sink = kwargs["event_sink"]
            sink.emit("start", mode="stub_run", lane="review")
            sink.emit("seat", seat="kimi", lane="review", status="stubbed")
            sink.emit("finish", rc=0)
            web_server.concilium_events.emit_done(sink, 0)
            return {"returncode": 0}

        with mock.patch.object(web_server.concilium_runtime, "run_concilium_adapter", side_effect=fake_adapter):
            web_server._run_thread({"repo": "/tmp/repo", "task": "Change routing.", "mode": "stub_run"}, q)

        events = drain(q)
        self.assertEqual(events[0]["type"], "start")
        self.assertEqual(events[0]["task"], "Change routing.")
        self.assertEqual(events[0]["repo"], "/tmp/repo")
        self.assertEqual(events[0]["lane"], "review")
        self.assertEqual(events[1]["type"], "seat")
        self.assertEqual(events[1]["agent"], "kimi")
        self.assertEqual(events[1]["phase"], "done")
        self.assertEqual(events[1]["rc"], 0)
        self.assertEqual(events[1]["mode"], "stub")
        self.assertEqual(events[2]["type"], "finish")
        self.assertEqual(events[2]["status"], "PASS")
        self.assertEqual(events[2]["rc"], 0)
        self.assertEqual(events[-1], {"rc": 0, "type": "done"})

    def test_run_thread_defaults_mode_from_dry_run_for_legacy_ui_payloads(self):
        captured = []

        def fake_adapter(params, **kwargs):
            captured.append(dict(params))
            web_server.concilium_events.emit_done(kwargs["event_sink"], 0)
            return {"returncode": 0}

        with mock.patch.object(web_server.concilium_runtime, "run_concilium_adapter", side_effect=fake_adapter):
            web_server._run_thread({"repo": ".", "task": "Preview task.", "dry_run": True}, queue.Queue())
            web_server._run_thread({"repo": ".", "task": "Live task.", "dry_run": False}, queue.Queue())

        self.assertEqual(captured[0]["mode"], "stub_run")
        self.assertEqual(captured[1]["mode"], "live_run")

    def test_write_token_file_creates_user_only_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "token.json"

            web_server.write_token_file(path, "http://127.0.0.1:8765/", "tok_123")

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["base_url"], "http://127.0.0.1:8765/")
            self.assertEqual(payload["token"], "tok_123")
            self.assertTrue(payload["created_at"].endswith("Z"))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_status_response_lists_local_service_endpoints(self):
        response = web_server.status_response()

        self.assertEqual(response["product"], "Concilium")
        self.assertEqual(response["service"], "ok")
        self.assertEqual(response["bind"], "127.0.0.1")
        self.assertTrue(response["token_required"])
        self.assertIn("/api/events", response["endpoints"])

    def test_effective_config_response_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(web_server.concilium_config, "load_config", return_value={
                    "api_key": "sk-secret123",
                    "headers": {"Authorization": "Bearer local-secret-123456"},
                    "lanes": {"fast": {"default_single_agent": "kimi"}},
                }):
            response = web_server.effective_config_response(td)

        text = json.dumps(response, ensure_ascii=False)
        self.assertEqual(set(response), {"repo", "config"})
        self.assertEqual(response["repo"], str(pathlib.Path(td).resolve()))
        self.assertEqual(response["config"]["lanes"]["fast"]["default_single_agent"], "kimi")
        self.assertNotIn("sk-secret123", text)
        self.assertNotIn("local-secret-123456", text)
        self.assertNotIn("Bearer", text)


if __name__ == "__main__":
    unittest.main()
