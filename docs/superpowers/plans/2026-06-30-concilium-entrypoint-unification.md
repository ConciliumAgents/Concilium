# Concilium Entrypoint Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every user-facing `roundtable` invocation enter the same Concilium runtime router by default, while keeping legacy conductor behavior only behind an explicit legacy command.

**Architecture:** `concilium-run.py` remains the single structured control plane for routing, Budget Guard, seat selection, and lane execution. The top-level `roundtable` launcher becomes a compatibility wrapper around that control plane, and direct legacy conductor/TUI execution is moved behind `roundtable legacy` / `roundtable --legacy`. Concilium lane executors create a fresh session per invocation by default so a second plan-review call cannot inherit stale seats or roles from an earlier audit run.

**Tech Stack:** Bash launcher, Python standard library, existing Concilium runtime modules, existing `unittest` suite.

---

## First Principles

1. **One user action must have one control plane.** If the user runs `roundtable --task ...`, the product must not silently bypass Concilium routing, Budget Guard, configured seats, or event metadata.
2. **A review-only task must never become maker-executor-reviewer work by accident.** Read-only audit and plan-review tasks must dispatch only `review` mode seats unless the user explicitly selects the legacy conductor path.
3. **Session state is evidence, not decoration.** `roundtable.json.participants`, `seat_timings`, and minutes must reflect actual invoked seats and modes. They must not contain hardcoded defaults, stale prior-session seats, or host-side subagents that did not run through native seat scripts.
4. **Fresh invocation beats ambient environment.** `LOOP_SESSION` is useful for legacy manual continuation, but Concilium runtime calls should create a fresh lane session unless a future explicit reuse option is added.
5. **Backward compatibility must be explicit.** The old conductor/TUI loop can stay for comparison and emergency fallback, but users must choose it with `legacy`; it should not be the default named `roundtable` behavior.

## Files

- Modify: `roundtable`
  - Default command path becomes `skills/loop-engine/bin/concilium-run.py --live`.
  - Preserve `--version`, `--doctor`, `web` / `--web`.
  - Add `legacy` and `--legacy` for the old TUI/conductor path.
  - Add test-only interpreter hooks so launcher tests do not start real agents.
- Modify: `skills/loop-engine/bin/concilium-run.py`
  - Accept legacy-compatible overlay flags: `--commander`, `--reviewer`, `--max-iters`, `--fast-agent`, `--review-executor`, `--review-reviewer`.
  - Add `--yes` / `--assume-approved` for explicit Budget Guard confirmation in non-interactive CLI use.
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
  - Create fresh lane session IDs by default instead of reusing ambient `LOOP_SESSION`.
  - Preserve explicit legacy continuation only in `conductor.py`, not in Concilium lanes.
- Modify: `docs/loop-engine/phase3-lane-routing.md`
  - Update the public-entry contract.
- Modify: `docs/loop-engine/phase4-closeout-2026-06-29.md`
  - Replace the old launcher status note with the unified-entry behavior.
- Test: `skills/loop-engine/tests/test_roundtable_launcher.py`
- Test: `skills/loop-engine/tests/test_concilium_run.py`
- Test: `skills/loop-engine/tests/test_concilium_lanes.py`
- Conditional Test: `skills/loop-engine/tests/test_concilium_runtime.py` only if task 5 adds a host-loop regression at the runtime boundary.

---

### Task 1: Route `roundtable --task` Through Concilium Runtime

**Files:**
- Modify: `roundtable`
- Test: `skills/loop-engine/tests/test_roundtable_launcher.py`

- [ ] **Step 1: Write the failing launcher default-route test**

Append this test to `RoundtableLauncherTests` in `skills/loop-engine/tests/test_roundtable_launcher.py`:

