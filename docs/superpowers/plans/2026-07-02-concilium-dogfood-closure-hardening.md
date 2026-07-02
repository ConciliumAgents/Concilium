# Concilium Dogfood Closure Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Concilium's default launcher, run evidence, capacity failures, and session retention reliable enough for Phase 5 menu-bar product work.

**Architecture:** Keep routing, Budget Guard, lane execution, and artifact gates in the existing Python backend. Add a small run-summary contract that turns each run into one canonical machine-readable record, then add a narrow session-retention scanner that reports and prunes sensitive `.roundtable` sessions without moving orchestration into UI code. Age-based stale-session policy stays out of this pass until the canonical summary and sensitivity scan are stable.

**Tech Stack:** Python standard library, existing `skills/loop-engine/bin/*.py` modules, existing `roundtable` shell launcher, existing `unittest` suite.

---

## First-Principles Basis

Concilium exists to decide and execute the cheapest safe agent collaboration pattern while preserving evidence about what actually happened. The FBA and agent-search dogfood runs showed the core native-seat path works, but they also exposed product-readiness gaps:

1. The default launcher used in both dogfood runs was `main@f44bbf0`, while the Phase 5 preflight cleanup work was still on `codex/concilium-phase5-preflight-cleanup@74b9939`.
2. FBA reached stable native-seat closure: `claude`, `hermes`, and `kimi` all used `external_cli` and passed.
3. Agent-search reached implementation closure in code and tests, but the final review evidence was split across sessions, with a Kimi `429` quota error in the last retained review.
4. The human reports captured `participants`, `backend_type`, Budget Guard, and seat failures, but retained `roundtable.json` files do not consistently carry that complete contract.
5. `.roundtable/sessions` can retain sensitive context, as seen in the FBA cleanup where older session material had to be removed.

The optimization target is therefore not "more agents" or "more UI". It is: the default product path must be current, every run must leave one trustworthy summary, quota exhaustion must be distinguishable from reviewer disagreement, and retained sessions must be visible and manageable.

## File Map

- Modify: `roundtable`
  - Add `sessions scan` and `sessions prune` subcommands after the existing `service` / `legacy` / `--doctor` blocks.
- Create: `skills/loop-engine/bin/concilium_run_summary.py`
  - Build and write the canonical `run-summary.json`.
  - Classify seat outcomes, including quota exhaustion.
  - Compute final verdict labels for UI and reports.
- Modify: `skills/loop-engine/bin/concilium_runtime.py`
  - Attach run summaries to preview/stub/live results.
  - Write `run-summary.json` when a lane returns `session_path`.
  - Reuse one local Budget Guard module after the Phase 5 preflight branch is merged.
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
  - Ensure Fast, Review, Audit, Plan Review, and Roundtable lanes return `session_path`.
  - Preserve `seat_results` for every lane that invokes a seat.
  - Keep the tightened audit artifact baseline from the Phase 5 preflight branch.
- Do not modify: `skills/loop-engine/bin/conductor.py`
  - Treat legacy `roundtable.json` as a read-only compatibility source.
  - Do not make conductor responsible for Budget Guard or runtime-level summary decisions.
- Create: `skills/loop-engine/bin/session_retention.py`
  - Scan `.roundtable/sessions` for sensitive indicators.
  - Prune only with explicit `--yes`.
- Modify: `skills/loop-engine/bin/report-session.py`
  - Prefer `run-summary.json` when present.
  - Fall back to legacy `roundtable.json`.
- Modify: `skills/loop-engine/client/menu_bar_view_model.py`
  - Read `run_summary` fields when available and keep the UI model thin.
- Create: `skills/loop-engine/tests/test_concilium_run_summary.py`
- Modify: `skills/loop-engine/tests/test_concilium_runtime.py`
- Modify: `skills/loop-engine/tests/test_concilium_lanes.py`
- Create: `skills/loop-engine/tests/test_session_retention.py`
- Modify: `skills/loop-engine/tests/test_roundtable_launcher.py`
- Modify: `skills/loop-engine/tests/test_report_session.py`
- Modify: `docs/loop-engine/concilium-menu-bar-contract.md`
- Create: `docs/loop-engine/dogfood-closure-hardening-2026-07-02.md`

## Task 0: Promote The Phase 5 Preflight Cleanup Into The Default Launcher

**Files:**
- Existing branch: `codex/concilium-phase5-preflight-cleanup`
- Target branch: `main`

- [ ] **Step 1: Confirm current default launcher state**

Run:

```bash
git status --short --branch
git log --oneline --decorate -5
git branch --contains 74b9939
```

Expected before merge, based on the dogfood snapshot observed on 2026-07-02. If the live SHA values have moved, use the live `git log` / `git branch --contains` result as the source of truth:

```text
main points at f44bbf0
codex/concilium-phase5-preflight-cleanup contains 74b9939
main does not contain 74b9939
```

- [ ] **Step 2: Merge the reviewed cleanup branch**

Run:

```bash
git switch main
git merge --no-ff codex/concilium-phase5-preflight-cleanup -m "merge: concilium phase5 preflight cleanup"
```

Expected: merge succeeds without code conflicts. If docs conflicts occur in `docs/audits/` or `docs/superpowers/plans/`, keep both dated files and do not delete the dogfood evidence files.

- [ ] **Step 3: Verify merged baseline**

Run:

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
bash -n roundtable
bash -n skills/loop-engine/bin/smoke-concilium-phase3.sh
bash -n skills/loop-engine/bin/smoke-concilium-phase4.sh
python3 -m py_compile \
  skills/loop-engine/bin/concilium_runtime.py \
  skills/loop-engine/bin/concilium_lanes.py \
  skills/loop-engine/bin/review-lane.py \
  skills/loop-engine/web/server.py
