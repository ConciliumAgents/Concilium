# Concilium Dogfood Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the three Concilium product defects exposed by the FBA fix-verification dogfood: brittle Hermes verdict parsing, misleading read-only Budget Guard payloads, and missing machine-readable verdict aggregation in `roundtable.json`.

**Architecture:** Keep the fix inside the existing Loop Engine control plane. Seat scripts continue to own process execution and exit codes; Budget Guard continues to own confirmation payload semantics; conductor state remains the single session metadata surface consumed by reports and UI. The implementation adds small, tested normalization helpers instead of changing lane routing or weakening BLOCK/PASS rules.

**Tech Stack:** Bash seat utility library, Python standard library, existing `unittest` suite, existing Concilium runtime modules.

---

## First Principles

1. **Machine-readable evidence must match human evidence.** If a native seat writes an explicit `VERDICT: BLOCK`, Concilium must record BLOCK, even if the seat formats the line as a Markdown heading.
2. **Read-only means no target-system mutation.** A read-only Audit Lane confirmation payload should not imply arbitrary source/config edits are expected. If artifact/report writes are allowed, that boundary must be named separately.
3. **Session metadata is audit evidence.** `roundtable.json` must identify actual participants, seat timings, and per-seat verdicts so a later reader does not have to scrape minutes by hand.
4. **Do not lower the bar to make dogfood pass.** FBA's P0/P1 findings remain BLOCK. This plan fixes Concilium's evidence and semantics, not the FBA project.

## Non-Goals

- Do not modify `/Users/melee/Documents/amazon-fba-workflow`.
- Do not rotate or remove the FBA Sorftime credential in this branch.
- Do not change route selection, default seats, or Budget Guard hard-block behavior.
- Do not implement Plan Review multi-round host-loop integration here; that is a separate product enhancement.

## Files

- Modify: `skills/loop-engine/bin/_lib.sh`
  - Accept explicit verdict lines formatted as Markdown headings.
- Modify: `skills/loop-engine/tests/test_verdict_parser.py`
  - Cover heading verdicts and prose false positives.
- Modify: `skills/loop-engine/bin/budget_guard.py`
  - Add read-only payload semantics while preserving explicit override behavior.
- Modify: `skills/loop-engine/tests/test_budget_guard.py`
  - Cover read-only Audit Lane confirmation payloads.
- Modify: `skills/loop-engine/bin/conductor.py`
  - Record review-mode seat verdicts in `roundtable.json`.
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
  - Add `verdict` to Audit Lane and Plan Review Lane `seat_results`.
- Modify: `skills/loop-engine/tests/test_conductor_core.py`
  - Cover `roundtable.json.verdicts` and `seat_verdicts`.
- Modify: `skills/loop-engine/tests/test_concilium_lanes.py`
  - Cover lane-level `seat_results[*].verdict`.
- Modify: `docs/loop-engine/concilium-menu-bar-contract.md`
  - Document read-only confirmation payload fields.
- Modify: `docs/loop-engine/phase3-lane-routing.md`
  - Document `roundtable.json.seat_verdicts`.

---

### Task 1: Parse Markdown Heading Verdict Lines

**Files:**
- Modify: `skills/loop-engine/bin/_lib.sh`
- Test: `skills/loop-engine/tests/test_verdict_parser.py`

- [ ] **Step 1: Add failing verdict parser tests**

Append these tests to `VerdictParserTests` in `skills/loop-engine/tests/test_verdict_parser.py`:

```python
    def test_accepts_markdown_heading_block_verdict_line(self):
        result = self.run_parser("Findings above\n## VERDICT: BLOCK\n")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("BLOCK", result.stdout)

    def test_accepts_bold_markdown_heading_pass_verdict_line(self):
        result = self.run_parser("Findings above\n### **VERDICT: PASS**\n")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_rejects_verdict_inside_prose_sentence(self):
        result = self.run_parser("The report title says ## VERDICT: BLOCK in prose.\n")
        self.assertEqual(result.returncode, 1, result.stdout)
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_verdict_parser.py
```

