#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
CLIENT = ROOT / "skills" / "loop-engine" / "client" / "concilium_client.py"
VIEW_MODEL = ROOT / "skills" / "loop-engine" / "client" / "menu_bar_view_model.py"
FIXTURES = ROOT / "skills" / "loop-engine" / "tests" / "fixtures" / "menu_bar"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MenuBarContractTests(unittest.TestCase):
    def fixture(self, name: str) -> dict:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def test_client_reads_token_file_and_strips_trailing_slash(self):
        concilium_client = load_module("concilium_client", CLIENT)
        with tempfile.TemporaryDirectory() as td:
            token_file = pathlib.Path(td) / "token.json"
            token_file.write_text(
                json.dumps({"base_url": "http://127.0.0.1:8765/", "token": "abc"}),
                encoding="utf-8",
            )

            client = concilium_client.ConciliumClient.from_token_file(token_file)

        self.assertEqual(client.base_url, "http://127.0.0.1:8765")
        self.assertEqual(client.token, "abc")

    def test_save_config_returns_explicit_not_implemented(self):
        concilium_client = load_module("concilium_client", CLIENT)
        client = concilium_client.ConciliumClient("http://127.0.0.1:8765", "abc")

        result = client.save_config("project", {"lanes": {"fast": {"default_single_agent": "codex"}}})

        self.assertEqual(result["status"], "not_implemented")
        self.assertIn("Phase 5", result["reason"])

    def test_events_uses_timeout_longer_than_server_keepalive(self):
        concilium_client = load_module("concilium_client", CLIENT)
        client = concilium_client.ConciliumClient("http://127.0.0.1:8765", "abc")
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"data: {}\n\n"

        with mock.patch.object(concilium_client.urllib.request, "urlopen", return_value=response) as urlopen:
            body = client.events("run1")

        self.assertEqual(body, "data: {}\n\n")
        self.assertGreater(urlopen.call_args.kwargs["timeout"], 30)

    def test_blocked_review_view_model_puts_block_near_top(self):
        menu_bar_view_model = load_module("menu_bar_view_model", VIEW_MODEL)

        model = menu_bar_view_model.build_popover_model(**self.fixture("blocked_review.json"))

        self.assertEqual(model["header"]["service"], "ok")
        self.assertEqual(model["active_decision"]["lane"], "review")
        self.assertEqual(model["verdict"]["kind"], "blocked")
        self.assertFalse(model["primary_action"]["enabled"])
        self.assertEqual(model["seat_capacity"][1]["seat"], "hermes")
        self.assertLess(list(model).index("verdict"), list(model).index("seat_capacity"))

    def test_active_fast_view_model_marks_ready_run_and_active_seat(self):
        menu_bar_view_model = load_module("menu_bar_view_model", VIEW_MODEL)

        model = menu_bar_view_model.build_popover_model(**self.fixture("active_fast.json"))

        self.assertTrue(model["primary_action"]["enabled"])
        self.assertEqual(model["verdict"]["kind"], "ready")
        self.assertEqual(model["execution_snapshot"]["active_seat"], "kimi")

    def test_view_model_accepts_effective_config_envelope(self):
        menu_bar_view_model = load_module("menu_bar_view_model", VIEW_MODEL)

        model = menu_bar_view_model.build_popover_model(**self.fixture("active_fast.json"))

        self.assertEqual(model["config_summary"]["risk_posture"], "speed-first")
        self.assertEqual(model["config_summary"]["fast_agent"], "kimi")

    def test_view_model_tolerates_partial_startup_state(self):
        menu_bar_view_model = load_module("menu_bar_view_model", VIEW_MODEL)

        model = menu_bar_view_model.build_popover_model(
            status=None,
            effective_config=None,
            preflight={"capacity": [None, "bad"], "route": "bad", "guard": None},
            events=[None, "bad"],
        )

        self.assertEqual(model["header"]["service"], "unknown")
        self.assertEqual(model["active_decision"]["lane"], "")
        self.assertEqual(model["seat_capacity"], [])
        self.assertEqual(model["execution_snapshot"]["active_seat"], "")

    def test_view_model_uses_run_fingerprint_for_confirmation(self):
        menu_bar_view_model = load_module("menu_bar_view_model", VIEW_MODEL)
        fixture = self.fixture("active_fast.json")
        fixture["preflight"]["request_fingerprint"] = "preview-fingerprint"
        fixture["preflight"]["run_request_fingerprint"] = "live-fingerprint"
        fixture["preflight"]["run_guard"] = {
            "status": "confirmation_required",
            "reason": "limited capacity",
            "confirmation_payload": {"request_fingerprint": "live-fingerprint"},
        }

        model = menu_bar_view_model.build_popover_model(**fixture)

        self.assertEqual(model["active_decision"]["request_fingerprint"], "live-fingerprint")
        self.assertTrue(model["primary_action"]["requires_confirmation"])
        self.assertFalse(model["primary_action"]["enabled"])

    def test_contract_doc_mentions_token_loader_and_effective_config_envelope(self):
        text = (ROOT / "docs" / "loop-engine" / "concilium-menu-bar-contract.md").read_text(encoding="utf-8")

        self.assertIn("from_token_file(path)", text)
        self.assertIn("{repo, config}", text)
        self.assertIn("inner `config`", text)


if __name__ == "__main__":
    unittest.main()