git diff --check
```

Expected:

```text
unittest: OK
all bash -n commands: exit 0
py_compile: exit 0
git diff --check: no output
```

- [ ] **Step 4: Commit only if the merge did not create a merge commit**

If Step 2 produced a merge commit, do not create another commit. If Step 2 had to be resolved manually and left staged files, commit:

```bash
git add roundtable skills/loop-engine docs
git commit -m "merge: concilium phase5 preflight cleanup"
```

## Task 1: Add A Canonical Run Summary Contract

**Files:**
- Create: `skills/loop-engine/bin/concilium_run_summary.py`
- Create: `skills/loop-engine/tests/test_concilium_run_summary.py`

- [ ] **Step 1: Write failing tests for the summary shape**

Create `skills/loop-engine/tests/test_concilium_run_summary.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium_run_summary.py"
spec = importlib.util.spec_from_file_location("concilium_run_summary", MODULE)
concilium_run_summary = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(concilium_run_summary)


def base_result() -> dict:
    return {
        "status": "ran",
        "mode": "live_run",
        "request_fingerprint": "abc123",
        "request": {"repo": "/repo", "task": "Audit.", "mode": "live_run"},
        "route": {"lane": "audit", "required_seats": ["claude", "hermes", "kimi"]},
        "preflight": {"status": "warn", "warnings": ["capacity unknown"], "blocking_seats": []},
        "guard": {"status": "allowed", "requires_confirmation": False},
        "capacity": [
            {"seat": "claude", "provider": "anthropic", "model": "opus", "status": "unknown", "source": "not_checked"},
            {"seat": "hermes", "provider": "DeepSeek", "model": "deepseek-v4-flash", "status": "unknown", "source": "not_checked"},
            {"seat": "kimi", "provider": "moonshot", "model": "kimi-code/kimi-for-coding", "status": "unknown", "source": "not_checked"},
        ],
        "seat_results": [
            {"seat": "claude", "mode": "review", "backend_type": "external_cli", "status": "invoked", "rc": 0, "verdict": "PASS"},
            {"seat": "hermes", "mode": "review", "backend_type": "external_cli", "status": "invoked", "rc": 0, "verdict": "PASS"},
            {"seat": "kimi", "mode": "review", "backend_type": "external_cli", "status": "invoked", "rc": 0, "verdict": "PASS"},
        ],
        "verify": {"returncode": 0, "output": "OK"},
        "artifact_gate": {"status": "passed", "disallowed_delta": []},
        "events": [],
        "returncode": 0,
    }


