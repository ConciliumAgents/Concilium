# Concilium Phase 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the routed live control plane that makes Concilium preview, guard, and run the exact same lane decision across CLI, WebUI Debug Console, and the future menu bar client.

**Architecture:** Keep routing, capacity, guard policy, execution, and event emission in framework-neutral Python modules under `skills/loop-engine/bin`. The web service becomes a thin localhost API over the runtime adapter, while the menu bar work is limited to a client contract and pure view-model fixtures. WebUI remains a debug console, not the final product surface.

**Tech Stack:** Python standard library, existing Loop Engine shell seat scripts, existing `unittest` suite, standard-library HTTP/SSE service in `skills/loop-engine/web/server.py`, no new runtime dependencies.

---

## First Principles

1. **Truth before polish.** The user must be able to trust that a shown route is the route that runs, even if the UI is still rough.
2. **Routing is a contract.** Preflight and run must share the same normalized request, config overlay, capacity records, route, and guard decision, or the run must stop and explain why it changed.
3. **Budget Guard is server-side.** Frontend button state is only presentation. Live agent calls are gated in Python before any seat process starts.
4. **Mode names must be literal.** `preview` means route and preflight only, `stub_run` means event stream without live model calls, and `live_run` means agent calls may happen after guard approval.
5. **UI code stays thin.** WebUI and future menu bar clients request status, preflight, run, events, and effective config; they do not reimplement routing, capacity policy, maker-checker review, or conductor behavior.
6. **Local-first, no secret writes.** Phase 4 may read local status and write explicit Concilium artifacts, but must not write global Claude, Codex, Kimi, Hermes, CodexBar, or provider config.

## Implementation Choices

- **Menu bar token handoff:** keep the existing in-memory `X-Loop-Token` behavior and add an explicit `--token-file PATH` server option. The service writes `{"base_url": "...", "token": "...", "created_at": "..."}` with file mode `0600` only when the flag is supplied.
- **Fast Lane context:** initialize the existing `.roundtable` session and KB before live Fast Lane execution so current `seat-*.sh` preambles keep working. The session name uses `fast-<slug>` and the participant list contains only the selected Fast Lane seat.
- **Process cleanup:** add one shared process helper using `subprocess.Popen(..., start_new_session=True)` and `os.killpg` on timeout. Fast Lane, Review Lane command calls, and future Roundtable wrappers use this helper where they start subprocesses directly.
- **Config writes:** defer `/api/config/user` and `/api/config/project` write endpoints to Phase 5. Phase 4 implements effective config read/preview and a `saveConfig` client contract method that returns an explicit `not_implemented` response.

## File Structure

- Create `skills/loop-engine/bin/concilium_runtime.py`
  - Owns request normalization, request overlay, decision fingerprinting, preflight build, guard invocation, selected-lane execution, final result shape, and adapter-level events.
- Create `skills/loop-engine/bin/budget_guard.py`
  - Pure Budget Guard state machine for `ok`, `soft_limited`, `unknown`, stale `hard_exhausted`, fresh `hard_exhausted`, `unavailable`, and missing required seat records.
- Create `skills/loop-engine/bin/concilium_events.py`
  - Small event sink abstraction with list and queue sinks, event redaction, and guaranteed `done` terminal event helpers.
- Create `skills/loop-engine/bin/process_runner.py`
  - Timeout-bounded process-group runner shared by Fast and Review lane process calls.
- Create `skills/loop-engine/bin/concilium_lanes.py`
  - Moves lane execution helpers out of `concilium-run.py`: capacity collection, Fast Lane live execution, Review Lane live execution, Roundtable live execution, and verify command execution.
- Modify `skills/loop-engine/bin/concilium-run.py`
  - Becomes a CLI wrapper over `concilium_runtime.run_concilium_adapter`.
- Modify `skills/loop-engine/bin/review-lane.py`
  - Uses `process_runner.run_process_group` for direct subprocess calls.
- Modify `skills/loop-engine/web/server.py`
  - Uses runtime adapter for `/api/preflight` and `/api/run`; adds `/api/status`, `/api/config/effective`, and explicit `--token-file`.
- Modify `skills/loop-engine/web/index.html`
  - Relabels browser surface as Concilium Debug Console and displays route, guard, effective config, and stable event stream fields.
- Create `skills/loop-engine/client/concilium_client.py`
  - Framework-neutral client contract for `status`, `preflight`, `run`, `events`, `effective_config`, and `save_config`.
- Create `skills/loop-engine/client/menu_bar_view_model.py`
  - Pure function that turns service status, route/preflight, capacity, guard, config, and events into the future menu bar popover model.
- Create `skills/loop-engine/tests/test_concilium_runtime.py`
- Create `skills/loop-engine/tests/test_budget_guard.py`
- Create `skills/loop-engine/tests/test_concilium_events.py`
- Create `skills/loop-engine/tests/test_process_runner.py`
- Create `skills/loop-engine/tests/test_web_runtime_adapter.py`
- Create `skills/loop-engine/tests/test_menu_bar_contract.py`
- Create `skills/loop-engine/tests/fixtures/menu_bar/blocked_review.json`
- Create `skills/loop-engine/tests/fixtures/menu_bar/active_fast.json`
- Create `docs/loop-engine/concilium-menu-bar-contract.md`
- Create `docs/loop-engine/phase4-closeout-2026-06-29.md`
- Create `skills/loop-engine/bin/smoke-concilium-phase4.sh`

## Success Criteria

- `POST /api/preflight` and `POST /api/run` use the same runtime adapter.
- `POST /api/run` never calls `conductor.run()` directly.
- A run uses the same lane as its accepted preflight fingerprint, or it blocks with `decision_changed`.
- `preview`, `stub_run`, and `live_run` are distinct and covered by tests.
- Live run blocks unavailable, fresh hard-exhausted, unresolved required seats, and stale mismatched confirmations before seat calls.
- Live run requires explicit per-run confirmation for unknown or soft-limited required seats.
- Fast, Review, and Roundtable adapter paths emit `start`, `preflight`, `guard`, `finish`, and `done`; live or stub seat work emits `seat`; verification emits `verify`; review emits `verdict`.
- WebUI is labeled as Debug Console and displays runtime adapter fields without owning routing logic.
- Menu bar contract and view-model fixtures exist without choosing SwiftUI, AppKit, Electron, Tauri, or any native framework.
- Effective config can be read for a repo through service and client contract.
- No Phase 4 action writes global provider config without an explicit user command.
- Tiny live Fast smoke is completed with redacted evidence, or skipped with a guard-produced block reason.

## Spec Coverage Map

- **G1 Runtime Adapter:** Tasks 1, 2, 3, and 4 create request normalization, request overlay, Budget Guard, event sinks, lane execution, timeout cleanup, and final result shape.
- **G2 Route-Run Consistency:** Tasks 1, 4, and 5 use the same normalized request and fingerprint for CLI preview, service preflight, and service run.
- **G3 Budget Guard:** Task 2 implements pure guard policy; Tasks 4 and 5 enforce it before live lane execution.
- **G4 Local Service Contract:** Task 5 implements `/api/status`, `/api/preflight`, `/api/run`, `/api/events`, and `/api/config/effective`.
- **G5 Menu Bar Contract:** Task 6 creates `ConciliumClient`, view-model fixtures, and the menu bar contract doc without selecting a native framework.
- **G6 Tiny Live Smoke:** Task 7 gates one disposable Fast Lane live smoke and records either redacted evidence or the guard block reason.

---

### Task 1: Runtime Request Contract

**Files:**
- Create: `skills/loop-engine/bin/concilium_runtime.py`
- Test: `skills/loop-engine/tests/test_concilium_runtime.py`

- [ ] **Step 1: Write failing tests for normalization and overlay precedence**