```python
    def test_default_task_invocation_execs_concilium_run_live(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            stub = pathlib.Path(td) / "python-stub"
            capture = pathlib.Path(td) / "argv.json"
            stub.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "open(os.environ['CAPTURE_ARGV'], 'w', encoding='utf-8').write(json.dumps(sys.argv))\n",
                encoding="utf-8",
            )
            stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
            env = dict(os.environ)
            env["CONCILIUM_LAUNCHER_PYTHON"] = str(stub)
            env["CAPTURE_ARGV"] = str(capture)

            subprocess.run(
                [str(LAUNCHER), "--repo", str(repo), "--task", "方案评审，只评不改。"],
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )

        argv = json.loads(capture.read_text(encoding="utf-8"))
        self.assertIn("concilium-run.py", " ".join(argv))
        self.assertIn("--live", argv)
        self.assertIn("--repo", argv)
        self.assertIn(str(repo), argv)
        self.assertNotIn("conductor.py", " ".join(argv))
        self.assertNotIn("tui.py", " ".join(argv))
```

Also add `import json` near the top of the file.

- [ ] **Step 2: Run the failing test**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_roundtable_launcher.py
```

Expected before implementation: FAIL in `test_default_task_invocation_execs_concilium_run_live`.

- [ ] **Step 3: Implement the default Concilium path**

In `roundtable`, add a helper after `print_launcher_info()`:

```bash
run_legacy() {
  LEGACY_VENV_PY="${CONCILIUM_LEGACY_VENV_PY:-$VENV_PY}"
  if [ -x "$LEGACY_VENV_PY" ] && "$LEGACY_VENV_PY" -c 'import rich' >/dev/null 2>&1; then
    exec "$LEGACY_VENV_PY" "$SKILL/tui/tui.py" ${ARGS[@]+"${ARGS[@]}"}
  else
    LEGACY_PY="${CONCILIUM_LEGACY_PYTHON:-python3}"
    echo "[roundtable] 未找到 .venv+rich，退回纯文本 legacy conductor" >&2
    exec "$LEGACY_PY" "$SKILL/bin/conductor.py" ${ARGS[@]+"${ARGS[@]}"}
  fi
}
```

Then replace the final engine selection block with:

```bash
if [ "${1:-}" = "legacy" ] || [ "${1:-}" = "--legacy" ]; then
  shift
  ARGS=()
  $inject_repo && ARGS+=(--repo "$PWD")
  [ "$#" -gt 0 ] && ARGS+=("$@")
  run_legacy
fi

PY="${CONCILIUM_LAUNCHER_PYTHON:-python3}"
exec "$PY" "$SKILL/bin/concilium-run.py" --live ${ARGS[@]+"${ARGS[@]}"}
```

Important: recompute `ARGS` after shifting for legacy. Keep `--version`, `--doctor`, and `web` branches before this block.

Implementation note: task 1 and task 2 are a paired compatibility change. Do not publish or use the branch after task 1 alone, because overlay flags such as `--commander` are only accepted after task 2.

- [ ] **Step 4: Run launcher tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_roundtable_launcher.py
```

Expected: all launcher tests pass.

- [ ] **Step 5: Commit task 1**

```bash
git add roundtable skills/loop-engine/tests/test_roundtable_launcher.py
git commit -m "fix(concilium): route roundtable launcher through runtime"
```

---

### Task 2: Preserve Compatibility Flags in `concilium-run.py`

**Files:**
- Modify: `skills/loop-engine/bin/concilium-run.py`
- Test: `skills/loop-engine/tests/test_concilium_run.py`

- [ ] **Step 1: Write the failing compatibility flag test**

Append this test to `ConciliumRunTests`:

```python
    def test_cli_legacy_roundtable_flags_reach_runtime_overlay(self):
        result = {
            "status": "preview",
            "route": {"lane": "roundtable", "required_seats": ["claude", "hermes", "kimi"]},
        }
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run.concilium_runtime, "run_concilium_adapter", return_value=result) as adapter, \
                contextlib.redirect_stdout(io.StringIO()):
            rc = concilium_run.main([
                "--repo", td,
                "--task", "Architecture decision with migration risk.",
                "--print-route",
                "--commander", "claude",
                "--reviewer", "hermes",
                "--max-iters", "2",
                "--review-executor", "kimi",
                "--review-reviewer", "hermes",
                "--fast-agent", "kimi",
            ])

        self.assertEqual(rc, 0)
        params = adapter.call_args.args[0]
        self.assertEqual(params["commander"], "claude")
        self.assertEqual(params["reviewer"], "hermes")
        self.assertEqual(params["max_iters"], 2)
        self.assertEqual(params["review_executor"], "kimi")
        self.assertEqual(params["review_reviewer"], "hermes")
        self.assertEqual(params["fast_agent"], "kimi")
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_run.py
```