Expected before implementation: the two heading verdict tests fail because `_lib.sh` accepts only plain or bold verdict lines.

- [ ] **Step 3: Implement a shared verdict-line regex**

In `skills/loop-engine/bin/_lib.sh`, add these constants immediately above `loop_verdict_exit()`:

```bash
LOOP_VERDICT_LINE_RE='^[[:space:]]*(#{1,6}[[:space:]]*)?(\*\*)?VERDICT:[[:space:]]*(PASS|BLOCK)(\*\*)?[[:space:]]*$'
LOOP_VERDICT_PASS_RE='^[[:space:]]*(#{1,6}[[:space:]]*)?(\*\*)?VERDICT:[[:space:]]*PASS(\*\*)?[[:space:]]*$'
LOOP_VERDICT_BLOCK_RE='^[[:space:]]*(#{1,6}[[:space:]]*)?(\*\*)?VERDICT:[[:space:]]*BLOCK(\*\*)?[[:space:]]*$'
```

Then replace the `line="$(grep ...)"` expression inside `loop_verdict_exit()` with:

```bash
  line="$(grep -aiE "$LOOP_VERDICT_LINE_RE" "$f" | tail -1 || true)"
```

Finally, update `loop_codex_verdict()` to reuse the same PASS/BLOCK regexes:

```bash
  if grep -aiqE "$LOOP_VERDICT_BLOCK_RE" "$f"; then loop_warn "裁决: BLOCK (显式 VERDICT)"; return 2; fi
  if grep -aiqE "$LOOP_VERDICT_PASS_RE"  "$f"; then loop_log  "裁决: PASS (显式 VERDICT)"; return 0; fi
```

Do not add fuzzy matching for lowercase words like `verdict block`, prose sentences, or headings that omit the `VERDICT:` prefix.

- [ ] **Step 4: Run verdict parser tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_verdict_parser.py
```

Expected: all verdict parser tests pass.

- [ ] **Step 5: Commit task 1**

```bash
git add skills/loop-engine/bin/_lib.sh skills/loop-engine/tests/test_verdict_parser.py
git commit -m "fix(concilium): parse markdown heading verdicts"
```

---

### Task 2: Make Read-Only Budget Guard Payloads Honest

**Files:**
- Modify: `skills/loop-engine/bin/budget_guard.py`
- Test: `skills/loop-engine/tests/test_budget_guard.py`

- [ ] **Step 1: Add the failing read-only payload test**

Append this test to `BudgetGuardTests` in `skills/loop-engine/tests/test_budget_guard.py`:

```python
    def test_read_only_audit_confirmation_payload_marks_target_files_not_modified(self):
        preview = {
            "request_fingerprint": "audit123",
            "mode": "live_run",
            "route": {
                "lane": "audit",
                "reason": "read-only audit uses reviewer-only lane with artifact gate",
                "required_seats": ["claude", "hermes", "kimi"],
            },
            "request": {
                "mode": "live_run",
                "signals": {
                    "read_only": True,
                    "allowed_write_paths": ["docs/audits/report.md"],
                    "required_artifact_paths": ["docs/audits/report.md"],
                },
            },
            "signals": {
                "read_only": True,
                "allowed_write_paths": ["docs/audits/report.md"],
                "required_artifact_paths": ["docs/audits/report.md"],
            },
            "capacity": [record("claude", "unknown"), record("hermes", "unknown"), record("kimi", "unknown")],
            "preflight": {
                "status": "warn",
                "required_seats": ["claude", "hermes", "kimi"],
                "blocking_seats": [],
                "warnings": ["capacity unknown"],
            },
        }

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        payload = result["confirmation_payload"]
        self.assertFalse(payload["files_may_be_modified"])
        self.assertTrue(payload["read_only_task"])
        self.assertEqual(payload["allowed_write_paths"], ["docs/audits/report.md"])
        self.assertEqual(payload["required_artifact_paths"], ["docs/audits/report.md"])