Create `skills/loop-engine/tests/test_concilium_runtime.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest

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

    def test_request_overlay_does_not_mutate_base_config(self):
        request = concilium_runtime.normalize_request({
            "repo": ".",
            "task": "Change routing.",
            "mode": "live_run",
            "seats": ["claude", "codex"],
            "seat_models": {"codex": "gpt-5-codex-high"},
            "fast_agent": "codex",
            "review_executor": "codex",
            "review_reviewer": "claude",
            "commander": "codex",
            "reviewer": "claude",
            "max_iters": 2,
            "timeout": 77,
        })

        effective = concilium_runtime.apply_request_overlay(BASE_CONFIG, request)

        self.assertEqual(BASE_CONFIG["lanes"]["fast"]["default_single_agent"], "kimi")
        self.assertEqual(effective["lanes"]["fast"]["default_single_agent"], "codex")
        self.assertEqual(effective["lanes"]["review"]["default_review_executor"], "codex")
        self.assertEqual(effective["lanes"]["review"]["default_review_reviewer"], "claude")
        self.assertEqual(effective["lanes"]["roundtable"]["commander"], "codex")
        self.assertEqual(effective["lanes"]["roundtable"]["reviewer"], "claude")
        self.assertEqual(effective["lanes"]["roundtable"]["seats"], ["claude", "codex"])
        self.assertEqual(effective["lanes"]["roundtable"]["max_iters"], 2)
        self.assertEqual(effective["seat_models"]["codex"], "gpt-5-codex-high")

    def test_fingerprint_changes_when_decision_input_changes(self):
        with tempfile.TemporaryDirectory() as td:
            base = concilium_runtime.normalize_request({"repo": td, "task": "Fix docs.", "mode": "stub_run"})
            changed = concilium_runtime.normalize_request({"repo": td, "task": "Fix docs.", "mode": "live_run"})

        self.assertNotEqual(
            concilium_runtime.request_fingerprint(base),
            concilium_runtime.request_fingerprint(changed),
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_concilium_runtime
```

Expected: FAIL with `FileNotFoundError` or import failure because `concilium_runtime.py` does not exist.

- [ ] **Step 3: Implement request normalization and overlay**

Create `skills/loop-engine/bin/concilium_runtime.py` with these public functions:

```python
#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

MODES = {"preview", "stub_run", "live_run"}
INTENTS = {"task", "tiny_smoke"}
FINGERPRINT_KEYS = (
    "repo",
    "task",
    "test_cmd",
    "mode",
    "timeout",
    "intent",
    "signals",
    "overlay",
)


def _bool(value: object) -> bool:
    return bool(value) and str(value).lower() not in {"0", "false", "no", "off"}


def normalize_request(params: dict) -> dict:
    repo = Path(params.get("repo") or ".").expanduser().resolve()
    task = str(params.get("task") or "").strip()
    if not task:
        raise ValueError("task is required")

    mode = str(params.get("mode") or "").strip()
    if not mode:
        mode = "preview" if _bool(params.get("dry_run")) or not _bool(params.get("live")) else "live_run"
    if mode not in MODES:
        raise ValueError(f"unknown execution mode: {mode}")

    intent = str(params.get("intent") or "task").strip()
    if intent not in INTENTS:
        raise ValueError(f"unknown intent: {intent}")

    overlay = {
        "seats": list(params.get("seats") or []),
        "seat_models": dict(params.get("seat_models") or {}),
        "fast_agent": str(params.get("fast_agent") or "").strip(),
        "review_executor": str(params.get("review_executor") or "").strip(),
        "review_reviewer": str(params.get("review_reviewer") or "").strip(),
        "commander": str(params.get("commander") or "").strip(),
        "reviewer": str(params.get("reviewer") or "").strip(),
        "max_iters": params.get("max_iters"),
    }

    timeout = int(params.get("timeout") or params.get("seat_timeout") or 300)
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    return {
        "repo": str(repo),
        "task": task,
        "test_cmd": str(params.get("test_cmd") or ""),
        "mode": mode,
        "timeout": timeout,
        "intent": intent,
        "signals": dict(params.get("signals") or {}),
        "overlay": overlay,
    }


def apply_request_overlay(config: dict, request: dict) -> dict:
    effective = copy.deepcopy(config)
    lanes = effective.setdefault("lanes", {})
    fast = lanes.setdefault("fast", {})
    review = lanes.setdefault("review", {})
    roundtable = lanes.setdefault("roundtable", {})
    overlay = request.get("overlay") or {}

    if overlay.get("fast_agent"):
        fast["default_single_agent"] = overlay["fast_agent"]
    if overlay.get("review_executor"):
        review["default_review_executor"] = overlay["review_executor"]
    if overlay.get("review_reviewer"):
        review["default_review_reviewer"] = overlay["review_reviewer"]
    if overlay.get("commander"):
        roundtable["commander"] = overlay["commander"]
    if overlay.get("reviewer"):
        roundtable["reviewer"] = overlay["reviewer"]
    if overlay.get("seats"):
        roundtable["seats"] = list(overlay["seats"])
    if overlay.get("max_iters") is not None:
        roundtable["max_iters"] = int(overlay["max_iters"])
    if overlay.get("seat_models"):
        seat_models = effective.setdefault("seat_models", {})
        seat_models.update(dict(overlay["seat_models"]))

    return effective


def request_fingerprint(request: dict) -> str:
    payload = {key: request.get(key) for key in FINGERPRINT_KEYS}
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Verify Task 1 passes**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_concilium_runtime
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add skills/loop-engine/bin/concilium_runtime.py skills/loop-engine/tests/test_concilium_runtime.py
git commit -m "feat(concilium): add runtime request contract"
```

---

### Task 2: Budget Guard State Machine

**Files:**
- Create: `skills/loop-engine/bin/budget_guard.py`
- Modify: `skills/loop-engine/bin/concilium_runtime.py`
- Test: `skills/loop-engine/tests/test_budget_guard.py`

- [ ] **Step 1: Write failing guard policy tests**

Create `skills/loop-engine/tests/test_budget_guard.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import datetime
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "budget_guard.py"
spec = importlib.util.spec_from_file_location("budget_guard", MODULE)
budget_guard = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(budget_guard)


def record(seat: str, status: str, *, checked_at: str = "2026-06-29T00:00:00Z", stale_after: int = 300) -> dict:
    return {
        "seat": seat,
        "provider": "local",
        "model": seat,
        "status": status,
        "source": "fixture",
        "reason": status,
        "checked_at": checked_at,
        "reset_at": "",
        "stale_after_seconds": stale_after,
        "blocking": status in {"hard_exhausted", "unavailable"},
    }


BASE_PREVIEW = {
    "request_fingerprint": "abc123",
    "route": {"lane": "review", "reason": "medium task", "required_seats": ["kimi", "hermes"]},
    "preflight": {"status": "ok", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": []},
    "capacity": [record("kimi", "ok"), record("hermes", "ok")],
}


class BudgetGuardTests(unittest.TestCase):
    def test_preview_allows_without_confirmation(self):
        result = budget_guard.evaluate_budget_guard(BASE_PREVIEW, mode="preview")

        self.assertEqual(result["status"], "allowed")
        self.assertFalse(result["requires_confirmation"])

    def test_live_unknown_requires_per_run_confirmation(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "unknown")]
        preview["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": ["hermes unknown"]}

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertEqual(result["status"], "confirmation_required")
        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(result["confirmation_payload"]["selected_lane"], "review")
        self.assertEqual(result["confirmation_payload"]["request_fingerprint"], "abc123")

    def test_matching_confirmation_allows_warn_live_run(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "soft_limited")]
        preview["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": ["hermes soft"]}

        required = budget_guard.evaluate_budget_guard(preview, mode="live_run")
        confirmed = budget_guard.evaluate_budget_guard(
            preview,
            mode="live_run",
            confirmation={"accepted": True, "request_fingerprint": required["confirmation_payload"]["request_fingerprint"]},
        )

        self.assertEqual(confirmed["status"], "allowed")

    def test_mismatched_confirmation_blocks(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "unknown")]
        preview["preflight"] = {"status": "warn", "required_seats": ["kimi", "hermes"], "blocking_seats": [], "warnings": ["hermes unknown"]}

        result = budget_guard.evaluate_budget_guard(
            preview,
            mode="live_run",
            confirmation={"accepted": True, "request_fingerprint": "old"},
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "confirmation does not match current preflight")

    def test_fresh_hard_exhausted_blocks(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok"), record("hermes", "hard_exhausted")]
        preview["preflight"] = {"status": "blocked", "required_seats": ["kimi", "hermes"], "blocking_seats": ["hermes"], "warnings": []}

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertEqual(result["status"], "blocked")
        self.assertIn("hermes", result["blocking_seats"])

    def test_stale_hard_exhausted_tiny_smoke_requires_confirmation(self):
        old = "2026-06-28T00:00:00Z"
        preview = dict(BASE_PREVIEW)
        preview["request"] = {"intent": "tiny_smoke"}
        preview["capacity"] = [record("kimi", "hard_exhausted", checked_at=old, stale_after=10)]
        preview["route"] = {"lane": "fast", "reason": "tiny smoke", "required_seats": ["kimi"]}
        preview["preflight"] = {"status": "blocked", "required_seats": ["kimi"], "blocking_seats": ["kimi"], "warnings": []}

        result = budget_guard.evaluate_budget_guard(
            preview,
            mode="live_run",
            now=datetime.datetime(2026, 6, 29, tzinfo=datetime.UTC),
        )

        self.assertEqual(result["status"], "confirmation_required")
        self.assertIn("stale hard_exhausted", result["reason"])

    def test_missing_required_seat_blocks_as_unresolved(self):
        preview = dict(BASE_PREVIEW)
        preview["capacity"] = [record("kimi", "ok")]
        preview["preflight"] = {"status": "blocked", "required_seats": ["kimi", "hermes"], "blocking_seats": ["hermes"], "warnings": []}

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertEqual(result["status"], "blocked")
        self.assertIn("hermes", result["unresolved_seats"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run guard tests to verify failure**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_budget_guard
```