class RunSummaryTests(unittest.TestCase):
    def test_build_summary_records_launcher_guard_seats_and_artifact_gate(self):
        summary = concilium_run_summary.build_run_summary(
            base_result(),
            launcher={"entrypoint": "/Users/melee/.local/bin/roundtable", "repo": "/Users/melee/Documents/agents", "branch": "main", "commit": "abc"},
        )

        self.assertEqual(summary["schema_version"], "concilium.run_summary.v1")
        self.assertEqual(summary["launcher"]["commit"], "abc")
        self.assertEqual(summary["route"]["lane"], "audit")
        self.assertEqual(summary["budget_guard"]["status"], "allowed")
        self.assertEqual(summary["final_verdict"], "pass")
        self.assertEqual([seat["seat"] for seat in summary["seats"]], ["claude", "hermes", "kimi"])
        self.assertTrue(all(seat["backend_type"] == "external_cli" for seat in summary["seats"]))
        self.assertEqual(summary["artifact_gate"]["status"], "passed")

    def test_quota_error_becomes_retry_required_not_block(self):
        result = base_result()
        result["returncode"] = 1
        result["seat_results"][2] = {
            "seat": "kimi",
            "mode": "review",
            "backend_type": "external_cli",
            "status": "invoked",
            "rc": 1,
            "verdict": "ERR",
            "output_tail": "provider.rate_limit: 429 You've reached your usage limit for this period. Your quota will be refreshed in the next period.",
        }

        summary = concilium_run_summary.build_run_summary(result, launcher={"commit": "abc"})

        self.assertEqual(summary["seats"][2]["outcome"], "quota_exhausted")
        self.assertEqual(summary["final_verdict"], "retry_required")
        self.assertIn("kimi", summary["retry_required_seats"])
        self.assertEqual(summary["blocking_seats"], [])

    def test_blocking_review_remains_block(self):
        result = base_result()
        result["returncode"] = 2
        result["seat_results"][1]["rc"] = 2
        result["seat_results"][1]["verdict"] = "BLOCK"

        summary = concilium_run_summary.build_run_summary(result, launcher={"commit": "abc"})

        self.assertEqual(summary["final_verdict"], "block")
        self.assertEqual(summary["blocking_seats"], ["hermes"])

    def test_blocking_review_with_quota_text_still_blocks(self):
        result = base_result()
        result["returncode"] = 2
        result["seat_results"][1] = {
            "seat": "hermes",
            "mode": "review",
            "backend_type": "external_cli",
            "status": "invoked",
            "rc": 2,
            "verdict": "BLOCK",
            "output_tail": "This quota classifier can mis-handle 429 errors and weaken reviewer authority.",
        }

        summary = concilium_run_summary.build_run_summary(result, launcher={"commit": "abc"})

        self.assertEqual(summary["seats"][1]["outcome"], "block")
        self.assertEqual(summary["final_verdict"], "block")
        self.assertEqual(summary["blocking_seats"], ["hermes"])

    def test_roundtable_state_fills_seats_when_lane_has_no_seat_results(self):
        result = base_result()
        result.pop("seat_results")
        result["roundtable_state"] = {
            "participants": ["claude", "hermes"],
            "seat_verdicts": [
                {"iter": 1, "seat": "claude", "mode": "review", "rc": 0, "verdict": "PASS"},
                {"iter": 1, "seat": "hermes", "mode": "review", "rc": 2, "verdict": "BLOCK"},
            ],
            "seat_timings": [
                {"iter": 1, "seat": "claude", "mode": "review", "rc": 0, "duration_seconds": 10.5},
                {"iter": 1, "seat": "hermes", "mode": "review", "rc": 2, "duration_seconds": 8.25},
            ],
        }

        summary = concilium_run_summary.build_run_summary(result, launcher={"commit": "abc"})

        self.assertEqual([seat["seat"] for seat in summary["seats"]], ["claude", "hermes"])
        self.assertEqual(summary["seats"][1]["duration_seconds"], 8.25)
        self.assertEqual(summary["final_verdict"], "block")

    def test_roundtable_state_uses_latest_iter_per_seat_mode(self):
        result = base_result()
        result.pop("seat_results")
        result["roundtable_state"] = {
            "participants": ["claude", "hermes"],
            "seat_verdicts": [
                {"iter": 1, "seat": "claude", "mode": "review", "rc": 0, "verdict": "PASS"},
                {"iter": 1, "seat": "hermes", "mode": "review", "rc": 2, "verdict": "BLOCK"},
                {"iter": 2, "seat": "claude", "mode": "review", "rc": 0, "verdict": "PASS"},
                {"iter": 2, "seat": "hermes", "mode": "review", "rc": 0, "verdict": "PASS"},
            ],
            "seat_timings": [
                {"iter": 1, "seat": "claude", "mode": "review", "rc": 0, "duration_seconds": 10.5},
                {"iter": 1, "seat": "hermes", "mode": "review", "rc": 2, "duration_seconds": 8.25},
                {"iter": 2, "seat": "claude", "mode": "review", "rc": 0, "duration_seconds": 6.5},
                {"iter": 2, "seat": "hermes", "mode": "review", "rc": 0, "duration_seconds": 7.25},
            ],
        }

        summary = concilium_run_summary.build_run_summary(result, launcher={"commit": "abc"})

        self.assertEqual(summary["final_verdict"], "pass")
        self.assertEqual(summary["blocking_seats"], [])
        self.assertEqual(summary["seats"][1]["duration_seconds"], 7.25)

    def test_write_summary_persists_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "run-summary.json"
            summary = concilium_run_summary.write_run_summary(path, base_result(), launcher={"commit": "abc"})

            self.assertTrue(path.is_file())
            self.assertEqual(summary["schema_version"], "concilium.run_summary.v1")
            self.assertIn('"final_verdict": "pass"', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail because the module does not exist**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_run_summary.py
```

Expected:

```text
FileNotFoundError or ImportError for concilium_run_summary.py
FAILED
```

- [ ] **Step 3: Implement the summary module**

Create `skills/loop-engine/bin/concilium_run_summary.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "concilium.run_summary.v1"
QUOTA_PATTERNS = (
    re.compile(r"\b429\b", re.I),
    re.compile(r"\brate[_ -]?limit\b", re.I),
    re.compile(r"\busage limit\b", re.I),
    re.compile(r"\bquota\b", re.I),
    re.compile(r"\brefreshed? in\b", re.I),
)


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _capacity_index(capacity: list[dict]) -> dict[str, dict]:
    return {str(item.get("seat", "")): item for item in capacity if isinstance(item, dict) and item.get("seat")}


def is_quota_error(row: dict) -> bool:
    rc = int(row.get("rc", 0) or 0)
    verdict = str(row.get("verdict", "")).upper()
    if rc != 1 and verdict != "ERR":
        return False
    text = " ".join(str(row.get(key, "")) for key in ("output_tail", "error", "reason"))
    return any(pattern.search(text) for pattern in QUOTA_PATTERNS)


def seat_outcome(row: dict) -> str:
    rc = int(row.get("rc", 0) or 0)
    verdict = str(row.get("verdict", "")).upper()
    if rc == 0 and verdict in {"", "PASS"}:
        return "pass"
    if rc == 2 or verdict == "BLOCK":
        return "block"
    if is_quota_error(row):
        return "quota_exhausted"
    if rc == 124:
        return "timeout"
    return "error"


def _roundtable_seat_rows(result: dict) -> list[dict]:
    state = _as_dict(result.get("roundtable_state"))
    if not state:
        return []
    timings = {
        (str(row.get("iter", "")), str(row.get("seat", "")), str(row.get("mode", ""))): row
        for row in _as_list(state.get("seat_timings"))
        if isinstance(row, dict)
    }
    latest = {}
    for row in _as_list(state.get("seat_verdicts")):
        if not isinstance(row, dict):
            continue
        seat = str(row.get("seat", ""))
        mode = str(row.get("mode", ""))
        try:
            iter_no = int(row.get("iter", 0) or 0)
        except (TypeError, ValueError):
            iter_no = 0
        key = (seat, mode)
        if key not in latest or iter_no >= latest[key][0]:
            latest[key] = (iter_no, row)
    rows = []
    for (seat, mode), (iter_no, row) in latest.items():
        key = (str(row.get("iter", "")), str(row.get("seat", "")), str(row.get("mode", "")))
        timing = timings.get(key, {})
        rows.append({
            "seat": seat,
            "mode": mode,
            "backend_type": "external_cli",
            "status": "invoked",
            "rc": int(row.get("rc", 0) or 0),
            "verdict": str(row.get("verdict", "")),
            "duration_seconds": timing.get("duration_seconds", ""),
        })
    return rows


def _seat_rows(result: dict) -> list[dict]:
    capacity = _capacity_index(_as_list(result.get("capacity")))
    source_rows = _as_list(result.get("seat_results")) or _roundtable_seat_rows(result)
    rows = []
    for item in source_rows:
        if not isinstance(item, dict):
            continue
        seat = str(item.get("seat", ""))
        cap = capacity.get(seat, {})
        rows.append({
            "seat": seat,
            "mode": str(item.get("mode", "")),
            "backend_type": str(item.get("backend_type", "")),
            "status": str(item.get("status", "")),
            "rc": int(item.get("rc", 0) or 0),
            "verdict": str(item.get("verdict", "")),
            "outcome": seat_outcome(item),
            "provider": str(cap.get("provider", "")),
            "model": str(cap.get("model", "")),
            "capacity_status": str(cap.get("status", "unknown")),
            "capacity_source": str(cap.get("source", "")),
            "duration_seconds": item.get("duration_seconds", ""),
        })
    return rows


def final_verdict(result: dict, seats: list[dict]) -> tuple[str, list[str], list[str]]:
    blocking = [row["seat"] for row in seats if row.get("outcome") == "block"]
    retry = [row["seat"] for row in seats if row.get("outcome") in {"quota_exhausted", "timeout", "error"}]
    if _as_dict(result.get("artifact_gate")).get("status") == "failed":
        return "artifact_failed", blocking, retry
    if blocking:
        return "block", blocking, retry
    if retry:
        return "retry_required", blocking, retry
    if int(result.get("returncode", 0) or 0) == 0 and str(result.get("status", "")) not in {"blocked", "error", "artifact_failed"}:
        return "pass", blocking, retry
    return "error", blocking, retry


def build_run_summary(result: dict, launcher: dict | None = None) -> dict:
    launcher = dict(launcher or {})
    seats = _seat_rows(result)
    verdict, blocking, retry = final_verdict(result, seats)
    request = _as_dict(result.get("request"))
    route = _as_dict(result.get("route"))
    preflight = _as_dict(result.get("preflight"))
    guard = _as_dict(result.get("guard"))
    artifact_gate = _as_dict(result.get("artifact_gate"))
    verify = _as_dict(result.get("verify"))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "launcher": launcher,
        "request_fingerprint": str(result.get("request_fingerprint", "")),
        "request": {
            "repo": str(request.get("repo", "")),
            "task": str(request.get("task", "")),
            "mode": str(request.get("mode", result.get("mode", ""))),
        },
        "route": {
            "lane": str(route.get("lane", result.get("lane", ""))),
            "required_seats": list(route.get("required_seats") or []),
            "reason": str(route.get("reason", "")),
        },
        "preflight": preflight,
        "budget_guard": guard,
        "capacity": _as_list(result.get("capacity")),
        "seats": seats,
        "final_verdict": verdict,
        "blocking_seats": blocking,
        "retry_required_seats": retry,
        "returncode": int(result.get("returncode", 0) or 0),
        "status": str(result.get("status", "")),
        "verify": verify,
        "artifact_gate": artifact_gate,
        "session_path": str(result.get("session_path", "")),
    }


