# Loop Engine Phase 2 Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Phase 2 benchmark harness that compares Loop Engine roundtable runs against a Kimi single-agent baseline on the same task set.

**Architecture:** Keep Phase 1 evals unchanged. Add a separate Phase 2 task definition, runner, summary tool, tests, and final report path under `evals/loop-engine/phase2/` and `docs/loop-engine/`. The runner controls isolated lane worktrees from the harness repo, records comparable JSON artifacts, and supports dry mode for tests plus explicit live mode for Kimi and roundtable lanes.

**Tech Stack:** Python standard library, Bash/git commands, existing Kimi CLI and Loop Engine scripts, Markdown docs, no new runtime dependencies.

---

## Source Design

Implement this spec:

- `docs/superpowers/specs/2026-06-29-loop-engine-phase2-benchmark-design.md`

Do not change:

- Phase 1 eval task file `evals/loop-engine/tasks.json`
- historical `.roundtable/` sessions
- global Claude/Kimi/Codex/Hermes/Codex config
- unrelated `.DS_Store` files

---

## File Structure

Create:

- `evals/loop-engine/phase2/tasks.json`
  - Five fixed benchmark tasks: three `repo-local`, two `dogfood`.
- `skills/loop-engine/bin/benchmark-roundtable.py`
  - Loads tasks, creates run directories, runs dry/live lanes, writes lane records and artifacts.
- `skills/loop-engine/bin/summarize-benchmark.py`
  - Reads `records.jsonl`, compares Kimi vs roundtable per task, writes `summary.md`.
- `skills/loop-engine/tests/test_benchmark_roundtable.py`
  - Tests schema validation, dry runs, verify command behavior, and safe path helpers.
- `skills/loop-engine/tests/test_summarize_benchmark.py`
  - Tests outcome classification and markdown summary generation.
- `docs/loop-engine/phase2-benchmark-report.md`
  - Filled after at least one controlled live task pair.

Modify:

- `.gitignore`
  - Ignore generated Phase 2 run/worktree directories.

Generated, not tracked:

- `evals/loop-engine/phase2/runs/**`
- `evals/loop-engine/phase2/worktrees/**`

---

### Task 1: Phase 2 Task File And Ignore Rules

**Files:**
- Create: `evals/loop-engine/phase2/tasks.json`
- Modify: `.gitignore`

- [ ] **Step 1: Create the Phase 2 task directory and task file**

Create `evals/loop-engine/phase2/tasks.json` with exactly this JSON:

```json
[
  {
    "id": "seat_contract_bold_verdict_doc",
    "category": "repo-local",
    "prompt": "Document in docs/loop-engine/seat-contract.md that review verdict parsers accept a single Markdown-bold verdict line such as **VERDICT: PASS** or **VERDICT: BLOCK**, while still requiring exactly one verdict line. Keep the change concise.",
    "allowed_paths": [
      "docs/loop-engine/seat-contract.md"
    ],
    "verify_cmds": [
      "rg -n \"Markdown-bold|\\*\\*VERDICT: PASS\\*\\*|\\*\\*VERDICT: BLOCK\\*\\*\" docs/loop-engine/seat-contract.md"
    ],
    "quality_checks": [
      "The doc says Markdown-bold verdict lines are accepted.",
      "The doc still says exactly one review verdict is required.",
      "No code or unrelated docs are changed."
    ],
    "expected_artifacts": [
      "report.md",
      "diff.patch",
      "test-results.txt",
      "result.json"
    ]
  },
  {
    "id": "report_session_block_test",
    "category": "repo-local",
    "prompt": "Add a focused unittest showing skills/loop-engine/bin/report-session.py includes a BLOCK review verdict in the minute index. Keep the implementation unchanged unless the test exposes a real bug.",
    "allowed_paths": [
      "skills/loop-engine/tests/test_report_session.py",
      "skills/loop-engine/bin/report-session.py"
    ],
    "verify_cmds": [
      "python3 skills/loop-engine/tests/test_report_session.py"
    ],
    "quality_checks": [
      "The new test constructs a temporary session fixture.",
      "The report minute index displays BLOCK for a review minute.",
      "The existing PASS test still passes."
    ],
    "expected_artifacts": [
      "report.md",
      "diff.patch",
      "test-results.txt",
      "result.json"
    ]
  },
  {
    "id": "eval_runner_missing_command_test",
    "category": "repo-local",
    "prompt": "Add a focused unittest for skills/loop-engine/bin/eval-roundtable.py showing eval_task returns ERR and passed=false when a task has no test_cmd. Keep behavior compatible with existing Phase 1 evals.",
    "allowed_paths": [
      "skills/loop-engine/tests/test_eval_roundtable.py",
      "skills/loop-engine/bin/eval-roundtable.py"
    ],
    "verify_cmds": [
      "python3 skills/loop-engine/tests/test_eval_roundtable.py"
    ],
    "quality_checks": [
      "The test checks missing test_cmd behavior directly.",
      "No live agents are called.",
      "Existing eval runner tests still pass."
    ],
    "expected_artifacts": [
      "report.md",
      "diff.patch",
      "test-results.txt",
      "result.json"
    ]
  },
  {
    "id": "dogfood_roundtable_report_note",
    "category": "dogfood",
    "prompt": "Improve docs/loop-engine/agent-moa-positioning.md by adding one concise sentence that a compact session report is the preferred human review artifact after a roundtable run. Do not change the product boundary.",
    "allowed_paths": [
      "docs/loop-engine/agent-moa-positioning.md"
    ],
    "verify_cmds": [
      "rg -n \"session report|human review artifact|report\" docs/loop-engine/agent-moa-positioning.md"
    ],
    "quality_checks": [
      "The sentence mentions session reports as human review artifacts.",
      "The existing private prototype boundary remains intact.",
      "No generated roundtable sessions are committed."
    ],
    "expected_artifacts": [
      "report.md",
      "diff.patch",
      "test-results.txt",
      "result.json"
    ]
  },
  {
    "id": "dogfood_memory_boundary_note",
    "category": "dogfood",
    "prompt": "Improve docs/loop-engine/agent-moa-positioning.md by adding one concise sentence that benchmark and demo artifacts must stay separate from private operational memory. Do not add publishing guidance.",
    "allowed_paths": [
      "docs/loop-engine/agent-moa-positioning.md"
    ],
    "verify_cmds": [
      "rg -n \"benchmark|demo|private operational memory|operational memory\" docs/loop-engine/agent-moa-positioning.md"
    ],
    "quality_checks": [
      "The sentence distinguishes benchmark/demo artifacts from private operational memory.",
      "The change does not imply public release readiness.",
      "No private memory files are modified."
    ],
    "expected_artifacts": [
      "report.md",
      "diff.patch",
      "test-results.txt",
      "result.json"
    ]
  }
]
```

