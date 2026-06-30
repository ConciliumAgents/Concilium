#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "web" / "server.py"
spec = importlib.util.spec_from_file_location("web_server", MODULE)
web_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(web_server)


class WebPreflightTests(unittest.TestCase):
    def test_build_preflight_response_redacts_and_includes_route(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(web_server, "build_preflight", return_value={
                    "route": {"lane": "review", "required_seats": ["kimi", "hermes"]},
                    "preflight": {"status": "warn", "warnings": ["kimi unknown capacity"], "blocking_seats": []},
                    "capacity": [{"seat": "kimi", "status": "unknown", "reason": "no token sk-secret"}],
                    "signals": {"risk": "medium"},
                    "guard": {"status": "allowed", "reason": "safe with sk-secret"},
                    "request_fingerprint": "abc123",
                    "expected_max_agent_calls": 2,
                }):
            response = web_server.preflight_response({"repo": td, "task": "Change config", "test_cmd": "true"})

        text = json.dumps(response, ensure_ascii=False)
        self.assertIn('"lane": "review"', text)
        self.assertEqual(response["signals"], {"risk": "medium"})
        self.assertEqual(response["guard"]["status"], "allowed")
        self.assertEqual(response["request_fingerprint"], "abc123")
        self.assertEqual(response["expected_max_agent_calls"], 2)
        self.assertNotIn("sk-secret", text)


if __name__ == "__main__":
    unittest.main()
