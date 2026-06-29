# Concilium Phase 3 Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Phase 3 by turning Concilium from a working multi-agent prototype into a configurable lane-routing system that can choose Fast, Review, or Roundtable with visible capacity signals and no silent downgrade.

**Architecture:** Keep the core local-first and testable. Configuration loads before capacity checks; capacity checks feed preflight; preflight feeds a pure lane router; the router feeds execution wrappers; WebUI/TUI only display and override these decisions. Review Lane is already implemented and is treated as the Phase 3.1 foundation, not reimplemented here.

**Tech Stack:** Python standard library, JSON config files, existing Loop Engine shell seat scripts, existing `unittest` suite, local WebUI based on standard-library HTTP/SSE, no new runtime dependency unless a task explicitly proves it is needed.

---

## First Principles

1. **The product goal is not "use more agents"; it is "spend the cheapest amount of agent time that gives enough confidence."** Phase 3 is done only when Concilium can decide among Fast, Review, and Roundtable before execution.
2. **Routing cannot be trusted without configuration.** Users must be able to choose the default Fast Lane agent, Review Lane executor/reviewer, Roundtable seats, and risk posture. The current Kimi/Hermes defaults are local defaults, not product truths.
3. **Capacity is a routing input, not a decoration.** A seat that is unavailable, exhausted, or rate-limited must be detected before the run where possible. Unknown capacity is allowed, but it must be labeled as unknown.
4. **No silent downgrade.** If the chosen lane cannot run, Concilium must return a visible preflight decision: block, ask for confirmation, or explicitly escalate according to config.
5. **No secret leakage.** Capacity probes may inspect local CLI status, local files, OAuth/browser sessions, or provider APIs, but reports and logs must redact tokens, cookies, API keys, email addresses, and account identifiers by default.
6. **Evidence before promotion.** Every Phase 3 slice must have unit tests, a dry-run check, and at least one live or fixture-backed smoke check before being marked complete.

## Current Foundation

- Completed: `docs/superpowers/plans/2026-06-29-concilium-review-lane-mvp.md`
- Completed: `skills/loop-engine/bin/review-lane.py`
- Completed: `skills/loop-engine/bin/benchmark-roundtable.py` supports `baseline-kimi`, `review`, and `roundtable`.
- Current decision document: `docs/loop-engine/phase3-lane-routing.md`
- CodexBar reference to study, not vendor-lock: `https://github.com/steipete/CodexBar`
  - Useful principles: provider-specific usage meters, reset countdowns, privacy-first reuse of existing provider sessions, multiple sources such as CLI, OAuth, browser cookies, local files, and APIs.
  - Do not copy CodexBar internals into Concilium in Phase 3. Use it as a reference for signal shape and failure modes.

## Success Criteria

Phase 3 is closed only when all of these are true:

- `concilium_config.py` loads bundled defaults, user config, and project config with deterministic precedence.
- `capacity_status.py` emits redacted machine-readable status for each seat, including `ok`, `soft_limited`, `hard_exhausted`, `unavailable`, or `unknown`.
- `lane_router.py` can route representative tasks into Fast, Review, or Roundtable from explicit signals and config.
- `concilium-run.py --dry-run --print-route` shows the selected lane and preflight result without starting agents.
- `concilium-run.py --live` can run Fast, Review, and Roundtable through the selected lane wrapper.
- WebUI `/api/doctor` or a new `/api/preflight` endpoint shows lane choice and capacity status per seat.
- The final dry benchmark records Fast, Review, and Roundtable lane data.
- No task writes global Claude, Codex, Kimi, Hermes, or CodexBar config without an explicit user command.

---

### Task 1: Layered Configuration

**Files:**
- Create: `skills/loop-engine/config/concilium.defaults.json`
- Create: `skills/loop-engine/bin/concilium_config.py`
- Create: `skills/loop-engine/tests/test_concilium_config.py`
- Modify: `docs/loop-engine/phase3-lane-routing.md`

- [x] **Step 1: Add default config fixture**

Create `skills/loop-engine/config/concilium.defaults.json`:

```json
{
  "version": 1,
  "product_name": "Concilium",
  "lanes": {
    "fast": {
      "default_single_agent": "kimi",
      "verify_required": true
    },
    "review": {
      "default_review_executor": "kimi",
      "default_review_reviewer": "hermes",
      "review_repair_limit": 1
    },
    "roundtable": {
      "commander": "claude",
      "reviewer": "",
      "seats": ["claude", "hermes", "kimi"]
    }
  },
  "routing": {
    "risk_posture": "balanced",
    "allow_auto_escalation": true,
    "allow_auto_downgrade": false
  },
  "capacity": {
    "warn_below_percent": 20,
    "block_below_percent": 5,
    "max_status_age_seconds": 300
  },
  "privacy": {
    "redact_account_identifiers": true,
    "redact_credentials": true
  }
}
```

- [x] **Step 2: Write failing tests for precedence and validation**

Create `skills/loop-engine/tests/test_concilium_config.py`:

