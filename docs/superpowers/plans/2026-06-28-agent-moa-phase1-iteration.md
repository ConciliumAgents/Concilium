# Agent MoA Phase 1 Iteration Implementation Plan

> Status: completed. This plan is retained as implementation history; the canonical closeout is `docs/loop-engine/mvp-closeout-2026-06-29.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Loop Engine from a personal working prototype into a reproducible, testable Agent-level MoA prototype with clear contracts, baseline evals, and handoff reports.

**Architecture:** Keep the existing blackboard + native-shell seat architecture. Phase 1 should not add new agent providers or public packaging; it should tighten the current `claude` / `hermes` / `kimi` / `codex` orchestration, document the seat contract, add offline eval infrastructure, and generate readable session reports.

**Tech Stack:** Python standard library, Bash seat wrappers, Markdown docs, existing `.roundtable/` blackboard, existing `roundtable-memory/`, no new runtime dependencies.

---

## New Session Start Prompt

Use this prompt in the new session:

```text
请在 /Users/melee/Documents/agents 里按 docs/superpowers/plans/2026-06-28-agent-moa-phase1-iteration.md 执行 Phase 1。先完整读计划和相关现有文件；不要改 .DS_Store；不要公开或清理历史 roundtable sessions；先做 Task 1，然后每个 task 完成后运行对应验证命令并汇报。
```

## Scope

This plan implements Phase 1 only.

Phase 1 includes:

- Resolve documentation drift around lesson archival and current seat roles.
- Add a durable seat contract document.
- Add an offline validator for seat outputs.
- Add a small eval dataset and runner that can run in dry mode first.
- Add a session report generator so each run can be reviewed without reading every minute file.
- Add a short README-style positioning note for the project.

Phase 1 excludes:

- Adding OpenClaw, Aider, Continue, or local model seats.
- Publishing a public repo.
- Changing global Claude, Codex, Kimi, or Hermes configuration.
- Deleting historical `.roundtable/` sessions.
- Refactoring `conductor.py` into many modules.

## Existing Files To Read First

- `skills/loop-engine/SKILL.md`
- `skills/loop-engine/bin/conductor.py`
- `skills/loop-engine/bin/seat-claude.sh`
- `skills/loop-engine/bin/seat-hermes.sh`
- `skills/loop-engine/bin/seat-kimi.sh`
- `skills/loop-engine/bin/seat-codex.sh`
- `skills/loop-engine/bin/smoke-roundtable-speedup.sh`
- `skills/loop-engine/bin/smoke-roundtable-memory.sh`
- `roundtable-memory/README.md`
- `roundtable-memory/LESSONS.md`
- `roundtable-memory/ROSTER-PROFILES.md`
- `docs/superpowers/specs/2026-06-24-loop-engine-design.md`
- `docs/superpowers/specs/2026-06-27-roundtable-speedup-design.md`
- `docs/superpowers/specs/2026-06-28-roster-profiles-design.md`

## File Structure

Create:

- `docs/loop-engine/agent-moa-positioning.md`
  Short product/architecture positioning: Agent MoA means mixing native agent shells, not only model outputs.

- `docs/loop-engine/seat-contract.md`
  Human-readable contract for `plan`, `exec`, and `review` seat modes.

- `skills/loop-engine/bin/seat-contract-validate.py`
  Offline validator for plan JSON, verdict lines, lesson sections, and basic minute hygiene.

- `skills/loop-engine/tests/test_seat_contract_validate.py`
  Standard-library tests for the validator.

- `evals/loop-engine/tasks.json`
  Small fixed eval dataset for Phase 1.

- `skills/loop-engine/bin/eval-roundtable.py`
  Offline-first eval runner that can call `conductor.py` in dry mode and write JSONL results.

- `skills/loop-engine/bin/report-session.py`
  Report generator for `.roundtable/sessions/<id>/`.

Modify:

- `roundtable-memory/LESSONS.md`
  Update stale archival wording from old `iter-*-claude-exec.md` behavior to current `iter-*-*-exec.md` behavior.

- `skills/loop-engine/SKILL.md`
  Add pointers to the seat contract, eval runner, and report generator.

- `skills/loop-engine/bin/smoke-roundtable-speedup.sh`
  Add one validator/report smoke check after the existing offline checks.

Do not modify:

- `.DS_Store` files already visible in git status.
- Historical `.roundtable/sessions/**` contents.
- Global config under `~/.claude`, `~/.codex`, `~/.kimi-code`, or Hermes config paths.

---

### Task 1: Documentation Drift And Positioning

**Files:**
- Create: `docs/loop-engine/agent-moa-positioning.md`
- Modify: `roundtable-memory/LESSONS.md`
- Modify: `skills/loop-engine/SKILL.md`

- [ ] **Step 1: Confirm current drift**

Run:

```bash
rg -n "iter-\\*-claude-exec|综合席纪要|iter-\\*-\\*-exec|ROSTER-PROFILES|Agent MoA|MoA" \
  roundtable-memory skills/loop-engine docs/superpowers
```

Expected:

- `roundtable-memory/LESSONS.md` still contains stale wording about `minutes/iter-*-claude-exec.md`.
- `conductor.py` already archives lessons from `iter-*-*-exec.md`.

- [ ] **Step 2: Update `roundtable-memory/LESSONS.md` wording**

Replace the top write-instruction block with:

```markdown
> 写入：`archive_to_memory()` 抽各执行席纪要 `minutes/iter-*-*-exec.md` 末尾的 `## 教训` 节，
> 按 `### 通用` / `### <项目>` 归位；同文本 SHA-256 去重。
```

Keep the existing lesson bullets unchanged unless they directly contradict this statement.

- [ ] **Step 3: Create `docs/loop-engine/agent-moa-positioning.md`**

Write this content:

```markdown
# Agent MoA Positioning

Loop Engine is an Agent-level Mixture of Agents system.

It does not only combine model outputs. It combines native agent shells: each seat keeps its own CLI, model routing, permissions, memory behavior, tool habits, timeout profile, and review style.

## Core Claim

Model-level MoA asks several models for answers and asks an aggregator to synthesize them.

Agent-level MoA coordinates complete working environments:

- `claude`: planning and synthesis when full context matters.
- `kimi`: fast execution and strict boundary review.
- `hermes`: fast execution and heterogeneous DeepSeek-family review.
- `codex`: code review when reachable in the local environment.

The shared blackboard `.roundtable/` is the source of truth. Seats pull context from the same KB, write minutes, and are coordinated by `conductor.py`.

## Current Product Boundary

This repo is a private working prototype. It is not ready to publish as a complete public product.

Public-facing work should first prove:

- repeatable seat contracts;
- eval results against single-agent baselines;
- readable reports for each session;
- clear separation between demo assets and private operational memory.

## Phase 1 Success Criteria

- A new worker can understand the architecture from docs without reading every historical session.
- Seat outputs can be checked offline.
- Eval tasks can run in dry mode without calling live models.
- A roundtable session can produce a compact report for human review.
```

- [ ] **Step 4: Add doc pointers in `skills/loop-engine/SKILL.md`**

Add a short paragraph after the opening description:

```markdown
补充文档：Agent MoA 的定位见 `docs/loop-engine/agent-moa-positioning.md`；座位输入/输出契约见 `docs/loop-engine/seat-contract.md`；离线验证与评测入口见 `bin/seat-contract-validate.py`、`bin/eval-roundtable.py`、`bin/report-session.py`。
```

- [ ] **Step 5: Verify docs**

Run:

```bash
rg -n "iter-\\*-claude-exec|docs/loop-engine/agent-moa-positioning.md|seat-contract.md|eval-roundtable.py|report-session.py" \
  roundtable-memory/LESSONS.md skills/loop-engine/SKILL.md docs/loop-engine
```

Expected:

- No `iter-*-claude-exec` remains in `roundtable-memory/LESSONS.md`.
- `skills/loop-engine/SKILL.md` links the new docs and tools.

Commit:

```bash
git add roundtable-memory/LESSONS.md skills/loop-engine/SKILL.md docs/loop-engine/agent-moa-positioning.md
git commit -m "docs: clarify agent moa positioning"
```

---

### Task 2: Seat Contract Document

**Files:**
- Create: `docs/loop-engine/seat-contract.md`

- [ ] **Step 1: Create the contract doc**

Write:

```markdown
# Loop Engine Seat Contract

This document defines the minimum contract for every native-shell seat called by `skills/loop-engine/bin/conductor.py`.

## Shared Context

Each seat receives a prompt containing `loop_seat_preamble`, which points it at the session blackboard:

- `.roundtable/sessions/<session>/KB/project.md`
- `.roundtable/sessions/<session>/KB/task.md`
- `.roundtable/sessions/<session>/KB/state.md`
- `.roundtable/sessions/<session>/KB/roster.md`
- `.roundtable/sessions/<session>/KB/diff.patch`
- `.roundtable/sessions/<session>/KB/test-results.txt`
- `.roundtable/sessions/<session>/minutes/`

The seat must read the blackboard instead of relying only on the brief.

## Mode: plan

Purpose: produce an execution plan for this iteration.

Allowed side effects: none.

Required output:

```json
[
  {"agent": "kimi", "subtask": "Implement the concrete change."},
  {"agent": "hermes", "subtask": "Check environment and docs consistency."}
]
```

Rules:

- The JSON plan must be inside a fenced `json` block.
- `agent` must be one of `claude`, `codex`, `hermes`, or `kimi`.
- Execution subtasks should target current executors, normally `kimi` or `hermes`.
- The conductor may drop tasks assigned to non-executors or the reviewer.

## Mode: exec

Purpose: implement one concrete subtask.

Allowed side effects: workspace file changes only. No deletion, spending, external publishing, or global config changes.

Required end section:

```markdown
## 教训
### 通用
- （无）
### <项目名>
- （无）
```

Rules:

- If there is no lesson, write `- （无）`.
- If work is incomplete, state that directly in the minute output and `KB/state.md`.
- Exit code `0` means the seat process completed. It does not mean the task is correct; review decides that.

## Mode: review

Purpose: independently check the work.

Allowed side effects: none.

Required final line:

```text
VERDICT: PASS
```

or:

```text
VERDICT: BLOCK
```

Rules:

- Mark findings with `[CRITICAL]`, `[HIGH]`, `[MEDIUM]`, or `[LOW]`.
- Return `PASS` only when there are no `[CRITICAL]` or `[HIGH]` issues.
- If the conductor brief says a seat failed or a subtask was dropped, judge whether task completeness was actually harmed. Do not mechanically block when another seat completed the work.

## Exit Code Mapping

- `0`: process succeeded; for review this maps to PASS only when the verdict parser finds PASS.
- `2`: review found a blocking issue.
- `1`: seat process or parsing error.
- `124`: conductor timeout killed the process group.

## Privacy Boundary

Seat outputs may be archived into `roundtable-memory/`. Do not write API keys, tokens, private customer data, payment data, or unsupported-region workarounds into minutes or lessons.
```

- [ ] **Step 2: Verify contract references match scripts**

Run:

```bash
rg -n "VERDICT: PASS|VERDICT: BLOCK|## 教训|plan\\|exec\\|review|124|loop_verdict_exit" \
  docs/loop-engine/seat-contract.md skills/loop-engine/bin
```

Expected:

- Contract terms appear in both docs and scripts.
- No missing mode names.

Commit:

```bash
git add docs/loop-engine/seat-contract.md
git commit -m "docs: define loop engine seat contract"
```

---

### Task 3: Offline Seat Contract Validator

**Files:**
- Create: `skills/loop-engine/bin/seat-contract-validate.py`
- Create: `skills/loop-engine/tests/test_seat_contract_validate.py`

- [ ] **Step 1: Create the validator**

Create `skills/loop-engine/bin/seat-contract-validate.py`:

```python
#!/usr/bin/env python3
"""Offline validator for Loop Engine seat minute files."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

AGENTS = {"claude", "codex", "hermes", "kimi"}
VERDICT_RE = re.compile(r"^\s*VERDICT:\s*(PASS|BLOCK)\s*$", re.M)


def extract_plan(text: str) -> list[dict]:
    match = re.search(r"```json\s*(.+?)```", text, re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent", "")).strip().lower()
        subtask = str(item.get("subtask", "")).strip()
        if agent in AGENTS and subtask:
            out.append({"agent": agent, "subtask": subtask})
    return out


def validate_plan(text: str) -> list[str]:
    errors = []
    if not extract_plan(text):
        errors.append("plan output must contain a fenced json list with valid agent/subtask entries")
    return errors


def validate_exec(text: str) -> list[str]:
    errors = []
    if "## 教训" not in text:
        errors.append("exec output must include ## 教训")
    if "### 通用" not in text:
        errors.append("exec output must include ### 通用")
    if "### <项目名>" not in text and not re.search(r"^###\s+\S+", text, re.M):
        errors.append("exec output must include a project lesson subsection")
    return errors


def validate_review(text: str) -> list[str]:
    errors = []
    verdicts = VERDICT_RE.findall(text)
    if len(verdicts) != 1:
        errors.append("review output must contain exactly one final VERDICT line")
    return errors


def infer_mode(path: Path) -> str:
    name = path.name
    if "-plan" in name:
        return "plan"
    if "-exec" in name:
        return "exec"
    if "-review" in name:
        return "review"
    return ""


def validate_file(path: Path, mode: str = "") -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    selected = mode or infer_mode(path)
    if selected == "plan":
        return validate_plan(text)
    if selected == "exec":
        return validate_exec(text)
    if selected == "review":
        return validate_review(text)
    return [f"cannot infer mode for {path.name}; pass --mode plan|exec|review"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Loop Engine seat minute files.")
    parser.add_argument("paths", nargs="+", help="Minute files to validate.")
    parser.add_argument("--mode", choices=["plan", "exec", "review"], default="")
    args = parser.parse_args()

    failed = 0
    for raw in args.paths:
        path = Path(raw)
        errors = validate_file(path, args.mode)
        if errors:
            failed += 1
            print(f"FAIL {path}", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
        else:
            print(f"PASS {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Create validator tests**

Create `skills/loop-engine/tests/test_seat_contract_validate.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / "bin" / "seat-contract-validate.py"
spec = importlib.util.spec_from_file_location("seat_contract_validate", MODULE)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


class SeatContractValidateTests(unittest.TestCase):
    def test_extract_valid_plan(self):
        text = '```json\n[{"agent":"kimi","subtask":"Do the work."}]\n```'
        self.assertEqual(
            validator.extract_plan(text),
            [{"agent": "kimi", "subtask": "Do the work."}],
        )

    def test_invalid_plan_has_error(self):
        self.assertTrue(validator.validate_plan("no json here"))

    def test_exec_requires_lessons(self):
        self.assertEqual(
            validator.validate_exec("done\n## 教训\n### 通用\n- （无）\n### agents\n- （无）"),
            [],
        )
        self.assertIn("## 教训", validator.validate_exec("done")[0])

    def test_review_requires_exactly_one_verdict(self):
        self.assertEqual(validator.validate_review("Looks fine\nVERDICT: PASS\n"), [])
        self.assertTrue(validator.validate_review("VERDICT: PASS\nVERDICT: BLOCK\n"))
        self.assertTrue(validator.validate_review("no verdict"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests**

Run:

```bash
python3 skills/loop-engine/tests/test_seat_contract_validate.py
```

Expected:

```text
....
----------------------------------------------------------------------
Ran 4 tests

OK
```

- [ ] **Step 4: Run validator against a known historical session**

Run:

```bash
python3 skills/loop-engine/bin/seat-contract-validate.py \
  .roundtable/sessions/20260627-001238-任务-迭代-Kimi-承接迁移方案至-PLAN-/minutes/iter-1-kimi-review.md
```

Expected:

- PASS if the historical review has exactly one verdict.
- If this historical file fails because old minutes predate the contract, record that in the implementation summary and do not rewrite history.

Commit:

```bash
git add skills/loop-engine/bin/seat-contract-validate.py skills/loop-engine/tests/test_seat_contract_validate.py
git commit -m "test: add loop engine seat contract validator"
```

---

### Task 4: Offline Eval Dataset And Runner

**Files:**
- Create: `evals/loop-engine/tasks.json`
- Create: `skills/loop-engine/bin/eval-roundtable.py`

- [ ] **Step 1: Create eval dataset**

Create `evals/loop-engine/tasks.json`:

```json
[
  {
    "id": "doc_drift_lessons_archive",
    "category": "docs-consistency",
    "task": "Check whether roundtable-memory/LESSONS.md describes the current lesson archival behavior in conductor.py.",
    "test_cmd": "python3 skills/loop-engine/tests/test_seat_contract_validate.py",
    "expected_status": "PASS"
  },
  {
    "id": "seat_contract_validator",
    "category": "contract",
    "task": "Validate that a review minute must contain exactly one VERDICT line and an exec minute must contain a lesson section.",
    "test_cmd": "python3 skills/loop-engine/tests/test_seat_contract_validate.py",
    "expected_status": "PASS"
  },
  {
    "id": "speedup_smoke",
    "category": "orchestration",
    "task": "Run the offline roundtable speedup smoke test and confirm reviewer resolution, fallback, and lesson archival logic.",
    "test_cmd": "bash skills/loop-engine/bin/smoke-roundtable-speedup.sh",
    "expected_status": "PASS"
  },
  {
    "id": "memory_smoke",
    "category": "memory",
    "task": "Run the roundtable memory smoke test and confirm memory import/archive behavior remains compatible.",
    "test_cmd": "bash skills/loop-engine/bin/smoke-roundtable-memory.sh /Users/melee/Documents/agents",
    "expected_status": "PASS"
  }
]
```

- [ ] **Step 2: Create eval runner**

Create `skills/loop-engine/bin/eval-roundtable.py`:

```python
#!/usr/bin/env python3
"""Offline-first eval runner for Loop Engine Phase 1."""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS = ROOT / "evals" / "loop-engine" / "tasks.json"
OUT_DIR = ROOT / "evals" / "loop-engine" / "runs"


def load_tasks(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("tasks file must contain a list")
    for item in data:
        for key in ("id", "task", "expected_status"):
            if key not in item:
                raise ValueError(f"task missing {key}: {item}")
    return data


def run_cmd(cmd: str, timeout: int) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout


def eval_task(task: dict, timeout: int) -> dict:
    cmd = task.get("test_cmd", "")
    if not cmd:
        return {
            "id": task["id"],
            "status": "ERR",
            "passed": False,
            "output": "missing test_cmd",
        }
    rc, output = run_cmd(cmd, timeout)
    status = "PASS" if rc == 0 else "ERR"
    return {
        "id": task["id"],
        "category": task.get("category", ""),
        "status": status,
        "expected_status": task["expected_status"],
        "passed": status == task["expected_status"],
        "returncode": rc,
        "command": cmd,
        "output": output[-4000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Loop Engine eval tasks.")
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS))
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    tasks = load_tasks(Path(args.tasks))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = OUT_DIR / f"{stamp}.jsonl"

    failed = 0
    with out_path.open("w", encoding="utf-8") as out:
        for task in tasks:
            result = eval_task(task, args.timeout)
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            mark = "PASS" if result["passed"] else "FAIL"
            print(f"{mark} {result['id']} status={result['status']} expected={result['expected_status']}")
            if not result["passed"]:
                failed += 1

    print(f"wrote {out_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run eval runner**

Run:

```bash
python3 skills/loop-engine/bin/eval-roundtable.py --timeout 180
```

Expected:

- It writes `evals/loop-engine/runs/<timestamp>.jsonl`.
- It prints one line per eval.
- Failing evals are acceptable only if the failure is an existing smoke-test limitation; record the exact failing task in the implementation summary.

Commit:

```bash
git add evals/loop-engine/tasks.json skills/loop-engine/bin/eval-roundtable.py
git commit -m "test: add loop engine phase one eval runner"
```

---

### Task 5: Session Report Generator

**Files:**
- Create: `skills/loop-engine/bin/report-session.py`

- [ ] **Step 1: Create report generator**

Create `skills/loop-engine/bin/report-session.py`:

```python
#!/usr/bin/env python3
"""Generate a compact human report for one Loop Engine session."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

VERDICT_RE = re.compile(r"^\s*VERDICT:\s*(PASS|BLOCK)\s*$", re.M)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def summarize_minutes(minutes_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(minutes_dir.glob("iter-*-*.md")):
        text = read(path)
        verdict = ",".join(VERDICT_RE.findall(text))
        match = re.match(r"iter-(\d+)-(.+?)-(plan|exec|review)", path.name)
        rows.append({
            "file": path.name,
            "iter": match.group(1) if match else "",
            "seat": match.group(2) if match else "",
            "mode": match.group(3) if match else "",
            "verdict": verdict,
            "bytes": len(text.encode("utf-8")),
        })
    return rows


def build_report(session: Path) -> str:
    kb = session / "KB"
    conclusion = read(kb / "conclusion.md").strip()
    task = read(kb / "task.md").strip()
    tests = read(kb / "test-results.txt").strip()
    roundtable = {}
    if (session / "roundtable.json").exists():
        try:
            roundtable = json.loads(read(session / "roundtable.json"))
        except json.JSONDecodeError:
            roundtable = {}

    rows = summarize_minutes(session / "minutes")
    lines = [
        f"# Roundtable Session Report: {session.name}",
        "",
        "## Session",
        f"- Participants: {', '.join(roundtable.get('participants', [])) or 'unknown'}",
        f"- Iteration: {roundtable.get('iter', 'unknown')}",
        "",
        "## Conclusion",
        conclusion or "No conclusion.md found.",
        "",
        "## Task Snapshot",
        task[:2000] or "No task.md found.",
        "",
        "## Minute Index",
        "| Iter | Seat | Mode | Verdict | Bytes | File |",
        "|---|---|---|---|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['iter']} | {row['seat']} | {row['mode']} | {row['verdict'] or '-'} | {row['bytes']} | `{row['file']}` |"
        )
    lines += [
        "",
        "## Latest Test Output",
        "```text",
        tests[-3000:] if tests else "No test-results.txt found.",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Loop Engine session report.")
    parser.add_argument("session", help=".roundtable/sessions/<id> path")
    parser.add_argument("--out", default="", help="Output markdown path. Defaults to KB/report.md.")
    args = parser.parse_args()

    session = Path(args.session).resolve()
    out = Path(args.out).resolve() if args.out else session / "KB" / "report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_report(session), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Generate report for one existing session**

Run:

```bash
python3 skills/loop-engine/bin/report-session.py \
  ".roundtable/sessions/20260627-001238-任务-迭代-Kimi-承接迁移方案至-PLAN-"
```

Expected:

- It prints the path to `KB/report.md`.
- The report contains a minute table.

- [ ] **Step 3: Validate report content**

Run:

```bash
rg -n "Roundtable Session Report|Minute Index|Latest Test Output" \
  ".roundtable/sessions/20260627-001238-任务-迭代-Kimi-承接迁移方案至-PLAN-/KB/report.md"
```

Expected:

- All three headings are present.

Commit:

```bash
git add skills/loop-engine/bin/report-session.py
git commit -m "feat: add loop engine session report generator"
```

Note: Do not add generated `.roundtable/**/KB/report.md` unless the repo already tracks that session content intentionally.

---

### Task 6: Wire Validator Into Existing Smoke Test

**Files:**
- Modify: `skills/loop-engine/bin/smoke-roundtable-speedup.sh`

- [ ] **Step 1: Add validator smoke section near the end**

Add this before the final summary:

```bash
# ---- T7: seat contract validator unit tests ----
echo ""; echo "=== T7: seat contract validator unit tests ==="
if python3 "$SCRIPT_DIR/../tests/test_seat_contract_validate.py" >/tmp/loop-seat-contract-test.out 2>&1; then
  _ok "T7 seat contract validator tests pass"
