# Concilium Read-Only Audit Legacy Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every Concilium and legacy roundtable entrypoint enforce read-only audit semantics, and make execution-plan review converge through a bounded reviewer loop before implementation starts.

**Architecture:** Keep the existing Concilium Audit Lane as the primary path. Add a small legacy conductor guard so direct `conductor.py` / old `roundtable` invocations cannot decompose a read-only audit into `exec` subtasks. Extend the existing artifact gate with an opt-in strict mode so legacy read-only audits can fail on any new repo delta outside explicit allowed paths while preserving current Audit Lane behavior. Add a Plan Review Loop contract made of two parts: a single-round reviewer-only `plan_review` lane, and a host/runtime loop that patches only the plan artifact between BLOCK rounds and stops only when every available reviewer PASSes or the configured round cap is reached.

**Tech Stack:** Python standard library, existing `conductor.py`, existing `concilium_artifacts.py`, existing unittest suite, existing shell smoke script.

---

## First Principles

1. A read-only audit is not maker work. It must never enter `plan -> exec -> review`.
2. Reviewers may inspect and write `.roundtable` transcripts, but they must not create project artifacts unless the caller explicitly allowed them.
3. The orchestrator owns artifact boundaries. Prompt text is helpful but not a safety mechanism.
4. Existing maker roundtable behavior must remain unchanged for non-audit tasks.
5. The fix must be proven against the FBA failure shape: a task that says read-only audit must not call `kimi exec` or create `docs/audits/review/*.md`.
6. An execution-plan review is not implementation. Reviewer seats may only review; plan revisions are bounded to the plan artifact and must be re-reviewed.

## Files

- Modify: `skills/loop-engine/bin/concilium_artifacts.py`
  - Add strict modes for artifact required-path and delta checks where explicit empty `allowed_write_paths` means "no repo writes allowed."
  - Reject artifact paths and write patterns that are absolute or contain `..` before any report writer can use them.
  - Match allowed artifact globs by path segment so `docs/audits/*.md` does not allow `docs/audits/review/extra.md`.
- Modify: `skills/loop-engine/tests/test_concilium_artifacts.py`
  - Cover strict empty-allowed behavior without changing existing default behavior.
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
  - Refuse to write a required audit report before checking that its path is allowed.
- Modify: `skills/loop-engine/bin/concilium_runtime.py`
  - Preserve explicit empty `allowed_write_paths: []` overlays instead of falling back to configured defaults.
- Modify: `skills/loop-engine/bin/conductor.py`
  - Detect legacy read-only audit tasks.
  - Add a reviewer-only audit flow.
  - Add CLI/env controls for explicit audit mode and allowed/required artifacts.
  - Run strict artifact gate after reviewer seats.
- Modify: `skills/loop-engine/bin/lane_router.py`
  - Route explicit execution-plan review tasks to a `plan_review` lane before generic review/roundtable rules.
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
  - Add a reviewer-only plan review round helper that returns PASS only when every available reviewer passes in the current round.
  - Enforce plan-review reviewer read-only boundaries with strict delta checks and a plan-file fingerprint.
- Modify: `skills/loop-engine/bin/concilium_runtime.py`
  - Surface `plan_review` lane events, round count, unresolved blockers, retry-needed errors, and max-round exhaustion.
  - Provide the host-loop state helper for BLOCK -> patch plan -> re-review up to 3 rounds.
- Modify: `skills/loop-engine/config/concilium.defaults.json`
  - Add `lanes.plan_review` defaults, including `max_rounds: 3`.
- Modify: `skills/loop-engine/tests/test_conductor_core.py`
  - Reproduce the FBA failure shape and prove no `plan` or `exec` calls happen.
  - Prove disallowed `docs/audits/review/*.md` output fails the run.
- Modify: `skills/loop-engine/tests/test_lane_router.py`
  - Cover execution-plan review routing.
- Modify: `skills/loop-engine/tests/test_concilium_runtime.py`
  - Cover Plan Review Loop PASS, BLOCK, and max-round status semantics.
- Modify: `docs/loop-engine/phase3-lane-routing.md`
  - Document that legacy roundtable now delegates read-only semantics to a reviewer-only guard and that plan review uses a bounded review loop.
- Modify: `docs/loop-engine/concilium-menu-bar-contract.md`
  - Mention strict artifact failure surfaces and plan-review round status if surfaced through UI/runtime events later.

---

## Implementation Order

Execute tasks in order. Task 1 introduces artifact path containment validation, `allow_unlisted_required`, `allow_unlisted_delta`, and anchored artifact matching; Tasks 2, 5, and 7 depend on those APIs and should not be implemented before Task 1 is complete.

### Task 1: Preserve Artifact Gate Compatibility And Add Strict Modes

**Files:**
- Modify: `skills/loop-engine/bin/concilium_artifacts.py`
- Modify: `skills/loop-engine/tests/test_concilium_artifacts.py`

- [ ] **Step 1: Add failing tests for default compatibility and strict empty allow-list**

In `skills/loop-engine/tests/test_concilium_artifacts.py`, add `from pathlib import Path` near the imports if it is not already present.

Add this helper method inside `ConciliumArtifactTests` before the new tests:

```python
    def init_repo(self, repo: Path) -> None:
        subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (repo / ".gitignore").write_text(".roundtable/\n__pycache__/\nevals/\n", encoding="utf-8")
        (repo / "tracked.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore", "tracked.md"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base"],
            cwd=repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
```

Append these tests to `ConciliumArtifactTests`:

```python
    def test_artifact_gate_default_allows_delta_when_allowed_paths_omitted(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.init_repo(repo)
            (repo / "docs").mkdir()
            (repo / "docs" / "extra.md").write_text("extra\n", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(repo)

        self.assertEqual(result["status"], "passed")
        self.assertIn("docs/extra.md", result["new_delta_paths"])
        self.assertEqual(result["disallowed_delta"], [])

    def test_artifact_gate_strict_empty_allowed_paths_blocks_any_new_delta(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.init_repo(repo)
            (repo / "docs").mkdir()
            (repo / "docs" / "extra.md").write_text("extra\n", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                allowed_write_paths=[],
                allow_unlisted_delta=False,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["disallowed_delta"], ["docs/extra.md"])

    def test_artifact_gate_strict_empty_allowed_paths_blocks_required_report(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.init_repo(repo)
            report = repo / "docs" / "audits" / "report.md"
            report.parent.mkdir(parents=True)
            report.write_text("# Report\n", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                required_artifact_paths=["docs/audits/report.md"],
                allowed_write_paths=[],
                baseline_delta_paths=concilium_artifacts.collect_delta(repo).get("delta_paths", []),
                allow_unlisted_required=False,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["disallowed"], ["docs/audits/report.md"])

    def test_artifact_gate_rejects_paths_that_escape_repo(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.init_repo(repo)

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                required_artifact_paths=["../outside.md", "/tmp/outside.md"],
                allowed_write_paths=["../*.md", "docs/audits/*.md"],
                allow_unlisted_required=False,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["invalid"], ["../*.md", "../outside.md", "/tmp/outside.md"])

    def test_artifact_snapshot_detects_existing_dirty_file_hash_change(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.init_repo(repo)
            tracked = repo / "tracked.md"
            tracked.write_text("dirty before review\n", encoding="utf-8")
            before = concilium_artifacts.hash_delta_snapshot(repo)

            tracked.write_text("dirty during review\n", encoding="utf-8")
            after = concilium_artifacts.hash_delta_snapshot(repo)

        self.assertEqual(
            concilium_artifacts.changed_snapshot_paths(before, after, allowed_paths=[]),
            ["tracked.md"],
        )

    def test_artifact_gate_glob_does_not_cross_directory_segments(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.init_repo(repo)
            review_dir = repo / "docs" / "audits" / "review"
            review_dir.mkdir(parents=True)
            (review_dir / "extra.md").write_text("extra\n", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                allowed_write_paths=["docs/audits/*.md"],
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["disallowed_delta"], ["docs/audits/review/extra.md"])

    def test_artifact_gate_glob_is_anchored_to_repo_relative_path(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.init_repo(repo)
            nested = repo / "tmp" / "docs" / "audits"
            nested.mkdir(parents=True)
            (nested / "report.md").write_text("wrong root\n", encoding="utf-8")

            result = concilium_artifacts.evaluate_artifact_gate(
                repo,
                allowed_write_paths=["docs/audits/*.md"],
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["disallowed_delta"], ["tmp/docs/audits/report.md"])
```