Expected: FAIL because these CLI flags are not recognized.

- [ ] **Step 3: Add parser flags**

In `concilium-run.py`, extend both the `run_concilium(...)` helper signature and the CLI parser. The helper should accept:

```python
    commander: str = "",
    reviewer: str = "",
    max_iters: int | None = None,
    fast_agent: str = "",
    review_executor: str = "",
    review_reviewer: str = "",
```

and include these values in its `params` dict. Then add parser flags:

```python
    parser.add_argument("--commander", default="")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--max-iters", type=int, default=None)
    parser.add_argument("--fast-agent", default="")
    parser.add_argument("--review-executor", default="")
    parser.add_argument("--review-reviewer", default="")
```

When building `params`, add:

```python
            "commander": args.commander,
            "reviewer": args.reviewer,
            "max_iters": args.max_iters,
            "fast_agent": args.fast_agent,
            "review_executor": args.review_executor,
            "review_reviewer": args.review_reviewer,
```

- [ ] **Step 4: Run Concilium CLI tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_run.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit task 2**

```bash
git add skills/loop-engine/bin/concilium-run.py skills/loop-engine/tests/test_concilium_run.py
git commit -m "fix(concilium): preserve roundtable overlay flags"
```

---

### Task 3: Add Explicit Non-Interactive Budget Approval

**Files:**
- Modify: `skills/loop-engine/bin/concilium-run.py`
- Test: `skills/loop-engine/tests/test_concilium_run.py`

- [ ] **Step 1: Write the failing `--yes` test**

Append this test to `ConciliumRunTests`:

```python
    def test_cli_yes_reuses_single_capacity_snapshot_for_confirmation(self):
        capacity = [
            {
                "seat": "claude",
                "provider": "anthropic",
                "model": "opus",
                "status": "unknown",
                "source": "test",
                "reason": "unknown",
                "checked_at": "2026-06-30T00:00:00Z",
                "reset_at": "",
                "stale_after_seconds": 300,
            },
            {
                "seat": "hermes",
                "provider": "DeepSeek",
                "model": "deepseek-v4-flash",
                "status": "unknown",
                "source": "test",
                "reason": "unknown",
                "checked_at": "2026-06-30T00:00:00Z",
                "reset_at": "",
                "stale_after_seconds": 300,
            },
            {
                "seat": "kimi",
                "provider": "moonshot",
                "model": "kimi-code/kimi-for-coding",
                "status": "unknown",
                "source": "test",
                "reason": "unknown",
                "checked_at": "2026-06-30T00:00:00Z",
                "reset_at": "",
                "stale_after_seconds": 300,
            },
        ]
        config = {
            "routing": {"risk_posture": "balanced", "allow_auto_escalation": True},
            "lanes": {
                "audit": {"seats": ["claude", "hermes", "kimi"]},
                "plan_review": {"seats": ["claude", "hermes", "kimi"], "max_rounds": 3},
                "fast": {"default_single_agent": "kimi"},
                "review": {"default_review_executor": "kimi", "default_review_reviewer": "hermes"},
                "roundtable": {"commander": "claude", "seats": ["hermes", "kimi"], "reviewer": "hermes"},
            },
            "seat_models": {},
        }
        result = {"status": "blocked", "returncode": 2}
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(concilium_run.concilium_config, "load_config", return_value=config), \
                mock.patch.object(concilium_run.concilium_lanes, "collect_capacity", return_value=capacity), \
                mock.patch.object(concilium_run.concilium_runtime, "run_concilium_adapter", return_value=result) as adapter, \
                contextlib.redirect_stdout(io.StringIO()):
            rc = concilium_run.main([
                "--repo", td,
                "--task", "Read-only audit the architecture and memory system. Do not modify files.",
                "--live",
                "--yes",
                "--signals-json", '{"read_only":true,"risk":"high","file_count":3}',
            ])

        self.assertEqual(rc, 3)
        self.assertIs(adapter.call_args.kwargs["capacity"], capacity)
        self.assertIs(adapter.call_args.kwargs["config"], config)
        confirmation = adapter.call_args.kwargs["confirmation"]
        self.assertTrue(confirmation["accepted"])
        self.assertTrue(confirmation["request_fingerprint"])
        self.assertTrue(confirmation["confirmation_fingerprint"])
```