- [ ] **Step 2: Ignore generated Phase 2 outputs**

Append these lines to `.gitignore`:

```gitignore
evals/loop-engine/phase2/runs/
evals/loop-engine/phase2/worktrees/
```

- [ ] **Step 3: Verify the JSON parses and ignored paths are ignored**

Run:

```bash
python3 -m json.tool evals/loop-engine/phase2/tasks.json >/dev/null
git check-ignore -q evals/loop-engine/phase2/runs/example
git check-ignore -q evals/loop-engine/phase2/worktrees/example
```

Expected: all commands exit `0`.

- [ ] **Step 4: Commit**

```bash
git add .gitignore evals/loop-engine/phase2/tasks.json
git commit -m "test: define loop engine phase2 benchmark tasks"
```

---

### Task 2: Benchmark Runner Schema And Dry Mode

**Files:**
- Create: `skills/loop-engine/bin/benchmark-roundtable.py`
- Create: `skills/loop-engine/tests/test_benchmark_roundtable.py`

- [ ] **Step 1: Write failing tests for task loading and dry-run output**

Create `skills/loop-engine/tests/test_benchmark_roundtable.py` with:

```python
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "benchmark-roundtable.py"
spec = importlib.util.spec_from_file_location("benchmark_roundtable", MODULE)
benchmark = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(benchmark)


def sample_task() -> dict:
    return {
        "id": "sample",
        "category": "repo-local",
        "prompt": "Make a small doc change.",
        "allowed_paths": ["docs/example.md"],
        "verify_cmds": ["python3 -c 'print(1)'"],
        "quality_checks": ["Report exists."],
        "expected_artifacts": ["report.md", "diff.patch", "test-results.txt", "result.json"],
    }


class BenchmarkRoundtableTests(unittest.TestCase):
    def test_load_tasks_requires_phase2_schema(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "tasks.json"
            path.write_text(json.dumps([{"id": "x"}]), encoding="utf-8")
            with self.assertRaises(ValueError):
                benchmark.load_tasks(path)

    def test_load_tasks_accepts_valid_task(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "tasks.json"
            path.write_text(json.dumps([sample_task()]), encoding="utf-8")
            tasks = benchmark.load_tasks(path)
        self.assertEqual(tasks[0]["id"], "sample")

    def test_dry_lane_writes_comparable_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = pathlib.Path(td)
            task = sample_task()
            record = benchmark.run_dry_lane(
                task=task,
                lane="baseline-kimi",
                lane_dir=run_dir / "task-sample" / "baseline-kimi",
                harness_commit="harness",
                task_base_commit="base",
            )

            self.assertEqual(record["lane"], "baseline-kimi")
            self.assertEqual(record["task_id"], "sample")
            self.assertEqual(record["status"], "PASS")
            self.assertTrue((run_dir / "task-sample" / "baseline-kimi" / "result.json").is_file())
            self.assertTrue((run_dir / "task-sample" / "baseline-kimi" / "report.md").is_file())
            self.assertTrue((run_dir / "task-sample" / "baseline-kimi" / "diff.patch").is_file())
            self.assertTrue((run_dir / "task-sample" / "baseline-kimi" / "test-results.txt").is_file())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail because the module is missing**

Run:

```bash
python3 skills/loop-engine/tests/test_benchmark_roundtable.py
```

Expected: FAIL or ERROR because `benchmark-roundtable.py` does not exist.

- [ ] **Step 3: Create the minimal dry-mode runner**

Create `skills/loop-engine/bin/benchmark-roundtable.py` with these functions and CLI:

```python
#!/usr/bin/env python3
"""Phase 2 benchmark runner for Loop Engine vs Kimi baseline."""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import time
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / ".git").exists() and (path / "skills" / "loop-engine").is_dir():
            return path
    raise RuntimeError(f"cannot find repo root from {start}")