- [ ] **Step 2: Run the focused failing tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_artifacts.py
```

Expected: the strict-mode tests fail with `TypeError` for the new `allow_unlisted_required` or `allow_unlisted_delta` keyword.
The segment-safe glob test also fails because Python `fnmatch` treats `*` as matching `/`.

- [ ] **Step 3: Implement strict modes without changing defaults**

In `skills/loop-engine/bin/concilium_artifacts.py`, change path normalization, `_matches_any`, and `evaluate_artifact_gate` as follows. Replace whole-path `fnmatch` with an anchored segment matcher so `*` stays inside one path segment, repo-relative patterns only match from the repo-relative root, and callers can use `**` when nested paths are intentional:

```python
import hashlib
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath


def _normalize_artifact_path(path: str) -> tuple[str, str | None]:
    raw = str(path).replace("\\", "/")
    pure = PurePosixPath(raw)
    parts = pure.parts
    if pure.is_absolute() or not parts or any(part in {"", ".", ".."} for part in parts):
        return raw, raw
    return pure.as_posix(), None


def _normalize_artifact_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    normalized: list[str] = []
    invalid: list[str] = []
    for path in paths:
        value, invalid_value = _normalize_artifact_path(path)
        if invalid_value is not None:
            invalid.append(invalid_value)
        else:
            normalized.append(value)
    return normalized, sorted(set(invalid))


def _match_parts(path_parts: tuple[str, ...], pattern_parts: tuple[str, ...]) -> bool:
    if not pattern_parts:
        return not path_parts
    head, tail = pattern_parts[0], pattern_parts[1:]
    if head == "**":
        return any(_match_parts(path_parts[index:], tail) for index in range(len(path_parts) + 1))
    if not path_parts:
        return False
    return fnmatchcase(path_parts[0], head) and _match_parts(path_parts[1:], tail)


def _matches_any(path: str, patterns: list[str], *, allow_when_empty: bool = True) -> bool:
    if not patterns:
        return allow_when_empty
    path_parts = PurePosixPath(path).parts
    return any(
        _match_parts(path_parts, PurePosixPath(pattern).parts)
        for pattern in patterns
    )


def _hash_delta_path(repo_path: Path, rel_path: str) -> str:
    target = (repo_path / rel_path).resolve()
    try:
        target.relative_to(repo_path)
    except ValueError:
        return "<outside>"
    if not target.exists():
        return "<missing>"
    if target.is_dir():
        return "<dir>"
    return hashlib.sha256(target.read_bytes()).hexdigest()


def hash_delta_snapshot(repo: str | Path, include_paths: list[str] | None = None) -> dict[str, str]:
    repo_path = Path(repo).expanduser().resolve()
    delta_paths = set(collect_delta(repo_path).get("delta_paths", []))
    extra_paths, invalid_extra = _normalize_artifact_paths([str(path) for path in (include_paths or [])])
    delta_paths.update(extra_paths)
    delta_paths.update(invalid_extra)
    return {path: _hash_delta_path(repo_path, path) for path in sorted(delta_paths)}


def changed_snapshot_paths(before: dict[str, str], after: dict[str, str], *, allowed_paths: list[str]) -> list[str]:
    allowed = set(allowed_paths)
    paths = set(before) | set(after)
    return sorted(path for path in paths if path not in allowed and before.get(path) != after.get(path))
```

Update the function signature:

```python
def evaluate_artifact_gate(
    repo: str | Path,
    *,
    required_artifact_paths: list[str] | None = None,
    allowed_write_paths: list[str] | None = None,
    baseline_delta_paths: list[str] | None = None,
    allow_unlisted_required: bool = True,
    allow_unlisted_delta: bool = True,
) -> dict:
```

Update the two call sites inside that function:

```python
    required, invalid_required = _normalize_artifact_paths([str(path) for path in (required_artifact_paths or [])])
    allowed, invalid_allowed = _normalize_artifact_paths([str(path) for path in (allowed_write_paths or [])])
    baseline, invalid_baseline = _normalize_artifact_paths([str(path) for path in (baseline_delta_paths or [])])
    invalid = sorted(set(invalid_required + invalid_allowed + invalid_baseline))
    baseline_set = set(baseline)
```

Then:

```python
    disallowed = [
        path
        for path in required
        if not _matches_any(path, allowed, allow_when_empty=allow_unlisted_required)
    ]
```

stays default-compatible unless a caller explicitly requests strict required-path behavior, and:

Use `baseline_set` when deriving post-baseline delta:

```python
    new_delta_paths = [path for path in delta_paths if path not in baseline_set]
```

Then:

```python
    disallowed_delta = [
        path
        for path in new_delta_paths
        if not _matches_any(path, allowed, allow_when_empty=allow_unlisted_delta)
    ]
```

uses strict behavior only when requested.

Include `invalid` in the returned dict and fail the gate when it is non-empty:

```python
    status = (
        "passed"
        if not invalid and not missing and not empty and not unchanged_required and not disallowed and not disallowed_delta
        else "failed"
    )
```

- [ ] **Step 4: Run artifact tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_artifacts.py
```

Expected: all artifact gate tests pass.

---

### Task 2: Prevent Audit Lane From Writing Disallowed Required Reports

**Files:**
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
- Modify: `skills/loop-engine/tests/test_concilium_runtime.py`

- [ ] **Step 0: Add a runtime test repository helper if missing**

In `skills/loop-engine/tests/test_concilium_runtime.py`, add this helper near the other test helpers if no equivalent exists:

```python
def init_repo(repo: Path) -> None:
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
```

If `Path` is not already imported directly in this test file, add `from pathlib import Path` near the imports.

- [ ] **Step 1: Write failing test for report-path prevalidation**

Add this test to `ConciliumRuntimeAdapterTests`:

```python
    def test_live_audit_rejects_disallowed_required_report_before_writing(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            init_repo(repo)
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["audit"]["seats"] = ["claude"]
            with mock.patch.object(
                concilium_runtime.concilium_lanes.conductor,
                "timed_run_seat",
                return_value=(0, "review ok\nVERDICT: PASS\n"),
            ):
                result = concilium_runtime.run_concilium_adapter({
                    "repo": str(repo),
                    "task": "read-only audit repo, only write the final report",
                    "mode": "live_run",
                    "signals": {
                        "read_only": True,
                        "required_artifact_paths": ["tmp/report.md"],
                        "allowed_write_paths": ["docs/audits/final.md"],
                    },
                }, event_sink=concilium_events.ListEventSink(), config=config)

            self.assertNotIn("tmp/report.md", result.get("report_path", ""))
            self.assertFalse((repo / "tmp" / "report.md").exists())
            self.assertNotEqual(result["returncode"], 0)

    def test_live_audit_explicit_empty_allow_list_blocks_default_report_before_writing(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            init_repo(repo)
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["audit"]["seats"] = ["claude"]
            config["lanes"]["audit"]["allowed_report_paths"] = ["docs/audits/*.md"]
            with mock.patch.object(
                concilium_runtime.concilium_lanes.conductor,
                "timed_run_seat",
                return_value=(0, "review ok\nVERDICT: PASS\n"),
            ):
                result = concilium_runtime.run_concilium_adapter({
                    "repo": str(repo),
                    "task": "read-only audit repo, no project files may be written",
                    "mode": "live_run",
                    "signals": {
                        "read_only": True,
                        "required_artifact_paths": ["docs/audits/report.md"],
                        "allowed_write_paths": [],
                    },
                }, event_sink=concilium_events.ListEventSink(), config=config)

            self.assertFalse((repo / "docs" / "audits" / "report.md").exists())
            self.assertEqual(result["status"], "artifact_failed")

    def test_live_audit_rejects_parent_required_report_before_writing(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            init_repo(repo)
            outside = repo.parent / f"{repo.name}-outside-report.md"
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["audit"]["seats"] = ["claude"]
            with mock.patch.object(
                concilium_runtime.concilium_lanes.conductor,
                "timed_run_seat",
                return_value=(0, "review ok\nVERDICT: PASS\n"),
            ):
                result = concilium_runtime.run_concilium_adapter({
                    "repo": str(repo),
                    "task": "read-only audit repo, malicious artifact path must not escape",
                    "mode": "live_run",
                    "signals": {
                        "read_only": True,
                        "required_artifact_paths": [f"../{outside.name}"],
                        "allowed_write_paths": [f"../{outside.name}"],
                    },
                }, event_sink=concilium_events.ListEventSink(), config=config)

            self.assertFalse(outside.exists())
            self.assertEqual(result["status"], "artifact_failed")
            self.assertIn(f"../{outside.name}", result["artifact_gate"]["invalid"])
```

- [ ] **Step 2: Run failing runtime test**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_runtime.py
```

Expected: fails because `_write_audit_report()` currently writes the disallowed required path before the later artifact gate can reject it.

- [ ] **Step 3: Add prevalidation before `_write_audit_report()`**

In `run_audit_lane()`, compute allowed paths before writing. Preserve explicit empty allow-lists by checking key presence, not truthiness:

```python
    if "allowed_write_paths" in audit:
        allowed_artifacts = list(audit.get("allowed_write_paths") or [])
    else:
        allowed_artifacts = list(audit.get("allowed_report_paths") or [])
```

Before calling `_write_audit_report()`, validate the first required report path:

```python
        report_path = ""
        if required_artifacts:
            strict_empty_allow_list = "allowed_write_paths" in audit and not allowed_artifacts
            pre_gate = concilium_artifacts.evaluate_artifact_gate(
                repo_path,
                required_artifact_paths=required_artifacts,
                allowed_write_paths=allowed_artifacts,
                baseline_delta_paths=concilium_artifacts.collect_delta(repo_path).get("delta_paths", []),
                allow_unlisted_required=not strict_empty_allow_list,
                allow_unlisted_delta=not strict_empty_allow_list,
            )
            if pre_gate.get("invalid") or pre_gate["disallowed"]:
                return {
                    "status": "artifact_failed",
                    "lane": "audit",
                    "returncode": 2,
                    "seat_results": seat_results,
                    "report_path": "",
                    "artifact_gate": pre_gate,
                    "verify": {"returncode": verify_rc, "output": verify_out[-4000:]},
                }
            report_path = _write_audit_report(repo_path, task, test_cmd, seat_results, verify_rc, verify_out, required_artifacts)
```

Import `concilium_artifacts` in `concilium_lanes.py` if it is not already imported.

The prevalidation intentionally checks `pre_gate["disallowed"]`, not the whole gate status. Before `_write_audit_report()` runs, the required report is allowed to be missing; this check only answers whether the configured required path is permitted to be written.

- [ ] **Step 4: Run runtime tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_runtime.py
```

Expected: runtime tests pass, and disallowed required report paths are rejected before any file is written.

---

### Task 3: Preserve Explicit Empty Audit Allow-Lists

**Files:**
- Modify: `skills/loop-engine/bin/concilium_runtime.py`
- Modify: `skills/loop-engine/tests/test_concilium_runtime.py`

- [ ] **Step 1: Add failing preview/runtime helper test**

Add this test to `ConciliumRuntimeAdapterTests`:

```python
    def test_explicit_empty_allowed_write_paths_are_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            init_repo(repo)
            preview = concilium_runtime.build_preflight({
                "repo": str(repo),
                "task": "read-only audit repo; no project files may be written",
                "mode": "preview",
                "signals": {
                    "read_only": True,
                    "required_artifact_paths": [],
                    "allowed_write_paths": [],
                },
            }, config=copy.deepcopy(BASE_CONFIG))
            required, allowed = concilium_runtime._artifact_requirements(preview, copy.deepcopy(BASE_CONFIG))

        self.assertEqual(required, [])
        self.assertEqual(allowed, [])

    def test_runtime_artifact_gate_treats_explicit_empty_allow_list_as_strict(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            init_repo(repo)
            report = repo / "docs" / "audits" / "report.md"
            report.parent.mkdir(parents=True)
            report.write_text("# Report\n", encoding="utf-8")
            baseline = concilium_runtime.concilium_artifacts.collect_delta(repo).get("delta_paths", [])
            preview = concilium_runtime.build_preflight({
                "repo": str(repo),
                "task": "read-only audit repo; no project files may be written",
                "mode": "preview",
                "signals": {
                    "read_only": True,
                    "required_artifact_paths": ["docs/audits/report.md"],
                    "allowed_write_paths": [],
                },
            }, config=copy.deepcopy(BASE_CONFIG))
            gate = concilium_runtime._evaluate_artifact_gate(
                preview,
                copy.deepcopy(BASE_CONFIG),
                baseline_delta_paths=baseline,
            )

        self.assertIsNotNone(gate)
        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["disallowed"], ["docs/audits/report.md"])
```

- [ ] **Step 2: Run failing runtime test**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_runtime.py
```

Expected: fails because `_artifact_requirements()` currently uses `signals.get("allowed_write_paths") or audit_config.get("allowed_report_paths")`, so explicit `[]` falls back to configured defaults.

- [ ] **Step 3: Preserve key presence, not truthiness**

Change `_artifact_requirements()`:

```python
    required = list(signals["required_artifact_paths"]) if "required_artifact_paths" in signals else []
    if "allowed_write_paths" in signals:
        allowed = list(signals["allowed_write_paths"])
    else:
        allowed = list(audit_config.get("allowed_report_paths") or [])
