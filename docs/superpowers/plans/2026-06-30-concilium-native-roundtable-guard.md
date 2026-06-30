# Concilium Native Roundtable Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` for each code task and `superpowers:verification-before-completion` before claiming completion. If a reviewer returns `VERDICT: BLOCK`, revise this plan only, then re-run plan review. Stop after 3 review rounds if blockers remain.

**Goal:** Prevent Concilium dogfood and read-only audits from silently degrading into same-source Codex subagent review, and make the visible session metadata match the actual native seats invoked.

**Architecture:** Keep Concilium's control plane in the existing Python and shell modules. Do not add a dependency or a second orchestrator. The fix changes the default lane configuration, exposes explicit seat selection at the CLI boundary, records actual participants from the invoked seats, keeps read-only audits on reviewer-only paths, adds a small launcher diagnostic, and redacts credential-like content before seat transcripts are published into `.roundtable/minutes`.

**Tech Stack:** Python standard library, existing shell seat wrappers, existing `unittest` suite, existing `capacity_status.redact()`, no new runtime dependencies.

---

## First Principles

1. **The product is heterogeneous judgment.** Concilium's value comes from independently invoked native agent shells. Multiple Codex subagents are useful internal help, but they are not a Concilium roundtable.
2. **Defaults express the product contract.** A user who says "roundtable audit" should get native heterogeneous seats by default. Codex may be opt-in, not an implicit Audit Lane default.
3. **Read-only review is not maker work.** Architecture or memory audits must not pass through `plan -> exec -> review`; reviewer seats inspect and report.
4. **Accounting must reflect invocation.** `participants`, event `seat` records, and `seat_timings` must name the seats actually called. Planned seats, unavailable seats, and host-side subagents must not be reported as if they spent external quota.
5. **Operator tooling must reveal stale launchers.** A successful commit in an isolated worktree is not deployed if `/Users/melee/.local/bin/roundtable` still points at old `main`. The tool must make its resolved path and commit visible.
6. **Local scratch can still leak secrets.** Reports already redact tails; raw minutes should not preserve credential-like strings by default. Exact raw capture is an explicit debug mode, not normal operation.

## Non-Goals

- Do not remove Codex as a valid explicitly selected seat.
- Do not choose a native menu bar UI framework in this patch.
- Do not mutate provider/global config such as `~/.claude.json`, `~/.codex/config.toml`, Kimi config, Hermes config, or CodexBar config.
- Do not make old unmerged worktree code magically active without an explicit deploy step; make stale entrypoints diagnosable and then merge/repoint intentionally.

---

## Files

- Modify: `skills/loop-engine/config/concilium.defaults.json`
- Modify: `skills/loop-engine/bin/lane_router.py`
- Modify: `skills/loop-engine/bin/concilium-run.py`
- Modify: `skills/loop-engine/bin/concilium_runtime.py`
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
- Modify: `skills/loop-engine/bin/conductor.py`
- Modify: `skills/loop-engine/bin/review-lane.py`
- Modify: `skills/loop-engine/bin/_lib.sh`
- Create: `skills/loop-engine/bin/redact-text.py`
- Modify: `skills/loop-engine/bin/seat-claude.sh`
- Modify: `skills/loop-engine/bin/seat-codex.sh`
- Modify: `skills/loop-engine/bin/seat-hermes.sh`
- Modify: `skills/loop-engine/bin/seat-kimi.sh`
- Modify: `roundtable`
- Modify: `skills/loop-engine/tests/test_lane_router.py`
- Modify: `skills/loop-engine/tests/test_concilium_run.py`
- Modify: `skills/loop-engine/tests/test_concilium_runtime.py`
- Modify: `skills/loop-engine/tests/test_concilium_lanes.py`
- Modify: `skills/loop-engine/tests/test_conductor_core.py`
- Create: `skills/loop-engine/tests/test_redact_text.py`
- Modify: `docs/loop-engine/phase3-lane-routing.md`
- Modify: `docs/loop-engine/phase4-closeout-2026-06-29.md`

