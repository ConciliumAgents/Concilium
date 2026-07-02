#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium_runtime.py"
spec = importlib.util.spec_from_file_location("concilium_runtime", MODULE)
concilium_runtime = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(concilium_runtime)


BASE_CONFIG = {
    "version": 1,
    "lanes": {
        "fast": {"default_single_agent": "kimi", "verify_required": True},
        "review": {
            "default_review_executor": "kimi",
            "default_review_reviewer": "hermes",
            "review_repair_limit": 1,
        },
        "audit": {
            "default_reviewer": "claude",
            "seats": ["claude", "hermes", "kimi"],
            "allowed_report_paths": ["docs/audits/*.md"],
        },
        "plan_review": {
            "seats": ["claude", "hermes", "kimi"],
            "max_rounds": 3,
        },
        "roundtable": {
            "commander": "claude",
            "reviewer": "",
            "seats": ["claude", "hermes", "kimi"],
            "max_iters": 5,
        },
    },
    "routing": {
        "risk_posture": "balanced",
        "allow_auto_escalation": True,
        "allow_auto_downgrade": False,
    },
    "capacity": {"warn_below_percent": 20, "block_below_percent": 5, "max_status_age_seconds": 300},
    "privacy": {"redact_account_identifiers": True, "redact_credentials": True},
}


def capacity_record(seat: str, status: str) -> dict:
    return {
        "seat": seat,
        "provider": "fixture",
        "model": seat,
        "status": status,
        "source": "test",
        "reason": status,
        "checked_at": "2026-06-29T00:00:00Z",
        "reset_at": "",
        "stale_after_seconds": 300,
        "blocking": status in {"hard_exhausted", "unavailable"},
    }