```

- [ ] **Step 2: Add explicit override coverage**

Append this test to preserve backward compatibility for callers that intentionally set `files_may_be_modified`:

```python
    def test_explicit_files_may_be_modified_override_wins_for_read_only_payload(self):
        preview = {
            "request_fingerprint": "audit124",
            "mode": "live_run",
            "route": {"lane": "audit", "required_seats": ["claude"]},
            "request": {"mode": "live_run", "signals": {"read_only": True}},
            "signals": {"read_only": True},
            "files_may_be_modified": True,
            "capacity": [record("claude", "unknown")],
            "preflight": {"status": "warn", "required_seats": ["claude"], "blocking_seats": [], "warnings": []},
        }

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertTrue(result["confirmation_payload"]["files_may_be_modified"])
        self.assertTrue(result["confirmation_payload"]["read_only_task"])
```

- [ ] **Step 3: Add route-inferred read-only coverage**

Append this test to cover the common path where the router selects Audit Lane from task text but no caller explicitly injects a `read_only` signal:

```python
    def test_inferred_audit_lane_without_read_only_signal_is_read_only_in_payload(self):
        preview = {
            "request_fingerprint": "audit125",
            "mode": "live_run",
            "route": {"lane": "audit", "required_seats": ["claude"]},
            "request": {"mode": "live_run"},
            "capacity": [record("claude", "unknown")],
            "preflight": {"status": "warn", "required_seats": ["claude"], "blocking_seats": [], "warnings": []},
        }

        result = budget_guard.evaluate_budget_guard(preview, mode="live_run")

        self.assertFalse(result["confirmation_payload"]["files_may_be_modified"])
        self.assertTrue(result["confirmation_payload"]["read_only_task"])
```

- [ ] **Step 4: Run the failing budget tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_budget_guard.py
```

Expected before implementation: `read_only_task`, `allowed_write_paths`, and `required_artifact_paths` are missing, and `files_may_be_modified` remains `True` for the read-only audit preview.

- [ ] **Step 5: Add signal and read-only lane helpers**

In `skills/loop-engine/bin/budget_guard.py`, add these helpers above `_files_may_be_modified()`:

```python
def _signals(preview, request):
    signals = {}
    if isinstance(request.get("signals"), dict):
        signals.update(request.get("signals") or {})
    if isinstance(preview.get("signals"), dict):
        signals.update(preview.get("signals") or {})
    return signals


def _is_read_only_task(preview, request):
    route = preview.get("route") or {}
    lane = str(route.get("lane", ""))
    return lane in {"audit", "plan_review"}
```

Audit Lane and Plan Review Lane are read-only lanes by contract. The helper must rely on the selected lane, not on optional caller-provided signals, because natural-language routing can select either lane without writing `read_only` or `plan_review` back into `signals`.

- [ ] **Step 6: Update file-modification semantics**

Replace `_files_may_be_modified()` with:

```python
def _files_may_be_modified(preview, request, mode=None):
    if "files_may_be_modified" in preview:
        return bool(preview.get("files_may_be_modified"))
    if "files_may_be_modified" in request:
        return bool(request.get("files_may_be_modified"))
    if _is_read_only_task(preview, request):
        return False
    return mode == "live_run" or preview.get("mode") == "live_run" or request.get("mode") == "live_run"
```

This preserves explicit overrides and the existing default for non-read-only live runs.

- [ ] **Step 7: Add boundary fields to the confirmation payload**

In `confirmation_payload()`, after `route` and `request` are defined, compute:

```python
    signals = _signals(preview, request)
```

Then add these fields to the `payload` dict:

```python
        "read_only_task": _is_read_only_task(preview, request),
        "allowed_write_paths": list(signals.get("allowed_write_paths") or []),
        "required_artifact_paths": list(signals.get("required_artifact_paths") or []),
```

Place them near `files_may_be_modified` so UI consumers can render the write boundary together.