```

Change `_default_lane_executor()` similarly:

```python
        audit_config["required_artifact_paths"] = list(preview.get("signals", {}).get("required_artifact_paths") or [])
        if "allowed_write_paths" in preview.get("signals", {}):
            audit_config["allowed_write_paths"] = list(preview["signals"]["allowed_write_paths"])
```

Add this helper near `_artifact_requirements()`:

```python
def _has_explicit_empty_allowed_write_paths(preview: dict) -> bool:
    signals = preview.get("signals") or {}
    return "allowed_write_paths" in signals and not list(signals.get("allowed_write_paths") or [])
```

Change `_evaluate_artifact_gate()` to use strict artifact semantics only for explicit empty allow-lists:

```python
def _evaluate_artifact_gate(preview: dict, effective: dict, baseline_delta_paths: list[str] | None = None) -> dict | None:
    required, allowed = _artifact_requirements(preview, effective)
    if not _uses_artifact_gate(preview):
        return None
    strict_empty_allow_list = _has_explicit_empty_allowed_write_paths(preview)
    return concilium_artifacts.evaluate_artifact_gate(
        preview["request"]["repo"],
        required_artifact_paths=required,
        allowed_write_paths=allowed,
        baseline_delta_paths=baseline_delta_paths,
        allow_unlisted_required=not strict_empty_allow_list,
        allow_unlisted_delta=not strict_empty_allow_list,
    )
```

- [ ] **Step 4: Run runtime tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_runtime.py
```

Expected: runtime tests pass and explicit empty allow-lists are preserved.

---

### Task 4: Add Legacy Read-Only Audit Detection And CLI Controls

**Files:**
- Modify: `skills/loop-engine/bin/conductor.py`
- Modify: `skills/loop-engine/tests/test_conductor_core.py`

- [ ] **Step 1: Write failing pure-helper tests**

Add these tests to `ConductorCoreTests`:

```python
    def test_detects_read_only_audit_task(self):
        task = "只读审查 /tmp/project 的全局架构，只允许给出审查意见，不得修改代码"
        self.assertTrue(conductor.is_read_only_audit_task(task))

    def test_does_not_detect_normal_roundtable_task_as_audit(self):
        task = "Implement routing fixes across multiple modules and run tests"
        self.assertFalse(conductor.is_read_only_audit_task(task))

    def test_split_path_list_accepts_commas_and_colons(self):
        self.assertEqual(
            conductor.split_path_list("docs/a.md,docs/b.md:docs/c.md"),
            ["docs/a.md", "docs/b.md", "docs/c.md"],
        )
```

- [ ] **Step 2: Run focused failing tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_conductor_core.py
```

Expected: fails because `is_read_only_audit_task` and `split_path_list` do not exist yet.

- [ ] **Step 3: Implement helpers in `conductor.py`**

Near the top-level constants in `conductor.py`, add:

```python
AUDIT_TERMS = {"audit", "review", "审查", "审计"}
READ_ONLY_TERMS = {
    "read-only",
    "readonly",
    "only write",
    "只读",
    "不要修改",
    "不得修改",
    "禁止修改",
    "只允许新增",
    "只允许给出",
}


def is_read_only_audit_task(task: str) -> bool:
    text = task.lower()
    return any(term in text for term in AUDIT_TERMS) and any(term in text for term in READ_ONLY_TERMS)


def split_path_list(value: str | None) -> list[str]:
    if not value:
        return []
    raw = re.split(r"[:,]", value)
    return [item.strip() for item in raw if item.strip()]
```

- [ ] **Step 4: Add CLI/env fields but do not change flow yet**

In `build_argparser()`, add:

```python
    ap.add_argument("--audit-only", action="store_true", default=os.environ.get("LOOP_AUDIT_ONLY") == "1",
                    help="Run reviewer-only read-only audit flow; never dispatch exec subtasks")
    ap.add_argument("--required-artifacts", default=os.environ.get("LOOP_REQUIRED_ARTIFACTS", ""),
                    help="Comma/colon-separated report paths that must be written or refreshed")
    ap.add_argument("--allowed-write-paths", default=os.environ.get("LOOP_ALLOWED_WRITE_PATHS", ""),
                    help="Comma/colon-separated project paths allowed to change during read-only audit")
```

In `main()`, pass the parsed values to `run()`:

```python
        audit_only=a.audit_only,
        required_artifact_paths=split_path_list(a.required_artifacts),
        allowed_write_paths=split_path_list(a.allowed_write_paths),
```

- [ ] **Step 5: Run conductor helper tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_conductor_core.py
```

Expected: helper tests pass. Some broader tests may still fail until `run()` accepts the new keyword arguments in Task 3.

---

### Task 5: Add Reviewer-Only Audit Flow To Legacy Conductor

**Files:**
- Modify: `skills/loop-engine/bin/conductor.py`
- Modify: `skills/loop-engine/tests/test_conductor_core.py`

- [ ] **Step 1: Write failing regression test for the FBA failure shape**

Add this test to `ConductorCoreTests`:

```python
    def test_read_only_audit_never_calls_plan_or_exec(self):
        calls = []
        reporter = QuietReporter()
        task = "只读审查 repo 的全局架构，只允许给出审查意见，不得修改代码"
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)

            def fake_run_seat(agent, mode, repo_arg, brief="", extra=None, provider="", model=""):
                calls.append((agent, mode, brief))
                if mode in {"plan", "exec"}:
                    return self.fail(f"read-only audit must not call {mode}")
                if mode == "review":
                    return 0, "VERDICT: PASS\n"
                return self.fail(f"unexpected call: {agent} {mode}")

            with ConductorPatch(self, repo, fake_run_seat):
                rc = conductor.run(str(repo), task, max_iters=1, reporter=reporter, seats=["claude", "kimi", "hermes"])

        self.assertEqual(rc, 0)
        self.assertEqual({mode for _, mode, _ in calls}, {"review"})
        self.assertIn(("finish", "PASS", 1), reporter.events)
```

- [ ] **Step 2: Write failing artifact-boundary regression test**

Add this test to `ConductorCoreTests`:

```python
    def test_read_only_audit_fails_on_disallowed_review_artifact(self):
        reporter = QuietReporter()
        task = "read-only audit repo architecture; only write the requested report"
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            init_repo(repo)

            def fake_run_seat(agent, mode, repo_arg, brief="", extra=None, provider="", model=""):
                if mode != "review":
                    return self.fail(f"read-only audit must not call {mode}")
                review_dir = pathlib.Path(repo_arg) / "docs" / "audits" / "review"
                review_dir.mkdir(parents=True, exist_ok=True)
                (review_dir / "extra.md").write_text("extra\n", encoding="utf-8")
                return 0, "VERDICT: PASS\n"

            with ConductorPatch(self, repo, fake_run_seat):
                rc = conductor.run(
                    str(repo),
                    task,
                    max_iters=1,
                    reporter=reporter,
                    seats=["kimi"],
                    audit_only=True,
                    allowed_write_paths=["docs/audits/final.md"],
                    required_artifact_paths=[],
                )

        self.assertEqual(rc, 2)
        logs = "\n".join(msg for kind, msg in reporter.events if kind == "log")
        self.assertIn("artifact gate failed", logs)
        self.assertIn("docs/audits/review/extra.md", logs)
```

