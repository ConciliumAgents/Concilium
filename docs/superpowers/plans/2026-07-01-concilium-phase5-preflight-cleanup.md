# Concilium Phase 5 Preflight Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Phase 5 blockers identified by the self-audit by clarifying the local service boundary, preserving seat provenance for every routed live lane, demoting legacy entrypoints, and tightening small runtime hygiene without building the desktop UI yet.

**Architecture:** Keep Concilium's Python runtime as the source of truth. The local service remains a thin API over `concilium_runtime.py`; browser HTML is demoted to an optional Debug Console; future desktop UI consumes service/client/view-model contracts without reimplementing routing, capacity, Budget Guard, artifact gates, or seat execution. Changes are additive or deprecation-oriented unless a path is demonstrably stale.

**Tech Stack:** Bash launcher, Python standard library, existing Concilium runtime modules, existing `unittest` suite, no new runtime dependency.

---

## Source Inputs

- Audit report: `docs/audits/concilium-phase5-readiness-self-audit-2026-07-01.md`
- Accepted reviewer round: Claude PASS, Hermes PASS, Kimi PASS in `.roundtable/sessions/audit-20260701-110946-444510-Concilium-Phase-5-readin/roundtable.json`
- Current verification baseline: `python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'` passes 224 tests

## First-Principles Constraints

1. Concilium's product value is truthful orchestration: show the lane, seats, cost/capacity risk, write boundary, and machine-readable result before and during execution.
2. Phase 5 UI must be thin. Routing, Budget Guard, artifact gates, capacity rules, and execution stay in the service/runtime.
3. The browser Debug Console is not the product UI. It can remain as a debug surface only if the launcher and docs stop promoting it as the recommended interface.
4. A "read-only" run must mean no trusted project delta outside the declared boundary. If the underlying seat cannot be physically sandboxed, the UI must describe detection/blocking honestly.
5. Legacy paths may remain only when explicitly named as legacy and kept out of normal product flows.

## Scope

In scope:

- Demote the browser WebUI entrypoint into a local service / Debug Console surface.
- Keep `skills/loop-engine/web/server.py` and the `/api/*` contract for the future menu-bar client.
- Add `seat_results` for Fast and Review lanes so service events can show real seat provenance.
- Move benchmark "roundtable" product path to Concilium runtime instead of direct `conductor.py`.
- Mark legacy/TUI/old smoke/docs as superseded or deprecated where they can mislead Phase 5.
- Tighten duplicate local `budget_guard` loading without weakening shadow-module isolation, and tighten `run_audit_lane()` inner artifact baseline behavior.

Out of scope:

- Building SwiftUI/AppKit/Electron/Tauri or any native desktop UI.
- Implementing `save_config()` / config-write endpoints. That belongs to Phase 5 itself.
- Removing `server.py` or deleting service endpoints.
- Rewriting lane routing semantics.
- Removing historical docs that are still useful as dated records.

## File Responsibility Map

- `roundtable`: user-facing launcher. Owns normal runtime entry, legacy entry, and local service shortcut naming.
- `skills/loop-engine/web/server.py`: localhost service/API and optional Debug Console host. Must not own routing logic.
- `skills/loop-engine/web/index.html`: optional Debug Console HTML. Not a product UI.
- `skills/loop-engine/bin/concilium_lanes.py`: lane executors and lane result shape.
- `skills/loop-engine/bin/review-lane.py`: Review Lane maker-checker loop and per-seat call tracking.
- `skills/loop-engine/bin/concilium_runtime.py`: runtime adapter, Budget Guard use, artifact gate, event emission.
- `skills/loop-engine/bin/benchmark-roundtable.py`: benchmark harness. Should measure the current Concilium product path when it says "roundtable".
- `skills/loop-engine/tui/tui.py`: legacy dashboard over direct conductor behavior.
- `skills/loop-engine/SKILL.md`: skill-facing usage docs; must point users at current `roundtable` / `concilium-run.py` defaults.
- `docs/loop-engine/*.md`: closeout and contract docs; preserve history, add current/superseded markers where needed.
- `skills/loop-engine/tests/*`: contract tests. Rename test intent away from WebUI-as-product and toward local service/debug console contracts.

---

### Task 1: Demote Browser WebUI Into Local Service / Debug Console

**Files:**
- Modify: `roundtable`
- Modify: `skills/loop-engine/web/server.py`
- Modify: `skills/loop-engine/tests/test_roundtable_launcher.py`
- Modify: `skills/loop-engine/tests/test_web_runtime_adapter.py`
- Modify: `docs/loop-engine/concilium-menu-bar-contract.md`
- Modify: `docs/loop-engine/phase4-closeout-2026-06-29.md`

- [ ] **Step 1: Write failing launcher tests for `service` and deprecated `web`**

Add these tests to `RoundtableLauncherTests` in `skills/loop-engine/tests/test_roundtable_launcher.py`:

```python
    def test_service_subcommand_starts_local_service_entrypoint(self):
        with tempfile.TemporaryDirectory() as td:
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
                [str(LAUNCHER), "service", "--port", "8765"],
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )

            argv = json.loads(capture.read_text(encoding="utf-8"))
            joined = " ".join(argv)
            self.assertIn("web/server.py", joined)
            self.assertIn("--port", argv)
            self.assertIn("8765", argv)
            self.assertNotIn("concilium-run.py", joined)
            self.assertNotIn("conductor.py", joined)

    def test_web_subcommand_is_deprecated_alias_for_service(self):
        with tempfile.TemporaryDirectory() as td:
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

            proc = subprocess.run(
                [str(LAUNCHER), "web", "--port", "8765"],
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )

            argv = json.loads(capture.read_text(encoding="utf-8"))
            self.assertIn("web/server.py", " ".join(argv))
            self.assertIn("deprecated", proc.stderr.lower())
            self.assertIn("service", proc.stderr.lower())
```

- [ ] **Step 2: Run launcher tests and confirm failure**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_roundtable_launcher.py
```

Expected now:

- `test_service_subcommand_starts_local_service_entrypoint` fails because `service` currently falls through to `concilium-run.py`.
- `test_web_subcommand_is_deprecated_alias_for_service` fails because `web` currently has no deprecation warning and hardcodes `python3`.

- [ ] **Step 3: Write failing service parser test**

Add this test to `WebRuntimeAdapterTests` in `skills/loop-engine/tests/test_web_runtime_adapter.py`:

```python
    def test_service_parser_defaults_to_no_browser_open(self):
        parser = web_server.build_arg_parser()

        default_args = parser.parse_args([])
        open_args = parser.parse_args(["--open"])
        no_open_args = parser.parse_args(["--no-open"])

        self.assertFalse(default_args.open_browser)
        self.assertTrue(open_args.open_browser)
        self.assertFalse(no_open_args.open_browser)
```

- [ ] **Step 4: Run service parser test and confirm failure**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_web_runtime_adapter.py
```

Expected now:

- `AttributeError: module 'web_server' has no attribute 'build_arg_parser'`

- [ ] **Step 5: Update `roundtable` service entrypoint**

Modify the usage header in `roundtable` so the first lines say:

```bash
# roundtable — Concilium one-shot launcher
#   用法: roundtable --task "<任务>" [--repo <仓库,默认当前目录>] [--test-cmd "<测试命令>"]
#        roundtable service [--port N] [--open|--no-open] [--token-file PATH]
#        roundtable legacy --task "<任务>" [legacy conductor/TUI options]
#   先探座位: roundtable --doctor
#   查看入口版本: roundtable --version
```

Replace the current `web` block with:

```bash
# service：启动本地 Concilium API；浏览器 Debug Console 仅作调试，不是 Phase 5 产品 UI。
if [ "${1:-}" = "service" ] || [ "${1:-}" = "serve" ] || [ "${1:-}" = "web" ] || [ "${1:-}" = "--web" ]; then
  cmd="${1:-}"
  shift
  if [ "$cmd" = "web" ] || [ "$cmd" = "--web" ]; then
    echo "[roundtable] 'web' is deprecated; use 'service' for the local Concilium API / Debug Console." >&2
  fi
  PY="${CONCILIUM_LAUNCHER_PYTHON:-python3}"
  exec "$PY" "$SKILL/web/server.py" ${@+"$@"}
fi
```

- [ ] **Step 6: Update `server.py` parser and startup behavior**

In `skills/loop-engine/web/server.py`, add this helper above `main()`:

```python
def build_arg_parser():
    import argparse

    ap = argparse.ArgumentParser(description="Run the local Concilium service.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", dest="open_browser")
    ap.add_argument("--no-open", action="store_false", dest="open_browser")
    ap.set_defaults(open_browser=False)
    ap.add_argument("--token-file", default="")
    return ap
```

Replace `main()` with:

```python
def main(argv=None):
    ap = build_arg_parser()
    a = ap.parse_args(argv)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    if a.token_file:
        write_token_file(Path(a.token_file).expanduser(), url, TOKEN)
    print(f"Concilium local service: {url}  (Ctrl+C to stop)", flush=True)
    print("Debug Console is available at the service URL; it is not the Phase 5 product UI.", flush=True)
    if a.open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")
```

- [ ] **Step 7: Update docs without deleting Debug Console**

In `docs/loop-engine/concilium-menu-bar-contract.md`, add after the opening Debug Console paragraph:

```markdown
The launcher should expose the localhost API as `roundtable service`. The old `roundtable web` wording is deprecated because the browser panel is only a Debug Console, not the product surface. Service startup should not open a browser unless the caller passes an explicit `--open`.
```

In `docs/loop-engine/phase4-closeout-2026-06-29.md`, add under "Risks And Unknowns":