```python
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

    def test_project_config_overrides_user_and_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            defaults = self.write_json(root / "defaults.json", {
                "version": 1,
                "lanes": {
                    "fast": {"default_single_agent": "kimi", "verify_required": True},
                    "review": {"default_review_executor": "kimi", "default_review_reviewer": "hermes", "review_repair_limit": 1},
                    "roundtable": {"commander": "claude", "reviewer": "", "seats": ["claude", "hermes", "kimi"]}
                },
                "routing": {"risk_posture": "balanced", "allow_auto_escalation": True, "allow_auto_downgrade": False},
                "capacity": {"warn_below_percent": 20, "block_below_percent": 5, "max_status_age_seconds": 300},
                "privacy": {"redact_account_identifiers": True, "redact_credentials": True}
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
                "lanes": {
                    "fast": {"default_single_agent": "kimi", "verify_required": True},
                    "review": {"default_review_executor": "kimi", "default_review_reviewer": "kimi", "review_repair_limit": 1},
                    "roundtable": {"commander": "claude", "reviewer": "", "seats": ["claude", "hermes", "kimi"]}
                },
                "routing": {"risk_posture": "balanced", "allow_auto_escalation": True, "allow_auto_downgrade": False},
                "capacity": {"warn_below_percent": 20, "block_below_percent": 5, "max_status_age_seconds": 300},
                "privacy": {"redact_account_identifiers": True, "redact_credentials": True}
            })

            with self.assertRaisesRegex(ValueError, "review executor and reviewer must differ"):
                concilium_config.load_config(path.parent, user_config=path, default_config=path)

    def test_cli_prints_redacted_effective_config(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            defaults = self.write_json(root / "defaults.json", {
                "version": 1,
                "lanes": {
                    "fast": {"default_single_agent": "kimi", "verify_required": True},
                    "review": {"default_review_executor": "kimi", "default_review_reviewer": "hermes", "review_repair_limit": 1},
                    "roundtable": {"commander": "claude", "reviewer": "", "seats": ["claude", "hermes", "kimi"]}
                },
                "routing": {"risk_posture": "balanced", "allow_auto_escalation": True, "allow_auto_downgrade": False},
                "capacity": {"warn_below_percent": 20, "block_below_percent": 5, "max_status_age_seconds": 300},
                "privacy": {"redact_account_identifiers": True, "redact_credentials": True}
            })
            out = concilium_config.render_effective_config(root, user_config=defaults, default_config=defaults)

        self.assertIn('"product_name"', out)
        self.assertNotIn("sk-", out)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 3: Run tests to verify failure**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_concilium_config
```

Expected: FAIL because `concilium_config.py` does not exist.

- [x] **Step 4: Implement config loader**

Create `skills/loop-engine/bin/concilium_config.py` with these public functions:

```python
default_config_path() -> Path
user_config_path() -> Path
project_config_path(repo: str | Path) -> Path
load_json(path: Path) -> dict
deep_merge(base: dict, override: dict) -> dict
validate_config(config: dict) -> None
load_config(repo: str | Path, user_config: str | Path | None = None, default_config: str | Path | None = None) -> dict
render_effective_config(repo: str | Path, user_config: str | Path | None = None, default_config: str | Path | None = None) -> str
```

Required behavior:

- Bundled defaults path: `skills/loop-engine/config/concilium.defaults.json`
- User config path: `~/.config/concilium/config.json`
- Project config path: `<repo>/.concilium.json`
- Precedence: bundled defaults < user config < project config
- Missing user and project config are normal.
- Unknown top-level keys are preserved, not rejected.
- `lanes.review.default_review_executor` must not equal `lanes.review.default_review_reviewer`.
- `routing.risk_posture` must be one of `speed-first`, `balanced`, `review-first`.
- `capacity.block_below_percent` must be less than or equal to `capacity.warn_below_percent`.

- [x] **Step 5: Add CLI**

`python3 skills/loop-engine/bin/concilium_config.py --repo /path --print-effective` must print JSON and exit 0.

`python3 skills/loop-engine/bin/concilium_config.py --repo /path --init-project` must create `<repo>/.concilium.json` with only user-editable overrides:

```json
{
  "version": 1,
  "lanes": {
    "fast": {
      "default_single_agent": "kimi"
    },
    "review": {
      "default_review_executor": "kimi",
      "default_review_reviewer": "hermes"
    }
  },
  "routing": {
    "risk_posture": "balanced"
  }
}
```

- [x] **Step 6: Verify**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_concilium_config
python3 -m unittest discover -s skills/loop-engine/tests
```

Expected: all tests pass.

- [x] **Step 7: Commit**

```bash
git add skills/loop-engine/config/concilium.defaults.json skills/loop-engine/bin/concilium_config.py skills/loop-engine/tests/test_concilium_config.py docs/loop-engine/phase3-lane-routing.md
git commit -m "feat(concilium): add layered configuration"
```

---

### Task 2: Capacity Status Model and Redaction

**Files:**
- Create: `skills/loop-engine/bin/capacity_status.py`
- Create: `skills/loop-engine/tests/test_capacity_status.py`
- Modify: `skills/loop-engine/bin/roster-detect.py`

- [ ] **Step 1: Write failing tests for capacity records**

Create `skills/loop-engine/tests/test_capacity_status.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "capacity_status.py"
spec = importlib.util.spec_from_file_location("capacity_status", MODULE)
capacity_status = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(capacity_status)