---

## Success Criteria

- Default Audit Lane required seats are `["claude", "hermes", "kimi"]`.
- Default Plan Review required seats are `["claude", "hermes", "kimi"]`.
- `codex` appears in Audit Lane or Plan Review only when explicitly selected through config, WebUI, API params, or CLI `--seats`.
- `concilium-run.py --seats claude,hermes,kimi ...` reaches `concilium_runtime` as `params["seats"] == ["claude", "hermes", "kimi"]`.
- Audit Lane and Plan Review Lane call all selected seats in `review` mode and never call `exec`.
- `.roundtable/sessions/<sid>/roundtable.json.participants` equals the actual selected seats after `write_roster()` filters availability.
- `seat_timings` and emitted `seat` events are consistent: no participant is shown as invoked unless a native seat runner was actually called.
- `roundtable --version` prints the resolved script path, repo root, branch, commit, and whether the entrypoint is a symlink.
- `roundtable --doctor` preserves the current seat-probe behavior and adds launcher diagnostics without hiding the roster output.
- Seat transcript files written to `.roundtable/minutes` redact credential-like strings by default; setting `LOOP_KEEP_RAW_MINUTES=1` preserves raw files with a `.raw` suffix for local debugging.
- Focused tests and the full loop-engine unit suite pass.

---

## Implementation Order

### Task 1: Lock The Desired Defaults With Failing Tests

**Files:**
- Modify: `skills/loop-engine/tests/test_lane_router.py`
- Modify: `skills/loop-engine/tests/test_concilium_runtime.py`
- Modify: `skills/loop-engine/config/concilium.defaults.json`

- [ ] Step 1: Update test fixtures first.

In `skills/loop-engine/tests/test_lane_router.py`, change `base_config()`:

```python
"audit": {
    "default_reviewer": "claude",
    "seats": ["claude", "hermes", "kimi"],
    "allowed_report_paths": ["docs/audits/*.md"],
},
"plan_review": {"seats": ["claude", "hermes", "kimi"], "max_rounds": 3},
```

Then update `test_read_only_audit_routes_to_audit_lane`:

```python
self.assertEqual(result["required_seats"], ["claude", "hermes", "kimi"])
self.assertNotIn("codex", result["required_seats"])
```

Add this test:

```python
def test_plan_review_defaults_to_native_heterogeneous_seats_without_codex(self):
    result = lane_router.route_task(
        "审核执行方案 docs/superpowers/plans/example.md，成员 BLOCK 后修改方案并复审",
        {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
        self.base_config(),
    )

    self.assertEqual(result["lane"], "plan_review")
    self.assertEqual(result["required_seats"], ["claude", "hermes", "kimi"])
    self.assertNotIn("codex", result["required_seats"])
```

In `skills/loop-engine/tests/test_concilium_runtime.py`, update `BASE_CONFIG` the same way. Replace audit-related capacity records that assumed `codex, claude` with `claude, hermes, kimi` unless a test is explicitly about Codex overlay.

Add this regression test near the overlay tests:

```python
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
```

- [ ] Step 2: Run focused tests and confirm they fail before config changes:

```bash
python3 -m unittest \
  skills/loop-engine/tests/test_lane_router.py \
  skills/loop-engine/tests/test_concilium_runtime.py
```

- [ ] Step 3: Update `skills/loop-engine/config/concilium.defaults.json`:

```json
"audit": {
  "default_reviewer": "claude",
  "seats": ["claude", "hermes", "kimi"],
  "allowed_report_paths": ["docs/audits/*.md"]
},
"plan_review": {
  "seats": ["claude", "hermes", "kimi"],
  "max_rounds": 3
}
```

Keep `roundtable.seats` unchanged because it is already `["claude", "hermes", "kimi"]`.