Expected: FAIL because `budget_guard.py` does not exist.

- [ ] **Step 3: Implement guard functions**

Create `skills/loop-engine/bin/budget_guard.py` with these public functions:

```python
#!/usr/bin/env python3
from __future__ import annotations

import datetime

BLOCKING_STATUSES = {"unavailable"}
FRESH_HARD_BLOCKING = {"hard_exhausted"}
WARNING_STATUSES = {"unknown", "soft_limited"}


def _parse_time(value: str) -> datetime.datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


def is_stale(record: dict, now: datetime.datetime | None = None) -> bool:
    checked = _parse_time(str(record.get("checked_at", "")))
    if checked is None:
        return True
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=datetime.UTC)
    current = now or datetime.datetime.now(datetime.UTC)
    stale_after = int(record.get("stale_after_seconds") or 0)
    return stale_after > 0 and (current - checked).total_seconds() > stale_after


def _required_records(preview: dict) -> tuple[list[str], dict[str, dict]]:
    required = list(preview.get("route", {}).get("required_seats") or preview.get("preflight", {}).get("required_seats") or [])
    by_seat = {str(item.get("seat", "")): item for item in preview.get("capacity", [])}
    return required, by_seat


def confirmation_payload(preview: dict) -> dict:
    route = preview.get("route", {})
    required, by_seat = _required_records(preview)
    return {
        "request_fingerprint": preview.get("request_fingerprint", ""),
        "selected_lane": route.get("lane", ""),
        "routing_reason": route.get("reason", ""),
        "required_seats": required,
        "seats": [
            {
                "seat": seat,
                "provider": by_seat.get(seat, {}).get("provider", ""),
                "model": by_seat.get(seat, {}).get("model", ""),
                "capacity_status": by_seat.get(seat, {}).get("status", "unresolved"),
                "capacity_source": by_seat.get(seat, {}).get("source", ""),
                "reason": by_seat.get(seat, {}).get("reason", "seat unresolved"),
                "checked_at": by_seat.get(seat, {}).get("checked_at", ""),
                "reset_at": by_seat.get(seat, {}).get("reset_at", ""),
            }
            for seat in required
        ],
        "expected_max_agent_calls": preview.get("expected_max_agent_calls", 0),
        "files_may_be_modified": preview.get("mode") == "live_run",
        "global_config_may_be_touched": False,
    }


def _confirmation_matches(preview: dict, confirmation: dict | None) -> bool:
    return bool(confirmation and confirmation.get("accepted") is True and confirmation.get("request_fingerprint") == preview.get("request_fingerprint"))


def evaluate_budget_guard(
    preview: dict,
    mode: str,
    confirmation: dict | None = None,
    now: datetime.datetime | None = None,
) -> dict:
    required, by_seat = _required_records(preview)
    unresolved = [seat for seat in required if seat not in by_seat]
    hard_blocked: list[str] = []
    warnings: list[str] = []

    for seat in required:
        record = by_seat.get(seat)
        if record is None:
            continue
        status = str(record.get("status", "unknown"))
        if status in BLOCKING_STATUSES:
            hard_blocked.append(seat)
        elif status in FRESH_HARD_BLOCKING:
            if is_stale(record, now) and preview.get("request", {}).get("intent") == "tiny_smoke":
                warnings.append(f"{seat} stale hard_exhausted treated as unknown for tiny smoke")
            else:
                hard_blocked.append(seat)
        elif status in WARNING_STATUSES:
            warnings.append(f"{seat} {status}")

    payload = confirmation_payload(preview)
    if unresolved or hard_blocked:
        return {
            "status": "blocked",
            "requires_confirmation": False,
            "reason": "seat unresolved or blocked",
            "blocking_seats": hard_blocked,
            "unresolved_seats": unresolved,
            "warnings": warnings,
            "confirmation_payload": payload,
        }

    if mode != "live_run":
        return {
            "status": "allowed",
            "requires_confirmation": False,
            "reason": f"{mode} does not call live agents",
            "blocking_seats": [],
            "unresolved_seats": [],
            "warnings": warnings,
            "confirmation_payload": payload,
        }

    if warnings:
        if _confirmation_matches(preview, confirmation):
            return {
                "status": "allowed",
                "requires_confirmation": False,
                "reason": "warning confirmed for this preflight",
                "blocking_seats": [],
                "unresolved_seats": [],
                "warnings": warnings,
                "confirmation_payload": payload,
            }
        if confirmation:
            return {
                "status": "blocked",
                "requires_confirmation": False,
                "reason": "confirmation does not match current preflight",
                "blocking_seats": [],
                "unresolved_seats": [],
                "warnings": warnings,
                "confirmation_payload": payload,
            }
        return {
            "status": "confirmation_required",
            "requires_confirmation": True,
            "reason": "; ".join(warnings),
            "blocking_seats": [],
            "unresolved_seats": [],
            "warnings": warnings,
            "confirmation_payload": payload,
        }

    return {
        "status": "allowed",
        "requires_confirmation": False,
        "reason": "all required seats fresh enough",
        "blocking_seats": [],
        "unresolved_seats": [],
        "warnings": [],
        "confirmation_payload": payload,
    }
```

- [ ] **Step 4: Add runtime import shim**

Append to `skills/loop-engine/bin/concilium_runtime.py`:

```python
def attach_guard(preview: dict, confirmation: dict | None = None) -> dict:
    import budget_guard

    guard = budget_guard.evaluate_budget_guard(preview, mode=preview.get("mode", "preview"), confirmation=confirmation)
    result = dict(preview)
    result["guard"] = guard
    return result
```

- [ ] **Step 5: Verify Task 2**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_budget_guard
python3 -m unittest skills.loop-engine.tests.test_concilium_runtime
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add skills/loop-engine/bin/budget_guard.py skills/loop-engine/bin/concilium_runtime.py skills/loop-engine/tests/test_budget_guard.py
git commit -m "feat(concilium): add server-side budget guard"
```

---

### Task 3: Events And Process Cleanup

**Files:**
- Create: `skills/loop-engine/bin/concilium_events.py`
- Create: `skills/loop-engine/bin/process_runner.py`
- Modify: `skills/loop-engine/bin/review-lane.py`
- Test: `skills/loop-engine/tests/test_concilium_events.py`
- Test: `skills/loop-engine/tests/test_process_runner.py`

- [ ] **Step 1: Write failing tests for terminal events**

Create `skills/loop-engine/tests/test_concilium_events.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium_events.py"
spec = importlib.util.spec_from_file_location("concilium_events", MODULE)
concilium_events = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(concilium_events)