```markdown
- After the Phase 5 readiness self-audit, browser WebUI wording should be demoted to Debug Console/service language before native menu-bar work starts.
```

- [ ] **Step 8: Verify Task 1**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_roundtable_launcher.py skills/loop-engine/tests/test_web_runtime_adapter.py
bash -n roundtable
git diff --check
```

Expected:

- Launcher tests pass.
- Web runtime adapter tests pass.
- Shell syntax check passes.
- No whitespace errors.

- [ ] **Step 9: Commit Task 1**

```bash
git add roundtable skills/loop-engine/web/server.py skills/loop-engine/tests/test_roundtable_launcher.py skills/loop-engine/tests/test_web_runtime_adapter.py docs/loop-engine/concilium-menu-bar-contract.md docs/loop-engine/phase4-closeout-2026-06-29.md
git commit -m "fix(concilium): demote browser debug console entrypoint"
```

---

### Task 2: Emit Seat Provenance For Fast And Review Lanes

**Files:**
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
- Modify: `skills/loop-engine/bin/review-lane.py`
- Modify: `skills/loop-engine/tests/test_concilium_lanes.py`
- Modify: `skills/loop-engine/tests/test_review_lane.py`
- Modify: `skills/loop-engine/tests/test_concilium_runtime.py`

- [ ] **Step 1: Write failing Fast Lane provenance assertion**

In `test_fast_lane_roster_write_uses_fast_session_and_restores_environment`, after `self.assertEqual(result["status"], "ran")`, add:

```python
        self.assertEqual(result["seat_results"], [{
            "seat": "kimi",
            "mode": "exec",
            "backend_type": "external_cli",
            "status": "invoked",
            "rc": 0,
        }])
```

- [ ] **Step 2: Write failing Review Lane provenance assertion**

In `ReviewLaneTests.test_pass_finishes_without_repair`, after the existing `set_iteration.assert_called_once()`, add:

```python
        self.assertEqual(result["seat_results"], [
            {
                "seat": "kimi",
                "mode": "exec",
                "backend_type": "external_cli",
                "status": "invoked",
                "rc": 0,
            },
            {
                "seat": "hermes",
                "mode": "review",
                "backend_type": "external_cli",
                "status": "invoked",
                "rc": 0,
                "verdict": "PASS",
            },
        ])
```

- [ ] **Step 3: Write failing runtime event test for live Fast Lane**

Add this test to `ConciliumRuntimeAdapterTests` in `skills/loop-engine/tests/test_concilium_runtime.py`:

```python
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
```

- [ ] **Step 4: Run focused tests and confirm failure**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_lanes.py skills/loop-engine/tests/test_review_lane.py skills/loop-engine/tests/test_concilium_runtime.py
```

Expected now:

- Fast Lane assertion fails because `seat_results` is missing.
- Review Lane assertion fails because `seat_results` is missing.
- Runtime Fast event test fails because no live seat event is emitted.

- [ ] **Step 5: Add Fast Lane `seat_results`**

In `skills/loop-engine/bin/concilium_lanes.py`, inside `run_fast_lane()`, replace the return block with:

```python
        seat_result = {
            "seat": agent,
            "mode": "exec",
            "backend_type": "external_cli",
            "status": "invoked",
            "rc": agent_rc,
        }
        return {
            "status": "ran",
            "lane": "fast",
            "agent": agent,
            "returncode": agent_rc if agent_rc != 0 else verify_rc,
            "seat_results": [seat_result],
            "agent_output": str(proc["output"])[-4000:],
            "verify": {"returncode": verify_rc, "output": verify_out[-4000:]},
        }
```

- [ ] **Step 6: Add Review Lane `seat_results`**

In `skills/loop-engine/bin/review-lane.py`, add `seat_results = []` after `review_verdict = "ERR"`.

After the executor call:

```python
            seat_results.append({
                "seat": executor,
                "mode": "exec",
                "backend_type": "external_cli",
                "status": "invoked",
                "rc": int(exec_rc),
            })
```

After the reviewer call and `review_verdict` assignment:

```python
            seat_results.append({
                "seat": reviewer,
                "mode": "review",
                "backend_type": "external_cli",
                "status": "invoked",
                "rc": int(review_rc),
                "verdict": review_verdict,
            })
```

Add `"seat_results": seat_results,` to the returned dict:

```python
    return {
        "returncode": final_rc,
        "review_verdict": review_verdict,
        "retries": retries,
        "agent_calls": calls,
        "seat_results": seat_results,
        "session_path": str(session_path(repo, session)),
    }
```

