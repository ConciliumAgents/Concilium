# Loop Engine Phase 3 Routing Timing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reliable seat-level timing evidence and document the Fast/Review/Roundtable lane routing model.

**Architecture:** Keep the conductor control flow unchanged. Add lightweight per-seat timing records to the existing session `roundtable.json`, then surface those records in the compact session report. Document product routing separately so the current Kimi baseline remains an implementation default, not a product-level rule.

**Tech Stack:** Python standard library, existing Loop Engine shell wrappers, Markdown docs, unittest.

---

### Task 1: Seat-Level Timing

**Files:**
- Modify: `skills/loop-engine/bin/conductor.py`
- Modify: `skills/loop-engine/bin/report-session.py`
- Test: `skills/loop-engine/tests/test_conductor_core.py`
- Test: `skills/loop-engine/tests/test_report_session.py`

- [x] Write a failing conductor test that runs a dry one-iteration session and asserts `roundtable.json` contains `seat_timings` entries for `claude/plan`, `kimi/exec`, and `hermes/review`.
- [x] Write a failing report test that provides `seat_timings` in `roundtable.json` and asserts the minute index includes a `Duration(s)` column.
- [x] Add a small timing helper in `conductor.py` using `time.monotonic()`, recording `iter`, `seat`, `mode`, `rc`, and `duration_seconds`.
- [x] Append timing rows after each plan, exec, and review seat call, including fallback review attempts.
- [x] Update `report-session.py` to join timing records onto minute rows by `(iter, seat, mode)` and display duration when present.
- [x] Run targeted tests, then the full loop-engine test suite.

### Task 2: Lane Routing Product Definition

**Files:**
- Create: `docs/loop-engine/phase3-lane-routing.md`

- [x] Define `Fast Lane` as default single-agent execution, with user-configurable `default_single_agent`.
- [x] Define `Review Lane` as one executor plus independent reviewer, escalating to Roundtable after repeated BLOCK or unclear requirements.
- [x] Define `Roundtable Lane` as the full planner/executor/reviewer loop for high-risk, ambiguous, cross-boundary tasks.
- [x] State setup/UI requirements: first-run setup should ask for default single agent, reviewer, and roundtable seats; current Kimi default is local evidence, not a product requirement.
- [x] Add a concise routing table and decision triggers.

### Verification

- [x] `python3 -m unittest skills.loop-engine.tests.test_conductor_core skills.loop-engine.tests.test_report_session`
- [x] `python3 -m unittest discover -s skills/loop-engine/tests`
- [x] `bash skills/loop-engine/bin/smoke-roundtable-speedup.sh`
- [x] `python3 skills/loop-engine/bin/benchmark-roundtable.py --dry-run --out /tmp/loop-phase3-routing-timing-dry`
- [x] `git diff --check`