class ConciliumEventsTests(unittest.TestCase):
    def test_list_sink_redacts_secret_text(self):
        sink = concilium_events.ListEventSink()
        sink.emit("seat", agent="kimi", text="token sk-secret123")

        self.assertEqual(sink.events[0]["type"], "seat")
        self.assertNotIn("sk-secret123", str(sink.events[0]))

    def test_done_is_emitted_once(self):
        sink = concilium_events.ListEventSink()
        concilium_events.emit_done(sink, rc=0)
        concilium_events.emit_done(sink, rc=1)

        done = [event for event in sink.events if event["type"] == "done"]
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["rc"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Write failing process timeout test**

Create `skills/loop-engine/tests/test_process_runner.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "process_runner.py"
spec = importlib.util.spec_from_file_location("process_runner", MODULE)
process_runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(process_runner)


class ProcessRunnerTests(unittest.TestCase):
    def test_timeout_returns_124_and_marks_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            result = process_runner.run_process_group(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                cwd=pathlib.Path(td),
                env={},
                timeout=1,
            )

        self.assertEqual(result["returncode"], 124)
        self.assertTrue(result["timed_out"])
        self.assertIn("timeout after 1s", result["output"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run new tests to verify failure**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_concilium_events skills.loop-engine.tests.test_process_runner
```

Expected: FAIL because the new modules do not exist.

- [ ] **Step 4: Implement event sinks**

Create `skills/loop-engine/bin/concilium_events.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import queue
from typing import Any

import capacity_status


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return capacity_status.redact(value)
    return value


class ListEventSink:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.done_emitted = False

    def emit(self, event_type: str, **fields) -> None:
        if event_type == "done" and self.done_emitted:
            return
        if event_type == "done":
            self.done_emitted = True
        event = {"type": event_type}
        event.update(fields)
        self.events.append(_redact(event))


class QueueEventSink:
    def __init__(self, q: "queue.Queue") -> None:
        self.q = q
        self.done_emitted = False

    def emit(self, event_type: str, **fields) -> None:
        if event_type == "done" and self.done_emitted:
            return
        if event_type == "done":
            self.done_emitted = True
        event = {"type": event_type}
        event.update(fields)
        self.q.put(_redact(event))


def emit_done(sink, rc: int) -> None:
    sink.emit("done", rc=rc)
```

- [ ] **Step 5: Implement process group runner**

Create `skills/loop-engine/bin/process_runner.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path


def run_process_group(
    args: list[str] | str,
    cwd: Path,
    env: dict,
    timeout: int,
    shell: bool = False,
) -> dict:
    started = time.monotonic()
    proc = subprocess.Popen(
        args,
        cwd=str(cwd),
        env=env or None,
        shell=shell,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        output, _ = proc.communicate(timeout=timeout)
        return {
            "returncode": proc.returncode,
            "output": output or "",
            "timed_out": False,
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            output, _ = proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            output, _ = proc.communicate()
        text = output or ""
        return {
            "returncode": 124,
            "output": text + f"\n(timeout after {timeout}s)",
            "timed_out": True,
            "duration_seconds": round(time.monotonic() - started, 3),
        }
```

- [ ] **Step 6: Move Review Lane direct subprocess calls to process runner**

Modify `skills/loop-engine/bin/review-lane.py`:

```python
import process_runner  # noqa: E402
```

Replace `run_cmd` with:

```python
def run_cmd(args: list[str], cwd: Path, env: dict, timeout: int) -> tuple[int, str]:
    result = process_runner.run_process_group(args, cwd=cwd, env=env, timeout=timeout)
    return int(result["returncode"]), str(result["output"])
```

- [ ] **Step 7: Verify Task 3**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_concilium_events
python3 -m unittest skills.loop-engine.tests.test_process_runner
python3 -m unittest skills.loop-engine.tests.test_review_lane
```

Expected: PASS.

- [ ] **Step 8: Commit Task 3**

Run:

```bash
git add skills/loop-engine/bin/concilium_events.py skills/loop-engine/bin/process_runner.py skills/loop-engine/bin/review-lane.py skills/loop-engine/tests/test_concilium_events.py skills/loop-engine/tests/test_process_runner.py
git commit -m "feat(concilium): add event sinks and process cleanup"
```

---

### Task 4: Runtime Adapter And CLI Parity

**Files:**
- Create: `skills/loop-engine/bin/concilium_lanes.py`
- Modify: `skills/loop-engine/bin/concilium_runtime.py`
- Modify: `skills/loop-engine/bin/concilium-run.py`
- Modify: `skills/loop-engine/tests/test_concilium_run.py`
- Modify: `skills/loop-engine/tests/test_concilium_runtime.py`

- [ ] **Step 1: Add adapter tests for mode behavior and blocked calls**

Append to `skills/loop-engine/tests/test_concilium_runtime.py`:

```python
class ConciliumRuntimeAdapterTests(unittest.TestCase):
    def test_preview_builds_route_without_executor_call(self):
        called = {"count": 0}

        def executor(*args, **kwargs):
            called["count"] += 1
            return {"status": "ran", "returncode": 0}

        result = concilium_runtime.run_concilium_adapter(
            {"repo": ".", "task": "Fix typo.", "mode": "preview", "signals": {"risk": "low", "file_count": 1}},
            config=BASE_CONFIG,
            capacity=[
                {"seat": "kimi", "provider": "local", "model": "kimi", "status": "ok", "source": "fixture", "reason": "", "checked_at": "", "reset_at": "", "stale_after_seconds": 300, "blocking": False}
            ],
            lane_executor=executor,
        )

        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["route"]["lane"], "fast")
        self.assertEqual(called["count"], 0)

    def test_stub_run_emits_done_without_live_executor(self):
        sink = concilium_runtime.concilium_events.ListEventSink()
        result = concilium_runtime.run_concilium_adapter(
            {"repo": ".", "task": "Fix typo.", "mode": "stub_run", "signals": {"risk": "low", "file_count": 1}},
            config=BASE_CONFIG,
            capacity=[
                {"seat": "kimi", "provider": "local", "model": "kimi", "status": "ok", "source": "fixture", "reason": "", "checked_at": "", "reset_at": "", "stale_after_seconds": 300, "blocking": False}
            ],
            event_sink=sink,
        )

        self.assertEqual(result["status"], "stubbed")
        self.assertEqual(sink.events[-1]["type"], "done")
        self.assertEqual(sink.events[-1]["rc"], 0)

    def test_live_unknown_blocks_before_executor_without_confirmation(self):
        called = {"count": 0}

        def executor(*args, **kwargs):
            called["count"] += 1
            return {"status": "ran", "returncode": 0}

        result = concilium_runtime.run_concilium_adapter(
            {"repo": ".", "task": "Fix typo.", "mode": "live_run", "signals": {"risk": "low", "file_count": 1}},
            config=BASE_CONFIG,
            capacity=[
                {"seat": "kimi", "provider": "local", "model": "kimi", "status": "unknown", "source": "fixture", "reason": "quota source not checked", "checked_at": "", "reset_at": "", "stale_after_seconds": 300, "blocking": False}
            ],
            lane_executor=executor,
        )

        self.assertEqual(result["status"], "confirmation_required")
        self.assertEqual(called["count"], 0)
```

- [ ] **Step 2: Run adapter tests to verify failure**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_concilium_runtime
```

Expected: FAIL because `run_concilium_adapter` is not defined.

- [ ] **Step 3: Move lane helpers into `concilium_lanes.py`**

Create `skills/loop-engine/bin/concilium_lanes.py` by moving these functions from `concilium-run.py`:

```python
collect_capacity(repo: str | Path, config: dict) -> list[dict]
run_fast_lane(repo: str | Path, task: str, test_cmd: str, agent: str, timeout: int) -> dict
run_review_lane(repo: str | Path, task: str, test_cmd: str, config: dict, timeout: int) -> dict
run_roundtable_lane(repo: str | Path, task: str, test_cmd: str, config: dict, timeout: int, reporter=None) -> dict
```

Use `process_runner.run_process_group` in `run_fast_lane` and verify command execution:

```python
def _run_shell(cmd: str, cwd: Path, timeout: int) -> tuple[int, str]:
    if not cmd:
        return 0, ""
    result = process_runner.run_process_group(cmd, cwd=cwd, env=dict(os.environ), timeout=timeout, shell=True)
    return int(result["returncode"]), str(result["output"])
```

Before Fast Lane live execution, initialize the existing Loop session:

```python
def init_fast_session(repo: Path, task: str, test_cmd: str, agent: str, env: dict, timeout: int) -> str:
    session = f"fast-{_slug(task)}"
    env["LOOP_SESSION"] = session
    process_runner.run_process_group([str(BIN / "roundtable-init.sh"), str(repo), task], cwd=BIN, env=env, timeout=timeout)
    process_runner.run_process_group([str(BIN / "kb-refresh.sh"), str(repo), test_cmd], cwd=BIN, env=env, timeout=timeout)
    conductor.write_roster(str(repo), seats=[agent])
    return session
```

`run_roundtable_lane` must accept `reporter=None` and pass it to `conductor.run(..., reporter=reporter)`.

- [ ] **Step 4: Implement adapter orchestration**

Extend `skills/loop-engine/bin/concilium_runtime.py` with imports:

```python
import budget_guard
import concilium_config
import concilium_events
import concilium_lanes
import concilium_preflight
import lane_router
```

Add:

