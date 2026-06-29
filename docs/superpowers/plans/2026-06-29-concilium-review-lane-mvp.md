# Concilium Review Lane MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a measurable Review Lane so Phase 3 can compare Fast, Review, and Roundtable outcomes before building capacity detection or router automation.

**Architecture:** Create a small reusable `review-lane.py` runner that uses the existing `.roundtable` blackboard and native seat scripts. Extend the existing benchmark harness to add a `review` lane, and update the benchmark summary so Review Lane can be evaluated next to Kimi and Roundtable. Do not rename product surfaces or add capacity detection in this slice.

**Tech Stack:** Python standard library, existing shell seat scripts, existing unittest suite, git worktrees for live benchmark isolation.

---

### Task 1: Review Lane Runner

**Files:**
- Create: `skills/loop-engine/bin/review-lane.py`
- Create: `skills/loop-engine/tests/test_review_lane.py`

- [x] Write failing tests for `run_review_lane()`:
  - executor and reviewer must be different;
  - PASS after one exec/review requires no repair;
  - BLOCK triggers exactly one repair pass when `repair_limit=1`;
  - final BLOCK leaves `review_verdict="BLOCK"`.
- [x] Run `python3 -m unittest skills.loop-engine.tests.test_review_lane`; expected failure: `review-lane.py` does not exist.
- [x] Implement `review-lane.py` with `run_review_lane(repo, task, test_cmd="", executor="kimi", reviewer="hermes", repair_limit=1, timeout=300, session="")`.
- [x] The runner must:
  - initialize a roundtable session;
  - write the roster for executor/reviewer;
  - refresh KB before and after executor calls;
  - call `seat-<executor>.sh exec`;
  - call `seat-<reviewer>.sh review`;
  - bump the session iteration before a repair pass;
  - return `review_verdict`, `returncode`, `retries`, `agent_calls`, and `session_path`.
- [x] Run `python3 -m unittest skills.loop-engine.tests.test_review_lane`; expected pass.

### Task 2: Benchmark Integration

**Files:**
- Modify: `skills/loop-engine/bin/benchmark-roundtable.py`
- Modify: `skills/loop-engine/tests/test_benchmark_roundtable.py`

- [x] Write failing tests showing dry-run batches include `baseline-kimi`, `review`, and `roundtable`.
- [x] Write a failing test showing `lane_record(..., review_verdict="BLOCK")` fails quality even when verify commands pass and target files changed.
- [x] Write a failing test showing benchmark `run_review_lane()` delegates to the reusable Review Lane runner and records `review_verdict`, `retries`, and `agent_calls`.
- [x] Run `python3 -m unittest skills.loop-engine.tests.test_benchmark_roundtable`; expected failures around missing `review` lane behavior.
- [x] Update `LANES` to include `review`.
- [x] Add a benchmark wrapper that calls `review-lane.py` and writes `report.md`, `diff.patch`, `test-results.txt`, and `result.json`.
- [x] Extend `lane_record()` with optional `review_verdict`, `retries`, and `agent_calls`.
- [x] Run `python3 -m unittest skills.loop-engine.tests.test_benchmark_roundtable`; expected pass.

### Task 3: Summary Integration

**Files:**
- Modify: `skills/loop-engine/bin/summarize-benchmark.py`
- Modify: `skills/loop-engine/tests/test_summarize_benchmark.py`

- [x] Write failing tests showing benchmark summaries include Review Lane status and a `review_better` count when only Review Lane passes.
- [x] Run `python3 -m unittest skills.loop-engine.tests.test_summarize_benchmark`; expected failures around missing Review column/count.
- [x] Update summary table to show `Kimi`, `Review`, and `Roundtable`.
- [x] Keep `classify_pair()` for compatibility, but add `classify_task()` for three-lane outcomes.
- [x] Run `python3 -m unittest skills.loop-engine.tests.test_summarize_benchmark`; expected pass.

### Task 4: Documentation and Verification

**Files:**
- Modify: `docs/loop-engine/phase3-lane-routing.md`
- Modify: `docs/superpowers/plans/2026-06-29-concilium-review-lane-mvp.md`

- [x] Add a short Phase 3 execution-order note saying Review Lane MVP and benchmark evidence come before capacity detection/router/UI work.
- [x] Mark completed plan checklist items.
- [x] Run `python3 -m unittest discover -s skills/loop-engine/tests`; expected pass.
- [x] Run `bash skills/loop-engine/bin/smoke-roundtable-speedup.sh`; expected pass.
- [x] Run `python3 skills/loop-engine/bin/benchmark-roundtable.py --dry-run --out /tmp/concilium-review-lane-dry`; expected pass and records for three lanes per task.
- [x] Run one live Review Lane task with `kimi` executor and `hermes` reviewer in a temp worktree; expected `review_verdict="PASS"` and only target-file changes.
- [x] Run `git diff --check`; expected no output.