def init_repo(repo: pathlib.Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (repo / ".gitignore").write_text(".roundtable/\n__pycache__/\nevals/\n", encoding="utf-8")
    (repo / "tracked.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore", "tracked.md"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base"],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


class ConciliumRuntimeRequestTests(unittest.TestCase):
    def test_normalize_request_resolves_repo_and_defaults_mode(self):
        with tempfile.TemporaryDirectory() as td:
            request = concilium_runtime.normalize_request({
                "repo": td,
                "task": "Fix one typo.",
                "dry_run": True,
                "test_cmd": "python3 -m unittest",
            })

        self.assertEqual(request["mode"], "preview")
        self.assertEqual(request["task"], "Fix one typo.")
        self.assertEqual(request["test_cmd"], "python3 -m unittest")
        self.assertEqual(request["timeout"], 300)
        self.assertEqual(request["intent"], "task")
        self.assertTrue(pathlib.Path(request["repo"]).is_absolute())

    def test_invalid_mode_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "unknown execution mode"):
                concilium_runtime.normalize_request({"repo": td, "task": "x", "mode": "dry-ish"})

    def test_zero_timeout_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            cases = (
                {"repo": td, "task": "x", "timeout": 0},
                {"repo": td, "task": "x", "seat_timeout": 0},
            )
            for params in cases:
                with self.subTest(params=params):
                    with self.assertRaisesRegex(ValueError, "timeout must be positive"):
                        concilium_runtime.normalize_request(params)

    def test_live_false_with_whitespace_defaults_to_preview(self):
        with tempfile.TemporaryDirectory() as td:
            request = concilium_runtime.normalize_request({"repo": td, "task": "x", "live": " false "})

        self.assertEqual(request["mode"], "preview")

    def test_request_overlay_does_not_mutate_base_config(self):
        request = concilium_runtime.normalize_request({
            "repo": ".",
            "task": "Change routing.",
            "mode": "live_run",
            "seats": ["claude", "codex"],
            "seat_models": {
                "codex": "gpt-5-codex-high",
                "kimi": {"provider": "moonshot", "model": "kimi-k2"},
            },
            "fast_agent": "codex",
            "review_executor": "codex",
            "review_reviewer": "claude",
            "commander": "codex",
            "reviewer": "claude",
            "max_iters": 2,
            "timeout": 77,
        })

        effective = concilium_runtime.apply_request_overlay(BASE_CONFIG, request)

        self.assertEqual(request["timeout"], 77)
        self.assertEqual(request["overlay"]["seat_models"]["codex"], {"model": "gpt-5-codex-high"})
        self.assertEqual(
            request["overlay"]["seat_models"]["kimi"],
            {"provider": "moonshot", "model": "kimi-k2"},
        )
        self.assertEqual(BASE_CONFIG["lanes"]["fast"]["default_single_agent"], "kimi")
        self.assertEqual(effective["lanes"]["fast"]["default_single_agent"], "codex")
        self.assertEqual(effective["lanes"]["review"]["default_review_executor"], "codex")
        self.assertEqual(effective["lanes"]["review"]["default_review_reviewer"], "claude")
        self.assertEqual(effective["lanes"]["roundtable"]["commander"], "codex")
        self.assertEqual(effective["lanes"]["roundtable"]["reviewer"], "claude")
        self.assertEqual(effective["lanes"]["roundtable"]["seats"], ["claude", "codex"])
        self.assertEqual(effective["lanes"]["roundtable"]["max_iters"], 2)
        self.assertEqual(effective["seat_models"]["codex"], {"model": "gpt-5-codex-high"})
        self.assertEqual(effective["seat_models"]["kimi"], {"provider": "moonshot", "model": "kimi-k2"})

    def test_fingerprint_changes_when_decision_input_changes(self):
        with tempfile.TemporaryDirectory() as td:
            base = concilium_runtime.normalize_request({"repo": td, "task": "Fix docs.", "mode": "stub_run"})
            changed = concilium_runtime.normalize_request({"repo": td, "task": "Fix docs.", "mode": "live_run"})

        self.assertNotEqual(
            concilium_runtime.request_fingerprint(base),
            concilium_runtime.request_fingerprint(changed),
        )

    def test_fingerprint_changes_for_each_declared_key(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as other:
            base = concilium_runtime.normalize_request({
                "repo": td,
                "task": "Fix docs.",
                "test_cmd": "python3 -m unittest",
                "mode": "stub_run",
                "timeout": 30,
                "intent": "task",
                "signals": {"risk": "low"},
                "fast_agent": "kimi",
            })

            variants = {
                "repo": {"repo": other},
                "task": {"task": "Fix docs and tests."},
                "test_cmd": {"test_cmd": "python3 -m pytest"},
                "mode": {"mode": "preview"},
                "timeout": {"timeout": 31},
                "intent": {"intent": "tiny_smoke"},
                "signals": {"signals": {"risk": "medium"}},
                "overlay": {"fast_agent": "codex"},
            }
            base_fingerprint = concilium_runtime.request_fingerprint(base)
            for key, updates in variants.items():
                params = {
                    "repo": td,
                    "task": "Fix docs.",
                    "test_cmd": "python3 -m unittest",
                    "mode": "stub_run",
                    "timeout": 30,
                    "intent": "task",
                    "signals": {"risk": "low"},
                    "fast_agent": "kimi",
                }
                params.update(copy.deepcopy(updates))
                with self.subTest(key=key):
                    changed = concilium_runtime.normalize_request(params)
                    self.assertNotEqual(
                        base_fingerprint,
                        concilium_runtime.request_fingerprint(changed),
                    )


class ConciliumRuntimeAccountingTests(unittest.TestCase):
    def test_review_expected_max_agent_calls_counts_executor_and_reviewer_per_attempt(self):
        route = {"lane": "review", "required_seats": ["kimi", "hermes"]}
        cases = {
            0: 2,
            1: 4,
            2: 6,
        }
        for repair_limit, expected in cases.items():
            with self.subTest(repair_limit=repair_limit):
                config = copy.deepcopy(BASE_CONFIG)
                config["lanes"]["review"]["review_repair_limit"] = repair_limit

                self.assertEqual(concilium_runtime.expected_max_agent_calls(route, config), expected)


class ConciliumRuntimeAdapterTests(unittest.TestCase):
    def test_preview_builds_route_without_executor_call(self):
        with tempfile.TemporaryDirectory() as td:
            executor = mock.Mock(side_effect=AssertionError("executor must not run for preview"))

            result = concilium_runtime.run_concilium_adapter(
                {
                    "repo": td,
                    "task": "Fix one typo in docs/example.md.",
                    "test_cmd": "true",
                    "mode": "preview",
                    "signals": {"risk": "low", "file_count": 1, "security_sensitive": False, "ambiguous": False},
                },
                config=BASE_CONFIG,
                capacity=[capacity_record("kimi", "ok")],
                lane_executor=executor,
            )

        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["route"]["lane"], "fast")
        self.assertEqual(result["guard"]["status"], "allowed")
        self.assertTrue(result["request_fingerprint"])
        executor.assert_not_called()

    def test_stub_run_emits_done_without_live_executor(self):
        with tempfile.TemporaryDirectory() as td:
            sink = concilium_runtime.concilium_events.ListEventSink()
            executor = mock.Mock(side_effect=AssertionError("executor must not run for stub_run"))

            result = concilium_runtime.run_concilium_adapter(
                {
                    "repo": td,
                    "task": "Change config routing behavior.",
                    "test_cmd": "true",
                    "mode": "stub_run",
                    "signals": {"risk": "medium", "file_count": 2, "security_sensitive": False, "ambiguous": False},
                },
                event_sink=sink,
                config=BASE_CONFIG,
                capacity=[capacity_record("kimi", "ok"), capacity_record("hermes", "ok")],
                lane_executor=executor,
            )

        self.assertEqual(result["status"], "stubbed")
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["route"]["lane"], "review")
        self.assertEqual(
            [event["type"] for event in sink.events],
            ["start", "preflight", "guard", "seat", "seat", "finish", "done"],
        )
        self.assertEqual([event["seat"] for event in sink.events if event["type"] == "seat"], ["kimi", "hermes"])
        for event in sink.events:
            if event["type"] == "seat":
                self.assertEqual(event["backend_type"], "configured_seat")
                self.assertEqual(event["provider"], "fixture")
                self.assertIn("model", event)
        executor.assert_not_called()

    def test_audit_stub_run_records_planned_external_cli_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            sink = concilium_runtime.concilium_events.ListEventSink()

            result = concilium_runtime.run_concilium_adapter(
                {
                    "repo": td,
                    "task": "Read-only audit the architecture; only write docs/audits/report.md.",
                    "test_cmd": "true",
                    "mode": "stub_run",
                    "signals": {
                        "risk": "high",
                        "file_count": 9,
                        "security_sensitive": False,
                        "ambiguous": True,
                        "read_only": True,
                        "allowed_write_paths": ["docs/audits/report.md"],
                    },
                },
                event_sink=sink,
                config=BASE_CONFIG,
                capacity=[
                    capacity_record("claude", "ok"),
                    capacity_record("hermes", "ok"),
                    capacity_record("kimi", "ok"),
                ],
            )

        self.assertEqual(result["route"]["lane"], "audit")
        seat_events = [event for event in sink.events if event["type"] == "seat"]
        self.assertEqual([event["seat"] for event in seat_events], ["claude", "hermes", "kimi"])
        self.assertEqual([event["backend_type"] for event in seat_events], ["external_cli", "external_cli", "external_cli"])
        self.assertEqual([event["provider"] for event in seat_events], ["fixture", "fixture", "fixture"])
        self.assertNotIn("codex", [event["seat"] for event in seat_events])

    def test_live_fast_default_executor_emits_exec_seat_event(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)
            sink = concilium_runtime.concilium_events.ListEventSink()
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["fast"]["default_single_agent"] = "kimi"

            with mock.patch.object(
                concilium_runtime.concilium_lanes.process_runner,
                "run_process_group",
                return_value={"returncode": 0, "output": "", "timed_out": False, "duration_seconds": 0.0},
            ), mock.patch.object(
                concilium_runtime.concilium_lanes.conductor,
                "write_roster",
                return_value=["kimi"],
            ), mock.patch.object(
                concilium_runtime.concilium_lanes.conductor,
                "set_participants",
            ):
                result = concilium_runtime.run_concilium_adapter(
                    {
                        "repo": str(repo),
                        "task": "Fix a typo in docs/readme.md.",
                        "test_cmd": "true",
                        "mode": "live_run",
                        "signals": {"risk": "low", "file_count": 1, "security_sensitive": False, "ambiguous": False},
                    },
                    event_sink=sink,
                    config=config,
                    capacity=[capacity_record("kimi", "ok")],
                )

        self.assertEqual(result["route"]["lane"], "fast")
        seat_events = [event for event in sink.events if event["type"] == "seat"]
        self.assertEqual([event["seat"] for event in seat_events], ["kimi"])
        self.assertEqual(seat_events[0]["backend_type"], "external_cli")
        self.assertEqual(seat_events[0]["mode"], "exec")
        self.assertEqual(seat_events[0]["status"], "invoked")

    def test_audit_defaults_do_not_include_codex_without_overlay(self):
        with tempfile.TemporaryDirectory() as td:
            result = concilium_runtime.build_preflight(
                {
                    "repo": td,
                    "task": "Read-only audit the architecture.",
                    "mode": "preview",
                    "signals": {
                        "risk": "high",
                        "file_count": 9,
                        "security_sensitive": False,
                        "ambiguous": True,
                        "read_only": True,
                    },
                },
                config=BASE_CONFIG,
                capacity=[
                    capacity_record("claude", "ok"),
                    capacity_record("hermes", "ok"),
                    capacity_record("kimi", "ok"),
                ],
            )

        self.assertEqual(result["route"]["lane"], "audit")
        self.assertEqual(result["route"]["required_seats"], ["claude", "hermes", "kimi"])
        self.assertNotIn("codex", result["route"]["required_seats"])

    def test_audit_seats_follow_request_overlay(self):
        with tempfile.TemporaryDirectory() as td:
            result = concilium_runtime.build_preflight(
                {
                    "repo": td,
                    "task": "Read-only audit the architecture.",
                    "test_cmd": "true",
                    "mode": "preview",
                    "seats": ["kimi", "hermes"],
                    "signals": {
                        "risk": "high",
                        "file_count": 9,
                        "security_sensitive": False,
                        "ambiguous": True,
                        "read_only": True,
                    },
                },
                config=BASE_CONFIG,
                capacity=[capacity_record("kimi", "ok"), capacity_record("hermes", "ok")],
            )

        self.assertEqual(result["route"]["lane"], "audit")
        self.assertEqual(result["route"]["required_seats"], ["kimi", "hermes"])

    def test_plan_review_seats_follow_request_overlay(self):
        with tempfile.TemporaryDirectory() as td:
            result = concilium_runtime.build_preflight(
                {
                    "repo": td,
                    "task": "审核执行方案 docs/superpowers/plans/example.md",
                    "test_cmd": "true",
                    "mode": "preview",
                    "seats": ["codex"],
                    "signals": {
                        "plan_review": True,
                        "plan_path": "docs/superpowers/plans/example.md",
                    },
                },
                config=BASE_CONFIG,
                capacity=[capacity_record("codex", "ok")],
            )

        self.assertEqual(result["route"]["lane"], "plan_review")
        self.assertEqual(result["route"]["required_seats"], ["codex"])

    def test_explicit_empty_allowed_write_paths_are_preserved(self):
        preview = {
            "signals": {
                "required_artifact_paths": ["docs/audits/report.md"],
                "allowed_write_paths": [],
            }
        }

        required, allowed = concilium_runtime._artifact_requirements(preview, BASE_CONFIG)

        self.assertEqual(required, ["docs/audits/report.md"])
        self.assertEqual(allowed, [])

    def test_runtime_artifact_gate_treats_explicit_empty_allow_list_as_strict(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)
            preview = {
                "request": {"repo": str(repo)},
                "route": {"lane": "audit"},
                "signals": {
                    "required_artifact_paths": ["docs/audits/report.md"],
                    "allowed_write_paths": [],
                },
            }

            gate = concilium_runtime._evaluate_artifact_gate(preview, BASE_CONFIG, baseline_delta_paths=[])

        self.assertEqual(gate["status"], "failed")
        self.assertIn("docs/audits/report.md", gate["disallowed"])

    def test_live_audit_without_report_fails_artifact_gate(self):
        with tempfile.TemporaryDirectory() as td:
            sink = concilium_runtime.concilium_events.ListEventSink()

            def audit_executor(preview, effective):
                return {"status": "ran", "lane": "audit", "returncode": 0}

            result = concilium_runtime.run_concilium_adapter(
                {
                    "repo": td,
                    "task": "Read-only audit; only write docs/audits/report.md.",
                    "test_cmd": "true",
                    "mode": "live_run",
                    "signals": {
                        "risk": "high",
                        "file_count": 8,
                        "security_sensitive": False,
                        "ambiguous": True,
                        "read_only": True,
                        "allowed_write_paths": ["docs/audits/report.md"],
                        "required_artifact_paths": ["docs/audits/report.md"],
                    },
                },
                event_sink=sink,
                config=BASE_CONFIG,
                capacity=[
                    capacity_record("claude", "ok"),
                    capacity_record("hermes", "ok"),
                    capacity_record("kimi", "ok"),
                ],
                lane_executor=audit_executor,
            )

        self.assertEqual(result["status"], "artifact_failed")
        self.assertEqual(result["returncode"], 1)
        self.assertEqual(result["artifact_gate"]["status"], "failed")
        self.assertIn("docs/audits/report.md", result["artifact_gate"]["missing"])
        seat_events = [event for event in sink.events if event["type"] == "seat"]
        self.assertEqual(seat_events, [])
        self.assertEqual([event["type"] for event in sink.events[-3:]], ["artifact_gate", "finish", "done"])
        self.assertEqual(sink.events[-1]["type"], "done")

    def test_live_run_attaches_run_summary_and_writes_session_summary(self):
        def executor(preview, effective):
            del preview, effective
            session = repo / ".roundtable" / "sessions" / "audit-unit"
            return {
                "status": "ran",
                "lane": "audit",
                "returncode": 0,
                "session_path": str(session),
                "seat_results": [
                    {"seat": "claude", "mode": "review", "backend_type": "external_cli", "status": "invoked", "rc": 0, "verdict": "PASS"},
                ],
                "verify": {"returncode": 0, "output": "OK"},
            }

        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["audit"]["seats"] = ["claude"]
            result = concilium_runtime.run_concilium_adapter(
                {
                    "repo": str(repo),
                    "task": "Read-only audit.",
                    "mode": "live_run",
                    "signals": {"read_only": True, "ambiguous": True},
                },
                event_sink=concilium_runtime.concilium_events.ListEventSink(),
                config=config,
                capacity=[capacity_record("claude", "ok")],
                lane_executor=executor,
            )

            summary_path = repo / ".roundtable" / "sessions" / "audit-unit" / "run-summary.json"

            self.assertEqual(result["run_summary"]["final_verdict"], "pass")
            self.assertTrue(summary_path.is_file())

    def test_quota_exhausted_review_seat_emits_retry_required_summary(self):
        sink = concilium_runtime.concilium_events.ListEventSink()

        def executor(preview, effective):
            del preview, effective
            return {
                "status": "retry_required",
                "lane": "plan_review",
                "returncode": 1,
                "seat_results": [
                    {"seat": "claude", "mode": "review", "backend_type": "external_cli", "status": "invoked", "rc": 0, "verdict": "PASS"},
                    {"seat": "hermes", "mode": "review", "backend_type": "external_cli", "status": "invoked", "rc": 0, "verdict": "PASS"},
                    {
                        "seat": "kimi",
                        "mode": "review",
                        "backend_type": "external_cli",
                        "status": "invoked",
                        "rc": 1,
                        "verdict": "ERR",
                        "output_tail": "provider.rate_limit: 429 You've reached your usage limit for this period.",
                    },
                ],
                "unresolved_blockers": [{"severity": "MEDIUM", "summary": "reviewer ERR; retry, fallback, or mark unavailable"}],
            }

        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["plan_review"] = {"seats": ["claude", "hermes", "kimi"], "max_rounds": 3}
            result = concilium_runtime.run_concilium_adapter(
                {
                    "repo": str(repo),
                    "task": "Review plan.",
                    "mode": "live_run",
                    "signals": {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
                },
                event_sink=sink,
                config=config,
                capacity=[
                    capacity_record("claude", "ok"),
                    capacity_record("hermes", "ok"),
                    capacity_record("kimi", "ok"),
                ],
                lane_executor=executor,
            )

        self.assertEqual(result["run_summary"]["final_verdict"], "retry_required")
        self.assertEqual(result["product_status"], "retry_required")
        self.assertEqual(result["run_summary"]["retry_required_seats"], ["kimi"])
        self.assertNotIn("kimi", result["run_summary"]["blocking_seats"])

    def test_live_audit_default_executor_propagates_reviewer_block(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            sink = concilium_runtime.concilium_events.ListEventSink()
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["audit"]["seats"] = ["claude"]

            with mock.patch.object(
                concilium_runtime.concilium_lanes.conductor,
                "timed_run_seat",
                return_value=(2, "High-risk finding\nVERDICT: BLOCK\n"),
            ):
                result = concilium_runtime.run_concilium_adapter(
                    {
                        "repo": td,
                        "task": "Read-only audit the architecture.",
                        "test_cmd": "true",
                        "mode": "live_run",
                        "signals": {
                            "risk": "high",
                            "file_count": 8,
                            "security_sensitive": False,
                            "ambiguous": True,
                            "read_only": True,
                        },
                    },
                    event_sink=sink,
                    config=config,
                    capacity=[capacity_record("claude", "ok")],
                )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["returncode"], 2)
        self.assertEqual(result["artifact_gate"]["status"], "passed")
        seat_events = [event for event in sink.events if event["type"] == "seat"]
        self.assertEqual([event["seat"] for event in seat_events], ["claude"])
        self.assertEqual(seat_events[0]["status"], "invoked")
        self.assertEqual(seat_events[0]["rc"], 2)
        self.assertEqual(sink.events[-1]["rc"], 2)

    def test_live_audit_dispatches_external_reviewer_seats_and_writes_report(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            sink = concilium_runtime.concilium_events.ListEventSink()
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["audit"]["seats"] = ["claude", "kimi"]

            with mock.patch.object(
                concilium_runtime.concilium_lanes.conductor,
                "timed_run_seat",
                side_effect=[
                    (0, "Claude audit findings\nVERDICT: PASS\n"),
                    (0, "Kimi audit findings\nVERDICT: PASS\n"),
                ],
            ) as timed_run_seat:
                result = concilium_runtime.run_concilium_adapter(
                    {
                        "repo": td,
                        "task": "Read-only audit; only write docs/audits/report.md.",
                        "test_cmd": "true",
                        "mode": "live_run",
                        "signals": {
                            "risk": "high",
                            "file_count": 8,
                            "security_sensitive": False,
                            "ambiguous": True,
                            "read_only": True,
                            "allowed_write_paths": ["docs/audits/report.md"],
                            "required_artifact_paths": ["docs/audits/report.md"],
                        },
                    },
                    event_sink=sink,
                    config=config,
                    capacity=[capacity_record("claude", "ok"), capacity_record("kimi", "ok")],
                )

                self.assertEqual(result["status"], "ran")
                self.assertEqual(result["returncode"], 0)
                self.assertEqual(result["artifact_gate"]["status"], "passed")
                self.assertEqual((repo / "docs" / "audits" / "report.md").read_text(encoding="utf-8").count("VERDICT: PASS"), 2)
                self.assertEqual([call.args[2:4] for call in timed_run_seat.call_args_list], [("claude", "review"), ("kimi", "review")])
                seat_events = [event for event in sink.events if event["type"] == "seat"]
                self.assertEqual([event["seat"] for event in seat_events], ["claude", "kimi"])
                self.assertEqual([event["status"] for event in seat_events], ["invoked", "invoked"])
                self.assertNotIn("not_invoked", [event.get("status") for event in sink.events])

    def test_live_audit_rejects_disallowed_required_report_before_writing(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            init_repo(repo)
            sink = concilium_runtime.concilium_events.ListEventSink()
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["audit"]["seats"] = ["claude"]

            with mock.patch.object(
                concilium_runtime.concilium_lanes.conductor,
                "timed_run_seat",
                return_value=(0, "review ok\nVERDICT: PASS\n"),
            ):
                result = concilium_runtime.run_concilium_adapter(
                    {
                        "repo": str(repo),
                        "task": "Read-only audit; only write docs/private/report.md.",
                        "test_cmd": "true",
                        "mode": "live_run",
                        "signals": {
                            "risk": "high",
                            "file_count": 8,
                            "security_sensitive": False,
                            "ambiguous": True,
                            "read_only": True,
                            "allowed_write_paths": ["docs/audits/*.md"],
                            "required_artifact_paths": ["docs/private/report.md"],
                        },
                    },
                    event_sink=sink,
                    config=config,
                    capacity=[capacity_record("claude", "ok")],
                )

            self.assertEqual(result["status"], "artifact_failed")
            self.assertIn("docs/private/report.md", result["artifact_gate"]["disallowed"])
            self.assertFalse((repo / "docs" / "private" / "report.md").exists())

    def test_live_audit_explicit_empty_allow_list_blocks_default_report_before_writing(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            init_repo(repo)
            sink = concilium_runtime.concilium_events.ListEventSink()
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["audit"]["seats"] = ["claude"]

            with mock.patch.object(
                concilium_runtime.concilium_lanes.conductor,
                "timed_run_seat",
                return_value=(0, "review ok\nVERDICT: PASS\n"),
            ):
                result = concilium_runtime.run_concilium_adapter(
                    {
                        "repo": str(repo),
                        "task": "Read-only audit; write no files.",
                        "test_cmd": "true",
                        "mode": "live_run",
                        "signals": {
                            "risk": "high",
                            "file_count": 8,
                            "security_sensitive": False,
                            "ambiguous": True,
                            "read_only": True,
                            "allowed_write_paths": [],
                            "required_artifact_paths": ["docs/audits/report.md"],
                        },
                    },
                    event_sink=sink,
                    config=config,
                    capacity=[capacity_record("claude", "ok")],
                )

            self.assertEqual(result["status"], "artifact_failed")
            self.assertIn("docs/audits/report.md", result["artifact_gate"]["missing"])
            self.assertFalse((repo / "docs" / "audits" / "report.md").exists())

    def test_live_audit_rejects_parent_required_report_before_writing(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = pathlib.Path(td)
            repo = workspace / "repo"
            repo.mkdir()
            init_repo(repo)
            sink = concilium_runtime.concilium_events.ListEventSink()
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["audit"]["seats"] = ["claude"]

            with mock.patch.object(
                concilium_runtime.concilium_lanes.conductor,
                "timed_run_seat",
                return_value=(0, "review ok\nVERDICT: PASS\n"),
            ):
                result = concilium_runtime.run_concilium_adapter(
                    {
                        "repo": str(repo),
                        "task": "Read-only audit; do not write outside the repo.",
                        "test_cmd": "true",
                        "mode": "live_run",
                        "signals": {
                            "risk": "high",
                            "file_count": 8,
                            "security_sensitive": False,
                            "ambiguous": True,
                            "read_only": True,
                            "allowed_write_paths": ["docs/audits/*.md"],
                            "required_artifact_paths": ["../escape.md"],
                        },
                    },
                    event_sink=sink,
                    config=config,
                    capacity=[capacity_record("claude", "ok")],
                )

            self.assertEqual(result["status"], "artifact_failed")
            self.assertIn("../escape.md", result["artifact_gate"]["invalid"])
            self.assertFalse((workspace / "escape.md").exists())

    def test_plan_review_passes_when_all_reviewers_pass(self):
        calls = []

        def executor(preview, effective):
            calls.append(preview["route"]["lane"])
            return {
                "status": "passed",
                "lane": "plan_review",
                "returncode": 0,
                "rounds": 1,
                "seat_results": [
                    {"seat": "claude", "mode": "review", "backend_type": "external_cli", "status": "invoked", "rc": 0},
                    {"seat": "kimi", "mode": "review", "backend_type": "external_cli", "status": "invoked", "rc": 0},
                ],
                "unresolved_blockers": [],
            }

        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)
            result = concilium_runtime.run_concilium_adapter(
                {
                    "repo": str(repo),
                    "task": "审核执行方案 docs/superpowers/plans/example.md",
                    "mode": "live_run",
                    "signals": {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
                },
                event_sink=concilium_runtime.concilium_events.ListEventSink(),
                config=copy.deepcopy(BASE_CONFIG),
                capacity=[
                    capacity_record("claude", "ok"),
                    capacity_record("hermes", "ok"),
                    capacity_record("kimi", "ok"),
                ],
                lane_executor=executor,
            )

        self.assertEqual(calls, ["plan_review"])
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["returncode"], 0)

    def test_plan_review_reports_max_rounds_with_unresolved_blockers(self):
        def executor(preview, effective):
            return {
                "status": "max_rounds",
                "lane": "plan_review",
                "returncode": 2,
                "rounds": 3,
                "seat_results": [
                    {"seat": "codex", "mode": "review", "backend_type": "external_cli", "status": "invoked", "rc": 2},
                ],
                "unresolved_blockers": [
                    {"seat": "codex", "severity": "HIGH", "summary": "Plan can still dispatch exec."}
                ],
            }

        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["plan_review"] = {"seats": ["codex"], "max_rounds": 3}
            result = concilium_runtime.run_concilium_adapter(
                {
                    "repo": str(repo),
                    "task": "审核执行方案 docs/superpowers/plans/example.md",
                    "mode": "live_run",
                    "signals": {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
                },
                event_sink=concilium_runtime.concilium_events.ListEventSink(),
                config=config,
                capacity=[capacity_record("codex", "ok")],
                lane_executor=executor,
            )

        self.assertEqual(result["status"], "max_rounds")
        self.assertEqual(result["returncode"], 2)
        self.assertEqual(result["rounds"], 3)
        self.assertEqual(result["unresolved_blockers"][0]["severity"], "HIGH")

    def test_default_plan_review_executor_dispatches_review_seats(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)
            plan = repo / "docs" / "superpowers" / "plans" / "example.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# Example Plan\n", encoding="utf-8")
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["plan_review"] = {"seats": ["claude", "kimi"], "max_rounds": 3}
            with mock.patch.object(
                concilium_runtime.concilium_lanes.conductor,
                "timed_run_seat",
                side_effect=[
                    (0, "Claude ok\nVERDICT: PASS\n"),
                    (0, "Kimi ok\nVERDICT: PASS\n"),
                ],
            ) as timed_run:
                result = concilium_runtime.run_concilium_adapter(
                    {
                        "repo": str(repo),
                        "task": "审核执行方案 docs/superpowers/plans/example.md",
                        "mode": "live_run",
                        "signals": {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
                    },
                    event_sink=concilium_runtime.concilium_events.ListEventSink(),
                    config=config,
                    capacity=[capacity_record("claude", "ok"), capacity_record("kimi", "ok")],
                )

        self.assertEqual(result["status"], "passed")
        self.assertEqual([call.args[2:4] for call in timed_run.call_args_list], [("claude", "review"), ("kimi", "review")])

    def test_plan_review_blocks_if_reviewer_changes_plan_file(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)
            plan = repo / "docs" / "superpowers" / "plans" / "example.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# Example Plan\n", encoding="utf-8")
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["plan_review"] = {"seats": ["kimi"], "max_rounds": 3}

            def mutate_plan(repo_arg, iter_arg, seat, mode, brief="", provider="", model=""):
                del iter_arg, seat, mode, brief, provider, model
                pathlib.Path(repo_arg, "docs/superpowers/plans/example.md").write_text("# Mutated\n", encoding="utf-8")
                return 0, "VERDICT: PASS\n"

            sink = concilium_runtime.concilium_events.ListEventSink()
            with mock.patch.object(concilium_runtime.concilium_lanes.conductor, "timed_run_seat", side_effect=mutate_plan):
                result = concilium_runtime.run_concilium_adapter(
                    {
                        "repo": str(repo),
                        "task": "审核执行方案 docs/superpowers/plans/example.md",
                        "mode": "live_run",
                        "signals": {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
                    },
                    event_sink=sink,
                    config=config,
                    capacity=[capacity_record("kimi", "ok")],
                )

        self.assertEqual(result["status"], "artifact_failed")
        self.assertIn("plan_fingerprint_changed", result["unresolved_blockers"][0]["summary"])
        self.assertIn("artifact_gate", [event["type"] for event in sink.events])

    def test_plan_review_blocks_if_reviewer_changes_preexisting_dirty_file(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)
            (repo / "tracked.md").write_text("dirty before review\n", encoding="utf-8")
            plan = repo / "docs" / "superpowers" / "plans" / "example.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# Example Plan\n", encoding="utf-8")
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["plan_review"] = {"seats": ["kimi"], "max_rounds": 3}

            def mutate_dirty_file(repo_arg, iter_arg, seat, mode, brief="", provider="", model=""):
                del iter_arg, seat, mode, brief, provider, model
                pathlib.Path(repo_arg, "tracked.md").write_text("dirty during review\n", encoding="utf-8")
                return 0, "VERDICT: PASS\n"

            with mock.patch.object(concilium_runtime.concilium_lanes.conductor, "timed_run_seat", side_effect=mutate_dirty_file):
                result = concilium_runtime.run_concilium_adapter(
                    {
                        "repo": str(repo),
                        "task": "审核执行方案 docs/superpowers/plans/example.md",
                        "mode": "live_run",
                        "signals": {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
                    },
                    event_sink=concilium_runtime.concilium_events.ListEventSink(),
                    config=config,
                    capacity=[capacity_record("kimi", "ok")],
                )

        self.assertEqual(result["status"], "artifact_failed")
        self.assertIn("tracked.md", result["unresolved_blockers"][0]["summary"])

    def test_plan_review_mixed_err_and_block_requires_retry_first(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)
            plan = repo / "docs" / "superpowers" / "plans" / "example.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# Example Plan\n", encoding="utf-8")
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["plan_review"] = {"seats": ["claude", "kimi"], "max_rounds": 3}
            with mock.patch.object(
                concilium_runtime.concilium_lanes.conductor,
                "timed_run_seat",
                side_effect=[
                    (2, "Plan blocker\nVERDICT: BLOCK\n"),
                    (1, "network error"),
                ],
            ):
                result = concilium_runtime.run_concilium_adapter(
                    {
                        "repo": str(repo),
                        "task": "审核执行方案 docs/superpowers/plans/example.md",
                        "mode": "live_run",
                        "signals": {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
                    },
                    event_sink=concilium_runtime.concilium_events.ListEventSink(),
                    config=config,
                    capacity=[capacity_record("claude", "ok"), capacity_record("kimi", "ok")],
                )

        self.assertEqual(result["status"], "retry_required")
        self.assertEqual(result["returncode"], 1)

    def test_plan_review_rejects_plan_path_outside_repo(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            init_repo(repo)
            outside = pathlib.Path(td) / "outside.md"
            outside.write_text("# Outside\n", encoding="utf-8")
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["plan_review"] = {"seats": ["codex"], "max_rounds": 3}
            result = concilium_runtime.run_concilium_adapter(
                {
                    "repo": str(repo),
                    "task": "审核执行方案 ../outside.md",
                    "mode": "live_run",
                    "signals": {"plan_review": True, "plan_path": "../outside.md"},
                },
                event_sink=concilium_runtime.concilium_events.ListEventSink(),
                config=config,
                capacity=[capacity_record("codex", "ok")],
            )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("outside repo", result["unresolved_blockers"][0]["summary"])

    def test_plan_review_next_action_distinguishes_retry_from_revision(self):
        self.assertEqual(
            concilium_runtime.plan_review_next_action({"status": "retry_required"}, 1, 3),
            "retry_or_mark_unavailable",
        )
        self.assertEqual(
            concilium_runtime.plan_review_next_action({"status": "blocked"}, 1, 3),
            "revise_plan",
        )
        self.assertEqual(
            concilium_runtime.plan_review_next_action({"status": "blocked"}, 3, 3),
            "max_rounds",
        )
        self.assertEqual(
            concilium_runtime.plan_review_next_action({"status": "passed"}, 1, 3),
            "approved",
        )

    def test_plan_review_host_loop_revises_then_passes(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)
            plan = repo / "docs" / "superpowers" / "plans" / "example.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# Example Plan\n", encoding="utf-8")
            revisions = []
            outcomes = [
                {"status": "blocked", "unresolved_blockers": [{"summary": "missing gate"}]},
                {"status": "passed", "unresolved_blockers": []},
            ]

            def revise_plan(blockers, round_index):
                revisions.append((round_index, blockers[0]["summary"]))
                plan.write_text("# Example Plan\n\nFixed missing gate.\n", encoding="utf-8")

            result = concilium_runtime.run_plan_review_host_loop(
                run_round=lambda round_index: outcomes[round_index - 1],
                revise_plan=revise_plan,
                repo=repo,
                plan_path="docs/superpowers/plans/example.md",
                max_rounds=3,
            )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["rounds"], 2)
        self.assertEqual(revisions, [(1, "missing gate")])

    def test_plan_review_host_loop_stops_at_max_rounds(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)
            plan = repo / "docs" / "superpowers" / "plans" / "example.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# Example Plan\n", encoding="utf-8")
            revisions = []

            result = concilium_runtime.run_plan_review_host_loop(
                run_round=lambda round_index: {"status": "blocked", "unresolved_blockers": [{"summary": f"block {round_index}"}]},
                revise_plan=lambda blockers, round_index: revisions.append(round_index),
                repo=repo,
                plan_path="docs/superpowers/plans/example.md",
                max_rounds=3,
            )

        self.assertEqual(result["status"], "max_rounds")
        self.assertEqual(result["rounds"], 3)
        self.assertEqual(revisions, [1, 2])

    def test_plan_review_host_loop_blocks_non_plan_revision(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)
            plan = repo / "docs" / "superpowers" / "plans" / "example.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# Example Plan\n", encoding="utf-8")

            def revise_plan(blockers, round_index):
                del blockers, round_index
                (repo / "tracked.md").write_text("implementation leaked before approval\n", encoding="utf-8")

            result = concilium_runtime.run_plan_review_host_loop(
                run_round=lambda round_index: {"status": "blocked", "unresolved_blockers": [{"summary": "missing gate"}]},
                revise_plan=revise_plan,
                repo=repo,
                plan_path="docs/superpowers/plans/example.md",
                max_rounds=3,
            )

        self.assertEqual(result["status"], "artifact_failed")
        self.assertEqual(result["returncode"], 2)
        self.assertIn("tracked.md", result["unresolved_blockers"][-1]["summary"])

    def test_live_run_warning_requires_confirmation_without_executor_call(self):
        with tempfile.TemporaryDirectory() as td:
            sink = concilium_runtime.concilium_events.ListEventSink()
            executor = mock.Mock(side_effect=AssertionError("executor must not run without guard allowance"))

            result = concilium_runtime.run_concilium_adapter(
                {
                    "repo": td,
                    "task": "Change config routing behavior.",
                    "test_cmd": "true",
                    "mode": "live_run",
                    "signals": {"risk": "medium", "file_count": 2, "security_sensitive": False, "ambiguous": False},
                },
                event_sink=sink,
                config=BASE_CONFIG,
                capacity=[capacity_record("kimi", "ok"), capacity_record("hermes", "unknown")],
                lane_executor=executor,
            )

        self.assertEqual(result["status"], "confirmation_required")
        self.assertEqual(result["guard"]["status"], "confirmation_required")
        self.assertTrue(result["guard"]["confirmation_payload"]["request_fingerprint"])
        self.assertEqual([event["type"] for event in sink.events], ["start", "preflight", "guard", "finish", "done"])
        self.assertEqual(sink.events[-2]["rc"], 3)
        self.assertEqual(sink.events[-1]["rc"], 3)
        executor.assert_not_called()

    def test_live_run_executor_error_returns_error_and_emits_finish_done_once(self):
        with tempfile.TemporaryDirectory() as td:
            sink = concilium_runtime.concilium_events.ListEventSink()

            def failing_executor(preview, effective):
                raise RuntimeError("executor failed with token sk-secret123 user@example.com")

            result = concilium_runtime.run_concilium_adapter(
                {
                    "repo": td,
                    "task": "Fix one typo in docs/example.md.",
                    "test_cmd": "true",
                    "mode": "live_run",
                    "signals": {"risk": "low", "file_count": 1, "security_sensitive": False, "ambiguous": False},
                },
                event_sink=sink,
                config=BASE_CONFIG,
                capacity=[capacity_record("kimi", "ok")],
                lane_executor=failing_executor,
            )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["returncode"], 1)
        self.assertIn("[REDACTED]", result["error"])
        self.assertNotIn("sk-secret123", result["error"])
        self.assertNotIn("user@example.com", result["error"])
        self.assertEqual([event["type"] for event in sink.events[-2:]], ["finish", "done"])
        self.assertEqual(sink.events[-1]["rc"], 1)
        self.assertEqual(len([event for event in sink.events if event["type"] == "done"]), 1)
        self.assertEqual(result["events"], sink.events)


if __name__ == "__main__":
    unittest.main()