def write_run_summary(path: str | Path, result: dict, launcher: dict | None = None) -> dict:
    summary = build_run_summary(result, launcher=launcher)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_run_summary.py
```

Expected:

```text
Ran 7 tests
OK
```

- [ ] **Step 5: Commit**

Run:

```bash
git add skills/loop-engine/bin/concilium_run_summary.py skills/loop-engine/tests/test_concilium_run_summary.py
git commit -m "feat(concilium): add canonical run summary contract"
```

## Task 2: Attach Run Summaries To Runtime Results And Session Artifacts

**Files:**
- Modify: `skills/loop-engine/bin/concilium_runtime.py`
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
- Modify: `skills/loop-engine/tests/test_concilium_runtime.py`
- Modify: `skills/loop-engine/tests/test_concilium_lanes.py`

- [ ] **Step 1: Add failing lane tests for `session_path`**

In `skills/loop-engine/tests/test_concilium_lanes.py`, add:

```python
    def test_audit_lane_returns_session_path(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_lanes.process_runner, "run_process_group", side_effect=self._successful_process), \
                mock.patch.object(concilium_lanes.conductor, "write_roster", return_value=["claude"]), \
                mock.patch.object(concilium_lanes.conductor, "set_participants"), \
                mock.patch.object(concilium_lanes.conductor, "timed_run_seat", return_value=(0, "VERDICT: PASS")):
            repo = pathlib.Path(td).resolve()
            result = concilium_lanes.run_audit_lane(
                repo,
                "Read-only audit.",
                "",
                {"lanes": {"audit": {"seats": ["claude"]}}, "seat_models": {}},
                timeout=12,
            )

        self.assertEqual(result["status"], "ran")
        self.assertIn("/.roundtable/sessions/audit-", result["session_path"])

    def test_plan_review_lane_returns_session_path_on_retry_required(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td).resolve()
            plan = repo / "docs" / "superpowers" / "plans" / "example.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# Example Plan\n", encoding="utf-8")
            config = {
                "lanes": {"plan_review": {"seats": ["kimi"], "plan_path": str(plan.relative_to(repo))}},
                "seat_models": {},
            }
            with mock.patch.object(concilium_lanes.process_runner, "run_process_group", side_effect=self._successful_process), \
                    mock.patch.object(concilium_lanes.conductor, "write_roster", return_value=["kimi"]), \
                    mock.patch.object(concilium_lanes.conductor, "set_participants"), \
                    mock.patch.object(concilium_lanes.conductor, "timed_run_seat", return_value=(1, "provider.rate_limit: 429 quota")):
                result = concilium_lanes.run_plan_review_lane(repo, "Review plan.", "", config, timeout=12)

        self.assertEqual(result["status"], "retry_required")
        self.assertIn("/.roundtable/sessions/plan-review-", result["session_path"])

    def test_plan_review_bad_plan_path_returns_blocked_without_session_path(self):
        result = concilium_lanes.run_plan_review_lane(
            "/tmp/repo",
            "Review plan.",
            "",
            {"lanes": {"plan_review": {"seats": ["kimi"], "plan_path": "../escape.md"}}, "seat_models": {}},
            timeout=12,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("session_path", result)

    def test_review_lane_preserves_delegated_session_path_without_summary_attachment(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td).resolve()
            session = repo / ".roundtable" / "sessions" / "review-unit"
            delegated = {
                "status": "done",
                "returncode": 0,
                "session_path": str(session),
            }
            with mock.patch.object(concilium_lanes.review_lane_module, "run_review_lane", return_value=delegated):
                result = concilium_lanes.run_review_lane(
                    repo,
                    "Review and repair.",
                    "",
                    {"lanes": {"review": {}}, "seat_models": {}},
                    timeout=12,
                )

        self.assertEqual(result["status"], "ran")
        self.assertEqual(result["lane"], "review")
        self.assertEqual(result["session_path"], str(session))
        self.assertNotIn("run_summary", result)
```

- [ ] **Step 2: Add failing runtime tests for summary attachment**

In `skills/loop-engine/tests/test_concilium_runtime.py`, add:

```python
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
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
python3 -m unittest \
  skills/loop-engine/tests/test_concilium_lanes.py \
  skills/loop-engine/tests/test_concilium_runtime.py
```

Expected: failures for missing `session_path` and missing `run_summary`.

- [ ] **Step 4: Add `session_path` helper and lane return fields**

In `skills/loop-engine/bin/concilium_lanes.py`, add near `_lane_env`:

```python
def _session_path(repo: str | Path, env: dict[str, str]) -> str:
    return str(Path(repo).expanduser().resolve() / ".roundtable" / "sessions" / str(env.get("LOOP_SESSION", "")))
```

Then add `"session_path": _session_path(repo_path, env)` only to return dictionaries that execute after `env` exists in:

- `run_fast_lane`
- `run_audit_lane`
- `run_plan_review_lane`
- `run_roundtable_lane`

Do not add `session_path` to the three early `run_plan_review_lane` returns for invalid, outside-repo, or missing `plan_path`; no session has been created in those branches.

For `run_review_lane`, do not compute a new `session_path` and do not attach run summaries in `concilium_lanes.py`. The delegated `review-lane.py` already returns `session_path`, and Task 2 Step 5 makes `concilium_runtime.py` the single place that attaches and writes `run-summary.json`:

```python
    result = dict(result)
    result["status"] = "ran"
    result["lane"] = "review"
    return result
```

For `run_roundtable_lane`, explicitly create a lane env that owns `LOOP_SESSION`, then read legacy `roundtable.json` as compatibility state:

```python
def _read_roundtable_state(session_path: str) -> dict:
    path = Path(session_path) / "roundtable.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


    # Inside run_roundtable_lane after repo_path, config, roundtable, and reporter are available.
    env = _lane_env("roundtable", task, timeout, config)
    scoped = {key: env[key] for key in ("LOOP_SESSION", "LOOP_ARCHIVE")}
    scoped.update(_seat_timeout_env(timeout, config))
    with _scoped_env(scoped):
        rc = conductor.run(
            str(repo_path),
            task,
            commander=roundtable.get("commander", "claude"),
            reviewer=roundtable.get("reviewer", ""),
            max_iters=int(roundtable.get("max_iters", 5)),
            test_cmd=test_cmd,
            reporter=reporter,
            seats=roundtable.get("seats") or None,
            seat_models=config.get("seat_models", {}),
        )
    session_path = _session_path(repo_path, env)
    return {
        "status": "ran" if rc == 0 else "blocked" if rc == 2 else "error",
        "lane": "roundtable",
        "returncode": rc,
        "session_path": session_path,
        "roundtable_state": _read_roundtable_state(session_path),
    }
```

- [ ] **Step 5: Attach and write run summaries in runtime**

In `skills/loop-engine/bin/concilium_runtime.py`, import the new module:

```python
import concilium_run_summary  # noqa: E402
```

Add helper:

```python
def _launcher_info() -> dict:
    return {
        "entrypoint": str(Path(__file__).resolve().parents[3] / "roundtable"),
        "repo": str(Path(__file__).resolve().parents[3]),
    }


def _attach_run_summary(result: dict) -> dict:
    summary = concilium_run_summary.build_run_summary(result, launcher=_launcher_info())
    result["run_summary"] = summary
    session_path = str(result.get("session_path", "")).strip()
    if session_path:
        concilium_run_summary.write_run_summary(Path(session_path) / "run-summary.json", result, launcher=_launcher_info())
    return result
```

Before each `return result` in `run_concilium_adapter`, call `_attach_run_summary(result)` for live/stub/guard results. For preview mode, attach a summary but do not write a session file because no session exists:

```python
        result = dict(preview)
        result["events"] = _events_from_sink(sink)
        result["run_summary"] = concilium_run_summary.build_run_summary(result, launcher=_launcher_info())
        return result
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
python3 -m unittest \
  skills/loop-engine/tests/test_concilium_run_summary.py \
  skills/loop-engine/tests/test_concilium_lanes.py \
  skills/loop-engine/tests/test_concilium_runtime.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add \
  skills/loop-engine/bin/concilium_runtime.py \
  skills/loop-engine/bin/concilium_lanes.py \
  skills/loop-engine/tests/test_concilium_runtime.py \
  skills/loop-engine/tests/test_concilium_lanes.py
git commit -m "feat(concilium): persist run summaries for product evidence"
```

## Task 3: Make Quota Failures First-Class Review Outcomes

**Files:**
- Modify: `skills/loop-engine/bin/concilium_run_summary.py`
- Modify: `skills/loop-engine/bin/concilium_runtime.py`
- Modify: `skills/loop-engine/tests/test_concilium_runtime.py`
- Modify: `docs/loop-engine/concilium-menu-bar-contract.md`

- [ ] **Step 1: Add failing tests for retry-required event semantics**

In `skills/loop-engine/tests/test_concilium_runtime.py`, add:

```python
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
                    capacity_record("kimi", "soft_limited"),
                ],
                lane_executor=executor,
            )

        self.assertEqual(result["run_summary"]["final_verdict"], "retry_required")
        self.assertEqual(result["run_summary"]["retry_required_seats"], ["kimi"])
        self.assertNotIn("kimi", result["run_summary"]["blocking_seats"])