- [ ] Step 4: Re-run the focused tests.

---

### Task 2: Expose Explicit Native Seats On The CLI

**Files:**
- Modify: `skills/loop-engine/bin/concilium-run.py`
- Modify: `skills/loop-engine/tests/test_concilium_run.py`

- [ ] Step 1: Add failing CLI tests.

Add to `ConciliumRunTests`:

```python
def test_run_concilium_passes_explicit_seats_to_adapter(self):
    preview = {"status": "preview", "route": {"lane": "audit", "required_seats": ["claude", "hermes", "kimi"]}}
    with tempfile.TemporaryDirectory() as td, \
            mock.patch.object(concilium_run.concilium_runtime, "run_concilium_adapter", return_value=preview) as adapter:
        concilium_run.run_concilium(
            repo=td,
            task="Read-only audit the architecture.",
            dry_run=True,
            seats=["claude", "hermes", "kimi"],
        )

    self.assertEqual(adapter.call_args.args[0]["seats"], ["claude", "hermes", "kimi"])

def test_cli_seats_comma_list_reaches_adapter(self):
    result = {"status": "preview", "route": {"lane": "audit", "required_seats": ["claude", "hermes", "kimi"]}}
    with tempfile.TemporaryDirectory() as td, \
            mock.patch.object(concilium_run.concilium_runtime, "run_concilium_adapter", return_value=result) as adapter, \
            contextlib.redirect_stdout(io.StringIO()):
        rc = concilium_run.main([
            "--repo", td,
            "--task", "Read-only audit the architecture.",
            "--print-route",
            "--seats", "claude,hermes,kimi",
        ])

    self.assertEqual(rc, 0)
    self.assertEqual(adapter.call_args.args[0]["seats"], ["claude", "hermes", "kimi"])
```

- [ ] Step 2: Add `seats` to `run_concilium()` and parser.

Implementation details:

```python
def _split_seats(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]
```

Add `seats: list[str] | None = None` to `run_concilium(...)`, and include:

```python
"seats": list(seats or []),
```

Add parser option:

```python
parser.add_argument("--seats", default="", help="Comma-separated native seats, for example claude,hermes,kimi.")
```

In `main()`, pass:

```python
"seats": _split_seats(args.seats),
```

- [ ] Step 3: Verify:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_run.py
```

---

### Task 3: Make Participants Equal Actual Invoked Seats

**Files:**
- Modify: `skills/loop-engine/bin/conductor.py`
- Modify: `skills/loop-engine/bin/review-lane.py`
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
- Modify: `skills/loop-engine/tests/test_concilium_lanes.py`
- Modify: `skills/loop-engine/tests/test_conductor_core.py`

- [ ] Step 1: Add `conductor.set_participants(repo, seats)`.

Move the duplicate participant writer from `review-lane.py` into `conductor.py`:

```python
def set_participants(repo: str | Path, seats: list[str]) -> None:
    try:
        state_path = session_dir(str(repo)) / "roundtable.json"
        state = {}
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        state["participants"] = list(seats)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
```

Then replace the manual participant patch block in `conductor.run()` with a call immediately after `write_roster()` and before the `audit_only or is_read_only_audit_task(task)` early return:

```python
seated = write_roster(repo, seats, seat_models)
set_participants(repo, seated)
if audit_only or is_read_only_audit_task(task):
    return _run_read_only_audit(...)