```python
def expected_max_agent_calls(route: dict, config: dict) -> int:
    lane = route.get("lane")
    if lane == "fast":
        return 1
    if lane == "review":
        repair_limit = int(config.get("lanes", {}).get("review", {}).get("review_repair_limit", 1))
        return 2 + repair_limit
    if lane == "roundtable":
        seats = route.get("required_seats") or config.get("lanes", {}).get("roundtable", {}).get("seats", [])
        max_iters = int(config.get("lanes", {}).get("roundtable", {}).get("max_iters", 5))
        return max(1, len(seats)) * max_iters
    return 0


def build_preflight(params: dict, config: dict | None = None, capacity: list[dict] | None = None) -> dict:
    request = normalize_request(params)
    effective = apply_request_overlay(config or concilium_config.load_config(request["repo"]), request)
    records = capacity if capacity is not None else concilium_lanes.collect_capacity(request["repo"], effective)
    signals = request["signals"] or lane_router.infer_task_signals(request["task"], request["repo"])
    route = lane_router.route_task(request["task"], signals, effective)
    preflight = concilium_preflight.evaluate_preflight(
        route["required_seats"],
        records,
        allow_auto_escalation=bool(effective.get("routing", {}).get("allow_auto_escalation", True)),
    )
    decision = lane_router.apply_preflight(route, preflight, effective)
    fingerprint = request_fingerprint({**request, "signals": signals})
    return {
        "status": "preview",
        "mode": request["mode"],
        "request": request,
        "request_fingerprint": fingerprint,
        "route": route,
        "decision": decision,
        "preflight": preflight,
        "capacity": records,
        "signals": signals,
        "expected_max_agent_calls": expected_max_agent_calls(route, effective),
    }


def _default_lane_executor(preview: dict, config: dict) -> dict:
    request = preview["request"]
    lane = preview["route"]["lane"]
    if lane == "fast":
        return concilium_lanes.run_fast_lane(
            request["repo"],
            request["task"],
            request["test_cmd"],
            preview["route"]["required_seats"][0],
            request["timeout"],
        )
    if lane == "review":
        return concilium_lanes.run_review_lane(request["repo"], request["task"], request["test_cmd"], config, request["timeout"])
    if lane == "roundtable":
        return concilium_lanes.run_roundtable_lane(request["repo"], request["task"], request["test_cmd"], config, request["timeout"])
    raise ValueError(f"unknown lane: {lane}")


def _emit_stub_events(sink, preview: dict) -> None:
    sink.emit("start", repo=preview["request"]["repo"], task=preview["request"]["task"], lane=preview["route"]["lane"], required_seats=preview["route"]["required_seats"])
    sink.emit("preflight", preflight=preview["preflight"])
    sink.emit("guard", guard=preview["guard"])
    for seat in preview["route"]["required_seats"]:
        sink.emit("seat", agent=seat, mode="stub", phase="done", rc=0)
    sink.emit("finish", status="stubbed", lane=preview["route"]["lane"])
    concilium_events.emit_done(sink, rc=0)


def run_concilium_adapter(
    params: dict,
    confirmation: dict | None = None,
    event_sink=None,
    config: dict | None = None,
    capacity: list[dict] | None = None,
    lane_executor=None,
) -> dict:
    request = normalize_request(params)
    effective = apply_request_overlay(config or concilium_config.load_config(request["repo"]), request)
    preview = build_preflight(request, config=effective, capacity=capacity)
    guard = budget_guard.evaluate_budget_guard(preview, mode=request["mode"], confirmation=confirmation)
    preview["guard"] = guard

    sink = event_sink or concilium_events.ListEventSink()
    if request["mode"] == "preview":
        return preview

    if guard["status"] != "allowed":
        sink.emit("start", repo=request["repo"], task=request["task"], lane=preview["route"]["lane"], required_seats=preview["route"]["required_seats"])
        sink.emit("preflight", preflight=preview["preflight"])
        sink.emit("guard", guard=guard)
        sink.emit("finish", status=guard["status"], lane=preview["route"]["lane"])
        concilium_events.emit_done(sink, rc=3)
        return {**preview, "status": guard["status"], "events": getattr(sink, "events", [])}

    if request["mode"] == "stub_run":
        _emit_stub_events(sink, preview)
        return {**preview, "status": "stubbed", "returncode": 0, "events": getattr(sink, "events", [])}

    sink.emit("start", repo=request["repo"], task=request["task"], lane=preview["route"]["lane"], required_seats=preview["route"]["required_seats"])
    sink.emit("preflight", preflight=preview["preflight"])
    sink.emit("guard", guard=guard)
    result = (lane_executor or _default_lane_executor)(preview, effective)
    rc = int(result.get("returncode", 0))
    if result.get("verify"):
        sink.emit("verify", verify=result["verify"])
    if result.get("verdict"):
        sink.emit("verdict", verdict=result["verdict"])
    sink.emit("finish", status=result.get("status", "ran"), lane=preview["route"]["lane"])
    concilium_events.emit_done(sink, rc=rc)
    result.update(preview)
    result["status"] = result.get("status", "ran")
    result["returncode"] = rc
    result["events"] = getattr(sink, "events", [])
    return result
```

- [ ] **Step 5: Refactor CLI wrapper**

Replace most of `skills/loop-engine/bin/concilium-run.py` with a thin CLI:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import concilium_runtime  # noqa: E402


