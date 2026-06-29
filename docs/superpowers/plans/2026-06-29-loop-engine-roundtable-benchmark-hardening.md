# Loop Engine Roundtable Benchmark Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Phase 2 benchmark lane results reflect task quality while preserving raw process-health evidence.

**Architecture:** Keep conductor behavior unchanged for normal roundtable runs. Harden `benchmark-roundtable.py` so benchmark lanes disable archive writes, require an allowed target diff, block path violations, and record non-zero process return codes as warnings rather than automatic quality failure.

**Tech Stack:** Python standard library, `unittest`, existing Loop Engine shell smoke/eval scripts.

---

## Files

- Modify: `skills/loop-engine/bin/benchmark-roundtable.py`
- Modify: `skills/loop-engine/tests/test_benchmark_roundtable.py`
- Reference: `docs/superpowers/specs/2026-06-29-loop-engine-roundtable-benchmark-hardening-design.md`

## Task 1: Add Quality Classification Tests

- [ ] **Step 1: Add tests for target changes, warnings, and archive suppression**

Add tests to `skills/loop-engine/tests/test_benchmark_roundtable.py`:

```python
    def test_allowed_target_changes_exclude_lane_report(self):
        task = sample_task()
        result = benchmark.classify_changed_files(task, ["BENCHMARK-REPORT.md", "docs/example.md"])
        self.assertEqual(result["allowed_target_changes"], ["docs/example.md"])
        self.assertEqual(result["violations"], [])

    def test_lane_record_blocks_when_only_lane_report_changed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (repo / "base.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "base.txt"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            (repo / "BENCHMARK-REPORT.md").write_text("report\n", encoding="utf-8")

            record = benchmark.lane_record(
                task=sample_task(),
                lane="roundtable",
                status="ERR",
                verify={"passed": True},
                repo=repo,
                lane_dir=pathlib.Path(td) / "lane",
                started=0,
                returncode=0,
                harness_commit="harness",
                task_base_commit=base,
            )

        self.assertEqual(record["status"], "ERR")
        self.assertIn("no changed files inside allowed_paths", record["blocking_findings"])

    def test_lane_record_warns_but_passes_on_nonzero_returncode_with_verified_target_diff(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
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
            (repo / "docs" / "example.md").write_text("base\nchanged\n", encoding="utf-8")

            record = benchmark.lane_record(
                task=sample_task(),
                lane="roundtable",
                status="ERR",
                verify={"passed": True},
                repo=repo,
                lane_dir=pathlib.Path(td) / "lane",
                started=0,
                returncode=1,
                harness_commit="harness",
                task_base_commit=base,
            )

        self.assertEqual(record["status"], "PASS")
        self.assertEqual(record["lane_returncode"], 1)
        self.assertIn("lane returncode 1", record["warnings"])

    def test_roundtable_env_disables_archive_for_benchmark(self):
        env = benchmark.roundtable_env(timeout=123, session="phase2-sample")
        self.assertEqual(env["LOOP_SESSION"], "phase2-sample")
        self.assertEqual(env["LOOP_SEAT_TIMEOUT"], "123")
        self.assertEqual(env["LOOP_ARCHIVE"], "0")
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
python3 skills/loop-engine/tests/test_benchmark_roundtable.py
```

Expected: FAIL because `classify_changed_files`, `warnings`, `lane_returncode`, and `roundtable_env` do not exist yet.

## Task 2: Implement Benchmark Quality Classification

- [ ] **Step 1: Add changed-file classifier and benchmark env helper**

In `skills/loop-engine/bin/benchmark-roundtable.py`, add:

```python
def classify_changed_files(task: dict, files: list[str]) -> dict:
    allowed = task.get("allowed_paths", [])
    allowed_target_changes = []
    violations = []
    for file in files:
        if file == "BENCHMARK-REPORT.md":
            continue
        if any(file == item or file.startswith(item.rstrip("/") + "/") for item in allowed):
            allowed_target_changes.append(file)
        else:
            violations.append(file)
    return {
        "allowed_target_changes": sorted(allowed_target_changes),
        "violations": sorted(violations),
    }


def roundtable_env(timeout: int, session: str) -> dict:
    env = dict(os.environ)
    env["LOOP_SESSION"] = session
    env["LOOP_SEAT_TIMEOUT"] = str(timeout)
    env["LOOP_ARCHIVE"] = "0"
    return env
```

- [ ] **Step 2: Update `path_violations` to use the classifier**

Replace `path_violations` body with:

```python
def path_violations(task: dict, files: list[str]) -> list[str]:
    return classify_changed_files(task, files)["violations"]
```

- [ ] **Step 3: Update `lane_record` status logic**

Inside `lane_record`, after `changed = changed_files_since(...)`, compute classification and warnings:

```python
    classification = classify_changed_files(task, changed)
    violations = classification["violations"]
    allowed_target_changes = classification["allowed_target_changes"]
    findings = []
    warnings = []
    if not verify["passed"]:
        findings.append("verify failed")
    if not allowed_target_changes:
        findings.append("no changed files inside allowed_paths")
    if violations:
        findings.append("changed files outside allowed_paths: " + ", ".join(violations))
    if returncode != 0:
        warnings.append(f"lane returncode {returncode}")
    final_status = "ERR" if status != "PASS" and not (verify["passed"] and allowed_target_changes and not violations) else "PASS"
    if findings:
        final_status = "ERR"
```

Add these fields to the returned record:

```python
        "lane_returncode": returncode,
        "warnings": warnings,
        "allowed_target_changes": allowed_target_changes,
```

- [ ] **Step 4: Use the benchmark env helper for roundtable lanes**

In `run_roundtable_lane`, replace manual env construction:

```python
    env = roundtable_env(timeout, session)
```

- [ ] **Step 5: Run tests**

Run:

```bash
python3 skills/loop-engine/tests/test_benchmark_roundtable.py
python3 -m unittest discover -s skills/loop-engine/tests
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add skills/loop-engine/bin/benchmark-roundtable.py skills/loop-engine/tests/test_benchmark_roundtable.py
git commit -m "fix: harden phase2 benchmark lane classification"
```

## Task 3: Adversarial Verification

- [ ] **Step 1: Run static and regression checks**

Run:

```bash
git diff --check
python3 -m unittest discover -s skills/loop-engine/tests
bash skills/loop-engine/bin/smoke-roundtable-speedup.sh
python3 skills/loop-engine/bin/eval-roundtable.py --timeout 180
python3 skills/loop-engine/bin/eval-roundtable.py --timeout 180 --include-optional
python3 skills/loop-engine/bin/benchmark-roundtable.py --dry-run --out /tmp/loop-phase2-hardening-dry
test -f /tmp/loop-phase2-hardening-dry/summary.md
```

Expected: all commands exit 0.

- [ ] **Step 2: Run one controlled live pair**

Run:

```bash
python3 skills/loop-engine/bin/benchmark-roundtable.py \
  --live \
  --task-id eval_runner_missing_command_test \
  --base loop-engine-mvp-v0.1-internal \
  --timeout 300
```

Expected: the run completes and writes a run directory. Inspect `records.jsonl`; a roundtable lane with verified allowed target diff and non-zero conductor return code should record `warnings` and `lane_returncode` rather than hiding the raw signal.

- [ ] **Step 3: Commit any report update only if live evidence changes the decision**

If the live pair meaningfully changes the Phase 2 report, update `docs/loop-engine/phase2-benchmark-report.md` with the new run path and interpretation. If it only validates harness behavior, do not edit the report.