Do not mock `concilium_runtime.build_preflight` in this test. The regression being protected is that the same capacity snapshot feeds both the confirmation payload and the subsequent adapter call.

- [ ] **Step 2: Run the failing test**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_run.py
```

Expected: FAIL because `--yes` is unknown.

- [ ] **Step 3: Implement `--yes`**

In `concilium-run.py`, add imports:

```python
import concilium_config  # noqa: E402
import concilium_lanes  # noqa: E402
```

Add the parser flag:

```python
    parser.add_argument("--yes", "--assume-approved", action="store_true", dest="yes")
```

Before calling `run_concilium_adapter`, add:

```python
        runtime_kwargs = {}
        if args.yes and mode == "live_run" and confirmation is None:
            config = concilium_config.load_config(args.repo)
            capacity = concilium_lanes.collect_capacity(args.repo, config)
            preview = concilium_runtime.build_preflight(params, config=config, capacity=capacity)
            payload = concilium_runtime.budget_guard.confirmation_payload(preview, mode="live_run")
            confirmation = {
                "accepted": True,
                "request_fingerprint": payload["request_fingerprint"],
                "confirmation_fingerprint": payload["confirmation_fingerprint"],
            }
            runtime_kwargs = {"config": config, "capacity": capacity}
        result = concilium_runtime.run_concilium_adapter(params, confirmation=confirmation, **runtime_kwargs)
```

Do not use `--yes` for preview mode. If `--confirmation-json` is supplied, it wins over `--yes`.

- [ ] **Step 4: Run Concilium CLI tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_run.py
```

Expected: all tests pass.

- [ ] **Step 5: Decide launcher default**

Keep `roundtable --task ...` conservative:

```bash
exec "$PY" "$SKILL/bin/concilium-run.py" --live ${ARGS[@]+"${ARGS[@]}"}
```

Users and scripted callers that want non-interactive approval must pass `--yes` explicitly:

```bash
roundtable --task "Read-only audit ..." --yes
```

- [ ] **Step 6: Commit task 3**

```bash
git add skills/loop-engine/bin/concilium-run.py skills/loop-engine/tests/test_concilium_run.py
git commit -m "feat(concilium): allow explicit cli budget approval"
```

---

### Task 4: Prevent Ambient `LOOP_SESSION` From Contaminating Concilium Lanes

**Files:**
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
- Test: `skills/loop-engine/tests/test_concilium_lanes.py`

- [ ] **Step 1: Write the failing audit-lane fresh-session test**

Append this test to `ConciliumLanesTests`:

```python
    def test_audit_lane_ignores_inherited_loop_session_by_default(self):
        observed = {}

        def capture_roster_env(*args, **kwargs):
            observed["loop_session"] = os.environ.get("LOOP_SESSION")
            return ["claude", "hermes", "kimi"]

        with tempfile.TemporaryDirectory() as td, \
                mock.patch.dict(os.environ, {"LOOP_SESSION": "stale-session"}, clear=False), \
                mock.patch.object(concilium_lanes.process_runner, "run_process_group", side_effect=self._successful_process), \
                mock.patch.object(concilium_lanes.conductor, "write_roster", side_effect=capture_roster_env), \
                mock.patch.object(concilium_lanes.conductor, "set_participants"), \
                mock.patch.object(
                    concilium_lanes.conductor,
                    "timed_run_seat",
                    side_effect=[(0, "VERDICT: PASS"), (0, "VERDICT: PASS"), (0, "VERDICT: PASS")],
                ):
            result = concilium_lanes.run_audit_lane(
                td,
                "Read-only audit the architecture.",
                "",
                {"lanes": {"audit": {"seats": ["claude", "hermes", "kimi"]}}, "seat_models": {}},
                timeout=12,
            )

        self.assertEqual(result["status"], "ran")
        self.assertNotEqual(observed["loop_session"], "stale-session")
        self.assertTrue(observed["loop_session"].startswith("audit-"))
        self.assertEqual(os.environ.get("LOOP_SESSION"), "stale-session")
```

