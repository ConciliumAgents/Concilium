#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium_config.py"
spec = importlib.util.spec_from_file_location("concilium_config", MODULE)
concilium_config = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(concilium_config)


class ConciliumConfigTests(unittest.TestCase):
    def write_json(self, path: pathlib.Path, data: dict) -> pathlib.Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def test_default_config_gives_claude_and_codex_longer_review_budget(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            config = concilium_config.load_config(root, user_config=root / "__no_such_user_config__.json")

        seat_modes = config["timeouts"]["seat_mode_seconds"]
        self.assertEqual(seat_modes["claude"]["plan"], 600)
        self.assertEqual(seat_modes["claude"]["review"], 600)
        self.assertEqual(seat_modes["codex"]["plan"], 600)
        self.assertEqual(seat_modes["codex"]["review"], 600)

    def test_default_audit_and_plan_review_seats_are_native_and_heterogeneous(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            config = concilium_config.load_config(root, user_config=root / "__no_such_user_config__.json")

        self.assertEqual(config["lanes"]["audit"]["default_reviewer"], "claude")
        self.assertEqual(config["lanes"]["audit"]["seats"], ["claude", "hermes", "kimi"])
        self.assertEqual(config["lanes"]["plan_review"]["seats"], ["claude", "hermes", "kimi"])
        self.assertNotIn("codex", config["lanes"]["audit"]["seats"])
        self.assertNotIn("codex", config["lanes"]["plan_review"]["seats"])

    def test_timeout_overrides_must_be_positive_numbers(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "bad.json"
            self.write_json(path, {
                "version": 1,
                "product_name": "Concilium",
                "lanes": {
                    "fast": {"default_single_agent": "kimi", "verify_required": True},
                    "review": {
                        "default_review_executor": "kimi",
                        "default_review_reviewer": "hermes",
                        "review_repair_limit": 1,
                    },
                    "roundtable": {"commander": "claude", "reviewer": "", "seats": ["claude", "hermes", "kimi"]},
                },
                "routing": {"risk_posture": "balanced", "allow_auto_escalation": True, "allow_auto_downgrade": False},
                "capacity": {"warn_below_percent": 20, "block_below_percent": 5, "max_status_age_seconds": 300},
                "timeouts": {"seat_mode_seconds": {"claude": {"review": 0}}},
                "privacy": {"redact_account_identifiers": True, "redact_credentials": True},
            })

            with self.assertRaisesRegex(ValueError, "timeout.*positive"):
                concilium_config.load_config(path.parent, user_config=path, default_config=path)

    def test_project_config_overrides_user_and_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            defaults = self.write_json(root / "defaults.json", {
                "version": 1,
                "product_name": "Concilium",
                "lanes": {
                    "fast": {"default_single_agent": "kimi", "verify_required": True},
                    "review": {
                        "default_review_executor": "kimi",
                        "default_review_reviewer": "hermes",
                        "review_repair_limit": 1,
                    },
                    "roundtable": {"commander": "claude", "reviewer": "", "seats": ["claude", "hermes", "kimi"]},
                },
                "routing": {"risk_posture": "balanced", "allow_auto_escalation": True, "allow_auto_downgrade": False},
                "capacity": {"warn_below_percent": 20, "block_below_percent": 5, "max_status_age_seconds": 300},
                "privacy": {"redact_account_identifiers": True, "redact_credentials": True},
            })
            user = self.write_json(root / "user.json", {
                "lanes": {"fast": {"default_single_agent": "hermes"}}
            })
            project = root / "repo"
            self.write_json(project / ".concilium.json", {
                "lanes": {"fast": {"default_single_agent": "claude"}}
            })

            config = concilium_config.load_config(project, user_config=user, default_config=defaults)

        self.assertEqual(config["lanes"]["fast"]["default_single_agent"], "claude")
        self.assertEqual(config["lanes"]["review"]["default_review_reviewer"], "hermes")

    def test_review_executor_and_reviewer_must_differ(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "bad.json"
            self.write_json(path, {
                "version": 1,
                "product_name": "Concilium",
                "lanes": {
                    "fast": {"default_single_agent": "kimi", "verify_required": True},
                    "review": {
                        "default_review_executor": "kimi",
                        "default_review_reviewer": "kimi",
                        "review_repair_limit": 1,
                    },
                    "roundtable": {"commander": "claude", "reviewer": "", "seats": ["claude", "hermes", "kimi"]},
                },
                "routing": {"risk_posture": "balanced", "allow_auto_escalation": True, "allow_auto_downgrade": False},
                "capacity": {"warn_below_percent": 20, "block_below_percent": 5, "max_status_age_seconds": 300},
                "privacy": {"redact_account_identifiers": True, "redact_credentials": True},
            })

            with self.assertRaisesRegex(ValueError, "review executor and reviewer must differ"):
                concilium_config.load_config(path.parent, user_config=path, default_config=path)

    def test_cli_prints_redacted_effective_config(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            defaults = self.write_json(root / "defaults.json", {
                "version": 1,
                "product_name": "Concilium",
                "lanes": {
                    "fast": {"default_single_agent": "kimi", "verify_required": True},
                    "review": {
                        "default_review_executor": "kimi",
                        "default_review_reviewer": "hermes",
                        "review_repair_limit": 1,
                    },
                    "roundtable": {"commander": "claude", "reviewer": "", "seats": ["claude", "hermes", "kimi"]},
                },
                "routing": {"risk_posture": "balanced", "allow_auto_escalation": True, "allow_auto_downgrade": False},
                "capacity": {"warn_below_percent": 20, "block_below_percent": 5, "max_status_age_seconds": 300},
                "privacy": {"redact_account_identifiers": True, "redact_credentials": True},
            })
            out = concilium_config.render_effective_config(root, user_config=defaults, default_config=defaults)

        self.assertIn('"product_name"', out)
        self.assertNotIn("sk-", out)

    def test_redaction_keeps_boolean_privacy_flags_but_removes_secret_values(self):
        rendered = concilium_config.redact_for_render({
            "privacy": {"redact_credentials": True},
            "provider": {"api_key": "sk-secret"},
            "note": "jwt abc.def.ghi",
        })

        self.assertTrue(rendered["privacy"]["redact_credentials"])
        self.assertEqual(rendered["provider"]["api_key"], "[REDACTED]")
        self.assertEqual(rendered["note"], "jwt [REDACTED]")

    def test_init_project_requires_existing_repo_directory(self):
        with tempfile.TemporaryDirectory() as td:
            missing = pathlib.Path(td) / "missing"

            with self.assertRaises(NotADirectoryError):
                concilium_config.init_project_config(missing)


if __name__ == "__main__":
    unittest.main()