ROOT = find_repo_root(Path(__file__).resolve())
DEFAULT_TASKS = ROOT / "evals" / "loop-engine" / "phase2" / "tasks.json"
RUNS_DIR = ROOT / "evals" / "loop-engine" / "phase2" / "runs"
REQUIRED_TASK_KEYS = {
    "id",
    "category",
    "prompt",
    "allowed_paths",
    "verify_cmds",
    "quality_checks",
    "expected_artifacts",
}
LANES = ("baseline-kimi", "roundtable")


def run_cmd(args: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str]:
    proc = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout or ""


def git_output(args: list[str], cwd: Path = ROOT) -> str:
    rc, out = run_cmd(["git", *args], cwd)
    if rc != 0:
        raise RuntimeError(out.strip() or f"git {' '.join(args)} failed")
    return out.strip()


def now_stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def output_path_for(stamp: str) -> Path:
    return RUNS_DIR / stamp


def load_tasks(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("tasks file must contain a list")
    for item in data:
        if not isinstance(item, dict):
            raise ValueError(f"task must be an object: {item}")
        missing = sorted(REQUIRED_TASK_KEYS - set(item))
        if missing:
            raise ValueError(f"task missing {', '.join(missing)}: {item}")
        for key in ("allowed_paths", "verify_cmds", "quality_checks", "expected_artifacts"):
            if not isinstance(item[key], list) or not all(isinstance(v, str) for v in item[key]):
                raise ValueError(f"task {item.get('id', '<unknown>')} field {key} must be a list of strings")
    return data


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_dry_lane(task: dict, lane: str, lane_dir: Path, harness_commit: str, task_base_commit: str) -> dict:
    started = time.time()
    lane_dir.mkdir(parents=True, exist_ok=True)
    report = [
        f"# Dry Benchmark Report: {task['id']} / {lane}",
        "",
        "This is a dry-run artifact. No live agent was called.",
        "",
        "## Prompt",
        task["prompt"],
        "",
    ]
    write_text(lane_dir / "report.md", "\n".join(report))
    write_text(lane_dir / "diff.patch", "# dry run: no diff\n")
    write_text(lane_dir / "test-results.txt", "# dry run: verify commands skipped\n")
    elapsed = time.time() - started
    record = {
        "task_id": task["id"],
        "category": task.get("category", ""),
        "lane": lane,
        "status": "PASS",
        "verify_passed": True,
        "review_verdict": "",
        "blocking_findings": [],
        "changed_files": [],
        "diff_summary": "",
        "contract_valid": True,
        "human_quality_score": None,
        "wall_seconds": round(elapsed, 3),
        "retries": 0,
        "agent_calls": 0,
        "timeout_count": 0,
        "manual_intervention_count": 0,
        "artifact_count": 4,
        "harness_commit": harness_commit,
        "task_base_commit": task_base_commit,
        "report_path": str(lane_dir / "report.md"),
    }
    write_json(lane_dir / "result.json", record)
    return record


def run_dry_batch(tasks: list[dict], run_dir: Path, harness_commit: str, task_base_commit: str) -> list[dict]:
    records = []
    for task in tasks:
        for lane in LANES:
            lane_dir = run_dir / f"task-{task['id']}" / lane
            records.append(run_dry_lane(task, lane, lane_dir, harness_commit, task_base_commit))
    return records


def write_records(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Loop Engine Phase 2 benchmark tasks.")
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS))
    parser.add_argument("--out", default="")
    parser.add_argument("--base", default="loop-engine-mvp-v0.1-internal")
    parser.add_argument("--dry-run", action="store_true", help="Write comparable records without live agent calls.")
    args = parser.parse_args()

    if not args.dry_run:
        raise SystemExit("--dry-run is required until live lanes are implemented")

    tasks = load_tasks(Path(args.tasks))
    stamp = now_stamp()
    run_dir = Path(args.out).resolve() if args.out else output_path_for(stamp)
    harness_commit = git_output(["rev-parse", "HEAD"])
    task_base_commit = git_output(["rev-parse", args.base])
    write_json(run_dir / "batch.json", {
        "stamp": stamp,
        "mode": "dry-run",
        "harness_commit": harness_commit,
        "task_base_commit": task_base_commit,
        "task_count": len(tasks),
    })
    records = run_dry_batch(tasks, run_dir, harness_commit, task_base_commit)
    write_records(run_dir / "records.jsonl", records)
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
python3 skills/loop-engine/tests/test_benchmark_roundtable.py
```

Expected: `Ran 3 tests` and `OK`.

- [ ] **Step 5: Run a dry benchmark batch**

Run:

```bash
python3 skills/loop-engine/bin/benchmark-roundtable.py --dry-run --out /tmp/loop-phase2-dry
test -f /tmp/loop-phase2-dry/records.jsonl
test -f /tmp/loop-phase2-dry/batch.json
```

Expected: all commands exit `0`.

- [ ] **Step 6: Commit**

```bash
git add skills/loop-engine/bin/benchmark-roundtable.py skills/loop-engine/tests/test_benchmark_roundtable.py
git commit -m "test: add phase2 benchmark dry runner"
```

---

### Task 3: Benchmark Summary Tool

**Files:**
- Create: `skills/loop-engine/bin/summarize-benchmark.py`
- Create: `skills/loop-engine/tests/test_summarize_benchmark.py`

- [ ] **Step 1: Write failing summary tests**

Create `skills/loop-engine/tests/test_summarize_benchmark.py` with:

```python
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "summarize-benchmark.py"
spec = importlib.util.spec_from_file_location("summarize_benchmark", MODULE)
summary = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(summary)