- [ ] **Step 2: Write the failing plan-review fresh-session test**

Append this test to `ConciliumLanesTests`:

```python
    def test_plan_review_lane_ignores_inherited_loop_session_by_default(self):
        observed = {}

        def capture_roster_env(*args, **kwargs):
            observed["loop_session"] = os.environ.get("LOOP_SESSION")
            return ["claude", "hermes", "kimi"]

        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            plan = repo / "docs" / "superpowers" / "plans" / "example.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# Example Plan\n", encoding="utf-8")
            config = {
                "lanes": {"plan_review": {"seats": ["claude", "hermes", "kimi"], "plan_path": str(plan.relative_to(repo))}},
                "seat_models": {},
            }
            with mock.patch.dict(os.environ, {"LOOP_SESSION": "stale-session"}, clear=False), \
                    mock.patch.object(concilium_lanes.process_runner, "run_process_group", side_effect=self._successful_process), \
                    mock.patch.object(concilium_lanes.conductor, "write_roster", side_effect=capture_roster_env), \
                    mock.patch.object(concilium_lanes.conductor, "set_participants"), \
                    mock.patch.object(
                        concilium_lanes.conductor,
                        "timed_run_seat",
                        side_effect=[(0, "VERDICT: PASS"), (0, "VERDICT: PASS"), (0, "VERDICT: PASS")],
                    ):
                result = concilium_lanes.run_plan_review_lane(repo, "方案评审，只评不改。", "", config, timeout=12)

        self.assertEqual(result["status"], "passed")
        self.assertNotEqual(observed["loop_session"], "stale-session")
        self.assertTrue(observed["loop_session"].startswith("plan-review-"))
        self.assertEqual(os.environ.get("LOOP_SESSION"), "stale-session")
```

- [ ] **Step 3: Run the failing tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_lanes.py
```

Expected: FAIL because the current lane env reuses ambient `LOOP_SESSION`.

- [ ] **Step 4: Implement fresh session helper**

In `concilium_lanes.py`, import `datetime`:

```python
import datetime
```

Add:

```python
def _fresh_session_id(lane: str, task: str) -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return f"{lane}-{stamp}-{_slug(task)}"


def _lane_env(lane: str, task: str, timeout: int, config: dict) -> dict[str, str]:
    env = dict(os.environ)
    env["LOOP_SESSION"] = _fresh_session_id(lane, task)
    env["LOOP_ARCHIVE"] = "0"
    env.update(_seat_timeout_env(timeout, config))
    return env
```

Then update `run_fast_lane`, `run_audit_lane`, and `run_plan_review_lane` to call `_lane_env(...)` instead of:

```python
env = dict(os.environ)
env["LOOP_SESSION"] = env.get("LOOP_SESSION") or ...
env["LOOP_ARCHIVE"] = "0"
env.update(_seat_timeout_env(timeout, config))
```

For each updated lane, keep the existing scoped environment behavior by deriving `scoped` from the new `env` return value:

```python
scoped = {key: env[key] for key in ("LOOP_SESSION", "LOOP_ARCHIVE")}
scoped.update(_seat_timeout_env(timeout, config))
```

For `run_fast_lane`, pass `timeout_config or {}` into `_lane_env(...)` and keep the fast-lane `LOOP_SEAT_TIMEOUT` assertion when updating the existing environment test. The updated test should no longer expect the exact old `fast-{slug}` value; it should assert the new value starts with `fast-`, differs from any inherited `LOOP_SESSION`, keeps the expected seat-timeout environment, and is restored after the lane exits. For the new audit and plan-review fresh-session tests, add at least one assertion that a seat-timeout key from `_seat_timeout_env(...)` is visible while the lane runs.

Keep `run_roundtable_lane` unchanged for now if it delegates to legacy conductor; task 5 will control how users reach it. `run_review_lane` is delegated through `review-lane.py` and does not currently own a roundtable session; leave it unchanged in this change and track review-lane session unification as a later cleanup only if needed.

- [ ] **Step 5: Run lane tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_lanes.py
```

Expected: all lane tests pass.

- [ ] **Step 6: Commit task 4**

```bash
git add skills/loop-engine/bin/concilium_lanes.py skills/loop-engine/tests/test_concilium_lanes.py
git commit -m "fix(concilium): isolate lane sessions per invocation"
```