else
  cat /tmp/loop-seat-contract-test.out
  _no "T7 seat contract validator tests fail"
fi
```

- [ ] **Step 2: Run speedup smoke**

Run:

```bash
bash skills/loop-engine/bin/smoke-roundtable-speedup.sh
```

Expected:

- The existing checks still pass.
- New `T7 seat contract validator tests pass` appears.

Commit:

```bash
git add skills/loop-engine/bin/smoke-roundtable-speedup.sh
git commit -m "test: include seat contract validator in smoke test"
```

---

### Task 7: Final Verification And Handoff

**Files:**
- No new files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
python3 skills/loop-engine/tests/test_seat_contract_validate.py
bash skills/loop-engine/bin/smoke-roundtable-speedup.sh
python3 skills/loop-engine/bin/eval-roundtable.py --timeout 180
```

Expected:

- Unit tests pass.
- Speedup smoke passes.
- Eval runner writes one JSONL result file and prints pass/fail per task.

- [ ] **Step 2: Check git status**

Run:

```bash
git status --short
```

Expected:

- Only intentional Phase 1 files are modified or added.
- Existing `.DS_Store` files may remain untracked; do not add or delete them unless the user explicitly asks.

- [ ] **Step 3: Write implementation summary**

In the final response, report:

- Which tasks were completed.
- Which verification commands passed.
- Any eval tasks that failed and why.
- Any files intentionally left uncommitted.
- Whether `.DS_Store` files were ignored.

## Self-Review Checklist

Before calling the work complete, verify:

- `roundtable-memory/LESSONS.md` no longer describes old `claude-exec` archival behavior.
- `docs/loop-engine/seat-contract.md` matches the current seat scripts.
- `seat-contract-validate.py` has passing unit tests.
- `eval-roundtable.py` can run without live model calls.
- `report-session.py` can generate a report from an existing session.
- `skills/loop-engine/SKILL.md` points future workers to the new docs/tools.
- No global config files were changed.
- No historical `.roundtable/sessions/**` files were rewritten except a generated report created for manual inspection.

## Phase 2 Backlog After This Plan

Do not start these until Phase 1 is green:

- Task-type routing profiles: quick fix, high-risk code, research, business automation, release review.
- Real single-agent vs roundtable eval comparison.
- Public demo extraction with private memory stripped.
- Additional seats such as Aider, OpenHands, Continue, OpenClaw, or local model runners.
- Worktree-based write isolation for parallel makers.