def _exit_code(result: dict) -> int:
    if result.get("status") == "preview":
        return 0
    if result.get("status") in {"blocked", "confirmation_required"}:
        return 3
    rc = int(result.get("returncode", 0))
    return 0 if rc == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Concilium lane routing and execution.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--test-cmd", default="")
    parser.add_argument("--mode", choices=sorted(concilium_runtime.MODES), default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-route", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--signals-json", default="")
    parser.add_argument("--confirmation-json", default="")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)

    if args.live and args.dry_run:
        print("ValueError: --live and --dry-run cannot be combined", file=sys.stderr)
        return 4

    mode = args.mode
    if not mode:
        mode = "live_run" if args.live else "preview"
    signals = json.loads(args.signals_json) if args.signals_json else {}
    confirmation = json.loads(args.confirmation_json) if args.confirmation_json else None
    try:
        result = concilium_runtime.run_concilium_adapter({
            "repo": args.repo,
            "task": args.task,
            "test_cmd": args.test_cmd,
            "mode": mode,
            "dry_run": args.dry_run or args.print_route,
            "signals": signals,
            "timeout": args.timeout,
        }, confirmation=confirmation)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 4
    except Exception as e:
        print(json.dumps({"status": "error", "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return _exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Update existing Concilium run tests**

Modify `skills/loop-engine/tests/test_concilium_run.py` to patch `concilium_runtime.run_concilium_adapter` for CLI tests and move direct adapter behavior assertions into `test_concilium_runtime.py`.

Keep these two existing guarantees:

```python
def test_print_route_does_not_run_agents(self):
    ...

def test_blocked_preflight_stops_before_agent_call(self):
    ...
```

Expected assertions after the move:

```python
self.assertEqual(result["route"]["lane"], "fast")
self.assertEqual(result["status"], "preview")
fast.assert_not_called()

self.assertEqual(result["status"], "blocked")
review.assert_not_called()
```

- [ ] **Step 7: Verify Task 4**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_concilium_runtime
python3 -m unittest skills.loop-engine.tests.test_concilium_run
python3 -m unittest discover -s skills/loop-engine/tests
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

Run:

```bash
git add skills/loop-engine/bin/concilium_lanes.py skills/loop-engine/bin/concilium_runtime.py skills/loop-engine/bin/concilium-run.py skills/loop-engine/tests/test_concilium_runtime.py skills/loop-engine/tests/test_concilium_run.py
git commit -m "feat(concilium): route CLI through runtime adapter"
```

---

### Task 5: Local Service Runtime Parity

**Files:**
- Modify: `skills/loop-engine/web/server.py`
- Modify: `skills/loop-engine/tests/test_web_preflight.py`
- Create: `skills/loop-engine/tests/test_web_runtime_adapter.py`

- [ ] **Step 1: Write failing service adapter tests**

Create `skills/loop-engine/tests/test_web_runtime_adapter.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import queue
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "web" / "server.py"
spec = importlib.util.spec_from_file_location("web_server", MODULE)
web_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(web_server)


class WebRuntimeAdapterTests(unittest.TestCase):
    def test_preflight_and_run_use_same_normalized_input_fields(self):
        captured = []

        def fake_adapter(params, confirmation=None, event_sink=None):
            captured.append(dict(params))
            return {
                "status": "preview",
                "request_fingerprint": "fp",
                "route": {"lane": "fast", "required_seats": ["kimi"]},
                "preflight": {"status": "ok", "required_seats": ["kimi"], "blocking_seats": [], "warnings": []},
                "capacity": [],
                "guard": {"status": "allowed"},
            }

        with tempfile.TemporaryDirectory() as td, mock.patch.object(web_server.concilium_runtime, "run_concilium_adapter", side_effect=fake_adapter):
            payload = {"repo": td, "task": "Fix docs.", "test_cmd": "true", "mode": "stub_run", "timeout": 11}
            web_server.preflight_response(payload)
            q = queue.Queue()
            web_server._run_thread(payload, q)

        self.assertEqual(captured[0]["repo"], captured[1]["repo"])
        self.assertEqual(captured[0]["task"], captured[1]["task"])
        self.assertEqual(captured[0]["test_cmd"], captured[1]["test_cmd"])
        self.assertEqual(captured[0]["mode"], captured[1]["mode"])
        self.assertEqual(captured[0]["timeout"], captured[1]["timeout"])

    def test_blocked_runtime_result_emits_done_without_conductor_run(self):
        def fake_adapter(params, confirmation=None, event_sink=None):
            event_sink.emit("guard", status="blocked")
            event_sink.emit("finish", status="blocked")
            event_sink.emit("done", rc=3)
            return {"status": "blocked", "returncode": 3, "guard": {"status": "blocked"}}

        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(web_server.concilium_runtime, "run_concilium_adapter", side_effect=fake_adapter), \
                mock.patch.object(web_server.conductor, "run") as conductor_run:
            q = queue.Queue()
            web_server._run_thread({"repo": td, "task": "Fix docs.", "mode": "live_run"}, q)

        conductor_run.assert_not_called()
        events = []
        while not q.empty():
            events.append(q.get())
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["rc"], 3)

    def test_token_file_payload_is_user_only(self):
        with tempfile.TemporaryDirectory() as td:
            token_path = pathlib.Path(td) / "token.json"
            web_server.write_token_file(token_path, "http://127.0.0.1:8765/", "secret-token")
            mode = token_path.stat().st_mode & 0o777
            payload = json.loads(token_path.read_text(encoding="utf-8"))

        self.assertEqual(mode, 0o600)
        self.assertEqual(payload["token"], "secret-token")
        self.assertEqual(payload["base_url"], "http://127.0.0.1:8765/")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run service tests to verify failure**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_web_runtime_adapter
```

Expected: FAIL because `server.py` still calls `conductor.run()` in `_run_thread` and lacks `write_token_file`.

- [ ] **Step 3: Refactor service imports and run thread**

Modify `skills/loop-engine/web/server.py`:

```python
import datetime
import stat

import concilium_runtime  # noqa: E402
import concilium_config  # noqa: E402
import concilium_events  # noqa: E402
```

Replace `_run_thread` with:

```python
def _run_thread(params: dict, q: "queue.Queue"):
    sink = concilium_events.QueueEventSink(q)
    try:
        confirmation = params.get("confirmation") if isinstance(params.get("confirmation"), dict) else None
        result = concilium_runtime.run_concilium_adapter(params, confirmation=confirmation, event_sink=sink)
        if not sink.done_emitted:
            concilium_events.emit_done(sink, int(result.get("returncode", 0 if result.get("status") in {"stubbed", "preview"} else 3)))
    except Exception as e:
        q.put({"type": "error", "msg": f"{type(e).__name__}: {capacity_status.redact(str(e))}"})
        q.put({"type": "done", "rc": -1})
```

Replace `build_preflight` with:

```python
def build_preflight(params: dict) -> dict:
    preview_params = dict(params)
    preview_params["mode"] = preview_params.get("mode") or "preview"
    return concilium_runtime.run_concilium_adapter(preview_params)
```

Add:

```python
def status_response() -> dict:
    return {
        "product": "Concilium",
        "service": "ok",
        "bind": "127.0.0.1",
        "token_required": True,
        "endpoints": ["/api/status", "/api/preflight", "/api/run", "/api/events", "/api/config/effective"],
    }


def effective_config_response(repo: str) -> dict:
    config = concilium_config.load_config(repo)
    return _redact_response({"repo": str(Path(repo).expanduser().resolve()), "config": config})


def write_token_file(path: Path, base_url: str, token: str) -> None:
    payload = {
        "base_url": base_url,
        "token": token,
        "created_at": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
```

- [ ] **Step 4: Add service endpoints**

In `Handler.do_GET`, add before `/api/doctor`:

```python
if u.path == "/api/status":
    return self._send(200, json.dumps(status_response(), ensure_ascii=False).encode("utf-8"))
if u.path == "/api/config/effective":
    repo = parse_qs(u.query).get("repo", [""])[0]
    if not repo:
        return self._send(400, b'{"error":"repo required"}')
    return self._send(200, json.dumps(effective_config_response(repo), ensure_ascii=False).encode("utf-8"))
```

In `main()`, add:

```python
ap.add_argument("--token-file", default="")
...
if a.token_file:
    write_token_file(Path(a.token_file).expanduser(), url, TOKEN)
```

- [ ] **Step 5: Update Web preflight test expectations**

Modify `skills/loop-engine/tests/test_web_preflight.py` so the mocked runtime result includes guard:

```python
with tempfile.TemporaryDirectory() as td, \
        mock.patch.object(web_server, "build_preflight", return_value={
            "route": {"lane": "review", "required_seats": ["kimi", "hermes"]},
            "preflight": {"status": "warn", "warnings": ["kimi unknown capacity"], "blocking_seats": []},
            "capacity": [{"seat": "kimi", "status": "unknown", "reason": "no token sk-secret"}],
            "guard": {"status": "confirmation_required", "reason": "kimi unknown"},
        }):
```

Assert:

```python
self.assertIn('"guard":', text)
self.assertNotIn("sk-secret", text)
```

- [ ] **Step 6: Verify Task 5**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_web_preflight
python3 -m unittest skills.loop-engine.tests.test_web_runtime_adapter
python3 -m unittest discover -s skills/loop-engine/tests
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

Run:

```bash
git add skills/loop-engine/web/server.py skills/loop-engine/tests/test_web_preflight.py skills/loop-engine/tests/test_web_runtime_adapter.py
git commit -m "feat(concilium): route web service through runtime adapter"
```

---

### Task 6: Debug Console And Menu Bar Contract

**Files:**
- Modify: `skills/loop-engine/web/index.html`
- Create: `skills/loop-engine/client/concilium_client.py`
- Create: `skills/loop-engine/client/menu_bar_view_model.py`
- Create: `skills/loop-engine/tests/test_menu_bar_contract.py`
- Create: `skills/loop-engine/tests/fixtures/menu_bar/blocked_review.json`
- Create: `skills/loop-engine/tests/fixtures/menu_bar/active_fast.json`
- Create: `docs/loop-engine/concilium-menu-bar-contract.md`

- [ ] **Step 1: Write failing menu bar contract tests**

Create `skills/loop-engine/tests/test_menu_bar_contract.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
CLIENT = ROOT / "skills" / "loop-engine" / "client" / "concilium_client.py"
VIEW_MODEL = ROOT / "skills" / "loop-engine" / "client" / "menu_bar_view_model.py"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MenuBarContractTests(unittest.TestCase):
    def test_client_reads_token_file(self):
        concilium_client = load_module("concilium_client", CLIENT)
        with tempfile.TemporaryDirectory() as td:
            token_file = pathlib.Path(td) / "token.json"
            token_file.write_text(json.dumps({"base_url": "http://127.0.0.1:8765/", "token": "abc"}), encoding="utf-8")
            client = concilium_client.ConciliumClient.from_token_file(token_file)

        self.assertEqual(client.base_url, "http://127.0.0.1:8765")
        self.assertEqual(client.token, "abc")

    def test_save_config_returns_explicit_not_implemented(self):
        concilium_client = load_module("concilium_client", CLIENT)
        client = concilium_client.ConciliumClient("http://127.0.0.1:8765", "abc")

        result = client.save_config("project", {"lanes": {"fast": {"default_single_agent": "codex"}}})

        self.assertEqual(result["status"], "not_implemented")
        self.assertIn("Phase 5", result["reason"])

    def test_blocked_review_view_model_puts_block_near_top(self):
        menu_bar_view_model = load_module("menu_bar_view_model", VIEW_MODEL)
        fixture = json.loads((ROOT / "skills" / "loop-engine" / "tests" / "fixtures" / "menu_bar" / "blocked_review.json").read_text(encoding="utf-8"))

        model = menu_bar_view_model.build_popover_model(**fixture)

        self.assertEqual(model["header"]["service"], "ok")
        self.assertEqual(model["active_decision"]["lane"], "review")
        self.assertEqual(model["verdict"]["kind"], "blocked")
        self.assertEqual(model["primary_action"]["enabled"], False)
        self.assertEqual(model["seat_capacity"][1]["seat"], "hermes")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Create fixtures**

Create `skills/loop-engine/tests/fixtures/menu_bar/blocked_review.json`:

```json
{
  "status": {"service": "ok", "repo": "/tmp/repo"},
  "effective_config": {
    "routing": {"risk_posture": "balanced", "allow_auto_escalation": true, "allow_auto_downgrade": false},
    "lanes": {
      "fast": {"default_single_agent": "kimi"},
      "review": {"default_review_executor": "kimi", "default_review_reviewer": "hermes"},
      "roundtable": {"commander": "claude", "reviewer": "", "seats": ["claude", "hermes", "kimi"]}
    }
  },
  "preflight": {
    "route": {"lane": "review", "reason": "bounded medium-risk task benefits from independent review", "required_seats": ["kimi", "hermes"]},
    "preflight": {"status": "blocked", "blocking_seats": ["hermes"], "warnings": []},
    "capacity": [
      {"seat": "kimi", "provider": "moonshot", "model": "kimi", "status": "ok", "checked_at": "2026-06-29T00:00:00Z", "reset_at": ""},
      {"seat": "hermes", "provider": "deepseek", "model": "deepseek-chat", "status": "hard_exhausted", "checked_at": "2026-06-29T00:00:00Z", "reset_at": ""}
    ],
    "guard": {"status": "blocked", "reason": "seat unresolved or blocked"}
  },
  "events": []
}
```

Create `skills/loop-engine/tests/fixtures/menu_bar/active_fast.json`:

```json
{
  "status": {"service": "ok", "repo": "/tmp/repo"},
  "effective_config": {
    "routing": {"risk_posture": "speed-first", "allow_auto_escalation": true, "allow_auto_downgrade": false},
    "lanes": {
      "fast": {"default_single_agent": "kimi"},
      "review": {"default_review_executor": "kimi", "default_review_reviewer": "hermes"},
      "roundtable": {"commander": "claude", "reviewer": "", "seats": ["claude", "hermes", "kimi"]}
    }
  },
  "preflight": {
    "route": {"lane": "fast", "reason": "clear low-risk task fits single-agent lane", "required_seats": ["kimi"]},
    "preflight": {"status": "ok", "blocking_seats": [], "warnings": []},
    "capacity": [
      {"seat": "kimi", "provider": "moonshot", "model": "kimi", "status": "ok", "checked_at": "2026-06-29T00:00:00Z", "reset_at": ""}
    ],
    "guard": {"status": "allowed", "reason": "all required seats fresh enough"}
  },
  "events": [{"type": "seat", "agent": "kimi", "phase": "start"}]
}
```

- [ ] **Step 3: Run menu bar tests to verify failure**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_menu_bar_contract
```

Expected: FAIL because client and view-model modules do not exist.

- [ ] **Step 4: Implement Concilium client contract**

Create `skills/loop-engine/client/concilium_client.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path


class ConciliumClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    @classmethod
    def from_token_file(cls, path: str | Path) -> "ConciliumClient":
        payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
        return cls(str(payload["base_url"]), str(payload["token"]))

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "X-Loop-Token": self.token},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")

    def status(self) -> dict:
        return self._request("GET", "/api/status")

    def preflight(self, request: dict) -> dict:
        return self._request("POST", "/api/preflight", request)

    def run(self, request: dict, confirmation: dict | None = None) -> dict:
        payload = dict(request)
        if confirmation is not None:
            payload["confirmation"] = confirmation
        return self._request("POST", "/api/run", payload)

    def events(self, run_id: str) -> str:
        query = urllib.parse.urlencode({"run": run_id})
        req = urllib.request.Request(self.base_url + "/api/events?" + query, method="GET")
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8")

    def effective_config(self, repo: str) -> dict:
        query = urllib.parse.urlencode({"repo": repo})
        return self._request("GET", "/api/config/effective?" + query)

    def save_config(self, target: str, patch: dict) -> dict:
        del target, patch
        return {"status": "not_implemented", "reason": "Config writes are deferred to Phase 5."}
```

- [ ] **Step 5: Implement menu bar view model**

Create `skills/loop-engine/client/menu_bar_view_model.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations


def _capacity(preflight: dict) -> list[dict]:
    return list(preflight.get("capacity") or [])


def build_popover_model(status: dict, effective_config: dict, preflight: dict, events: list[dict]) -> dict:
    route = preflight.get("route", {})
    preflight_status = preflight.get("preflight", {})
    guard = preflight.get("guard", {})
    capacity = _capacity(preflight)
    blocked = guard.get("status") in {"blocked", "confirmation_required"} or preflight_status.get("status") == "blocked"
    latest_event = events[-1] if events else {}

    return {
        "header": {
            "product": "Concilium",
            "service": status.get("service", "unknown"),
            "repo": status.get("repo", ""),
        },
        "active_decision": {
            "lane": route.get("lane", ""),
            "reason": route.get("reason", ""),
            "preflight_status": preflight_status.get("status", ""),
            "required_seats": route.get("required_seats", []),
        },
        "verdict": {
            "kind": "blocked" if blocked else "ready",
            "text": guard.get("reason") or preflight_status.get("status", ""),
        },
        "primary_action": {
            "label": "Run",
            "enabled": not blocked,
            "requires_confirmation": guard.get("status") == "confirmation_required",
        },
        "seat_capacity": [
            {
                "seat": item.get("seat", ""),
                "provider": item.get("provider", ""),
                "model": item.get("model", ""),
                "status": item.get("status", "unknown"),
                "checked_at": item.get("checked_at", ""),
                "reset_at": item.get("reset_at", ""),
            }
            for item in capacity
        ],
        "config_summary": {
            "risk_posture": effective_config.get("routing", {}).get("risk_posture", ""),
            "auto_escalation": bool(effective_config.get("routing", {}).get("allow_auto_escalation", False)),
            "auto_downgrade": bool(effective_config.get("routing", {}).get("allow_auto_downgrade", False)),
            "project_override_active": bool(status.get("project_override_active", False)),
        },
        "execution_snapshot": {
            "lane": route.get("lane", ""),
            "active_seat": latest_event.get("agent", ""),
            "latest_event": latest_event.get("type", ""),
            "phase": latest_event.get("phase", ""),
        },
        "debug_action": {"label": "Open Debug Console", "target": "webui"},
    }
```

- [ ] **Step 6: Relabel WebUI as Debug Console**

Modify `skills/loop-engine/web/index.html`:

- Replace visible product header text that names the surface as WebUI with `Concilium Debug Console`.
- Add fields for `route.lane`, `preflight.status`, `guard.status`, and `request_fingerprint`.
- Keep raw event log visible because this surface is the debug console.
- Do not add menu-bar-only routing logic to JavaScript; POST the same JSON request to `/api/preflight` and `/api/run`.

- [ ] **Step 7: Document menu bar contract**

Create `docs/loop-engine/concilium-menu-bar-contract.md`:

```markdown
# Concilium Menu Bar Contract

Phase 4 defines the service and view-model contract for a future menu bar shell. It does not choose a native app framework.

## Service

- `GET /api/status`
- `POST /api/preflight`
- `POST /api/run`
- `GET /api/events?run=<id>`
- `GET /api/config/effective?repo=<path>`

Mutation requests use `X-Loop-Token`.

## Token Handoff

The service may be launched with `--token-file PATH`. When supplied, it writes a user-only JSON token file:

```json
{"base_url": "http://127.0.0.1:8765/", "token": "...", "created_at": "2026-06-29T00:00:00Z"}
```

No token file is written unless the caller explicitly supplies `--token-file`.

## Client Methods

- `status()`
- `preflight(request)`
- `run(request, confirmation)`
- `events(run_id)`
- `effectiveConfig(repo)`
- `saveConfig(target, patch)`

`saveConfig` returns `not_implemented` in Phase 4 because config write endpoints are deferred to Phase 5.

## View Model Order

1. Service and project header
2. Active decision
3. Verdict or block reason
4. Seat capacity and role assignment
5. Config summary
6. Execution snapshot
7. Debug Console action
```

- [ ] **Step 8: Verify Task 6**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_menu_bar_contract
python3 -m unittest discover -s skills/loop-engine/tests
```

Expected: PASS.

- [ ] **Step 9: Commit Task 6**

Run:

```bash
git add skills/loop-engine/web/index.html skills/loop-engine/client/concilium_client.py skills/loop-engine/client/menu_bar_view_model.py skills/loop-engine/tests/test_menu_bar_contract.py skills/loop-engine/tests/fixtures/menu_bar/blocked_review.json skills/loop-engine/tests/fixtures/menu_bar/active_fast.json docs/loop-engine/concilium-menu-bar-contract.md
git commit -m "feat(concilium): add debug console and menu bar contract"
```

---

### Task 7: Phase 4 Smoke And Closeout

**Files:**
- Create: `skills/loop-engine/bin/smoke-concilium-phase4.sh`
- Create: `docs/loop-engine/phase4-closeout-2026-06-29.md`
- Modify: `docs/superpowers/specs/2026-06-29-concilium-phase4-design.md`

- [ ] **Step 1: Create smoke script**

Create `skills/loop-engine/bin/smoke-concilium-phase4.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
REPO="${1:-$ROOT}"

echo "[phase4] unit suite"
python3 -m unittest discover -s "$ROOT/skills/loop-engine/tests"

echo "[phase4] CLI preview"
python3 "$ROOT/skills/loop-engine/bin/concilium-run.py" \
  --repo "$REPO" \
  --task "Fix one typo in docs/example.md." \
  --test-cmd "true" \
  --mode preview \
  --signals-json '{"risk":"low","file_count":1,"security_sensitive":false,"ambiguous":false}' \
  >/tmp/concilium-phase4-preview.json

python3 - <<'PY'
import json
from pathlib import Path
preview = json.loads(Path("/tmp/concilium-phase4-preview.json").read_text(encoding="utf-8"))
assert preview["status"] == "preview"
assert preview["route"]["lane"] in {"fast", "review", "roundtable"}
assert preview["request_fingerprint"]
PY

echo "[phase4] CLI stub run"
python3 "$ROOT/skills/loop-engine/bin/concilium-run.py" \
  --repo "$REPO" \
  --task "Fix one typo in docs/example.md." \
  --test-cmd "true" \
  --mode stub_run \
  --signals-json '{"risk":"low","file_count":1,"security_sensitive":false,"ambiguous":false}' \
  >/tmp/concilium-phase4-stub.json

python3 - <<'PY'
import json
from pathlib import Path
stub = json.loads(Path("/tmp/concilium-phase4-stub.json").read_text(encoding="utf-8"))
assert stub["status"] in {"stubbed", "confirmation_required", "blocked"}
events = stub.get("events", [])
if events:
    assert events[-1]["type"] == "done"
PY

echo "[phase4] diff check"
git -C "$ROOT" diff --check
```

- [ ] **Step 2: Make smoke script executable**

Run:

```bash
chmod +x skills/loop-engine/bin/smoke-concilium-phase4.sh
```

- [ ] **Step 3: Run smoke script**

Run:

```bash
skills/loop-engine/bin/smoke-concilium-phase4.sh /Users/melee/Documents/agents
```

Expected: PASS with `[phase4] diff check` as the final section.

- [ ] **Step 4: Run tiny live Fast smoke gate**

First run preflight for the disposable smoke task:

```bash
python3 skills/loop-engine/bin/concilium-run.py \
  --repo /Users/melee/Documents/agents \
  --task "Append no files; respond with a one-line dry confirmation for Concilium Phase 4 smoke." \
  --test-cmd "true" \
  --mode live_run \
  --signals-json '{"risk":"low","file_count":0,"security_sensitive":false,"ambiguous":false}' \
  > /tmp/concilium-phase4-live-gate.json
```

If the result status is `confirmation_required`, inspect `/tmp/concilium-phase4-live-gate.json`, confirm only if the required seat and provider are acceptable for a tiny smoke, then rerun with:

```bash
python3 - <<'PY' >/tmp/concilium-phase4-confirmation.json
import json
gate = json.load(open("/tmp/concilium-phase4-live-gate.json", encoding="utf-8"))
payload = gate["guard"]["confirmation_payload"]
print(json.dumps({"accepted": True, "request_fingerprint": payload["request_fingerprint"]}))
PY

python3 skills/loop-engine/bin/concilium-run.py \
  --repo /Users/melee/Documents/agents \
  --task "Append no files; respond with a one-line dry confirmation for Concilium Phase 4 smoke." \
  --test-cmd "true" \
  --mode live_run \
  --signals-json '{"risk":"low","file_count":0,"security_sensitive":false,"ambiguous":false}' \
  --confirmation-json "$(cat /tmp/concilium-phase4-confirmation.json)" \
  > /tmp/concilium-phase4-live-smoke.json
```

If the result status is `blocked`, do not rerun. Record the guard block reason in closeout.

- [ ] **Step 5: Write closeout report**

Create `docs/loop-engine/phase4-closeout-2026-06-29.md`:

```markdown
# Concilium Phase 4 Closeout

## Conclusion

Phase 4 [closed or blocked] the routed live control plane.

## Evidence

- Unit suite:
- Phase 4 smoke script:
- CLI preview:
- CLI stub run:
- Tiny live Fast smoke:

## Acceptance Matrix

| Criterion | Status | Evidence |
|---|---:|---|
| `/api/run` uses runtime adapter |  |  |
| Preflight/run parity enforced |  |  |
| `preview`, `stub_run`, `live_run` distinct |  |  |
| Budget Guard blocks unavailable/hard/unresolved |  |  |
| Budget Guard confirms unknown/soft-limited |  |  |
| Event stream ends with `done` |  |  |
| Debug Console labeled |  |  |
| Menu bar contract and fixtures exist |  |  |
| Effective config preview exists |  |  |
| No global provider config writes |  |  |
| Tiny live Fast smoke completed or guard-skipped |  |  |

## Risks And Unknowns

- Native menu bar framework selection remains Phase 5 work.
- Provider-specific quota probes remain best-effort and may be unknown.
- Config write endpoints are deferred to Phase 5.

## Next Decision Trigger

Start Phase 5 when the user wants a native menu bar shell or config write/setup UX.
```

Fill each evidence row with the actual command result, commit hash, and redacted smoke status from this implementation run.

- [ ] **Step 6: Mark Phase 4 spec status**

Append to `docs/superpowers/specs/2026-06-29-concilium-phase4-design.md`:

```markdown
## Implementation Status

Implemented by `docs/superpowers/plans/2026-06-29-concilium-phase4-implementation.md`.

Closeout evidence: `docs/loop-engine/phase4-closeout-2026-06-29.md`.
```

- [ ] **Step 7: Run final verification**

Run:

```bash
python3 -m unittest discover -s skills/loop-engine/tests
skills/loop-engine/bin/smoke-concilium-phase4.sh /Users/melee/Documents/agents
rg -n "conductor\\.run\\(" skills/loop-engine/web/server.py
python3 - <<'PY'
import pathlib
import re
import sys
patterns = ["TO" + "DO", "TB" + "D", "place" + "holder", "implement " + "later", "fill in " + "details"]
regex = re.compile("|".join(re.escape(item) for item in patterns), re.IGNORECASE)
paths = [
    pathlib.Path("docs/superpowers/plans/2026-06-29-concilium-phase4-implementation.md"),
    pathlib.Path("docs/loop-engine/phase4-closeout-2026-06-29.md"),
    pathlib.Path("skills/loop-engine"),
]
matches = []
for root in paths:
    files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
    for path in files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if regex.search(line):
                matches.append(f"{path}:{lineno}:{line}")
if matches:
    print("\n".join(matches))
    sys.exit(1)
PY
git diff --check
```

Expected:

- Unit suite PASS.
- Smoke script PASS.
- `rg -n "conductor\\.run\\(" skills/loop-engine/web/server.py` prints no matches.
- Red-flag text scan prints no matches.
- `git diff --check` prints no output and exits 0.

- [ ] **Step 8: Commit Task 7**

Run:

```bash
git add skills/loop-engine/bin/smoke-concilium-phase4.sh docs/loop-engine/phase4-closeout-2026-06-29.md docs/superpowers/specs/2026-06-29-concilium-phase4-design.md
git commit -m "docs(concilium): close phase4 control plane"
```

---

## Adversarial Review Checklist

Run this after Task 7 and before proposing merge:

1. **Route-run contract:** compare `/api/preflight` and `/api/run` paths. Both must call `concilium_runtime.run_concilium_adapter`; WebUI must not call `conductor.run()` directly.
2. **Guard before spend:** patch lane executor in tests and prove blocked, unresolved, unknown-without-confirmation, and mismatched-confirmation live runs do not call the executor.
3. **No silent downgrade:** prove Review is not rewritten to Fast when reviewer capacity blocks. The result must be blocked or confirmation-gated according to Budget Guard.
4. **Mode clarity:** confirm `preview` never emits live seat calls, `stub_run` emits terminal events without live agent calls, and `live_run` requires Budget Guard.
5. **Terminal events:** every service run path must put exactly one `done` event.
6. **Secret hygiene:** redaction applies to preflight response, service error response, event payloads, and closeout evidence.
7. **No global provider writes:** scan changed files for writes outside repo, `.roundtable`, `~/.config/concilium` with explicit command, and token-file path supplied by the caller.
8. **Client thinness:** WebUI JavaScript and menu bar client may format and submit requests, but must not contain routing, capacity, or maker-checker policy.
9. **Spec coverage:** map every Phase 4 acceptance criterion to a test, smoke result, or closeout row.
10. **Regression:** run the full `skills/loop-engine/tests` suite and Phase 3 smoke scripts if they still exist in the branch.

## Execution Order

Implement tasks in order. Commit after every task. Do not start Task 5 until Tasks 1 through 4 pass, because service parity depends on the runtime adapter. Do not start Task 6 until Task 5 passes, because the menu bar contract must reflect the actual service shape. Do not mark Phase 4 closed until Task 7 smoke and adversarial review both pass.