- [ ] **Step 3: Run the focused failing tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_conductor_core.py
```

Expected: fails because `conductor.run()` does not accept `audit_only`, and auto-detected read-only audit still enters plan/exec.

- [ ] **Step 4: Import artifact gate into `conductor.py`**

Near the imports in `conductor.py`, add:

```python
BIN = pathlib.Path(__file__).resolve().parent
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import concilium_artifacts  # noqa: E402
```

If `BIN` already exists in the file, reuse the existing value rather than redefining it.

- [ ] **Step 5: Extend `run()` signature**

Change the `run()` signature to include:

```python
def run(
    repo: str,
    task: str,
    commander: str = "claude",
    reviewer: str = "",
    max_iters: int = 5,
    test_cmd: str = "",
    reporter: Reporter | None = None,
    seats: list[str] | None = None,
    seat_models: dict | None = None,
    *,
    audit_only: bool = False,
    required_artifact_paths: list[str] | None = None,
    allowed_write_paths: list[str] | None = None,
) -> int:
```

Keep all existing caller defaults valid.

- [ ] **Step 6: Implement `_run_read_only_audit()`**

Add this helper before `run()`:

```python
def _run_read_only_audit(
    repo: str,
    task: str,
    reviewer: str,
    test_cmd: str,
    reporter: Reporter,
    seats: list[str] | None,
    seat_models: dict | None,
    timeout_label: str,
    required_artifact_paths: list[str] | None,
    allowed_write_paths: list[str] | None,
) -> int:
    del timeout_label
    seat_models = seat_models or {}
    if "LOOP_SESSION" not in os.environ:
        os.environ["LOOP_SESSION"] = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + _slug(task)
    reporter.log(f"[conductor] 会话: {os.environ['LOOP_SESSION']}")
    baseline = concilium_artifacts.collect_delta(repo).get("delta_paths", [])
    _, out = sh_capture("roundtable-init.sh", repo, task)
    reporter.log(out)
    seated = write_roster(repo, seats, seat_models)
    nimp = import_memory(repo)
    if nimp:
        reporter.log(f"[loop-engine] 记忆桥：导入 {nimp} 份仓库外项目记忆到黑板")
    _, out = sh_capture("kb-refresh.sh", repo, test_cmd)
    reporter.log(out)

    review_seats = seated
    if reviewer:
        review_seats = [seat for seat in seated if seat == reviewer] + [seat for seat in seated if seat != reviewer]
    reporter.start(repo, task, "audit", ",".join(review_seats), 1)
    reporter.round(1)
    verdicts: list[str] = []
    for seat in review_seats:
        provider, model = resolve_seat_model(seat, seat_models)
        brief = (
            "Read-only audit review. Do not modify project files. "
            "Return concrete evidence and end with VERDICT: PASS or VERDICT: BLOCK."
        )
        reporter.seat(seat, "review", "只读审查", phase="start")
        rc, output = timed_run_seat(repo, 1, seat, "review", brief=brief, provider=provider, model=model)
        verdict = VERDICT_MAP.get(rc, "ERR")
        reporter.seat(seat, "review", "", rc, phase="done")
        reporter.transcript(seat, "review", output)
        verdicts.append(verdict)

    gate = concilium_artifacts.evaluate_artifact_gate(
        repo,
        required_artifact_paths=required_artifact_paths or [],
        allowed_write_paths=allowed_write_paths or [],
        baseline_delta_paths=baseline,
        allow_unlisted_required=False,
        allow_unlisted_delta=False,
    )
    if gate["status"] != "passed":
        reporter.log("[conductor] artifact gate failed: " + json.dumps(gate, ensure_ascii=False, sort_keys=True))
        write_conclusion(repo, task, "CAP", 1, verdicts)
        reporter.finish("CAP", 1)
        return 2

    status = "PASS" if all(verdict == "PASS" for verdict in verdicts) else "CAP" if any(verdict == "BLOCK" for verdict in verdicts) else "ERR"
    write_conclusion(repo, task, status, 1, verdicts)
    archive_to_memory(repo, task, status, 1, verdicts)
    reporter.finish(status, 1)
    return {"PASS": 0, "ERR": 1, "CAP": 2}[status]
```

Use the repository's existing seat-model resolver name. If the existing helper is named `sm` inside `run()`, lift a tiny top-level helper:

```python
def resolve_seat_model(seat: str, seat_models: dict | None = None) -> tuple[str, str]:
    cfg = (seat_models or {}).get(seat, {})
    return str(cfg.get("provider", "")), str(cfg.get("model", ""))
```

- [ ] **Step 7: Dispatch to read-only audit before executor pool setup**

Near the start of `run()`, after `reporter` and `seat_models` defaults are initialized, add:

```python
    if audit_only or is_read_only_audit_task(task):
        return _run_read_only_audit(
            repo,
            task,
            reviewer,
            test_cmd,
            reporter,
            seats,
            seat_models,
            "audit",
            required_artifact_paths,
            allowed_write_paths,
        )
```

This must happen before commander plan generation and before `executors` is used.

- [ ] **Step 8: Run conductor focused tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_conductor_core.py
```

Expected: both tests pass.

---

### Task 6: Ensure Concilium Runtime Still Uses Audit Lane And Reports Provenance

**Files:**
- Modify only if tests reveal a regression:
  - `skills/loop-engine/bin/concilium_runtime.py`
  - `skills/loop-engine/bin/concilium_lanes.py`
- Test:
  - `skills/loop-engine/tests/test_concilium_runtime.py`