```

- [ ] **Step 2: Run test and verify failure if Task 1/2 did not classify quota**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_runtime.py
```

Expected before full implementation: failure on `run_summary` or `retry_required_seats`.

- [ ] **Step 3: Add explicit final status mapping in runtime**

After `_attach_run_summary(result)` is available, keep the lane `returncode` unchanged, but set a UI-safe field:

```python
    result = _attach_run_summary(result)
    result["product_status"] = result["run_summary"]["final_verdict"]
    return result
```

This ensures command-line compatibility while letting UI and reports distinguish:

- `pass`
- `block`
- `artifact_failed`
- `retry_required`
- `error`

- [ ] **Step 4: Document the quota rule**

In `docs/loop-engine/concilium-menu-bar-contract.md`, add:

```markdown
### Quota Exhaustion And Provisional Closure

Seat quota exhaustion is not the same as reviewer disagreement. Runtime summaries classify rate-limit, quota, usage-limit, and refresh-window failures as `quota_exhausted` and set `final_verdict: retry_required` unless the failed seat is not required for the current lane. The UI must not display this as PASS. It should display the passing seats and the exact retry seat, for example `kimi retry required after capacity refresh`.

If a seat previously raised a BLOCK in the same implementation closure sequence, a later quota failure by that same seat cannot close the sequence as PASS. The sequence remains `retry_required` until that seat passes or the user explicitly removes it from the required seat set.
```