---

### Task 5: Add End-to-End Metadata Regression Tests

**Files:**
- Modify: `skills/loop-engine/tests/test_roundtable_launcher.py`
- Modify: `skills/loop-engine/tests/test_concilium_lanes.py`
- Conditional Modify: `skills/loop-engine/tests/test_concilium_runtime.py` only if this task adds a runtime-boundary regression that cannot be expressed in launcher or lane tests.

- [ ] **Step 1: Add launcher legacy test**

Append:

```python
    def test_legacy_subcommand_keeps_old_conductor_path_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            stub = pathlib.Path(td) / "python-stub"
            venv_stub = pathlib.Path(td) / "venv-python-stub"
            capture = pathlib.Path(td) / "argv.json"
            stub.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "open(os.environ['CAPTURE_ARGV'], 'w', encoding='utf-8').write(json.dumps(sys.argv))\n",
                encoding="utf-8",
            )
            stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
            venv_stub.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            venv_stub.chmod(venv_stub.stat().st_mode | stat.S_IXUSR)
            env = dict(os.environ)
            env["PATH"] = f"{td}{os.pathsep}{env.get('PATH', '')}"
            env["CONCILIUM_LEGACY_PYTHON"] = str(stub)
            env["CONCILIUM_LEGACY_VENV_PY"] = str(venv_stub)
            env["CAPTURE_ARGV"] = str(capture)

            subprocess.run(
                [str(LAUNCHER), "legacy", "--repo", td, "--task", "legacy smoke"],
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )

        argv = json.loads(capture.read_text(encoding="utf-8"))
        self.assertTrue("tui.py" in " ".join(argv) or "conductor.py" in " ".join(argv))
```

Implementation support: in `roundtable`, use `${CONCILIUM_LEGACY_PYTHON:-python3}` for the plain conductor fallback and `${CONCILIUM_LEGACY_VENV_PY:-$VENV_PY}` for TUI detection so tests can avoid real agents.

- [ ] **Step 2: Add no-exec assertion for plan review**

In `test_plan_review_lane_initializes_session_and_sets_actual_participants`, update the `write_roster` mock to return all three plan-review seats:

```python
mock.patch.object(concilium_lanes.conductor, "write_roster", return_value=["claude", "hermes", "kimi"])
```

Then extend `timed_run_seat` to three successful review responses:

```python
mock.patch.object(
    concilium_lanes.conductor,
    "timed_run_seat",
    side_effect=[(0, "VERDICT: PASS"), (0, "VERDICT: PASS"), (0, "VERDICT: PASS")],
) as timed_run
```

Delete the old two-seat assertion and assert the exact three review-mode calls:

```python
self.assertEqual(
    [call.args[2:4] for call in timed_run.call_args_list],
    [("claude", "review"), ("hermes", "review"), ("kimi", "review")],
)
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
python3 -m unittest \
  skills/loop-engine/tests/test_roundtable_launcher.py \
  skills/loop-engine/tests/test_concilium_lanes.py \
  skills/loop-engine/tests/test_concilium_run.py
```

Expected: all focused tests pass.

- [ ] **Step 4: Commit task 5**

```bash
git add skills/loop-engine/tests/test_roundtable_launcher.py skills/loop-engine/tests/test_concilium_lanes.py skills/loop-engine/tests/test_concilium_run.py roundtable
git commit -m "test(concilium): guard launcher and reviewer-only metadata"
```

---

### Task 6: Update Docs and Run Verification

**Files:**
- Modify: `docs/loop-engine/phase3-lane-routing.md`
- Modify: `docs/loop-engine/phase4-closeout-2026-06-29.md`

- [ ] **Step 1: Update `phase3-lane-routing.md`**

Add this paragraph near the Audit Lane / Legacy Roundtable section:

```markdown
The public `roundtable --task ...` launcher now enters Concilium runtime routing by default. Direct conductor/TUI behavior is available only through `roundtable legacy ...` or `roundtable --legacy ...`. This keeps Audit Lane and Plan Review Lane semantics consistent across CLI, WebUI, and future menu-bar clients: read-only audit and plan-review tasks route to reviewer-only native seats instead of the old commander/executor/reviewer loop.
```