- [ ] **Step 7: Verify Task 2**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_lanes.py skills/loop-engine/tests/test_review_lane.py skills/loop-engine/tests/test_concilium_runtime.py
git diff --check
```

Expected:

- Focused tests pass.
- No whitespace errors.

- [ ] **Step 8: Commit Task 2**

```bash
git add skills/loop-engine/bin/concilium_lanes.py skills/loop-engine/bin/review-lane.py skills/loop-engine/tests/test_concilium_lanes.py skills/loop-engine/tests/test_review_lane.py skills/loop-engine/tests/test_concilium_runtime.py
git commit -m "fix(concilium): emit seat provenance for fast and review lanes"
```

---

### Task 3: Demote Legacy And Benchmark Paths

**Files:**
- Modify: `roundtable`
- Modify: `skills/loop-engine/tui/tui.py`
- Modify: `skills/loop-engine/bin/benchmark-roundtable.py`
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
- Modify: `skills/loop-engine/tests/test_roundtable_launcher.py`
- Modify: `skills/loop-engine/tests/test_benchmark_roundtable.py`
- Modify: `skills/loop-engine/tests/test_concilium_lanes.py`
- Modify: `skills/loop-engine/SKILL.md`
- Modify: `skills/loop-engine/bin/smoke-concilium-phase3.sh`
- Modify: `docs/loop-engine/phase3-closeout-2026-06-29.md`
- Modify: `docs/loop-engine/phase4-closeout-2026-06-29.md`

- [ ] **Step 1: Write failing legacy warning test**

In `test_legacy_subcommand_keeps_old_conductor_path_explicit`, capture `proc` and assert the warning:

```python
            proc = subprocess.run(
                [str(LAUNCHER), "legacy", "--repo", td, "--task", "legacy smoke"],
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )

            self.assertIn("deprecated", proc.stderr.lower())
            self.assertIn("legacy", proc.stderr.lower())