- [ ] **Step 5: Run focused tests and docs diff**

Run:

```bash
python3 -m unittest \
  skills/loop-engine/tests/test_concilium_run_summary.py \
  skills/loop-engine/tests/test_concilium_runtime.py
git diff --check
```

Expected: tests pass and diff check has no output.

- [ ] **Step 6: Commit**

Run:

```bash
git add \
  skills/loop-engine/bin/concilium_run_summary.py \
  skills/loop-engine/bin/concilium_runtime.py \
  skills/loop-engine/tests/test_concilium_runtime.py \
  docs/loop-engine/concilium-menu-bar-contract.md
git commit -m "feat(concilium): classify quota failures as retry required"
```

## Task 4: Add Session Retention Scan And Prune Commands

**Files:**
- Create: `skills/loop-engine/bin/session_retention.py`
- Create: `skills/loop-engine/tests/test_session_retention.py`
- Modify: `roundtable`
- Modify: `skills/loop-engine/tests/test_roundtable_launcher.py`

- [ ] **Step 1: Write failing retention tests**

Create `skills/loop-engine/tests/test_session_retention.py`:

```python
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

            self.assertEqual(removed, [str(session)])
            self.assertFalse(session.exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify module import failure**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_session_retention.py
```

Expected: missing module failure.

- [ ] **Step 3: Implement session retention module**

Create `skills/loop-engine/bin/session_retention.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

SENSITIVE_PATTERNS = {
    ".codex/config.toml": re.compile(r"\.codex/config\.toml", re.I),
    ".env": re.compile(r"(^|[/\\])\.env(\.|$|[/\\])", re.I),
    "aws_env": re.compile(r"\bAWS_(ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN)\b"),
    "ssh_private_key": re.compile(r"-----BEGIN (OPENSSH|RSA|EC|DSA) PRIVATE KEY-----"),
    "api_key": re.compile(r"\b(api[_-]?key|token|secret|credential)\b\s*[:=]", re.I),
    "sk_token": re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
}


def _session_root(repo: str | Path) -> Path:
    return Path(repo).expanduser().resolve() / ".roundtable" / "sessions"


def _read_sample(session: Path) -> str:
    chunks = []
    for path in sorted(session.rglob("*")):
        if path.is_file() and path.suffix in {".md", ".txt", ".json", ".patch"}:
            try:
                chunks.append(path.read_text(encoding="utf-8", errors="replace")[:2000])
            except OSError:
                continue
    return "\n".join(chunks)[:20000]


def _indicators(text: str) -> list[str]:
    return [name for name, pattern in SENSITIVE_PATTERNS.items() if pattern.search(text)]


def scan_repo(repo: str | Path) -> dict:
    root = _session_root(repo)
    sessions = []
    if not root.is_dir():
        return {"repo": str(Path(repo).expanduser().resolve()), "sessions": []}
    for session in sorted(path for path in root.iterdir() if path.is_dir()):
        indicators = _indicators(_read_sample(session))
        sessions.append({
            "session": session.name,
            "path": str(session),
            "sensitivity": "sensitive_possible" if indicators else "normal",
            "indicators": indicators,
        })
    return {"repo": str(Path(repo).expanduser().resolve()), "sessions": sessions}


def prune_repo(repo: str | Path, *, yes: bool, sensitive_only: bool = False) -> list[str]:
    report = scan_repo(repo)
    removed = []
    for item in report["sessions"]:
        if sensitive_only and item["sensitivity"] != "sensitive_possible":
            continue
        path = Path(item["path"])
        if yes:
            shutil.rmtree(path)
            removed.append(str(path))
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan or prune Concilium .roundtable sessions.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--repo", default=".")
    prune = sub.add_parser("prune")
    prune.add_argument("--repo", default=".")
    prune.add_argument("--sensitive-only", action="store_true")
    prune.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "scan":
        print(json.dumps(scan_repo(args.repo), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    removed = prune_repo(args.repo, yes=bool(args.yes), sensitive_only=bool(args.sensitive_only))
    print(json.dumps({"removed": removed, "requires_yes": not bool(args.yes)}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add launcher subcommands**

In `roundtable`, add before the legacy block:

```bash
if [[ "${1:-}" == "sessions" ]]; then
  shift
  exec "${CONCILIUM_LAUNCHER_PYTHON:-python3}" "$SKILL/bin/session_retention.py" "$@"