- [ ] **Step 2: Update `phase4-closeout-2026-06-29.md`**

Add this verification note:

```markdown
Post-closeout entrypoint hardening: the `roundtable` launcher no longer bypasses Concilium runtime for normal `--task` calls. Use `roundtable legacy ...` only when intentionally testing the old conductor loop.
```

- [ ] **Step 3: Run full verification**

Run:

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
bash -n roundtable
python3 -m py_compile skills/loop-engine/bin/concilium-run.py skills/loop-engine/bin/concilium_lanes.py
git diff --check
```

Expected:

```text
OK
```

for unit tests, zero output from `bash -n`, zero output from `py_compile`, and zero output from `git diff --check`.

- [ ] **Step 4: Run self-contained route smokes for FBA-like tasks**

Run:

```bash
python3 skills/loop-engine/bin/concilium-run.py \
  --repo /Users/melee/Documents/agents \
  --task "Read-only audit a product workflow repository architecture, code structure, and memory/agent instructions. Do not modify project files except writing the required audit report." \
  --print-route \
  --seats claude,hermes,kimi \
  --signals-json '{"risk":"high","file_count":20,"security_sensitive":false,"ambiguous":true,"read_only":true,"allowed_write_paths":["docs/audits/concilium-route-smoke-2026-06-30.md"],"required_artifact_paths":["docs/audits/concilium-route-smoke-2026-06-30.md"]}'
```

Expected JSON contains:

```json
"lane": "audit"
"required_seats": ["claude", "hermes", "kimi"]
```

Run:

```bash
python3 skills/loop-engine/bin/concilium-run.py \
  --repo /Users/melee/Documents/agents \
  --task "方案评审，只评不改。审核 docs/superpowers/plans/2026-06-30-concilium-entrypoint-unification.md 的执行方案。" \
  --print-route \
  --signals-json '{"plan_review":true,"plan_path":"docs/superpowers/plans/2026-06-30-concilium-entrypoint-unification.md"}'
```

Expected JSON contains:

```json
"lane": "plan_review"
"required_seats": ["claude", "hermes", "kimi"]
```

- [ ] **Step 5: Commit task 6**

```bash
git add docs/loop-engine/phase3-lane-routing.md docs/loop-engine/phase4-closeout-2026-06-29.md
git commit -m "docs(concilium): document unified roundtable entrypoint"
```

---

## Self-Review Checklist

- [ ] The default public `roundtable` path no longer calls `tui.py` or `conductor.py` directly.
- [ ] Legacy conductor/TUI path remains available through an explicit command.
- [ ] Read-only audit and plan-review requests route through Concilium runtime, not ambient legacy sessions.
- [ ] `concilium-run.py` accepts compatibility flags formerly used by `roundtable`.
- [ ] Live execution still passes through Budget Guard; non-interactive approval requires explicit `--yes`.
- [ ] Concilium lanes create fresh sessions by default and restore the caller environment after each run.
- [ ] Plan review dispatches only `review` mode seats.
- [ ] Full unit suite, shell syntax checks, route smokes, and `git diff --check` pass.

## Roundtable Review Command

After writing this plan, review it through the current Concilium Plan Review Lane:

```bash
python3 skills/loop-engine/bin/concilium-run.py \
  --repo /Users/melee/Documents/agents \
  --task "方案评审，只评不改。请审核 docs/superpowers/plans/2026-06-30-concilium-entrypoint-unification.md。重点检查：是否真正统一 roundtable 入口、是否保留 legacy 显式路径、是否避免同 session 污染、是否有足够 TDD 回归测试、是否存在过度设计或破坏 Budget Guard 的风险。" \
  --live \
  --yes \
  --timeout 900 \
  --signals-json '{"plan_review":true,"plan_path":"docs/superpowers/plans/2026-06-30-concilium-entrypoint-unification.md","risk":"high","file_count":6,"security_sensitive":false,"ambiguous":true}'
```

Expected:

- route: `plan_review`
- required seats: `claude`, `hermes`, `kimi`
- no `exec` mode seat calls
- `roundtable.json.participants` equals the actual invoked reviewer seats
- status is `passed`, or `blocked` with concrete plan edits required before implementation