class CapacityStatusTests(unittest.TestCase):
    def test_status_classifies_thresholds(self):
        self.assertEqual(capacity_status.classify_percent(80, warn_below=20, block_below=5), "ok")
        self.assertEqual(capacity_status.classify_percent(15, warn_below=20, block_below=5), "soft_limited")
        self.assertEqual(capacity_status.classify_percent(4, warn_below=20, block_below=5), "hard_exhausted")
        self.assertEqual(capacity_status.classify_percent(None, warn_below=20, block_below=5), "unknown")

    def test_redaction_removes_credentials_and_account_ids(self):
        text = "token sk-live-secret email user@example.com cookie abc.def.ghi"
        redacted = capacity_status.redact(text)
        self.assertNotIn("sk-live-secret", redacted)
        self.assertNotIn("user@example.com", redacted)
        self.assertNotIn("abc.def.ghi", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_record_shape_is_stable(self):
        record = capacity_status.make_record(
            seat="kimi",
            provider="moonshot",
            model="kimi-code/kimi-for-coding",
            status="unknown",
            source="local",
            reason="quota endpoint unavailable",
        )

        self.assertEqual(record["seat"], "kimi")
        self.assertEqual(record["status"], "unknown")
        self.assertIn("checked_at", record)
        self.assertIn("blocking", record)

    def test_hard_exhausted_is_blocking(self):
        record = capacity_status.make_record(
            seat="claude",
            provider="anthropic",
            model="opus",
            status="hard_exhausted",
            source="fixture",
            reason="0 percent remaining",
        )

        self.assertTrue(record["blocking"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_capacity_status
```

Expected: FAIL because `capacity_status.py` does not exist.

- [ ] **Step 3: Implement status model**

Create `skills/loop-engine/bin/capacity_status.py` with:

```python
STATUSES = {"ok", "soft_limited", "hard_exhausted", "unavailable", "unknown"}

classify_percent(percent_remaining: float | int | None, warn_below: int, block_below: int) -> str
redact(text: str) -> str
make_record(seat: str, provider: str, model: str, status: str, source: str, reason: str,
            percent_remaining: float | None = None, reset_at: str = "", stale_after_seconds: int = 300) -> dict
summarize_blockers(records: list[dict]) -> list[str]
```

Record shape:

```json
{
  "seat": "kimi",
  "provider": "moonshot",
  "model": "kimi-code/kimi-for-coding",
  "status": "unknown",
  "source": "local",
  "percent_remaining": null,
  "reset_at": "",
  "checked_at": "2026-06-29T08:00:00Z",
  "stale_after_seconds": 300,
  "blocking": false,
  "reason": "quota endpoint unavailable"
}
```

- [ ] **Step 4: Extend roster output without changing existing keys**

Modify `skills/loop-engine/bin/roster-detect.py` so each detected seat may include:

```json
"capacity": {
  "status": "unknown",
  "source": "not_checked",
  "percent_remaining": null,
  "reset_at": "",
  "blocking": false,
  "reason": "capacity-status not requested"
}
```

Do not make `roster-detect.py --json` call network or provider APIs in this task. It should only expose the stable default capacity shape above so UI and router code can consume it.

- [ ] **Step 5: Verify**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_capacity_status
python3 -m unittest discover -s skills/loop-engine/tests
python3 skills/loop-engine/bin/roster-detect.py --json | python3 -m json.tool >/tmp/concilium-roster.json
```

Expected: tests pass and roster JSON remains valid.

- [ ] **Step 6: Commit**

```bash
git add skills/loop-engine/bin/capacity_status.py skills/loop-engine/bin/roster-detect.py skills/loop-engine/tests/test_capacity_status.py
git commit -m "feat(concilium): add capacity status model"
```

---

### Task 3: Provider Capacity Probe Spike

**Files:**
- Create: `docs/loop-engine/capacity-probe-notes.md`
- Create: `skills/loop-engine/tests/fixtures/capacity/README.md`
- Modify: `skills/loop-engine/bin/capacity_status.py`

- [ ] **Step 1: Capture local command inventory**

Run these commands and paste redacted findings into `docs/loop-engine/capacity-probe-notes.md`:

```bash
which codexbar || true
codexbar --help 2>&1 | sed -n '1,120p' || true
which claude || true
claude --version 2>&1 | sed -n '1,20p' || true
claude --help 2>&1 | sed -n '1,120p' || true
which hermes || true
hermes --version 2>&1 | sed -n '1,20p' || true
hermes status 2>&1 | sed -n '1,160p' || true
which kimi || true
kimi --version 2>&1 | sed -n '1,20p' || true
kimi --help 2>&1 | sed -n '1,120p' || true
which codex || true
codex --version 2>&1 | sed -n '1,20p' || true
codex --help 2>&1 | sed -n '1,120p' || true
```

Required redaction before saving:

- Replace API keys with `[REDACTED_API_KEY]`.
- Replace cookies and JWT-looking strings with `[REDACTED_TOKEN]`.
- Replace personal email/account names with `[REDACTED_ACCOUNT]`.

- [ ] **Step 2: Document source choices**

In `docs/loop-engine/capacity-probe-notes.md`, include exactly these sections:

```md
# Concilium Capacity Probe Notes

## Principle

Capacity probes are best-effort local signals. They can block only when the signal is fresh and explicit.

## CodexBar Reference

CodexBar is a reference for provider-specific quota shapes, reset windows, and privacy-first source reuse. Concilium Phase 3 does not depend on CodexBar.

## Local Commands Checked

| Tool | Installed | Useful quota command | Notes |
|---|---:|---|---|
| codexbar | no | none | command unavailable |
| claude | yes | none observed | replace after local evidence |
| hermes | yes | hermes status | status shows provider/model, not quota |
| kimi | yes | none observed | replace after local evidence |
| codex | yes | none observed | replace after local evidence |

## Initial Adapter Decision

- `roster`: always available, no quota percentage, can mark unavailable if CLI missing.
- `codexbar`: optional future source if local CLI exposes machine-readable usage.
- `provider_api`: not implemented until official endpoint and credential source are verified.
```

If local evidence differs, edit only the table values and notes.

- [ ] **Step 3: Add fixture directory**

Create `skills/loop-engine/tests/fixtures/capacity/README.md`:

```md
# Capacity Fixtures

Store redacted command outputs used by capacity adapter tests.

Rules:

- No API keys.
- No cookies.
- No account emails.
- No raw bearer tokens.
- Keep one fixture per provider/source.
```

- [ ] **Step 4: Implement adapter registry without live provider calls**

Extend `capacity_status.py` with:

```python
roster_capacity_from_detected_seat(seat: dict, config: dict) -> dict
collect_capacity_from_roster(detected: list[dict], config: dict) -> list[dict]
```

Required behavior:

- CLI missing: `status="unavailable"`, `blocking=True`.
- CLI present but quota unknown: `status="unknown"`, `blocking=False`.
- Percent present in fixture or future adapter: classify through `classify_percent`.

- [ ] **Step 5: Add tests for roster-backed capacity**

Append tests to `test_capacity_status.py`:

```python
    def test_roster_unavailable_blocks(self):
        config = {"capacity": {"warn_below_percent": 20, "block_below_percent": 5, "max_status_age_seconds": 300}}
        record = capacity_status.roster_capacity_from_detected_seat(
            {"seat": "claude", "available": False, "provider": "anthropic", "model": "opus"},
            config,
        )
        self.assertEqual(record["status"], "unavailable")
        self.assertTrue(record["blocking"])

    def test_roster_available_unknown_does_not_block(self):
        config = {"capacity": {"warn_below_percent": 20, "block_below_percent": 5, "max_status_age_seconds": 300}}
        record = capacity_status.roster_capacity_from_detected_seat(
            {"seat": "kimi", "available": True, "provider": "moonshot", "model": "kimi-code/kimi-for-coding"},
            config,
        )
        self.assertEqual(record["status"], "unknown")
        self.assertFalse(record["blocking"])
```

- [ ] **Step 6: Verify**

Run:

```bash
python3 -m unittest skills.loop-engine.tests.test_capacity_status
python3 -m unittest discover -s skills/loop-engine/tests
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add docs/loop-engine/capacity-probe-notes.md skills/loop-engine/tests/fixtures/capacity/README.md skills/loop-engine/bin/capacity_status.py skills/loop-engine/tests/test_capacity_status.py
git commit -m "feat(concilium): add capacity probe spike notes"
```

---

### Task 4: Preflight Gate

**Files:**
- Create: `skills/loop-engine/bin/concilium_preflight.py`
- Create: `skills/loop-engine/tests/test_concilium_preflight.py`

- [ ] **Step 1: Write failing tests**

Create `skills/loop-engine/tests/test_concilium_preflight.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium_preflight.py"
spec = importlib.util.spec_from_file_location("concilium_preflight", MODULE)
concilium_preflight = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(concilium_preflight)


class ConciliumPreflightTests(unittest.TestCase):
    def test_hard_exhausted_required_seat_blocks(self):
        result = concilium_preflight.evaluate_preflight(
            required_seats=["kimi", "hermes"],
            capacity=[
                {"seat": "kimi", "status": "ok", "blocking": False, "reason": ""},
                {"seat": "hermes", "status": "hard_exhausted", "blocking": True, "reason": "0 percent remaining"},
            ],
            allow_auto_escalation=True,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("hermes", result["blocking_seats"])

    def test_unknown_capacity_warns_but_allows(self):
        result = concilium_preflight.evaluate_preflight(
            required_seats=["kimi"],
            capacity=[{"seat": "kimi", "status": "unknown", "blocking": False, "reason": "no quota source"}],
            allow_auto_escalation=True,
        )

        self.assertEqual(result["status"], "warn")
        self.assertIn("unknown", result["warnings"][0])

    def test_missing_required_seat_blocks(self):
        result = concilium_preflight.evaluate_preflight(
            required_seats=["claude"],
            capacity=[{"seat": "kimi", "status": "ok", "blocking": False, "reason": ""}],
            allow_auto_escalation=True,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("claude", result["blocking_seats"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify failure**

```bash
python3 -m unittest skills.loop-engine.tests.test_concilium_preflight
```

Expected: FAIL because `concilium_preflight.py` does not exist.

- [ ] **Step 3: Implement preflight**

Create `skills/loop-engine/bin/concilium_preflight.py` with:

```python
evaluate_preflight(required_seats: list[str], capacity: list[dict], allow_auto_escalation: bool) -> dict
render_preflight(result: dict) -> str
```

Return shape:

```json
{
  "status": "ok",
  "blocking_seats": [],
  "warnings": [],
  "required_seats": ["kimi", "hermes"]
}
```

Status rules:

- `blocked` if a required seat is missing, unavailable, or hard-exhausted.
- `warn` if required seats exist but one or more are `unknown` or `soft_limited`.
- `ok` if all required seats are `ok`.
- Do not auto-escalate inside preflight. Preflight reports facts; router decides escalation.

- [ ] **Step 4: Verify**

```bash
python3 -m unittest skills.loop-engine.tests.test_concilium_preflight
python3 -m unittest discover -s skills/loop-engine/tests
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add skills/loop-engine/bin/concilium_preflight.py skills/loop-engine/tests/test_concilium_preflight.py
git commit -m "feat(concilium): add lane preflight gate"
```

---

### Task 5: Pure Lane Router

**Files:**
- Create: `skills/loop-engine/bin/lane_router.py`
- Create: `skills/loop-engine/tests/test_lane_router.py`
- Modify: `docs/loop-engine/phase3-lane-routing.md`

- [ ] **Step 1: Write failing tests**

Create `skills/loop-engine/tests/test_lane_router.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "lane_router.py"
spec = importlib.util.spec_from_file_location("lane_router", MODULE)
lane_router = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(lane_router)


class LaneRouterTests(unittest.TestCase):
    def base_config(self):
        return {
            "lanes": {
                "fast": {"default_single_agent": "kimi"},
                "review": {"default_review_executor": "kimi", "default_review_reviewer": "hermes", "review_repair_limit": 1},
                "roundtable": {"commander": "claude", "reviewer": "", "seats": ["claude", "hermes", "kimi"]}
            },
            "routing": {"risk_posture": "balanced", "allow_auto_escalation": True, "allow_auto_downgrade": False}
        }

    def test_clear_small_task_routes_fast(self):
        result = lane_router.route_task(
            task="Fix one typo in docs/example.md.",
            signals={"file_count": 1, "risk": "low", "security_sensitive": False, "ambiguous": False},
            config=self.base_config(),
        )
        self.assertEqual(result["lane"], "fast")
        self.assertEqual(result["required_seats"], ["kimi"])

    def test_semantic_edge_routes_review(self):
        result = lane_router.route_task(
            task="Change config routing behavior and update tests.",
            signals={"file_count": 2, "risk": "medium", "security_sensitive": False, "ambiguous": False},
            config=self.base_config(),
        )
        self.assertEqual(result["lane"], "review")
        self.assertEqual(result["required_seats"], ["kimi", "hermes"])

    def test_ambiguous_or_security_routes_roundtable(self):
        result = lane_router.route_task(
            task="Redesign auth routing.",
            signals={"file_count": 4, "risk": "high", "security_sensitive": True, "ambiguous": True},
            config=self.base_config(),
        )
        self.assertEqual(result["lane"], "roundtable")
        self.assertIn("claude", result["required_seats"])

    def test_preflight_block_does_not_silent_downgrade(self):
        result = lane_router.apply_preflight(
            route={"lane": "review", "required_seats": ["kimi", "hermes"], "reason": "medium risk"},
            preflight={"status": "blocked", "blocking_seats": ["hermes"], "warnings": []},
            config=self.base_config(),
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["lane"], "review")
        self.assertIn("no silent downgrade", result["reason"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify failure**

```bash
python3 -m unittest skills.loop-engine.tests.test_lane_router
```

Expected: FAIL because `lane_router.py` does not exist.

- [ ] **Step 3: Implement router**

Create `skills/loop-engine/bin/lane_router.py` with:

```python
infer_task_signals(task: str, repo: str | Path | None = None) -> dict
route_task(task: str, signals: dict, config: dict) -> dict
required_seats_for_lane(lane: str, config: dict) -> list[str]
apply_preflight(route: dict, preflight: dict, config: dict) -> dict
```

Routing rules:

- Fast Lane if `risk=low`, `file_count <= 1`, not ambiguous, not security-sensitive.
- Review Lane if bounded and `risk=medium`, or config/routing/evaluation terms appear in the task.
- Roundtable Lane if ambiguous, security-sensitive, architecture/migration/high-impact business decision, or `file_count >= 4`.
- `risk_posture=speed-first` may route low-medium tasks to Fast only when `security_sensitive=False` and `ambiguous=False`.
- `risk_posture=review-first` routes low-medium tasks to Review unless they are clearly one-file docs-only changes.
- `apply_preflight` must never change a lane from Review to Fast. If a required seat is blocked and `allow_auto_escalation=True`, it may recommend Roundtable only when Roundtable required seats are not known-blocked. Otherwise return blocked.

- [ ] **Step 4: Add CLI preview**

`python3 skills/loop-engine/bin/lane_router.py --task "Change config routing behavior and update tests." --signals '{"risk":"medium","file_count":2}' --config-json /tmp/config.json`

Expected output:

```json
{
  "lane": "review",
  "required_seats": ["kimi", "hermes"],
  "status": "selected",
  "reason": "bounded medium-risk task benefits from independent review"
}
```

- [ ] **Step 5: Verify**

```bash
python3 -m unittest skills.loop-engine.tests.test_lane_router
python3 -m unittest discover -s skills/loop-engine/tests
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add skills/loop-engine/bin/lane_router.py skills/loop-engine/tests/test_lane_router.py docs/loop-engine/phase3-lane-routing.md
git commit -m "feat(concilium): add pure lane router"
```

---

### Task 6: Concilium Run Wrapper

**Files:**
- Create: `skills/loop-engine/bin/concilium-run.py`
- Create: `skills/loop-engine/tests/test_concilium_run.py`
- Modify: `skills/loop-engine/bin/review-lane.py`

- [ ] **Step 1: Write failing tests for dry-run route preview**

Create `skills/loop-engine/tests/test_concilium_run.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium-run.py"
spec = importlib.util.spec_from_file_location("concilium_run", MODULE)
concilium_run = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(concilium_run)


class ConciliumRunTests(unittest.TestCase):
    def test_print_route_does_not_run_agents(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run, "run_fast_lane") as fast:
            result = concilium_run.run_concilium(
                repo=td,
                task="Fix one typo in docs/example.md.",
                test_cmd="true",
                dry_run=True,
                print_route=True,
                signals={"risk": "low", "file_count": 1, "security_sensitive": False, "ambiguous": False},
            )

        self.assertEqual(result["route"]["lane"], "fast")
        self.assertEqual(result["status"], "preview")
        fast.assert_not_called()

    def test_blocked_preflight_stops_before_agent_call(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run, "collect_capacity", return_value=[
                    {"seat": "kimi", "status": "ok", "blocking": False, "reason": ""},
                    {"seat": "hermes", "status": "hard_exhausted", "blocking": True, "reason": "0 percent remaining"},
                ]), \
                mock.patch.object(concilium_run, "run_review_lane") as review:
            result = concilium_run.run_concilium(
                repo=td,
                task="Change config routing behavior.",
                test_cmd="true",
                dry_run=False,
                print_route=False,
                signals={"risk": "medium", "file_count": 2, "security_sensitive": False, "ambiguous": False},
            )

        self.assertEqual(result["status"], "blocked")
        review.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify failure**

```bash
python3 -m unittest skills.loop-engine.tests.test_concilium_run
```

Expected: FAIL because `concilium-run.py` does not exist.

- [ ] **Step 3: Implement wrapper functions**

Create `skills/loop-engine/bin/concilium-run.py` with:

```python
collect_capacity(repo: str | Path, config: dict) -> list[dict]
run_fast_lane(repo: str | Path, task: str, test_cmd: str, agent: str, timeout: int) -> dict
run_review_lane(repo: str | Path, task: str, test_cmd: str, config: dict, timeout: int) -> dict
run_roundtable_lane(repo: str | Path, task: str, test_cmd: str, config: dict, timeout: int) -> dict
run_concilium(repo: str | Path, task: str, test_cmd: str = "", dry_run: bool = False,
              print_route: bool = False, signals: dict | None = None, timeout: int = 300) -> dict
```

Wrapper behavior:

- Load config first.
- Run roster/capacity collection second.
- Infer or accept task signals third.
- Route fourth.
- Preflight fifth.
- If `print_route=True` or `dry_run=True`, return preview JSON and do not call any seat script.
- If preflight blocked, return exit code 3 from CLI.
- If Fast Lane selected, call `seat-<agent>.sh exec` and then run `test_cmd`.
- If Review Lane selected, call existing `review-lane.py`.
- If Roundtable Lane selected, call existing `conductor.run()`.

- [ ] **Step 4: Add CLI**

Required examples:

```bash
python3 skills/loop-engine/bin/concilium-run.py --repo /path/to/repo --task "Fix typo" --test-cmd true --dry-run --print-route
python3 skills/loop-engine/bin/concilium-run.py --repo /path/to/repo --task "Fix typo" --test-cmd true --live
```

Exit codes:

- `0`: lane ran or preview generated successfully.
- `2`: selected lane returned BLOCK.
- `3`: preflight blocked before execution.
- `4`: invalid config or invalid CLI arguments.
- `1`: unexpected execution error.

- [ ] **Step 5: Verify**

```bash
python3 -m unittest skills.loop-engine.tests.test_concilium_run
python3 -m unittest discover -s skills/loop-engine/tests
python3 skills/loop-engine/bin/concilium-run.py --repo . --task "Fix one typo in docs/example.md." --test-cmd true --dry-run --print-route | python3 -m json.tool
```

Expected: all tests pass and route preview prints valid JSON.

- [ ] **Step 6: Commit**

```bash
git add skills/loop-engine/bin/concilium-run.py skills/loop-engine/tests/test_concilium_run.py skills/loop-engine/bin/review-lane.py
git commit -m "feat(concilium): add routed run wrapper"
```

---

### Task 7: Benchmark Router Mode

**Files:**
- Modify: `skills/loop-engine/bin/benchmark-roundtable.py`
- Modify: `skills/loop-engine/tests/test_benchmark_roundtable.py`
- Modify: `skills/loop-engine/bin/summarize-benchmark.py`
- Modify: `skills/loop-engine/tests/test_summarize_benchmark.py`

- [ ] **Step 1: Add failing test for routed lane records**

Append to `test_benchmark_roundtable.py`:

```python
    def test_dry_batch_can_include_router_lane(self):
        with tempfile.TemporaryDirectory() as td:
            records = benchmark.run_dry_batch([sample_task()], pathlib.Path(td), "harness", "base", lanes=("router",))

        self.assertEqual([record["lane"] for record in records], ["router"])
        self.assertIn("selected_lane", records[0])
```

- [ ] **Step 2: Run focused test to verify failure**

```bash
python3 -m unittest skills.loop-engine.tests.test_benchmark_roundtable.BenchmarkRoundtableTests.test_dry_batch_can_include_router_lane
```

Expected: FAIL because `run_dry_batch` does not accept `lanes`.

- [ ] **Step 3: Add router lane support**

Modify `benchmark-roundtable.py`:

- Add optional `lanes` argument with default value `LANES` to `run_dry_batch`.
- Add `router` as an opt-in lane, not a default lane.
- `router` lane dry record must include:

```json
{
  "lane": "router",
  "selected_lane": "fast",
  "preflight_status": "ok"
}
```

- Live router benchmark must call `concilium-run.py` and record selected lane, preflight status, wall time, return code, report path, diff, and tests.

- [ ] **Step 4: Update summary**

Modify `summarize-benchmark.py` so router records display as:

```md
| Task | Kimi | Review | Roundtable | Router | Outcome | Reason |
```

The router column should show `PASS(selected=review)` or `ERR(blocked)`.

- [ ] **Step 5: Verify**

```bash
python3 -m unittest skills.loop-engine.tests.test_benchmark_roundtable
python3 -m unittest skills.loop-engine.tests.test_summarize_benchmark
python3 -m unittest discover -s skills/loop-engine/tests
python3 skills/loop-engine/bin/benchmark-roundtable.py --dry-run --out /tmp/concilium-phase3-router-dry
```

Expected: tests pass. Default dry benchmark still writes only `baseline-kimi`, `review`, and `roundtable` unless `--include-router` is added.

- [ ] **Step 6: Commit**

```bash
git add skills/loop-engine/bin/benchmark-roundtable.py skills/loop-engine/bin/summarize-benchmark.py skills/loop-engine/tests/test_benchmark_roundtable.py skills/loop-engine/tests/test_summarize_benchmark.py
git commit -m "feat(concilium): add router benchmark lane"
```

---

### Task 8: WebUI Preflight and Setup Surface

**Files:**
- Modify: `skills/loop-engine/web/server.py`
- Modify: `skills/loop-engine/web/index.html`
- Create: `skills/loop-engine/tests/test_web_preflight.py`

- [ ] **Step 1: Write server tests for preflight endpoint**

Create `skills/loop-engine/tests/test_web_preflight.py`:

```python
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
                }):
            response = web_server.preflight_response({"repo": td, "task": "Change config", "test_cmd": "true"})

        text = json.dumps(response, ensure_ascii=False)
        self.assertIn('"lane": "review"', text)
        self.assertNotIn("sk-secret", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify failure**

```bash
python3 -m unittest skills.loop-engine.tests.test_web_preflight
```

Expected: FAIL because `preflight_response` does not exist.

- [ ] **Step 3: Add `/api/preflight`**

Modify `server.py`:

- Import `concilium-run.py` or shared functions without starting a run.
- Add `preflight_response(params: dict) -> dict`.
- Add `POST /api/preflight`, protected by `X-Loop-Token`.
- Response shape:

```json
{
  "route": {"lane": "review", "required_seats": ["kimi", "hermes"], "reason": "bounded medium-risk task"},
  "preflight": {"status": "warn", "warnings": ["kimi capacity unknown"], "blocking_seats": []},
  "capacity": [{"seat": "kimi", "status": "unknown", "percent_remaining": null, "reset_at": ""}]
}
```

- [ ] **Step 4: Add UI route preview**

Modify `index.html`:

- Product title should say `Concilium`.
- Keep `Loop Engine` visible only as internal engine wording, for example `Concilium · Loop Engine`.
- Add a lane preview row above the run button:

```html
<div class="hint" id="routepreview">填写任务后可预检 lane 和席位状态。</div>
```

- Add a `预检` button that calls `/api/preflight`.
- Show each seat's capacity status inside the existing seat card:

```html
<div class="meta capacity" data-seat="${s.seat}">capacity: unknown</div>
```

- If preflight status is `blocked`, disable the run button and show the blocking seats.
- If preflight status is `warn`, keep run enabled and show the warning.

- [ ] **Step 5: Verify**

```bash
python3 -m unittest skills.loop-engine.tests.test_web_preflight
python3 -m unittest discover -s skills/loop-engine/tests
python3 skills/loop-engine/web/server.py --port 8765 --no-open
```

Manual smoke in browser:

- Open `http://127.0.0.1:8765/`.
- Enter repo path and task.
- Click `预检`.
- Confirm lane, required seats, and capacity statuses are visible before `开跑`.
- Stop server with Ctrl-C.

- [ ] **Step 6: Commit**

```bash
git add skills/loop-engine/web/server.py skills/loop-engine/web/index.html skills/loop-engine/tests/test_web_preflight.py
git commit -m "feat(concilium): expose preflight in web ui"
```

---

### Task 9: Live Smoke Matrix

**Files:**
- Create: `skills/loop-engine/bin/smoke-concilium-phase3.sh`
- Modify: `docs/loop-engine/phase3-lane-routing.md`

- [ ] **Step 1: Create smoke script**

Create executable `skills/loop-engine/bin/smoke-concilium-phase3.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TMP="${TMPDIR:-/tmp}/concilium-phase3-smoke"
rm -rf "$TMP"
git -C "$ROOT" worktree add --detach "$TMP" HEAD >/dev/null
cleanup() {
  git -C "$ROOT" worktree remove --force "$TMP" >/dev/null 2>&1 || true
}
trap cleanup EXIT

python3 "$ROOT/skills/loop-engine/bin/concilium-run.py" \
  --repo "$TMP" \
  --task "Fix one typo in docs/loop-engine/agent-moa-positioning.md." \
  --test-cmd "true" \
  --dry-run \
  --print-route \
  | python3 -m json.tool >/tmp/concilium-phase3-fast-preview.json

python3 "$ROOT/skills/loop-engine/bin/concilium-run.py" \
  --repo "$TMP" \
  --task "Change config routing behavior and update tests." \
  --test-cmd "true" \
  --dry-run \
  --print-route \
  | python3 -m json.tool >/tmp/concilium-phase3-review-preview.json

python3 "$ROOT/skills/loop-engine/bin/concilium-run.py" \
  --repo "$TMP" \
  --task "Design a security-sensitive migration across multiple modules." \
  --test-cmd "true" \
  --dry-run \
  --print-route \
  | python3 -m json.tool >/tmp/concilium-phase3-roundtable-preview.json

rg -n '"lane": "fast"' /tmp/concilium-phase3-fast-preview.json
rg -n '"lane": "review"' /tmp/concilium-phase3-review-preview.json
rg -n '"lane": "roundtable"' /tmp/concilium-phase3-roundtable-preview.json

echo "Concilium Phase 3 smoke passed"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x skills/loop-engine/bin/smoke-concilium-phase3.sh
```

- [ ] **Step 3: Verify**

```bash
bash skills/loop-engine/bin/smoke-concilium-phase3.sh
python3 -m unittest discover -s skills/loop-engine/tests
```

Expected: smoke prints `Concilium Phase 3 smoke passed` and tests pass.

- [ ] **Step 4: Commit**

```bash
git add skills/loop-engine/bin/smoke-concilium-phase3.sh docs/loop-engine/phase3-lane-routing.md
git commit -m "test(concilium): add phase3 routing smoke"
```

---

### Task 10: Phase 3 Closeout Report

**Files:**
- Create: `docs/loop-engine/phase3-closeout-2026-06-29.md`
- Modify: `docs/loop-engine/mvp-closeout-2026-06-29.md`

- [ ] **Step 1: Run final verification**

```bash
python3 -m unittest discover -s skills/loop-engine/tests
bash skills/loop-engine/bin/smoke-roundtable-speedup.sh
bash skills/loop-engine/bin/smoke-concilium-phase3.sh
python3 skills/loop-engine/bin/benchmark-roundtable.py --dry-run --out /tmp/concilium-phase3-final-dry
git diff --check
```

Expected:

- Unit tests pass.
- Both smoke scripts pass.
- Final dry benchmark writes valid `records.jsonl` and `summary.md`.
- `git diff --check` has no output.

- [ ] **Step 2: Write closeout report**

Create `docs/loop-engine/phase3-closeout-2026-06-29.md`:

```md
# Concilium Phase 3 Closeout

## Conclusion

Phase 3 is complete when this report says all acceptance criteria below passed.

## What Phase 3 Added

- Layered configuration: bundled defaults, user config, project config.
- Capacity status model with redaction and blocking semantics.
- Preflight gate before agent execution.
- Pure lane router for Fast, Review, and Roundtable.
- Routed `concilium-run.py` wrapper.
- Router-aware benchmark path.
- WebUI preflight and visible capacity status.

## Evidence

| Check | Result | Evidence Path |
|---|---|---|
| Unit tests | PASS | paste command output summary |
| Roundtable smoke | PASS | paste command output summary |
| Phase 3 smoke | PASS | paste command output summary |
| Dry benchmark | PASS | `/tmp/concilium-phase3-final-dry/summary.md` |

## Assumptions

- Capacity probes are best-effort unless a provider exposes a fresh, explicit quota source.
- Unknown capacity warns but does not block.
- Hard-exhausted required seats block before execution.

## Risks

- Some providers may not expose reliable local quota information.
- WebUI status can become stale after the configured status age.
- Provider APIs and CLI outputs can change without notice.

## Next Decision Trigger

Phase 4 should start only after a user can run `concilium-run.py --dry-run --print-route` and see the same route/preflight decision in WebUI.
```

Replace `paste command output summary` with exact summaries from Step 1, such as `Ran 68 tests in 1.2s OK`.

- [ ] **Step 3: Update MVP closeout pointer**

Append to `docs/loop-engine/mvp-closeout-2026-06-29.md`:

```md
## Phase 3 Follow-up

Concilium Phase 3 closeout is tracked in `docs/loop-engine/phase3-closeout-2026-06-29.md`.
```

- [ ] **Step 4: Commit**

```bash
git add docs/loop-engine/phase3-closeout-2026-06-29.md docs/loop-engine/mvp-closeout-2026-06-29.md
git commit -m "docs(concilium): close phase3 routing work"
```

---

## Adversarial Review Checklist

Before declaring Phase 3 complete, answer each item with evidence:

- [ ] Can a project override the default Fast Lane model without editing bundled defaults?
- [ ] Can a user override defaults without creating a project file?
- [ ] Does project config win over user config?
- [ ] Does Review Lane reject same-seat executor/reviewer?
- [ ] Does hard-exhausted required capacity block before execution?
- [ ] Does unknown capacity warn without pretending to know quota?
- [ ] Does the router avoid silent downgrade from Review to Fast?
- [ ] Does the router escalate ambiguous/security-sensitive tasks to Roundtable?
- [ ] Does `concilium-run.py --dry-run --print-route` avoid seat calls?
- [ ] Does live execution still work for existing Review Lane?
- [ ] Does WebUI show route and capacity before starting a run?
- [ ] Do logs avoid tokens, cookies, API keys, and account emails?
- [ ] Does final benchmark still compare baseline Kimi, Review Lane, and Roundtable?

## Recommended Execution Order

1. Task 1: config layer.
2. Task 2: capacity status model.
3. Task 3: provider probe spike.
4. Task 4: preflight gate.
5. Task 5: pure router.
6. Task 6: routed run wrapper.
7. Task 7: benchmark router mode.
8. Task 8: WebUI preflight.
9. Task 9: smoke matrix.
10. Task 10: closeout report.

Do not start Task 8 before Tasks 1-6 are passing. UI should display tested decisions, not invent them.