fi
```

- [ ] **Step 5: Add launcher tests**

In `skills/loop-engine/tests/test_roundtable_launcher.py`, add:

```python
    def test_sessions_subcommand_dispatches_retention_tool(self):
        with tempfile.TemporaryDirectory() as td:
            fake_python = pathlib.Path(td) / "python"
            log = pathlib.Path(td) / "args.txt"
            fake_python.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$@\" > {log}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = dict(os.environ)
            env["CONCILIUM_LAUNCHER_PYTHON"] = str(fake_python)
            subprocess.run([str(ROUND_TABLE), "sessions", "scan", "--repo", td], env=env, check=True)

            args = log.read_text(encoding="utf-8")

        self.assertIn("session_retention.py", args)
        self.assertIn("scan", args)
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
python3 -m unittest \
  skills/loop-engine/tests/test_session_retention.py \
  skills/loop-engine/tests/test_roundtable_launcher.py
bash -n roundtable
```

Expected: tests pass and `bash -n` exits 0.

- [ ] **Step 7: Commit**

Run:

```bash
git add \
  roundtable \
  skills/loop-engine/bin/session_retention.py \
  skills/loop-engine/tests/test_session_retention.py \
  skills/loop-engine/tests/test_roundtable_launcher.py
git commit -m "feat(concilium): add session retention controls"
```

## Task 5: Make Human Reports Prefer The Canonical Summary

**Files:**
- Modify: `skills/loop-engine/bin/report-session.py`
- Modify: `skills/loop-engine/tests/test_report_session.py`
- Modify: `skills/loop-engine/client/menu_bar_view_model.py`
- Modify: `skills/loop-engine/tests/test_menu_bar_contract.py`

- [ ] **Step 1: Add failing report-session test**

In `skills/loop-engine/tests/test_report_session.py`, add:

```python
    def test_report_prefers_run_summary_when_present(self):
        with tempfile.TemporaryDirectory() as td:
            session = pathlib.Path(td) / "audit-1"
            (session / "KB").mkdir(parents=True)
            (session / "minutes").mkdir(parents=True)
            (session / "run-summary.json").write_text(
                json.dumps({
                    "schema_version": "concilium.run_summary.v1",
                    "final_verdict": "retry_required",
                    "launcher": {"commit": "abc"},
                    "seats": [{"seat": "kimi", "outcome": "quota_exhausted", "backend_type": "external_cli"}],
                    "budget_guard": {"status": "allowed"},
                }),
                encoding="utf-8",
            )

            report = report_session.build_report(session)

        self.assertIn("Final verdict: retry_required", report)
        self.assertIn("kimi", report)
        self.assertIn("quota_exhausted", report)
```

- [ ] **Step 2: Modify report builder**

In `skills/loop-engine/bin/report-session.py`, add:

```python
def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(read(path))
    except json.JSONDecodeError:
        return {}
```

Then in `build_report`, load:

```python
    run_summary = load_json(session / "run-summary.json")
```

Add after the Session lines:

```python
        f"- Final verdict: {run_summary.get('final_verdict', 'unknown') if run_summary else 'unknown'}",
        f"- Budget Guard: {run_summary.get('budget_guard', {}).get('status', 'unknown') if run_summary else 'unknown'}",
```

Add a seat table from `run_summary["seats"]` when present:

```python
    if run_summary.get("seats"):
        lines += [
            "",
            "## Run Summary Seats",
            "| Seat | Outcome | Backend |",
            "|---|---|---|",
        ]
        for seat in run_summary["seats"]:
            lines.append(f"| {seat.get('seat', '')} | {seat.get('outcome', '')} | {seat.get('backend_type', '')} |")
```

- [ ] **Step 3: Add menu-bar model test**

In `skills/loop-engine/tests/test_menu_bar_contract.py`, add:

```python
    def test_view_model_exposes_run_summary_final_verdict(self):
        model = menu_bar_view_model.build_popover_model(
            status={"state": "idle"},
            effective_config={},
            preflight={
                "route": {"lane": "audit"},
                "guard": {"status": "allowed"},
                "run_summary": {"final_verdict": "retry_required", "retry_required_seats": ["kimi"]},
            },
            events=[],
        )

        self.assertEqual(model["execution_snapshot"]["final_verdict"], "retry_required")
        self.assertEqual(model["execution_snapshot"]["retry_required_seats"], ["kimi"])
```

- [ ] **Step 4: Implement menu-bar pass-through**

In `skills/loop-engine/client/menu_bar_view_model.py`, inside `build_popover_model`, read:

```python
    run_summary = _dict(preflight.get("run_summary"))
```

Add to `execution_snapshot`:

```python
            "final_verdict": run_summary.get("final_verdict", ""),
            "retry_required_seats": list(run_summary.get("retry_required_seats") or []),
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
python3 -m unittest \
  skills/loop-engine/tests/test_report_session.py \
  skills/loop-engine/tests/test_menu_bar_contract.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add \
  skills/loop-engine/bin/report-session.py \
  skills/loop-engine/tests/test_report_session.py \
  skills/loop-engine/client/menu_bar_view_model.py \
  skills/loop-engine/tests/test_menu_bar_contract.py
git commit -m "feat(concilium): surface canonical run summaries"
```

## Task 6: Document The Dogfood Closure Protocol

**Files:**
- Create: `docs/loop-engine/dogfood-closure-hardening-2026-07-02.md`
- Modify: `docs/loop-engine/concilium-menu-bar-contract.md`

- [ ] **Step 1: Create dogfood closure doc**

Create `docs/loop-engine/dogfood-closure-hardening-2026-07-02.md`:

```markdown
# Concilium Dogfood Closure Hardening - 2026-07-02