```

Do not leave the later manual JSON patch block in place. The old block sits after the read-only audit early return, so it cannot fix legacy direct `conductor.run(..., audit_only=True)` or task-text read-only audit sessions.

- [ ] Step 2: Make all lane init paths call it after availability filtering.

In `review-lane.py:init_session`, replace local `set_participants(repo, seats)` with:

```python
seated = conductor.write_roster(str(repo), seats=seats, seat_models=seat_models or {})
conductor.set_participants(repo, seated)
```

In `concilium_lanes.run_fast_lane`, after `write_roster`:

```python
seated = conductor.write_roster(...)
conductor.set_participants(str(repo_path), seated)
```

In `concilium_lanes.run_audit_lane` and `run_plan_review_lane`, do the same, and iterate over `seated` rather than the originally requested `seats`. This prevents unavailable seats from being shown as participants or invoked.

- [ ] Step 3: Add tests.

In `skills/loop-engine/tests/test_concilium_lanes.py`, add a test using mocks to prove Audit Lane updates participants and calls only seated seats:

```python
def test_audit_lane_sets_participants_to_actual_seated_reviewers(self):
    with tempfile.TemporaryDirectory() as td, \
            mock.patch.object(concilium_lanes.process_runner, "run_process_group", side_effect=self._successful_process), \
            mock.patch.object(concilium_lanes.conductor, "write_roster", return_value=["claude", "kimi"]) as write_roster, \
            mock.patch.object(concilium_lanes.conductor, "set_participants") as set_participants, \
            mock.patch.object(concilium_lanes.conductor, "timed_run_seat", side_effect=[(0, "VERDICT: PASS"), (0, "VERDICT: PASS")]) as timed_run:
        config = {"lanes": {"audit": {"seats": ["claude", "hermes", "kimi"]}}, "seat_models": {}}
        result = concilium_lanes.run_audit_lane(td, "Read-only audit.", "", config, timeout=12)

    write_roster.assert_called_once()
    set_participants.assert_called_once_with(str(pathlib.Path(td).resolve()), ["claude", "kimi"])
    self.assertEqual([call.args[2:4] for call in timed_run.call_args_list], [("claude", "review"), ("kimi", "review")])
    self.assertEqual([row["seat"] for row in result["seat_results"]], ["claude", "kimi"])
```

In `skills/loop-engine/tests/test_conductor_core.py`, add a direct `set_participants` unit test that writes a minimal `roundtable.json` under a temporary repo and asserts replacement.

- [ ] Step 4: Verify:

```bash
python3 -m unittest \
  skills/loop-engine/tests/test_concilium_lanes.py \
  skills/loop-engine/tests/test_conductor_core.py
```

---

### Task 4: Keep Audit And Plan Review Reviewer-Only

**Files:**
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
- Modify: `skills/loop-engine/tests/test_concilium_runtime.py`
- Modify: `skills/loop-engine/tests/test_concilium_lanes.py`

- [ ] Step 1: Add tests that `audit` and `plan_review` never call `exec`.

In `test_concilium_runtime.py`, update or add assertions around default executor tests:

```python
self.assertEqual([call.args[3] for call in timed_run_seat.call_args_list], ["review", "review", "review"])
```

In `test_concilium_lanes.py`, add a Plan Review test with two reviewers and assert:

```python
self.assertEqual([call.args[2:4] for call in timed_run.call_args_list], [("claude", "review"), ("kimi", "review")])
```

- [ ] Step 2: Ensure implementation iterates only through reviewer calls.

`run_audit_lane` already calls `timed_run_seat(..., seat, "review", ...)`; keep it and make the Task 3 `seated` change there.

`run_plan_review_lane` already calls review mode; make it use `seated` after `write_roster()` and call `conductor.set_participants()`.

- [ ] Step 3: Verify:

```bash
python3 -m unittest \
  skills/loop-engine/tests/test_concilium_runtime.py \
  skills/loop-engine/tests/test_concilium_lanes.py