- [ ] **Step 8: Run budget tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_budget_guard.py
```

Expected: all budget guard tests pass.

- [ ] **Step 9: Commit task 2**

```bash
git add skills/loop-engine/bin/budget_guard.py skills/loop-engine/tests/test_budget_guard.py
git commit -m "fix(concilium): clarify read-only budget payloads"
```

---

### Task 3: Persist Per-Seat Verdict Metadata

**Files:**
- Modify: `skills/loop-engine/bin/conductor.py`
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
- Test: `skills/loop-engine/tests/test_conductor_core.py`
- Test: `skills/loop-engine/tests/test_concilium_lanes.py`

- [ ] **Step 1: Extend the conductor metadata test**

In `test_run_records_seat_timings_in_roundtable_state()` in `skills/loop-engine/tests/test_conductor_core.py`, add these assertions after the existing `seat_timings` assertions:

```python
        self.assertEqual(state["verdicts"], ["PASS"])
        self.assertEqual(
            state["seat_verdicts"],
            [
                {
                    "iter": 1,
                    "seat": "hermes",
                    "mode": "review",
                    "rc": 0,
                    "verdict": "PASS",
                }
            ],
        )
```

- [ ] **Step 2: Add a BLOCK metadata regression test**

Append this test to `ConductorCoreTests`:

```python
    def test_review_block_is_recorded_in_roundtable_verdict_metadata(self):
        reporter = QuietReporter()
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)

            def fake_run_seat(agent, mode, repo_arg, brief="", extra=None, provider="", model=""):
                if mode == "plan":
                    return 0, '```json\n[{"agent":"kimi","subtask":"edit tracked.md"}]\n```'
                if mode == "exec":
                    pathlib.Path(repo_arg, "tracked.md").write_text("base\nchanged\n", encoding="utf-8")
                    return 0, "edited"
                if mode == "review":
                    return 2, "Finding\nVERDICT: BLOCK\n"
                return self.fail(f"unexpected call: {agent} {mode}")

            with ConductorPatch(self, repo, fake_run_seat):
                rc = conductor.run(str(repo), "Edit tracked.md", max_iters=1, reporter=reporter)

            state = json.loads(
                (repo / ".roundtable" / "sessions" / "unit-session" / "roundtable.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(rc, 2)
        self.assertEqual(state["verdicts"], ["BLOCK"])
        self.assertEqual(state["seat_verdicts"][0]["seat"], "hermes")
        self.assertEqual(state["seat_verdicts"][0]["mode"], "review")
        self.assertEqual(state["seat_verdicts"][0]["verdict"], "BLOCK")
```

- [ ] **Step 3: Add lane `seat_results` verdict assertions**

In `test_audit_lane_sets_participants_to_actual_seated_reviewers()` in `skills/loop-engine/tests/test_concilium_lanes.py`, add:

```python
        self.assertEqual([row["verdict"] for row in result["seat_results"]], ["PASS", "PASS"])
```

In `test_plan_review_lane_initializes_session_and_sets_actual_participants()`, add:

```python
        self.assertEqual([row["verdict"] for row in result["seat_results"]], ["PASS", "PASS", "PASS"])
```

- [ ] **Step 4: Run the failing metadata tests**

Run:

```bash
python3 -m unittest \
  skills/loop-engine/tests/test_conductor_core.py \
  skills/loop-engine/tests/test_concilium_lanes.py
```

Expected before implementation: the new `verdicts`, `seat_verdicts`, and `seat_results[*].verdict` assertions fail.

- [ ] **Step 5: Add a conductor verdict recorder**

In `skills/loop-engine/bin/conductor.py`, add this helper above `_append_seat_timing()`:

```python
def _record_review_verdict(state: dict, iteration: int, agent: str, mode: str, rc: int) -> None:
    if mode != "review":
        return
    verdict = VERDICT_MAP.get(int(rc), "ERR")
    row = {
        "iter": iteration,
        "seat": agent,
        "mode": mode,
        "rc": int(rc),
        "verdict": verdict,
    }
    state.setdefault("seat_verdicts", []).append(row)
    state["verdicts"] = [
        item.get("verdict", "ERR")
        for item in state.get("seat_verdicts", [])
        if item.get("mode") == "review"
    ]
```

Then call it inside `_append_seat_timing()` immediately after appending the timing row:

```python
        _record_review_verdict(state, iteration, agent, mode, rc)
```

This records only review-seat verdicts, so planner/executor rc values do not pollute the audit verdict list.

- [ ] **Step 6: Add a lane verdict helper**

In `skills/loop-engine/bin/concilium_lanes.py`, add this helper near the existing small helper functions:

```python
def _verdict_for_rc(rc: int) -> str:
    return conductor.VERDICT_MAP.get(int(rc), "ERR")
```

Then add `"verdict": _verdict_for_rc(src),` to Audit Lane `seat_results.append(...)` and `"verdict": _verdict_for_rc(rc),` to Plan Review Lane `result = {...}`.

- [ ] **Step 7: Run metadata tests**

Run:

```bash
python3 -m unittest \
  skills/loop-engine/tests/test_conductor_core.py \
  skills/loop-engine/tests/test_concilium_lanes.py
```

Expected: both test modules pass.

- [ ] **Step 8: Commit task 3**

```bash
git add \
  skills/loop-engine/bin/conductor.py \
  skills/loop-engine/bin/concilium_lanes.py \
  skills/loop-engine/tests/test_conductor_core.py \
  skills/loop-engine/tests/test_concilium_lanes.py
git commit -m "fix(concilium): persist native seat verdict metadata"
```

---

### Task 4: Document the Dogfood Fix Contract and Verify

**Files:**
- Modify: `docs/loop-engine/concilium-menu-bar-contract.md`
- Modify: `docs/loop-engine/phase3-lane-routing.md`

- [ ] **Step 1: Update the menu-bar payload contract**

In `docs/loop-engine/concilium-menu-bar-contract.md`, near the Budget Guard or run-guard payload section, add:

```markdown
For read-only Audit Lane and Plan Review Lane runs, `run_guard.confirmation_payload.files_may_be_modified` means target project files may be edited outside the declared review boundary. It must be `false` when the route is read-only and no caller explicitly overrides it. Report/artifact writes are represented separately through `read_only_task`, `allowed_write_paths`, and `required_artifact_paths` so the UI can say "review is read-only; this report path may be written" instead of warning about arbitrary file edits.
```

- [ ] **Step 2: Update lane-routing metadata docs**

In `docs/loop-engine/phase3-lane-routing.md`, near the existing `roundtable.json.participants` paragraph, add:

```markdown
`roundtable.json.seat_verdicts` records every review-seat verdict call as structured evidence rows: `iter`, `seat`, `mode`, `rc`, and `verdict`. `roundtable.json.verdicts` is the ordered review-call summary derived from those rows, not a replacement for lane return codes or final `conclusion.md` status. Audit Lane and Plan Review Lane reports should use these fields before scraping minute files.
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
python3 -m unittest \
  skills/loop-engine/tests/test_verdict_parser.py \
  skills/loop-engine/tests/test_budget_guard.py \
  skills/loop-engine/tests/test_conductor_core.py \
  skills/loop-engine/tests/test_concilium_lanes.py
```

Expected: all focused tests pass.

- [ ] **Step 4: Run full verification**

Run:

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
bash -n roundtable
python3 -m py_compile \
  skills/loop-engine/bin/budget_guard.py \
  skills/loop-engine/bin/conductor.py \
  skills/loop-engine/bin/concilium_lanes.py
git diff --check
```

Expected: full test suite reports `OK`; the syntax, compile, and diff checks exit 0 with no output.

- [ ] **Step 5: Run a local route/payload smoke**

Run:

```bash
python3 skills/loop-engine/bin/concilium-run.py \
  --repo /Users/melee/Documents/agents \
  --task "Read-only audit smoke for Concilium dogfood fixes. Do not modify source files." \
  --print-route \
  --seats claude,hermes,kimi \
  --signals-json '{"read_only":true,"risk":"medium","file_count":3,"allowed_write_paths":["docs/audits/concilium-dogfood-fix-smoke.md"],"required_artifact_paths":["docs/audits/concilium-dogfood-fix-smoke.md"]}'
```

Expected JSON contains:

```json
"lane": "audit"
"required_seats": ["claude", "hermes", "kimi"]
```

Then run this small Budget Guard payload check:

```bash
python3 - <<'PY'
import importlib.util
from pathlib import Path

root = Path("/Users/melee/Documents/agents")
module = root / "skills" / "loop-engine" / "bin" / "budget_guard.py"
spec = importlib.util.spec_from_file_location("budget_guard", module)
budget_guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget_guard)
preview = {
    "request_fingerprint": "smoke",
    "mode": "live_run",
    "route": {"lane": "audit", "required_seats": ["claude"]},
    "request": {"mode": "live_run", "signals": {"read_only": True}},
    "signals": {"read_only": True},
    "capacity": [{"seat": "claude", "provider": "anthropic", "model": "opus", "status": "unknown", "source": "smoke", "reason": "unknown", "checked_at": "", "reset_at": ""}],
    "preflight": {"status": "warn", "required_seats": ["claude"], "blocking_seats": [], "warnings": []},
}
payload = budget_guard.confirmation_payload(preview, mode="live_run")
assert payload["read_only_task"] is True, payload
assert payload["files_may_be_modified"] is False, payload
print("payload ok")
PY
```

Expected output:

```text
payload ok
```

- [ ] **Step 6: Commit task 4**

```bash
git add \
  docs/loop-engine/concilium-menu-bar-contract.md \
  docs/loop-engine/phase3-lane-routing.md
git commit -m "docs(concilium): document dogfood fix semantics"
```

---

## Self-Review Checklist

- [ ] Hermes output like `## VERDICT: BLOCK` maps to rc 2 instead of ERR.
- [ ] Prose containing `## VERDICT: BLOCK` inside a sentence is still rejected.
- [ ] `--yes` and Budget Guard hard-block behavior are unchanged.
- [ ] Read-only Audit Lane confirmation payloads set `files_may_be_modified=false` unless explicitly overridden.
- [ ] Route-inferred Audit Lane and Plan Review Lane payloads are read-only even when optional `signals.read_only` is absent.
- [ ] Allowed report/artifact paths remain visible in the confirmation payload.
- [ ] `roundtable.json.participants` remains actual seated native seats.
- [ ] `roundtable.json.seat_timings` remains unchanged except for normal added timings.
- [ ] `roundtable.json.seat_verdicts` and `roundtable.json.verdicts` are populated from review-seat rc values.
- [ ] Audit Lane and Plan Review Lane `seat_results` include `verdict`.
- [ ] Full unit suite, syntax checks, py_compile, route smoke, and diff check pass.

## Roundtable Review Command

Review this plan through Concilium Plan Review Lane before implementation:

```bash
python3 skills/loop-engine/bin/concilium-run.py \
  --repo /Users/melee/Documents/agents \
  --task "方案评审，只评不改。请审核 docs/superpowers/plans/2026-06-30-concilium-dogfood-fixes.md。重点检查：是否只修 dogfood 暴露的 Concilium 问题、是否保持 P0/P1 BLOCK 严格性、是否正确处理 Hermes heading verdict、read-only Budget Guard 语义、roundtable.json verdict metadata，以及是否存在过度设计或破坏现有 UI/CLI 契约的风险。" \
  --live \
  --yes \
  --timeout 900 \
  --seats claude,hermes,kimi \
  --signals-json '{"plan_review":true,"plan_path":"docs/superpowers/plans/2026-06-30-concilium-dogfood-fixes.md","risk":"medium","file_count":6,"security_sensitive":false,"ambiguous":false}'
```

Expected:

- route: `plan_review`
- required seats: `claude`, `hermes`, `kimi`
- all selected seats run in `review` mode
- status is `passed`, or `blocked` with concrete plan edits required before implementation