- [ ] **Step 1: Run existing Audit Lane focused tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_runtime.py
```

Expected: all pass. If one fails because `conductor.run()` signature changed, update only the affected mock assertion to preserve the intended `("claude", "review")`, `("kimi", "review")` behavior.

- [ ] **Step 2: Add one runtime guard test only if missing coverage is observed**

If no existing runtime test proves read-only audit routes to `audit`, add this test to `test_concilium_runtime.py`:

```python
    def test_read_only_audit_request_does_not_route_to_roundtable(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            init_repo(repo)
            result = concilium_runtime.build_preflight({
                "repo": str(repo),
                "task": "只读审查 repo architecture，不得修改代码，只允许给出审查意见",
                "mode": "preview",
            }, config=copy.deepcopy(BASE_CONFIG))

        self.assertEqual(result["route"]["lane"], "audit")
        self.assertNotEqual(result["route"]["lane"], "roundtable")
```

- [ ] **Step 3: Run runtime tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_concilium_runtime.py
```

Expected: runtime tests pass.

---

### Task 7: Add Plan Review Loop Lane

**Files:**
- Modify: `skills/loop-engine/bin/lane_router.py`
- Modify: `skills/loop-engine/bin/concilium_lanes.py`
- Modify: `skills/loop-engine/bin/concilium_runtime.py`
- Modify: `skills/loop-engine/config/concilium.defaults.json`
- Modify: `skills/loop-engine/tests/test_lane_router.py`
- Modify: `skills/loop-engine/tests/test_concilium_runtime.py`

- [ ] **Step 1: Add failing router test for execution-plan review**

Add this test to `LaneRouterTests`:

```python
    def test_execution_plan_review_routes_to_plan_review_lane(self):
        result = lane_router.route_task(
            "审核执行方案 docs/superpowers/plans/example.md，成员 BLOCK 后修改方案并复审",
            {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
            self.config,
        )

        self.assertEqual(result["lane"], "plan_review")
        self.assertIn("review", result["reason"])
```

- [ ] **Step 2: Run failing router test**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_lane_router.py
```

Expected: fails because `plan_review` is not a known lane.

- [ ] **Step 3: Add plan-review defaults and router support**

In `skills/loop-engine/config/concilium.defaults.json`, add:

```json
    "plan_review": {
      "seats": ["claude", "kimi", "hermes", "codex"],
      "max_rounds": 3
    }
```

under `lanes`.

In `lane_router.py`, add a term set:

```python
PLAN_REVIEW_TERMS = {"execution plan", "implementation plan", "执行方案", "实施方案", "计划审查", "审核方案"}
```

Update `required_seats_for_lane()`:

```python
    if lane == "plan_review":
        plan_review = lanes.get("plan_review", {})
        return _unique(list(plan_review.get("seats") or lanes.get("audit", {}).get("seats") or ["codex"]))
```

Route explicit plan-review tasks before generic audit/review routing:

```python
    plan_review = bool(merged.get("plan_review", False)) or any(term in text for term in PLAN_REVIEW_TERMS)
    if plan_review:
        return _route("plan_review", "execution-plan review uses bounded reviewer loop before implementation", config)
```

- [ ] **Step 4: Add failing runtime tests for PASS and max-round semantics**

Add these tests to `ConciliumRuntimeAdapterTests`:

```python
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
            repo = Path(td)
            init_repo(repo)
            result = concilium_runtime.run_concilium_adapter({
                "repo": str(repo),
                "task": "审核执行方案 docs/superpowers/plans/example.md",
                "mode": "live_run",
                "signals": {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
            }, event_sink=concilium_events.ListEventSink(), config=copy.deepcopy(BASE_CONFIG), lane_executor=executor)

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
            repo = Path(td)
            init_repo(repo)
            result = concilium_runtime.run_concilium_adapter({
                "repo": str(repo),
                "task": "审核执行方案 docs/superpowers/plans/example.md",
                "mode": "live_run",
                "signals": {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
            }, event_sink=concilium_events.ListEventSink(), config=copy.deepcopy(BASE_CONFIG), lane_executor=executor)

        self.assertEqual(result["status"], "max_rounds")
        self.assertEqual(result["returncode"], 2)
        self.assertEqual(result["rounds"], 3)
        self.assertEqual(result["unresolved_blockers"][0]["severity"], "HIGH")

    def test_default_plan_review_executor_dispatches_review_seats(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
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
                result = concilium_runtime.run_concilium_adapter({
                    "repo": str(repo),
                    "task": "审核执行方案 docs/superpowers/plans/example.md",
                    "mode": "live_run",
                    "signals": {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
                }, event_sink=concilium_events.ListEventSink(), config=config)

        self.assertEqual(result["status"], "passed")
        self.assertEqual([call.args[2:4] for call in timed_run.call_args_list], [("claude", "review"), ("kimi", "review")])

    def test_plan_review_blocks_if_reviewer_changes_plan_file(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            init_repo(repo)
            plan = repo / "docs" / "superpowers" / "plans" / "example.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# Example Plan\n", encoding="utf-8")
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["plan_review"] = {"seats": ["kimi"], "max_rounds": 3}

            def mutate_plan(repo_arg, iter_arg, seat, mode, brief="", provider="", model=""):
                del iter_arg, seat, mode, brief, provider, model
                Path(repo_arg, "docs/superpowers/plans/example.md").write_text("# Mutated\n", encoding="utf-8")
                return 0, "VERDICT: PASS\n"

            with mock.patch.object(concilium_runtime.concilium_lanes.conductor, "timed_run_seat", side_effect=mutate_plan):
                result = concilium_runtime.run_concilium_adapter({
                    "repo": str(repo),
                    "task": "审核执行方案 docs/superpowers/plans/example.md",
                    "mode": "live_run",
                    "signals": {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
                }, event_sink=concilium_events.ListEventSink(), config=config)

        self.assertEqual(result["status"], "artifact_failed")
        self.assertIn("plan_fingerprint_changed", result["unresolved_blockers"][0]["summary"])

    def test_plan_review_blocks_if_reviewer_changes_preexisting_dirty_file(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            init_repo(repo)
            (repo / "tracked.md").write_text("dirty before review\n", encoding="utf-8")
            plan = repo / "docs" / "superpowers" / "plans" / "example.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# Example Plan\n", encoding="utf-8")
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["plan_review"] = {"seats": ["kimi"], "max_rounds": 3}

            def mutate_dirty_file(repo_arg, iter_arg, seat, mode, brief="", provider="", model=""):
                del iter_arg, seat, mode, brief, provider, model
                Path(repo_arg, "tracked.md").write_text("dirty during review\n", encoding="utf-8")
                return 0, "VERDICT: PASS\n"

            with mock.patch.object(concilium_runtime.concilium_lanes.conductor, "timed_run_seat", side_effect=mutate_dirty_file):
                result = concilium_runtime.run_concilium_adapter({
                    "repo": str(repo),
                    "task": "审核执行方案 docs/superpowers/plans/example.md",
                    "mode": "live_run",
                    "signals": {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
                }, event_sink=concilium_events.ListEventSink(), config=config)

        self.assertEqual(result["status"], "artifact_failed")
        self.assertIn("tracked.md", result["unresolved_blockers"][0]["summary"])

    def test_plan_review_mixed_err_and_block_requires_retry_first(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
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
                result = concilium_runtime.run_concilium_adapter({
                    "repo": str(repo),
                    "task": "审核执行方案 docs/superpowers/plans/example.md",
                    "mode": "live_run",
                    "signals": {"plan_review": True, "plan_path": "docs/superpowers/plans/example.md"},
                }, event_sink=concilium_events.ListEventSink(), config=config)

        self.assertEqual(result["status"], "retry_required")
        self.assertEqual(result["returncode"], 1)

    def test_plan_review_rejects_plan_path_outside_repo(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            init_repo(repo)
            outside = Path(td) / "outside.md"
            outside.write_text("# Outside\n", encoding="utf-8")
            config = copy.deepcopy(BASE_CONFIG)
            config["lanes"]["plan_review"] = {"seats": ["codex"], "max_rounds": 3}
            result = concilium_runtime.run_concilium_adapter({
                "repo": str(repo),
                "task": "审核执行方案 ../outside.md",
                "mode": "live_run",
                "signals": {"plan_review": True, "plan_path": "../outside.md"},
            }, event_sink=concilium_events.ListEventSink(), config=config)

        self.assertEqual(result["status"], "blocked")
        self.assertIn("outside repo", result["unresolved_blockers"][0]["summary"])
```

- [ ] **Step 5: Add reviewer-only plan-review lane executor**

In `concilium_lanes.py`, import the helpers needed by the new lane:

```python
import hashlib

import concilium_artifacts
```

Then add:

```python
def run_plan_review_lane(repo: str | Path, task: str, test_cmd: str, config: dict, timeout: int) -> dict:
    del test_cmd
    repo_path = Path(repo).expanduser().resolve()
    plan_review = config.get("lanes", {}).get("plan_review", {})
    seats = list(plan_review.get("seats") or config.get("lanes", {}).get("audit", {}).get("seats") or ["codex"])
    plan_path = str(plan_review.get("plan_path") or "")
    raw_plan_path = Path(plan_path)
    if not plan_path or raw_plan_path.is_absolute() or ".." in raw_plan_path.parts:
        return {
            "status": "blocked",
            "lane": "plan_review",
            "returncode": 2,
            "rounds": 0,
            "seat_results": [],
            "unresolved_blockers": [{"severity": "HIGH", "summary": f"plan_path is missing or outside repo: {plan_path}"}],
        }
    plan_file = (repo_path / raw_plan_path).resolve()
    try:
        plan_file.relative_to(repo_path)
    except ValueError:
        return {
            "status": "blocked",
            "lane": "plan_review",
            "returncode": 2,
            "rounds": 0,
            "seat_results": [],
            "unresolved_blockers": [{"severity": "HIGH", "summary": f"plan_path is outside repo: {plan_path}"}],
        }
    if not plan_file.exists():
        return {
            "status": "blocked",
            "lane": "plan_review",
            "returncode": 2,
            "rounds": 0,
            "seat_results": [],
            "unresolved_blockers": [{"severity": "HIGH", "summary": f"plan_path is not found: {plan_path}"}],
        }

    baseline_delta = concilium_artifacts.collect_delta(repo_path).get("delta_paths", [])
    before_hash = hashlib.sha256(plan_file.read_bytes()).hexdigest()
    plan_rel = plan_file.relative_to(repo_path).as_posix()
    before_snapshot = concilium_artifacts.hash_delta_snapshot(repo_path, include_paths=[plan_rel])
    seat_results = []
    blockers = []
    for seat in seats:
        model_config = dict(config.get("seat_models", {}).get(seat, {}))
        provider = str(model_config.get("provider", ""))
        model = str(model_config.get("model", ""))
        brief = (
            f"Review execution plan {plan_path}. Do not modify files. "
            "If blocking, provide severity, plan section or file line, blocker reason, and required change. "
            "End with VERDICT: PASS or VERDICT: BLOCK."
        )
        rc, output = conductor.timed_run_seat(str(repo_path), 1, seat, "review", brief=brief, provider=provider, model=model)
        result = {
            "seat": seat,
            "mode": "review",
            "backend_type": "external_cli",
            "status": "invoked",
            "rc": int(rc),
            "output_tail": capacity_status.redact(str(output)[-4000:]),
        }
        seat_results.append(result)
        if int(rc) == 2:
            blockers.append({"seat": seat, "severity": "HIGH", "summary": capacity_status.redact(str(output)[-500:])})

    gate = concilium_artifacts.evaluate_artifact_gate(
        repo_path,
        required_artifact_paths=[],
        allowed_write_paths=[],
        baseline_delta_paths=baseline_delta,
        allow_unlisted_required=False,
        allow_unlisted_delta=False,
    )
    fingerprint_changed = hashlib.sha256(plan_file.read_bytes()).hexdigest() != before_hash
    after_snapshot = concilium_artifacts.hash_delta_snapshot(repo_path, include_paths=[plan_rel])
    non_plan_review_paths = concilium_artifacts.changed_snapshot_paths(before_snapshot, after_snapshot, allowed_paths=[plan_rel])
    if gate["status"] != "passed" or fingerprint_changed or non_plan_review_paths:
        artifact_blockers = []
        if fingerprint_changed:
            artifact_blockers.append({"severity": "HIGH", "summary": "plan_fingerprint_changed"})
        for path in gate.get("disallowed_delta", []):
            artifact_blockers.append({"severity": "HIGH", "summary": f"disallowed_delta: {path}"})
        for path in non_plan_review_paths:
            artifact_blockers.append({"severity": "HIGH", "summary": f"non_plan_review_delta: {path}"})
        return {
            "status": "artifact_failed",
            "lane": "plan_review",
            "returncode": 2,
            "rounds": 1,
            "seat_results": seat_results,
            "artifact_gate": gate,
            "unresolved_blockers": artifact_blockers,
        }

    if any(int(result["rc"]) not in (0, 2) for result in seat_results):
        return {
            "status": "retry_required",
            "lane": "plan_review",
            "returncode": 1,
            "rounds": 1,
            "seat_results": seat_results,
            "unresolved_blockers": [{"severity": "MEDIUM", "summary": "reviewer ERR; retry, fallback, or mark unavailable"}],
        }
    if blockers:
        return {
            "status": "blocked",
            "lane": "plan_review",
            "returncode": 2,
            "rounds": 1,
            "seat_results": seat_results,
            "unresolved_blockers": blockers,
        }
    return {
        "status": "passed",
        "lane": "plan_review",
        "returncode": 0,
        "rounds": 1,
        "seat_results": seat_results,
        "unresolved_blockers": [],
    }
```

This lane executor intentionally performs one reviewer-only round. The outer controller, current host agent, or UI owns the patch-and-retry loop because modifying the plan is a plan-owner action, not a reviewer action.

- [ ] **Step 6: Wire runtime execution and max-call estimates**

In `concilium_runtime.py`, update `expected_max_agent_calls()`:

```python
    if lane == "plan_review":
        plan_review = config.get("lanes", {}).get("plan_review", {})
        seats = list(route.get("required_seats") or plan_review.get("seats") or [])
        return len(seats) * int(plan_review.get("max_rounds", 3))
```

In `_default_lane_executor()`, before `roundtable`:

```python
    if lane == "plan_review":
        plan_effective = copy.deepcopy(effective)
        plan_config = plan_effective.setdefault("lanes", {}).setdefault("plan_review", {})
        if "plan_path" in preview.get("signals", {}):
            plan_config["plan_path"] = str(preview["signals"]["plan_path"])
        return concilium_lanes.run_plan_review_lane(repo, task, test_cmd, plan_effective, timeout)
```

- [ ] **Step 7: Define host-loop state machine for revise and re-review**

Add a small pure helper in `concilium_runtime.py`:

```python
def plan_review_next_action(result: dict, round_index: int, max_rounds: int) -> str:
    if result.get("status") == "passed":
        return "approved"
    if result.get("status") == "retry_required":
        return "retry_or_mark_unavailable"
    if round_index >= max_rounds:
        return "max_rounds"
    if result.get("status") in {"blocked", "artifact_failed"}:
        return "revise_plan"
    return "stop_error"
```

The executable host loop is:

```text
for round in 1..max_rounds:
  run plan_review lane
  if all reviewers PASS: approve plan
  if reviewer ERR: retry that reviewer, use a fallback reviewer, or mark it unavailable; do not patch the plan
  if BLOCK/artifact_failed and round < max_rounds: plan owner patches only the plan artifact, then re-run
  if BLOCK/artifact_failed and round == max_rounds: stop with unresolved blockers
```

This is the exact workflow used by the current Codex session when reviewing this plan.

Add tests for the helper:

```python
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
```

- [ ] **Step 8: Add a testable host-loop helper**

Add these helpers in `concilium_runtime.py` so the loop itself is concrete and testable even though the actual plan-editing action is supplied by the host. The guard reuses `concilium_artifacts.hash_delta_snapshot()` and `concilium_artifacts.changed_snapshot_paths()` to compare current repo delta and file hashes before and after `revise_plan()`; only `plan_path` is allowed to change between review rounds:

```python
def _resolve_plan_review_path(repo: str | Path, plan_path: str) -> tuple[Path, str]:
    repo_path = Path(repo).expanduser().resolve()
    raw_plan_path = Path(plan_path)
    if not plan_path or raw_plan_path.is_absolute() or ".." in raw_plan_path.parts:
        raise ValueError(f"plan_path is missing or outside repo: {plan_path}")
    plan_file = (repo_path / raw_plan_path).resolve()
    plan_file.relative_to(repo_path)
    return plan_file, plan_file.relative_to(repo_path).as_posix()


def _plan_revision_snapshot(repo: str | Path, plan_path: str) -> tuple[dict[str, str], str]:
    repo_path = Path(repo).expanduser().resolve()
    _plan_file, plan_rel = _resolve_plan_review_path(repo_path, plan_path)
    return concilium_artifacts.hash_delta_snapshot(repo_path, include_paths=[plan_rel]), plan_rel


def run_plan_review_host_loop(run_round, revise_plan, *, repo: str | Path, plan_path: str, max_rounds: int = 3) -> dict:
    history = []
    for round_index in range(1, max_rounds + 1):
        result = dict(run_round(round_index) or {})
        result["round_index"] = round_index
        history.append(result)
        action = plan_review_next_action(result, round_index, max_rounds)
        if action == "approved":
            result["status"] = "passed"
            result["rounds"] = round_index
            result["history"] = history
            return result
        if action == "retry_or_mark_unavailable":
            result["status"] = "retry_required"
            result["rounds"] = round_index
            result["history"] = history
            return result
        if action == "max_rounds":
            result["status"] = "max_rounds"
            result["rounds"] = round_index
            result["history"] = history
            return result
        if action == "revise_plan":
            before_snapshot, plan_rel = _plan_revision_snapshot(repo, plan_path)
            revise_plan(result.get("unresolved_blockers") or [], round_index)
            after_snapshot, _plan_rel_after = _plan_revision_snapshot(repo, plan_path)
            non_plan_paths = concilium_artifacts.changed_snapshot_paths(before_snapshot, after_snapshot, allowed_paths=[plan_rel])
            if non_plan_paths:
                result["status"] = "artifact_failed"
                result["returncode"] = 2
                result["rounds"] = round_index
                result["history"] = history
                blockers = list(result.get("unresolved_blockers") or [])
                blockers.append({
                    "severity": "HIGH",
                    "summary": "non_plan_revision: " + ", ".join(non_plan_paths),
                })
                result["unresolved_blockers"] = blockers
                return result
            continue
        result["status"] = "error"
        result["rounds"] = round_index
        result["history"] = history
        return result
    return {"status": "max_rounds", "rounds": max_rounds, "history": history}
```

Add tests:

```python
    def test_plan_review_host_loop_revises_then_passes(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
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
            repo = Path(td)
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
            repo = Path(td)
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
```

- [ ] **Step 9: Run focused tests**

Run:

```bash
python3 -m unittest skills/loop-engine/tests/test_lane_router.py
python3 -m unittest skills/loop-engine/tests/test_concilium_runtime.py
```

Expected: plan-review routing and runtime status tests pass.

---

### Task 8: Document The Entry-Point Contract

**Files:**
- Modify: `docs/loop-engine/phase3-lane-routing.md`
- Modify: `docs/loop-engine/concilium-menu-bar-contract.md`

- [ ] **Step 1: Update lane routing docs**

In `docs/loop-engine/phase3-lane-routing.md`, add a short subsection:

```markdown
### Legacy Roundtable Read-Only Audit Guard

Direct legacy `roundtable` / `conductor.py` invocations now apply the same first-principles boundary as Concilium Audit Lane when the task is explicitly read-only audit/review work:

- no commander planning step;
- no `exec` subtasks;
- selected seats run in `review` mode only;
- new project delta is rejected unless it matches explicit allowed write paths;
- `.roundtable` session transcripts remain the internal audit log.

This guard exists because legacy roundtable can be called outside `concilium-run.py`. It is a backstop, not a replacement for the primary Concilium Audit Lane.

### Plan Review Loop

Execution-plan review uses a bounded reviewer loop before implementation starts:

- reviewer seats run in `review` mode only;
- BLOCK findings must identify severity, plan section or file line, blocker reason, and required change;
- the plan owner may patch only the plan artifact between rounds;
- the plan is re-reviewed after each BLOCK patch;
- the loop stops when every available reviewer PASSes or when `plan_review.max_rounds` is reached;
- default `plan_review.max_rounds` is `3`.

Review seat ERR is capacity/tooling failure, not a BLOCK finding. The host may retry that seat, use a fallback reviewer, or mark it unavailable before deciding whether quorum is satisfied.
```

- [ ] **Step 2: Update menu bar contract**

In `docs/loop-engine/concilium-menu-bar-contract.md`, add:

```markdown
Legacy read-only audit runs may surface as a blocked run when the strict artifact gate detects unexpected project delta. UI consumers should show the artifact-gate failure as an execution-boundary violation, not as a model quality failure.

Plan Review Loop runs should surface current round, max rounds, reviewer verdicts, unresolved blockers, and whether the run stopped because all reviewers passed or because the max round cap was reached.
```

- [ ] **Step 3: Run docs diff check**

Run:

```bash
git diff --check docs/loop-engine/phase3-lane-routing.md docs/loop-engine/concilium-menu-bar-contract.md
```

Expected: no whitespace errors.

---

### Task 9: Full Verification And Adversarial Review

**Files:**
- No planned file edits.

- [ ] **Step 1: Run full unit suite**

Run:

```bash
python3 -m unittest discover -s skills/loop-engine/tests
```

Expected: all tests pass.

- [ ] **Step 2: Run phase smoke**

Run:

```bash
bash skills/loop-engine/bin/smoke-concilium-phase4.sh /Users/melee/.config/superpowers/worktrees/agents/codex-concilium-dogfood-hardening
```

Expected: smoke script exits 0 and still reports Audit Lane external CLI provenance in stub output.

- [ ] **Step 3: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 4: Manual adversarial check**

Review these questions against the final diff:

```text
1. Can a read-only audit task still reach timed_run_seat(..., mode="exec")?
2. Can a review seat create docs/audits/review/*.md without the run failing?
3. Did non-audit roundtable tests still prove normal plan/exec/review behavior?
4. Did the new artifact gate parameter preserve default Concilium Audit Lane behavior?
5. Are any logs or reports capable of exposing secret-bearing config values?
6. Can execution-plan review begin implementation before all reviewers PASS or the max round cap is reached?
7. Are reviewer BLOCK findings required to be structured enough for plan revision?
8. Can `revise_plan()` change non-plan files between review rounds and hide them in the next baseline?
9. Can a plan-review seat mutate a pre-existing dirty non-plan file without the run failing?
```

Expected answer: `No, No, Yes, Yes, No, No, Yes, No, No`.

---

## Acceptance Criteria

- Legacy read-only audit tasks run reviewer-only.
- No `plan` or `exec` seat call happens for read-only audit.
- Unexpected repo delta from review seats fails the run.
- Existing Concilium Audit Lane still routes through external `seat-*.sh` reviewer calls.
- Existing non-audit roundtable behavior remains unchanged.
- Execution-plan review routes to Plan Review Loop instead of maker lanes.
- Plan Review Loop stops only on all-reviewer PASS or max-round exhaustion.
- Plan Review Loop plan revision steps can change only the reviewed plan artifact between rounds.
- Plan Review Loop reviewer rounds catch both new non-plan delta and hash changes to pre-existing dirty non-plan files.
- Default Plan Review Loop cap is 3 rounds.
- Unit suite, phase smoke, and `git diff --check` pass.