def record(task_id: str, lane: str, status: str, seconds: float) -> dict:
    return {
        "task_id": task_id,
        "category": "repo-local",
        "lane": lane,
        "status": status,
        "verify_passed": status == "PASS",
        "review_verdict": "",
        "blocking_findings": [] if status == "PASS" else ["failed verify"],
        "wall_seconds": seconds,
    }


class SummarizeBenchmarkTests(unittest.TestCase):
    def test_classify_roundtable_better_when_only_roundtable_passes(self):
        kimi = record("x", "baseline-kimi", "ERR", 10)
        rt = record("x", "roundtable", "PASS", 20)
        outcome, reason = summary.classify_pair(kimi, rt)
        self.assertEqual(outcome, "roundtable_better")
        self.assertIn("roundtable passed", reason)

    def test_classify_kimi_better_when_only_kimi_passes(self):
        kimi = record("x", "baseline-kimi", "PASS", 10)
        rt = record("x", "roundtable", "ERR", 20)
        outcome, reason = summary.classify_pair(kimi, rt)
        self.assertEqual(outcome, "kimi_better")
        self.assertIn("kimi passed", reason)

    def test_classify_tie_when_both_pass(self):
        kimi = record("x", "baseline-kimi", "PASS", 10)
        rt = record("x", "roundtable", "PASS", 20)
        outcome, reason = summary.classify_pair(kimi, rt)
        self.assertEqual(outcome, "tie")
        self.assertIn("both passed", reason)

    def test_build_summary_groups_records_by_task(self):
        records = [
            record("x", "baseline-kimi", "PASS", 10),
            record("x", "roundtable", "PASS", 20),
        ]
        report = summary.build_summary(records)
        self.assertIn("# Loop Engine Phase 2 Benchmark Summary", report)
        self.assertIn("| x | PASS | PASS | tie |", report)

    def test_main_writes_summary_file(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = pathlib.Path(td)
            records_path = run_dir / "records.jsonl"
            records_path.write_text(
                "\n".join(json.dumps(r) for r in [
                    record("x", "baseline-kimi", "PASS", 10),
                    record("x", "roundtable", "PASS", 20),
                ]) + "\n",
                encoding="utf-8",
            )
            rc = summary.main(["--records", str(records_path), "--out", str(run_dir / "summary.md")])
            self.assertEqual(rc, 0)
            self.assertTrue((run_dir / "summary.md").is_file())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail because the module is missing**

Run:

```bash
python3 skills/loop-engine/tests/test_summarize_benchmark.py
```

Expected: FAIL or ERROR because `summarize-benchmark.py` does not exist.

- [ ] **Step 3: Create the summary tool**

Create `skills/loop-engine/bin/summarize-benchmark.py` with:

```python
#!/usr/bin/env python3
"""Summarize Loop Engine Phase 2 benchmark records."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def read_records(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def passed(record: dict | None) -> bool:
    return bool(record and record.get("status") == "PASS" and record.get("verify_passed") is not False)


def classify_pair(kimi: dict | None, roundtable: dict | None) -> tuple[str, str]:
    kimi_passed = passed(kimi)
    roundtable_passed = passed(roundtable)
    if roundtable_passed and not kimi_passed:
        return "roundtable_better", "roundtable passed while kimi did not"
    if kimi_passed and not roundtable_passed:
        return "kimi_better", "kimi passed while roundtable did not"
    if kimi_passed and roundtable_passed:
        return "tie", "both passed quality checks"
    return "inconclusive", "neither lane passed quality checks"


def group_by_task(records: list[dict]) -> dict[str, dict[str, dict]]:
    grouped: dict[str, dict[str, dict]] = defaultdict(dict)
    for record in records:
        grouped[record["task_id"]][record["lane"]] = record
    return dict(grouped)


def build_summary(records: list[dict]) -> str:
    grouped = group_by_task(records)
    counts = defaultdict(int)
    lines = [
        "# Loop Engine Phase 2 Benchmark Summary",
        "",
        "| Task | Kimi | Roundtable | Outcome | Reason |",
        "|---|---|---|---|---|",
    ]
    for task_id in sorted(grouped):
        kimi = grouped[task_id].get("baseline-kimi")
        roundtable = grouped[task_id].get("roundtable")
        outcome, reason = classify_pair(kimi, roundtable)
        counts[outcome] += 1
        lines.append(
            f"| {task_id} | {kimi.get('status', '-') if kimi else '-'} | "
            f"{roundtable.get('status', '-') if roundtable else '-'} | {outcome} | {reason} |"
        )
    lines += [
        "",
        "## Counts",
        "",
    ]
    for key in ("roundtable_better", "kimi_better", "tie", "inconclusive"):
        lines.append(f"- {key}: {counts[key]}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize Loop Engine Phase 2 benchmark records.")
    parser.add_argument("--records", required=True)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    records_path = Path(args.records).resolve()
    out = Path(args.out).resolve() if args.out else records_path.parent / "summary.md"
    out.write_text(build_summary(read_records(records_path)), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
python3 skills/loop-engine/tests/test_summarize_benchmark.py
```

Expected: `Ran 5 tests` and `OK`.

- [ ] **Step 5: Integrate summary generation after dry benchmark**

Run:

```bash
rm -rf /tmp/loop-phase2-dry
python3 skills/loop-engine/bin/benchmark-roundtable.py --dry-run --out /tmp/loop-phase2-dry
python3 skills/loop-engine/bin/summarize-benchmark.py --records /tmp/loop-phase2-dry/records.jsonl --out /tmp/loop-phase2-dry/summary.md
rg -n "tie|roundtable_better|kimi_better|inconclusive" /tmp/loop-phase2-dry/summary.md
```

Expected: all commands exit `0`.

- [ ] **Step 6: Commit**

```bash
git add skills/loop-engine/bin/summarize-benchmark.py skills/loop-engine/tests/test_summarize_benchmark.py
git commit -m "test: add phase2 benchmark summarizer"
```

---

### Task 4: Verify Commands And Live Lane Helpers

**Files:**
- Modify: `skills/loop-engine/bin/benchmark-roundtable.py`
- Modify: `skills/loop-engine/tests/test_benchmark_roundtable.py`

- [ ] **Step 1: Add failing tests for verify commands and dirty-base guard**

Append these tests to `BenchmarkRoundtableTests`:

```python
    def test_run_verify_cmds_marks_failure(self):
        with tempfile.TemporaryDirectory() as td:
            result = benchmark.run_verify_cmds(
                pathlib.Path(td),
                ["python3 -c 'import sys; sys.exit(3)'"],
                timeout=30,
            )
        self.assertFalse(result["passed"])
        self.assertEqual(result["commands"][0]["returncode"], 3)

    def test_refuse_dirty_repo_without_force(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess = __import__("subprocess")
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (repo / "dirty.txt").write_text("dirty", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                benchmark.ensure_clean_repo(repo, force=False)
```

- [ ] **Step 2: Run tests to verify they fail because helpers are missing**

Run:

```bash
python3 skills/loop-engine/tests/test_benchmark_roundtable.py
```

Expected: FAIL with missing `run_verify_cmds` and `ensure_clean_repo`.

- [ ] **Step 3: Add helper functions**

Add these functions to `benchmark-roundtable.py`:

```python
def run_shell(cmd: str, cwd: Path, timeout: int) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout or ""


def run_verify_cmds(repo: Path, commands: list[str], timeout: int) -> dict:
    results = []
    passed = True
    for cmd in commands:
        rc, out = run_shell(cmd, repo, timeout)
        results.append({"command": cmd, "returncode": rc, "output": out[-4000:]})
        if rc != 0:
            passed = False
    return {"passed": passed, "commands": results}


def git_status_porcelain(repo: Path) -> str:
    rc, out = run_cmd(["git", "status", "--porcelain"], repo)
    if rc != 0:
        raise RuntimeError(out.strip() or "git status failed")
    return out.strip()


def ensure_clean_repo(repo: Path, force: bool) -> None:
    status = git_status_porcelain(repo)
    if status and not force:
        raise RuntimeError(f"dirty repository: {repo}")


def changed_files(repo: Path) -> list[str]:
    rc, tracked = run_cmd(["git", "diff", "--name-only", "HEAD"], repo)
    rc2, untracked = run_cmd(["git", "ls-files", "--others", "--exclude-standard"], repo)
    if rc != 0 or rc2 != 0:
        return []
    return sorted({*(x for x in tracked.splitlines() if x), *(x for x in untracked.splitlines() if x)})


def diff_stat(repo: Path) -> str:
    rc, out = run_cmd(["git", "diff", "--stat", "HEAD"], repo)
    return out.strip() if rc == 0 else ""


def diff_patch(repo: Path) -> str:
    rc, out = run_cmd(["git", "diff", "HEAD"], repo)
    return out if rc == 0 else ""
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
python3 skills/loop-engine/tests/test_benchmark_roundtable.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add skills/loop-engine/bin/benchmark-roundtable.py skills/loop-engine/tests/test_benchmark_roundtable.py
git commit -m "test: add phase2 benchmark lane helpers"
```

---

### Task 5: Live Worktree Lane Orchestration

**Files:**
- Modify: `skills/loop-engine/bin/benchmark-roundtable.py`
- Modify: `skills/loop-engine/tests/test_benchmark_roundtable.py`

- [ ] **Step 1: Add failing tests for lane worktree path construction**

Add:

```python
    def test_lane_worktree_path_is_under_phase2_worktrees(self):
        path = benchmark.lane_worktree_path("run-1", "baseline-kimi", "sample")
        self.assertIn("evals/loop-engine/phase2/worktrees", str(path))
        self.assertTrue(str(path).endswith("run-1/baseline-kimi/sample"))
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python3 skills/loop-engine/tests/test_benchmark_roundtable.py
```

Expected: FAIL with missing `lane_worktree_path`.

- [ ] **Step 3: Add lane orchestration helpers**

Add:

```python
WORKTREES_DIR = ROOT / "evals" / "loop-engine" / "phase2" / "worktrees"


def lane_worktree_path(stamp: str, lane: str, task_id: str) -> Path:
    return WORKTREES_DIR / stamp / lane / task_id


def create_lane_worktree(path: Path, base_ref: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"lane worktree already exists: {path}")
    rc, out = run_cmd(["git", "worktree", "add", "--detach", str(path), base_ref], ROOT, timeout=120)
    if rc != 0:
        raise RuntimeError(out.strip() or f"git worktree add failed: {path}")


def lane_prompt(task: dict, lane: str) -> str:
    return "\n".join([
        f"You are running the Loop Engine Phase 2 benchmark lane: {lane}.",
        "Work only inside the current git worktree.",
        "Do not publish, delete external data, change global config, or spend money.",
        "Allowed paths:",
        *[f"- {p}" for p in task["allowed_paths"]],
        "",
        "Task:",
        task["prompt"],
        "",
        "After changes, write a concise report to BENCHMARK-REPORT.md with what changed, verification, and risks.",
    ])
```

- [ ] **Step 4: Add live lane functions**

Add:

```python
def run_kimi_lane(task: dict, lane_repo: Path, lane_dir: Path, timeout: int) -> dict:
    started = time.time()
    prompt = lane_prompt(task, "baseline-kimi")
    rc, out = run_cmd(["kimi", "-p", prompt], lane_repo, timeout=timeout)
    verify = run_verify_cmds(lane_repo, task["verify_cmds"], timeout=timeout)
    report_text = (lane_repo / "BENCHMARK-REPORT.md").read_text(encoding="utf-8", errors="replace") if (lane_repo / "BENCHMARK-REPORT.md").exists() else out[-4000:]
    write_text(lane_dir / "report.md", report_text)
    write_text(lane_dir / "diff.patch", diff_patch(lane_repo))
    write_text(lane_dir / "test-results.txt", json.dumps(verify, ensure_ascii=False, indent=2))
    status = "PASS" if rc == 0 and verify["passed"] else "ERR"
    record = lane_record(task, "baseline-kimi", status, verify, lane_repo, lane_dir, started, rc)
    write_json(lane_dir / "result.json", record)
    return record


def run_roundtable_lane(task: dict, lane_repo: Path, lane_dir: Path, timeout: int) -> dict:
    started = time.time()
    session = f"phase2-{task['id']}"
    env = dict(os.environ)
    env["LOOP_SESSION"] = session
    env["LOOP_SEAT_TIMEOUT"] = str(timeout)
    test_cmd = " && ".join(task["verify_cmds"])
    cmd = [
        "python3",
        str(ROOT / "skills" / "loop-engine" / "bin" / "conductor.py"),
        "--repo",
        str(lane_repo),
        "--task",
        task["prompt"],
        "--test-cmd",
        test_cmd,
        "--max-iters",
        "2",
        "--seats",
        "claude,hermes,kimi",
    ]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout * 4,
    )
    verify = run_verify_cmds(lane_repo, task["verify_cmds"], timeout=timeout)
    session_dir = lane_repo / ".roundtable" / "sessions" / session
    report_path = session_dir / "KB" / "report.md"
    subprocess.run(
        ["python3", str(ROOT / "skills" / "loop-engine" / "bin" / "report-session.py"), str(session_dir), "--out", str(report_path)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else proc.stdout[-4000:]
    write_text(lane_dir / "report.md", report_text)
    write_text(lane_dir / "diff.patch", diff_patch(lane_repo))
    write_text(lane_dir / "test-results.txt", json.dumps(verify, ensure_ascii=False, indent=2))
    status = "PASS" if proc.returncode == 0 and verify["passed"] else "ERR"
    record = lane_record(task, "roundtable", status, verify, lane_repo, lane_dir, started, proc.returncode)
    write_json(lane_dir / "result.json", record)
    return record
```

Also add `lane_record` used above:

```python
def lane_record(task: dict, lane: str, status: str, verify: dict, repo: Path, lane_dir: Path, started: float, returncode: int) -> dict:
    elapsed = time.time() - started
    return {
        "task_id": task["id"],
        "category": task.get("category", ""),
        "lane": lane,
        "status": status,
        "verify_passed": verify["passed"],
        "review_verdict": "",
        "blocking_findings": [] if status == "PASS" else [f"lane returncode {returncode} or verify failed"],
        "changed_files": changed_files(repo),
        "diff_summary": diff_stat(repo),
        "contract_valid": True,
        "human_quality_score": None,
        "wall_seconds": round(elapsed, 3),
        "retries": 0,
        "agent_calls": 1 if lane == "baseline-kimi" else 0,
        "timeout_count": 0,
        "manual_intervention_count": 0,
        "artifact_count": 4,
        "harness_commit": git_output(["rev-parse", "HEAD"]),
        "task_base_commit": git_output(["rev-parse", "HEAD"], repo),
        "report_path": str(lane_dir / "report.md"),
    }
```

- [ ] **Step 5: Extend the CLI for live runs**

Update `main()` so:

- `--dry-run` keeps current dry behavior.
- `--live` enables live lanes.
- `--task-id <id>` can limit to one task.
- `--force-dirty-base` allows a dirty harness repo, but default refuses dirty tracked/untracked state except ignored files.

Expected command shape:

```bash
python3 skills/loop-engine/bin/benchmark-roundtable.py --live --task-id seat_contract_bold_verdict_doc --base loop-engine-mvp-v0.1-internal
```

- [ ] **Step 6: Run tests**

Run:

```bash
python3 skills/loop-engine/tests/test_benchmark_roundtable.py
```

Expected: all tests pass without calling live agents.

- [ ] **Step 7: Commit**

```bash
git add skills/loop-engine/bin/benchmark-roundtable.py skills/loop-engine/tests/test_benchmark_roundtable.py
git commit -m "feat: add phase2 benchmark live lane orchestration"
```

---

### Task 6: Full Verification And Dry Benchmark Integration

**Files:**
- Modify: `skills/loop-engine/bin/benchmark-roundtable.py`

- [ ] **Step 1: Make the runner call the summarizer automatically**

After writing `records.jsonl`, call `summarize-benchmark.py` logic directly or by subprocess to write `summary.md`.

If importing, use:

```python
def write_summary(run_dir: Path) -> None:
    import importlib.util
    module_path = ROOT / "skills" / "loop-engine" / "bin" / "summarize-benchmark.py"
    spec = importlib.util.spec_from_file_location("summarize_benchmark", module_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    records = mod.read_records(run_dir / "records.jsonl")
    write_text(run_dir / "summary.md", mod.build_summary(records))
```

- [ ] **Step 2: Verify dry benchmark writes summary**

Run:

```bash
rm -rf /tmp/loop-phase2-dry
python3 skills/loop-engine/bin/benchmark-roundtable.py --dry-run --out /tmp/loop-phase2-dry
test -f /tmp/loop-phase2-dry/summary.md
rg -n "Loop Engine Phase 2 Benchmark Summary" /tmp/loop-phase2-dry/summary.md
```

Expected: all commands exit `0`.

- [ ] **Step 3: Run full local verification**

Run:

```bash
python3 -m unittest discover -s skills/loop-engine/tests
bash skills/loop-engine/bin/smoke-roundtable-speedup.sh
python3 skills/loop-engine/bin/eval-roundtable.py --timeout 180
python3 skills/loop-engine/bin/eval-roundtable.py --timeout 180 --include-optional
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add skills/loop-engine/bin/benchmark-roundtable.py
git commit -m "feat: summarize phase2 benchmark runs"
```

---

### Task 7: Controlled Live Task Pair

**Files:**
- Generated ignored artifacts under `evals/loop-engine/phase2/runs/**`
- Generated ignored worktrees under `evals/loop-engine/phase2/worktrees/**`

- [ ] **Step 1: Confirm live CLIs are available**

Run:

```bash
kimi --version
hermes --version
claude --version
```

Expected: each command exits `0`. If one is missing, mark the controlled live run blocked in the final report and do not fake evidence.

- [ ] **Step 2: Run one controlled live pair**

Use the lowest-risk docs-only task:

```bash
python3 skills/loop-engine/bin/benchmark-roundtable.py \
  --live \
  --task-id seat_contract_bold_verdict_doc \
  --base loop-engine-mvp-v0.1-internal
```

Expected:

- one run directory under `evals/loop-engine/phase2/runs/`;
- one baseline lane result;
- one roundtable lane result;
- `records.jsonl`;
- `summary.md`.

- [ ] **Step 3: Inspect generated records**

Run:

```bash
latest="$(ls -td evals/loop-engine/phase2/runs/* | head -1)"
cat "$latest/records.jsonl"
sed -n '1,180p' "$latest/summary.md"
```

Expected:

- Both lanes have a record.
- Statuses are evidence-based.
- If either lane is `ERR`, the reason is visible in `blocking_findings` or `test-results.txt`.

- [ ] **Step 4: Do not merge lane worktree changes**

Run:

```bash
git status --short --branch
```

Expected: no tracked changes from lane worktrees appear in the harness repo.

Commit nothing in this task unless the runner itself required a fix.

---

### Task 8: Phase 2 Benchmark Report

**Files:**
- Create: `docs/loop-engine/phase2-benchmark-report.md`

- [ ] **Step 1: Create the report from dry and live evidence**

Generate `docs/loop-engine/phase2-benchmark-report.md` from the latest live summary so the status cells come from observed evidence:

```bash
latest="$(ls -td evals/loop-engine/phase2/runs/* | head -1)"
python3 - "$latest" <<'PY'
from pathlib import Path
import sys

run = Path(sys.argv[1])
summary = run / "summary.md"
rows = [
    line for line in summary.read_text(encoding="utf-8").splitlines()
    if line.startswith("| seat_contract_bold_verdict_doc |")
]
live_row = rows[0] if rows else "| seat_contract_bold_verdict_doc | missing | missing | inconclusive | summary row not found |"
body = f"""# Loop Engine Phase 2 Benchmark Report

## Status

Phase 2 benchmark harness is implemented. Full five-task live benchmark is not complete until all five task pairs are run or explicitly marked blocked.

## Current Evidence

- Dry benchmark mode produced comparable records for all five tasks.
- One controlled live task pair was attempted for `seat_contract_bold_verdict_doc`.

## Live Pair Result

| Task | Kimi | Roundtable | Outcome | Notes |
|---|---|---|---|---|
{live_row}

Latest run directory: `{run}`

## Interpretation

The harness is now capable of collecting evidence. It is too early to claim the roundtable is better than Kimi until all five pairs are run or blocked with reasons.

## Next Runs

- `report_session_block_test`
- `eval_runner_missing_command_test`
- `dogfood_roundtable_report_note`
- `dogfood_memory_boundary_note`

## Decision

Current decision: continue Phase 2 data collection.
"""
Path("docs/loop-engine/phase2-benchmark-report.md").write_text(body, encoding="utf-8")
PY
```

- [ ] **Step 2: Verify report references no fake evidence**

Run:

```bash
rg -n "missing \\| missing|summary row not found|fake" docs/loop-engine/phase2-benchmark-report.md
```

Expected: command exits non-zero when the live summary row was found and no fake evidence marker remains.

- [ ] **Step 3: Commit**

```bash
git add docs/loop-engine/phase2-benchmark-report.md
git commit -m "docs: start loop engine phase2 benchmark report"
```

---

### Task 9: Final Verification

**Files:**
- No file edits unless verification exposes a bug.

- [ ] **Step 1: Run all verification**

Run:

```bash
git diff --check
python3 -m unittest discover -s skills/loop-engine/tests
bash skills/loop-engine/bin/smoke-roundtable-speedup.sh
python3 skills/loop-engine/bin/eval-roundtable.py --timeout 180
python3 skills/loop-engine/bin/eval-roundtable.py --timeout 180 --include-optional
python3 skills/loop-engine/bin/benchmark-roundtable.py --dry-run --out /tmp/loop-phase2-final-dry
test -f /tmp/loop-phase2-final-dry/summary.md
```

Expected: all commands pass.

- [ ] **Step 2: Clean only generated caches**

Run:

```bash
find skills/loop-engine -name __pycache__ -type d -print
rm -rf skills/loop-engine/bin/__pycache__ skills/loop-engine/tests/__pycache__
```

Do not delete `.roundtable/`, `roundtable-memory/`, historical branch refs, or unrelated `.DS_Store`.

- [ ] **Step 3: Inspect final status**

Run:

```bash
git status --short --branch --ignored
git log --oneline --decorate -10
```

Expected:

- only known unrelated `.DS_Store`, ignored `.roundtable/`, ignored `.venv/`, ignored eval run/worktree output, or existing untracked plans remain;
- all Phase 2 implementation files are committed.

---

## Self-Review Checklist

- Spec coverage: tasks map to schema, runner, summary, dry run, live worktree lanes, report, and verification.
- Scope: no publishing, no new seats, no global config changes.
- TDD: each production script starts with a failing test.
- Safety: live mode is explicit; dry mode is testable and default for local verification.
- Evidence: final report must distinguish "harness works" from "roundtable is proven better".