```

Remove the previous direct `subprocess.run(...)` call in that test so the command only runs once.

- [ ] **Step 2: Write failing benchmark product-path test**

Add this test to `BenchmarkRoundtableTests` in `skills/loop-engine/tests/test_benchmark_roundtable.py`:

```python
    def test_run_roundtable_lane_uses_concilium_runtime_product_path(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            lane_dir = pathlib.Path(td) / "lane"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (repo / "docs").mkdir()
            (repo / "docs" / "example.md").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "docs/example.md"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

            def fake_run_concilium(repo_arg, task_arg, **kwargs):
                self.assertEqual(pathlib.Path(repo_arg), repo)
                self.assertEqual(task_arg, sample_task()["prompt"])
                self.assertEqual(kwargs["signals"]["risk"], "high")
                self.assertGreaterEqual(kwargs["signals"]["file_count"], 4)
                self.assertTrue(kwargs["signals"]["ambiguous"])
                self.assertEqual(kwargs["timeout"], 120)
                (repo / "docs" / "example.md").write_text("base\nchanged\n", encoding="utf-8")
                session_path = repo / ".roundtable" / "sessions" / "runtime-session"
                (session_path / "KB").mkdir(parents=True)
                (session_path / "minutes").mkdir()
                (session_path / "KB" / "task.md").write_text(sample_task()["prompt"], encoding="utf-8")
                (session_path / "KB" / "conclusion.md").write_text("runtime report source\n", encoding="utf-8")
                (session_path / "KB" / "test-results.txt").write_text("ok\n", encoding="utf-8")
                (session_path / "roundtable.json").write_text(
                    json.dumps({"participants": ["claude", "hermes", "kimi"], "iter": 1}),
                    encoding="utf-8",
                )
                return {"status": "ran", "lane": "roundtable", "returncode": 0, "session_path": str(session_path)}

            with mock.patch.object(benchmark.concilium_run, "run_concilium", side_effect=fake_run_concilium), \
                    mock.patch.object(benchmark.subprocess, "run", wraps=subprocess.run) as run:
                record = benchmark.run_roundtable_lane(
                    sample_task(),
                    repo,
                    lane_dir,
                    timeout=30,
                    harness_commit="harness",
                    task_base_commit=base,
                )

            conductor_calls = [
                call for call in run.call_args_list
                if "conductor.py" in " ".join(str(part) for part in call.args[0])
            ]
            self.assertEqual(conductor_calls, [])
            self.assertEqual(record["lane"], "roundtable")
            self.assertEqual(record["status"], "PASS")
            self.assertTrue((lane_dir / "report.md").is_file())
            self.assertIn("Roundtable Session Report: runtime-session", (lane_dir / "report.md").read_text(encoding="utf-8"))
```

- Also add this test to `ConciliumLanesTests` in `skills/loop-engine/tests/test_concilium_lanes.py`:

```python
    def test_roundtable_lane_returns_runtime_session_path(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td).resolve()
            captured = {}

            def fake_run(repo_arg, task_arg, **kwargs):
                del repo_arg, task_arg, kwargs
                captured["session"] = os.environ.get("LOOP_SESSION", "")
                return 0

            with mock.patch.object(concilium_lanes.conductor, "run", side_effect=fake_run):
                result = concilium_lanes.run_roundtable_lane(
                    repo,
                    "Complex task.",
                    "",
                    {"lanes": {"roundtable": {"seats": ["claude", "hermes", "kimi"], "max_iters": 2}}},
                    timeout=30,
                )

        self.assertTrue(captured["session"].startswith("roundtable-"))
        self.assertEqual(result["session_path"], str(repo / ".roundtable" / "sessions" / captured["session"]))
```

- Update the existing `test_roundtable_lane_passes_seat_models_to_conductor` in the same file so the new `session_path` key does not break an exact-dict assertion:

```python
        self.assertEqual(result["status"], "ran")
        self.assertEqual(result["lane"], "roundtable")
        self.assertEqual(result["returncode"], 0)
        self.assertTrue(result["session_path"])
```

- [ ] **Step 3: Run focused tests and confirm failure**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_roundtable_launcher.py skills/loop-engine/tests/test_benchmark_roundtable.py skills/loop-engine/tests/test_concilium_lanes.py
```

Expected now:

- Legacy warning assertion fails.
- Benchmark test fails because `run_roundtable_lane()` still calls `conductor.py`.
- Runtime roundtable session-path test fails because `concilium_lanes.run_roundtable_lane()` does not set/return the runtime session path.

- [ ] **Step 4: Add legacy deprecation warning**

At the top of `run_legacy()` in `roundtable`, add:

```bash
  echo "[roundtable] legacy mode is deprecated; use the default Concilium runtime unless you are explicitly testing old conductor/TUI behavior." >&2
```

In `skills/loop-engine/tui/tui.py`, add this comment under the module docstring:

```python
# Deprecated product path: this TUI drives legacy conductor behavior directly.
# Phase 5 clients should use concilium-run.py / web/server.py service contracts.
```

- [ ] **Step 5: Route benchmark Roundtable lane through Concilium runtime**

In `skills/loop-engine/bin/concilium_lanes.py`, update `run_roundtable_lane()` so the product runtime owns the session id and returns the resulting session path:

```python
    repo_path = Path(repo).expanduser().resolve()
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
    return {
        "status": "ran",
        "lane": "roundtable",
        "returncode": rc,
        "session_path": str(repo_path / ".roundtable" / "sessions" / env["LOOP_SESSION"]),
    }
```

In `skills/loop-engine/bin/benchmark-roundtable.py`, remove the old `session = ...` and `env = roundtable_env(...)` locals from `run_roundtable_lane()`. If `roundtable_env()` has no remaining call sites after this change, delete that helper as part of this task because this task creates the orphan. Replace the `cmd = [...]` through `except subprocess.TimeoutExpired` block with:

```python
    result = {}
    try:
        result = concilium_run.run_concilium(
            lane_repo,
            task["prompt"],
            test_cmd=test_cmd,
            dry_run=False,
            print_route=False,
            signals={
                "risk": "high",
                "file_count": max(4, len(task.get("allowed_paths") or [])),
                "security_sensitive": False,
                "ambiguous": True,
            },
            timeout=timeout * 4,
            seats=["claude", "hermes", "kimi"],
            commander="claude",
            max_iters=2,
        )
        rc = int(result.get("returncode", 0))
        out = json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        out = f"{type(e).__name__}: {e}"
        rc = 1
```

Keep the legacy benchmark's broader wall-clock budget by passing `timeout * 4`; the runtime still applies per-seat timeout semantics internally.

Replace the fixed legacy session lookup with the runtime-returned session path:

```python
    session_path = Path(result.get("session_path") or "")
    if session_path:
        report_path = session_path / "KB" / "report.md"
        run_cmd(
            [
                "python3",
                str(ROOT / "skills" / "loop-engine" / "bin" / "report-session.py"),
                str(session_path),
                "--out",
                str(report_path),
            ],
            ROOT,
            timeout=60,
        )
        report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else out[-4000:]
    else:
        report_text = out[-4000:]
```

Then leave the existing `diff.patch`, `test-results.txt`, `result.json`, and verification artifact writes in place. If `session_path` is empty or the report cannot be generated, fall back to `out[-4000:]` as today, but this must be the fallback path, not the expected benchmark report path.

- [ ] **Step 6: Update skill and historical docs**

In `skills/loop-engine/SKILL.md`, replace the automatic mode bullet with:

```markdown
- **自动模式**：默认走 `roundtable --task "<任务+验收标准>"` 或底层 `bin/concilium-run.py --repo <repo> --task "<任务+验收标准>" --live`。这一路径会先进入 Concilium runtime：lane routing、Budget Guard、seat provenance、artifact gate 与事件模型都在这里生效。`bin/conductor.py` 只作为 legacy/底层调试入口保留，不应作为产品默认路径。
```

In `skills/loop-engine/bin/smoke-concilium-phase3.sh`, add after the shebang:

```bash
# DEPRECATED: retained as a Phase 3 routing smoke. Use smoke-concilium-phase4.sh for the current service/runtime contract.
```

In `docs/loop-engine/phase3-closeout-2026-06-29.md`, add under the title:

```markdown
> Historical note: Phase 3 is superseded by the Phase 4 runtime/service contract. Keep this document as dated evidence, not as the current entrypoint contract.
```

In `docs/loop-engine/phase4-closeout-2026-06-29.md`, add under "Evidence":

```markdown
Current post-closeout unit count is higher than the original Phase 4 closeout table because later dogfood fixes added tests. Treat the table below as Phase 4 closeout evidence, not the current total test count.
```

- [ ] **Step 7: Verify Task 3**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_roundtable_launcher.py skills/loop-engine/tests/test_benchmark_roundtable.py skills/loop-engine/tests/test_concilium_lanes.py
bash -n roundtable
bash -n skills/loop-engine/bin/smoke-concilium-phase3.sh
git diff --check
```

Expected:

- Focused tests pass.
- Shell syntax checks pass.
- No whitespace errors.

- [ ] **Step 8: Commit Task 3**

```bash
git add roundtable skills/loop-engine/tui/tui.py skills/loop-engine/bin/benchmark-roundtable.py skills/loop-engine/bin/concilium_lanes.py skills/loop-engine/tests/test_roundtable_launcher.py skills/loop-engine/tests/test_benchmark_roundtable.py skills/loop-engine/tests/test_concilium_lanes.py skills/loop-engine/SKILL.md skills/loop-engine/bin/smoke-concilium-phase3.sh docs/loop-engine/phase3-closeout-2026-06-29.md docs/loop-engine/phase4-closeout-2026-06-29.md
git commit -m "fix(concilium): route product benchmarks through runtime"
```

---

### Task 4: Tighten Runtime Hygiene And Inner Audit Gate

**Files:**
- Modify: `skills/loop-engine/bin/concilium_runtime.py`
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
- Modify: `skills/loop-engine/tests/test_budget_guard.py`
- Modify: `skills/loop-engine/tests/test_concilium_lanes.py`

- [ ] **Step 1: Write failing single-local-loader test for Budget Guard**

Add this test to `BudgetGuardTests` in `skills/loop-engine/tests/test_budget_guard.py`:

```python
    def test_runtime_attach_guard_reuses_single_local_guard_module(self):
        runtime_spec = importlib.util.spec_from_file_location("concilium_runtime", RUNTIME_MODULE)
        concilium_runtime = importlib.util.module_from_spec(runtime_spec)
        assert runtime_spec.loader is not None
        runtime_spec.loader.exec_module(concilium_runtime)

        calls = []

        def fake_evaluate(preview, mode="preview", confirmation=None):
            calls.append((preview, mode, confirmation))
            return {"status": "allowed", "requires_confirmation": False, "reason": "", "warnings": []}

        with mock.patch.object(concilium_runtime.budget_guard, "evaluate_budget_guard", side_effect=fake_evaluate):
            result = concilium_runtime.attach_guard(BASE_PREVIEW)

        self.assertEqual(result["guard"]["status"], "allowed")
        self.assertEqual(len(calls), 1)
```

Keep the existing `test_runtime_attach_guard_ignores_shadowed_budget_guard_module` unchanged; it is the safety check that prevents a normal `import budget_guard` from accidentally accepting a shadowed module.

- [ ] **Step 2: Write failing inner audit gate test**

Add this test to `ConciliumLanesTests` in `skills/loop-engine/tests/test_concilium_lanes.py`:

```python
    def test_audit_lane_inner_gate_rejects_disallowed_seat_delta(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            def rogue_review(repo_arg, iteration, seat, mode, brief="", provider="", model=""):
                pathlib.Path(repo_arg, "unexpected.txt").write_text("bad\n", encoding="utf-8")
                return 0, "VERDICT: PASS\n"

            config = {
                "lanes": {
                    "audit": {
                        "seats": ["claude"],
                        "required_artifact_paths": ["docs/audits/report.md"],
                        "allowed_write_paths": ["docs/audits/report.md"],
                    }
                },
                "seat_models": {},
            }

            with mock.patch.object(concilium_lanes.process_runner, "run_process_group", side_effect=self._successful_process), \
                    mock.patch.object(concilium_lanes.conductor, "write_roster", return_value=["claude"]), \
                    mock.patch.object(concilium_lanes.conductor, "set_participants"), \
                    mock.patch.object(concilium_lanes.conductor, "timed_run_seat", side_effect=rogue_review):
                result = concilium_lanes.run_audit_lane(repo, "Read-only audit.", "", config, timeout=12)

        self.assertEqual(result["status"], "artifact_failed")
        self.assertEqual(result["returncode"], 2)
        self.assertIn("unexpected.txt", result["artifact_gate"]["disallowed_delta"])
```

- [ ] **Step 3: Run focused tests and confirm failure**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_budget_guard.py skills/loop-engine/tests/test_concilium_runtime.py skills/loop-engine/tests/test_concilium_lanes.py
```

Expected now:

- Budget Guard single-local-loader test fails because `attach_guard()` loads a second module instead of reusing module-level `concilium_runtime.budget_guard`.
- The existing shadowed-module test still passes before and after this change.
- Inner audit gate test fails because `run_audit_lane()` collects baseline delta after seat execution.

- [ ] **Step 4: Reuse one locally loaded Budget Guard module**

In `skills/loop-engine/bin/concilium_runtime.py`, keep local file loading so `sys.modules["budget_guard"]` cannot shadow the repo-local guard. Use one module-level instance:

```python
budget_guard = _load_local_module("_concilium_budget_guard", "budget_guard.py")
```

Then replace `attach_guard()` with:

```python
def attach_guard(preview: dict, confirmation: dict | None = None) -> dict:
    guard = budget_guard.evaluate_budget_guard(preview, mode=preview.get("mode", "preview"), confirmation=confirmation)
    result = dict(preview)
    result["guard"] = guard
    return result
```

Do not add a normal `import budget_guard`. Keep `_load_local_module()` in `concilium_runtime.py` because it is still the local-isolation mechanism for `budget_guard.py`.

- [ ] **Step 5: Capture Audit Lane baseline before seats and post-check after report write**

In `skills/loop-engine/bin/concilium_lanes.py`, inside `run_audit_lane()` before the seat loop, add:

```python
        baseline_delta = concilium_artifacts.collect_delta(repo_path).get("delta_paths", [])
```

Replace the existing post-seat artifact gate block with this shape:

```python
        if required_artifacts:
            strict_empty_allow_list = "allowed_write_paths" in audit and not allowed_artifacts
            post_seat_gate = concilium_artifacts.evaluate_artifact_gate(
                repo_path,
                required_artifact_paths=required_artifacts,
                allowed_write_paths=allowed_artifacts,
                baseline_delta_paths=baseline_delta,
                allow_unlisted_required=not strict_empty_allow_list,
                allow_unlisted_delta=not strict_empty_allow_list,
            )
            if post_seat_gate.get("invalid") or post_seat_gate.get("disallowed") or post_seat_gate.get("disallowed_delta"):
                return {
                    "status": "artifact_failed",
                    "lane": "audit",
                    "returncode": 2,
                    "seat_results": seat_results,
                    "report_path": "",
                    "artifact_gate": post_seat_gate,
                    "verify": {"returncode": verify_rc, "output": verify_out[-4000:]},
                }
            report_path = _write_audit_report(repo_path, task, test_cmd, seat_results, verify_rc, verify_out, required_artifacts)
            post_gate = concilium_artifacts.evaluate_artifact_gate(
                repo_path,
                required_artifact_paths=required_artifacts,
                allowed_write_paths=allowed_artifacts,
                baseline_delta_paths=baseline_delta,
                allow_unlisted_required=not strict_empty_allow_list,
                allow_unlisted_delta=not strict_empty_allow_list,
            )
            if post_gate.get("status") != "passed":
                return {
                    "status": "artifact_failed",
                    "lane": "audit",
                    "returncode": 2,
                    "seat_results": seat_results,
                    "report_path": report_path,
                    "artifact_gate": post_gate,
                    "verify": {"returncode": verify_rc, "output": verify_out[-4000:]},
                }
```

Keep the existing `failing_rcs`, `returncode`, and `status` calculation after the artifact-gate block; this task changes gate timing, not audit verdict semantics.

In the final success return, include `artifact_gate` when a `post_gate` exists:

```python
    result = {
        "status": status,
        "lane": "audit",
        "returncode": returncode,
        "seat_results": seat_results,
        "report_path": report_path,
        "verify": {"returncode": verify_rc, "output": verify_out[-4000:]},
    }
    if required_artifacts:
        result["artifact_gate"] = post_gate
    return result
```

- [ ] **Step 6: Verify Task 4**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_budget_guard.py skills/loop-engine/tests/test_concilium_runtime.py skills/loop-engine/tests/test_concilium_lanes.py
python3 -m py_compile skills/loop-engine/bin/concilium_runtime.py skills/loop-engine/bin/concilium_lanes.py
git diff --check
```

Expected:

- Focused tests pass.
- Python compile check passes.
- No whitespace errors.

- [ ] **Step 7: Commit Task 4**

```bash
git add skills/loop-engine/bin/concilium_runtime.py skills/loop-engine/bin/concilium_lanes.py skills/loop-engine/tests/test_budget_guard.py skills/loop-engine/tests/test_concilium_lanes.py
git commit -m "fix(concilium): tighten audit gate and budget guard loading"
```

---

### Task 5: Final Verification And Cleanup Closeout

**Files:**
- Modify: `docs/loop-engine/concilium-menu-bar-contract.md`
- Modify: `docs/loop-engine/phase4-closeout-2026-06-29.md`
- Modify or keep: `docs/audits/concilium-phase5-readiness-self-audit-2026-07-01.md`

- [ ] **Step 1: Remove ignored local artifacts if present**

Run:

```bash
find skills/loop-engine -type d -name __pycache__ -prune -print
find evals/loop-engine/phase2/runs -type f -print 2>/dev/null | head
```

If the first command prints `__pycache__` paths, remove only those ignored cache directories:

```bash
find skills/loop-engine -type d -name __pycache__ -prune -exec rm -rf {} +
```

If the second command prints local ignored benchmark run files, remove only that ignored run output directory:

```bash
rm -rf evals/loop-engine/phase2/runs
```

- [ ] **Step 2: Run full verification**

Run:

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
bash -n roundtable
bash -n skills/loop-engine/bin/smoke-concilium-phase3.sh
bash -n skills/loop-engine/bin/smoke-concilium-phase4.sh
python3 -m py_compile skills/loop-engine/bin/concilium_runtime.py skills/loop-engine/bin/concilium_lanes.py skills/loop-engine/bin/review-lane.py skills/loop-engine/web/server.py
git diff --check
```

Expected:

- Unit suite passes.
- Shell syntax checks pass.
- Python compile checks pass.
- No whitespace errors.

- [ ] **Step 3: Run focused runtime smoke**

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

- JSON output includes `status` or preview fields.
- `route.lane` is `fast`.
- No files are modified.

- [ ] **Step 4: Commit final docs/report state if changed**

If Task 5 changed docs or kept the audit report uncommitted, commit them:

```bash
git add docs/audits/concilium-phase5-readiness-self-audit-2026-07-01.md docs/loop-engine/concilium-menu-bar-contract.md docs/loop-engine/phase4-closeout-2026-06-29.md
git commit -m "docs(concilium): close phase5 preflight audit cleanup"
```

If there are no staged changes after the previous task commits, skip this commit and record that the working tree is clean.

- [ ] **Step 5: Post-implementation adversarial review**

Run Concilium Audit Lane against the implementation diff:

```bash
python3 skills/loop-engine/bin/concilium-run.py \
  --repo /Users/melee/Documents/agents \
  --task "Read-only adversarial audit of the Concilium Phase 5 preflight cleanup implementation. Review the diff from main before this cleanup branch to HEAD. Focus on service/API vs browser Debug Console boundary, Fast/Review seat provenance events, benchmark/runtime path correctness, legacy deprecation clarity, audit artifact gate behavior, and whether any change weakens read-only or same-source-seat protections. Return BLOCK only for concrete HIGH/CRITICAL regressions." \
  --live --yes --timeout 1200 --seats claude,hermes,kimi \
  --test-cmd "python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'" \
  --signals-json '{"read_only":true,"risk":"high","file_count":60,"security_sensitive":false,"ambiguous":true,"allowed_write_paths":[],"required_artifact_paths":[]}'
```

Expected:

- Claude, Hermes, and Kimi are selected as native external CLI seats.
- All available seats return `VERDICT: PASS`.
- If a seat times out, narrow the review prompt once and rerun; do not count a timeout as a PASS.

---

## Self-Review Checklist

- Spec coverage: every MEDIUM/LOW finding in `docs/audits/concilium-phase5-readiness-self-audit-2026-07-01.md` maps to a task above.
- Product boundary: the plan keeps `server.py` and service API; it does not build desktop UI.
- Debug Console: the plan demotes browser UI without prematurely deleting it.
- Seat provenance: Fast, Review, Audit, and Plan Review all have a path to machine-readable seat events.
- Read-only safety: artifact gate behavior is tightened, not loosened.
- Legacy paths: still available only when explicit, and labeled as deprecated.
- Verification: every task has focused tests plus a final full suite.

## Roundtable Plan Review Command

Review this plan before implementation:

```bash
python3 skills/loop-engine/bin/concilium-run.py \
  --repo /Users/melee/Documents/agents \
  --task "方案评审，只评不改。请审核 docs/superpowers/plans/2026-07-01-concilium-phase5-preflight-cleanup.md。重点检查：是否遵循第一性原理、是否只做 Phase 5 前最小 cleanup、是否保留 service/API 而不误删 WebUI 后端、是否补齐 Fast/Review seat provenance、是否正确 demote legacy/benchmark 路径、是否增强 artifact gate 而不破坏 read-only 语义、是否存在过度设计或遗漏测试。" \
  --live --yes --timeout 1200 --seats claude,hermes,kimi \
  --signals-json '{"plan_review":true,"plan_path":"docs/superpowers/plans/2026-07-01-concilium-phase5-preflight-cleanup.md","read_only":true,"risk":"high","file_count":60,"security_sensitive":false,"ambiguous":true}'
```

Plan review passes only when every selected reviewer seat returns `VERDICT: PASS`. If any reviewer BLOCKs, revise only this plan file, then rerun the same review command. Stop after 5 total review rounds and report unresolved blockers.