## First-Principles Rule

A Concilium run is not complete because a markdown report exists. It is complete when the default launcher version is known, required seats are accounted for, Budget Guard state is recorded, artifact gate state is recorded, and `run-summary.json` gives a machine-readable final verdict.

## Closure States

| final_verdict | Meaning | User Action |
| --- | --- | --- |
| pass | Required seats passed and gates passed. | Safe to treat as closed. |
| block | At least one required reviewer returned BLOCK. | Fix and rerun. |
| retry_required | A required seat failed for quota, timeout, or technical error. | Rerun after capacity refresh or explicitly change required seats. |
| artifact_failed | Output or write-boundary requirements failed. | Fix artifact path/scope and rerun. |
| error | Runtime failed outside normal review semantics. | Debug runtime. |

## Dogfood Lessons Applied

- FBA reached stable PASS with native `claude`, `hermes`, and `kimi` seats.
- Agent-search showed why a final Kimi quota ERR must not be collapsed into either PASS or BLOCK.
- Both dogfood runs showed that human reports are not enough for Phase 5 UI; `run-summary.json` is the UI source of truth.
- Session retention must be explicit because `.roundtable/sessions` can preserve sensitive context.
```

- [ ] **Step 2: Add a contract pointer**

In `docs/loop-engine/concilium-menu-bar-contract.md`, add:

```markdown
The menu-bar product should treat `run-summary.json` as the durable status source for completed runs. Runtime events are the live stream; `run-summary.json` is the settled ledger.
```

- [ ] **Step 3: Commit**

Run:

```bash
git add docs/loop-engine/dogfood-closure-hardening-2026-07-02.md docs/loop-engine/concilium-menu-bar-contract.md
git commit -m "docs(concilium): define dogfood closure protocol"
```

## Task 7: Full Verification And Dogfood Recheck

**Files:**
- No new files unless verification produces intentionally retained reports.

- [ ] **Step 1: Run full local verification**

Run:

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
bash -n roundtable
bash -n skills/loop-engine/bin/smoke-concilium-phase3.sh
bash -n skills/loop-engine/bin/smoke-concilium-phase4.sh
python3 -m py_compile \
  skills/loop-engine/bin/concilium_runtime.py \
  skills/loop-engine/bin/concilium_lanes.py \
  skills/loop-engine/bin/concilium_run_summary.py \
  skills/loop-engine/bin/session_retention.py \
  skills/loop-engine/bin/report-session.py \
  skills/loop-engine/web/server.py
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 2: Run preview smoke on default launcher**

Run:

```bash
python3 skills/loop-engine/bin/concilium-run.py \
  --repo /Users/melee/Documents/agents \
  --task "Preview a low-risk docs cleanup without editing files." \
  --mode preview \
  --signals-json '{"risk":"low","file_count":1,"security_sensitive":false,"ambiguous":false}' \
  | python3 -m json.tool
```

Expected:

```text
lane: fast
guard.status: allowed
run_summary.final_verdict: pass or empty-preview-safe status with no seat dispatch
```

- [ ] **Step 3: Run read-only plan review of this implementation branch**

Run:

```bash
python3 skills/loop-engine/bin/concilium-run.py \
  --repo /Users/melee/Documents/agents \
  --task "Read-only adversarial audit of Concilium dogfood closure hardening. Verify run-summary contract, quota retry semantics, session retention controls, launcher version parity, and that no UI code reimplements routing or Budget Guard. Do not modify files. BLOCK only for concrete HIGH/CRITICAL regressions." \
  --live --yes --timeout 1200 --seats claude,hermes,kimi \
  --test-cmd "python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'" \
  --signals-json '{"read_only":true,"risk":"high","file_count":40,"security_sensitive":false,"ambiguous":true,"allowed_write_paths":[],"required_artifact_paths":[]}'
```

Expected:

- If all seats pass: `returncode=0`, `final_verdict=pass`.
- If Kimi returns `429` quota exhaustion while Claude and Hermes pass: `final_verdict=retry_required`, not PASS and not BLOCK. Wait for Kimi capacity refresh or rerun with an explicit user-approved reduced seat set.
- If any seat returns BLOCK for a concrete HIGH/CRITICAL issue: fix the issue and rerun this step.

- [ ] **Step 4: Run session retention scan**

Run:

```bash
python3 skills/loop-engine/bin/session_retention.py scan --repo /Users/melee/Documents/agents | python3 -m json.tool
```

Expected: JSON report with sessions and sensitivity indicators. No secret values printed.

- [ ] **Step 5: Commit verification notes only if a new retained report is intentionally created**

If a new retained report is written under `docs/audits/`, commit it:

```bash
git add docs/audits/<new-report>.md
git commit -m "docs(concilium): record dogfood closure hardening verification"
```

## Self-Review Checklist

- Spec coverage:
  - Default launcher drift: Task 0.
  - Run evidence and UI source of truth: Tasks 1, 2, 5, 6.
  - Kimi quota / seat ERR semantics: Task 3 and Task 7.
  - Sensitive `.roundtable` retention: Task 4 and Task 7.
  - Phase 5 menu-bar readiness: Tasks 5 and 6.
- Placeholder scan:
  - No task contains unresolved placeholders.
  - All tests include concrete assertions.
  - All commands include expected outcomes.
- Type consistency:
- `run_summary.final_verdict` is the durable verdict field.
- `retry_required_seats` and `blocking_seats` are lists of seat names.
- `session_path` is an absolute path returned by lane executors.
- `budget_guard` is the summary field derived from runtime `guard`.
- `rc=2` or `verdict=BLOCK` always wins over quota-text matching.
- Roundtable lane summaries derive legacy seat rows from `roundtable_state` when `seat_results` is absent and collapse multi-round verdicts to the latest iter per seat/mode.