```

---

### Task 5: Redact Seat Minutes By Default

**Files:**
- Modify: `skills/loop-engine/bin/_lib.sh`
- Create: `skills/loop-engine/bin/redact-text.py`
- Create: `skills/loop-engine/tests/test_redact_text.py`
- Modify: `skills/loop-engine/bin/seat-claude.sh`
- Modify: `skills/loop-engine/bin/seat-codex.sh`
- Modify: `skills/loop-engine/bin/seat-hermes.sh`
- Modify: `skills/loop-engine/bin/seat-kimi.sh`

- [ ] Step 1: Create `redact-text.py` as a tiny executable wrapper over the existing redactor.

Implementation:

```python
#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import capacity_status  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    del argv
    sys.stdout.write(capacity_status.redact(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Set executable mode so tests and shell helpers can invoke it directly:

```bash
chmod +x skills/loop-engine/bin/redact-text.py
```

- [ ] Step 2: Add tests.

Create `skills/loop-engine/tests/test_redact_text.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills" / "loop-engine" / "bin" / "redact-text.py"


class RedactTextTests(unittest.TestCase):
    def test_redacts_query_tokens_and_assignment_secrets(self):
        raw = "SORFTIME_MCP_URL=https://example.invalid/mcp?key=abc123\nOPENAI_API_KEY=sk-test123\n"
        proc = subprocess.run([str(SCRIPT)], input=raw, text=True, capture_output=True, check=True)

        self.assertNotIn("abc123", proc.stdout)
        self.assertNotIn("sk-test123", proc.stdout)
        self.assertIn("[REDACTED]", proc.stdout)


if __name__ == "__main__":
    unittest.main()
```

- [ ] Step 3: Add a shell helper in `_lib.sh`.

Add one shared function to `_lib.sh`; do not duplicate redaction logic in the four seat wrappers. Because `_lib.sh` is sourced, compute the loop-engine bin path inside `_lib.sh` instead of relying on each caller's `SCRIPT_DIR`.

Shared behavior:

```bash
LOOP_BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

loop_publish_minutes() {
  local raw="$1" out="$2"
  if [ "${LOOP_KEEP_RAW_MINUTES:-0}" = "1" ]; then
    cp "${raw}" "${out}.raw"
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 "${LOOP_BIN_DIR}/redact-text.py" <"${raw}" >"${out}" 2>/dev/null || cp "${raw}" "${out}"
  else
    cp "${raw}" "${out}"
  fi
}
```

For each command block that currently redirects directly to `"${OUT}"`, change to:

```bash
RAW="${OUT}.tmp"
( cd "${REPO}" && ... ) >"${RAW}" 2>&1
rc=$?
loop_publish_minutes "${RAW}" "${OUT}"
rm -f "${RAW}"
cat "${OUT}"
```

Do not change verdict parsing paths; parse the redacted `${OUT}`. This preserves PASS/BLOCK semantics while avoiding secret retention in normal minutes.

- [ ] Step 4: Verify:

```bash
python3 -m unittest skills/loop-engine/tests/test_redact_text.py skills/loop-engine/tests/test_capacity_status.py
```

Manual smoke with a fake transcript is enough; do not call real agents only to test redaction.

---

### Task 6: Make The Entrypoint Diagnose Stale Code Without Breaking Seat Probe

**Files:**
- Modify: `roundtable`

- [ ] Step 1: Add `--version` and extend, not replace, `--doctor`.

The current `roundtable --doctor` means "probe seats" via `roster-detect.py`. Keep that behavior. Add launcher diagnostics to stderr for `--doctor`, and add `--version` for launcher-only diagnostics.

Implementation detail: add helper functions after `PROJ`, `SKILL`, and `VENV_PY` are resolved:

```bash
print_launcher_info() {
    echo "Concilium roundtable"
    echo "entrypoint: ${src}"
    if [ -L "${BASH_SOURCE[0]}" ]; then
      echo "symlink_entrypoint: ${BASH_SOURCE[0]}"
      echo "symlink_target: $(readlink "${BASH_SOURCE[0]}")"
    fi
    echo "repo_root: ${PROJ}"
    git -C "${PROJ}" rev-parse --abbrev-ref HEAD 2>/dev/null | sed 's/^/branch: /' || true
    git -C "${PROJ}" rev-parse --short HEAD 2>/dev/null | sed 's/^/commit: /' || true
    git -C "${PROJ}" status --short 2>/dev/null | sed 's/^/status: /' || true
}
```

Then handle flags:

```bash
case "${1:-}" in
  --version)
    print_launcher_info
    exit 0
    ;;
  --doctor)
    print_launcher_info >&2
    exec python3 "$SKILL/bin/roster-detect.py"
    ;;
esac
```

- [ ] Step 2: Update script usage comments.

The header currently says `先探座位: roundtable --doctor`. Keep that line true, and add `查看入口版本: roundtable --version`. Also update any inline `--doctor` comment so it says "launcher diagnostics to stderr plus seat probe", not "only launcher info".

- [ ] Step 3: Add a note to the closeout docs that `/Users/melee/.local/bin/roundtable --version` must show the expected commit before dogfood tests are considered current, and that `/Users/melee/.local/bin/roundtable --doctor` must still show seat probe output.

- [ ] Step 4: Verify locally:

```bash
./roundtable --version
./roundtable --doctor
/Users/melee/.local/bin/roundtable --version
/Users/melee/.local/bin/roundtable --doctor
```

Expected: before merge/repoint, `--version` may show different repo roots or commits between worktree and `/Users/melee/.local/bin/roundtable`. That is useful evidence, not a test failure. `--doctor` must still run `roster-detect.py`.

---

### Task 7: Documentation And Deployment Boundary

**Files:**
- Modify: `docs/loop-engine/phase3-lane-routing.md`
- Modify: `docs/loop-engine/phase4-closeout-2026-06-29.md`

- [ ] Step 1: Document the lane contract.

Add concise notes:

- Audit Lane default seats: `claude`, `hermes`, `kimi`.
- Plan Review default seats: `claude`, `hermes`, `kimi`.
- Codex is opt-in for these lanes.
- `--seats` overrides defaults for CLI use.
- `participants` means actual seated and invoked native seats, not host-side planning helpers.
- Read-only audits and plan reviews use `review` mode only.
- Minutes are redacted by default; `LOOP_KEEP_RAW_MINUTES=1` keeps local `.raw` files for debugging.

- [ ] Step 2: Document deploy verification.

Add this checklist to closeout:

```bash
git status --short
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
./roundtable --version
./roundtable --doctor
/Users/melee/.local/bin/roundtable --version
/Users/melee/.local/bin/roundtable --doctor
```

Only after merge/repoint should the two `--version` outputs show the same intended code line. The two `--doctor` outputs must still probe seats.

---

## Final Verification

Run:

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
./roundtable --version
./roundtable --doctor
python3 skills/loop-engine/bin/concilium-run.py \
  --repo "$PWD" \
  --task "Read-only audit the Concilium native roundtable guard; do not modify files." \
  --print-route \
  --seats claude,hermes,kimi \
  --signals-json '{"risk":"high","file_count":8,"security_sensitive":false,"ambiguous":true,"read_only":true}'
```

Expected:

- Unit suite passes.
- `--version` prints the current worktree path, branch, and commit.
- `--doctor` still probes seats and includes launcher diagnostics on stderr.
- Print-route shows `lane: audit`, required seats `claude`, `hermes`, `kimi`, and no implicit `codex`.

## Adversarial Review Checklist

- Can a default read-only audit still call `kimi exec`? It must not.
- Can Codex appear in Audit Lane without an explicit config/API/CLI override? It must not.
- Can `participants` include a seat that was unavailable or never invoked? It must not.
- Can report output be redacted while raw minutes still preserve credentials by default? It must not.
- Can a stale `/Users/melee/.local/bin/roundtable` look current? It must not; `--version` must reveal it and `--doctor` must still probe seats.
- Can this patch break normal maker roundtable tasks? It must not; non-audit `conductor.run()` should still use existing plan/exec/review behavior.
