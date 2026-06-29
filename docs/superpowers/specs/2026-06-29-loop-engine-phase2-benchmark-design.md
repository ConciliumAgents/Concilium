# Loop Engine Phase 2 Benchmark Design

> 状态：草案 v1（Phase 2 启动设计）
> 日期：2026-06-29
> 前置状态：`loop-engine-mvp-v0.1-internal` 已标记内部 MVP 收官点。

---

## 1. Conclusion

Phase 2 should test whether Loop Engine's Agent-level MoA produces better operational outcomes than a single Kimi agent on the same tasks.

This is an evidence phase, not a feature-expansion phase. The output should be a small benchmark harness, comparable run records, and a decision memo. It should not add new seats, publish the project, or optimize the UI.

---

## 2. Decisions Already Made

- Direction: Roundtable vs single-agent benchmark.
- Task mix: 3 reproducible repo-local tasks and 2 real dogfood tasks.
- Baseline: Kimi single-agent.
- Scoring priority: quality first, speed second.
- Execution boundary: live agents are allowed, but only inside isolated worktrees.
- Merge boundary: benchmark task worktrees produce reports, diffs, and metrics; they do not merge task outputs back to `main` by default.
- Question policy: technical details can be decided by the implementing agent; ask the user only for changes that affect real business/runtime behavior, irreversible actions, publishing, deletion, spending, or external side effects.

---

## 3. Goals

Phase 2 should answer one question:

> For this workflow, does a Loop Engine roundtable run produce measurably better outcomes than a single Kimi run?

Success means:

- every benchmark task can be run in a baseline lane and a roundtable lane from the same starting commit;
- both lanes produce comparable structured records;
- quality is judged from tests, diffs, contract checks, and review verdicts;
- time, retries, and failure reasons are captured as secondary metrics;
- the final memo says whether Agent-level MoA is useful enough to continue investing in.

---

## 4. Non-Goals

Phase 2 does not:

- publish Loop Engine;
- add OpenClaw, Aider, Continue, local model seats, or other providers;
- change global Claude, Kimi, Codex, Hermes, or Codex config;
- delete historical `.roundtable/` sessions;
- auto-merge benchmark task outputs into `main`;
- build a statistical research benchmark;
- optimize the WebUI.

---

## 5. Benchmark Shape

### 5.1 Task Set

Create a fixed task file for Phase 2 with five tasks:

- 3 repo-local reproducible tasks;
- 2 real dogfood tasks.

Each task should have:

- `id`: stable slug;
- `category`: `repo-local` or `dogfood`;
- `prompt`: the exact task text given to each lane;
- `allowed_paths`: paths the agents may modify;
- `verify_cmds`: commands used after the lane finishes;
- `quality_checks`: plain-language criteria for human review;
- `expected_artifacts`: report, diff, test output, and timing record.

The task prompt must be identical for Kimi baseline and roundtable unless the lane wrapper needs mechanical context such as "you are the baseline lane" or "you are the roundtable lane". That lane context must not change the task requirements.

### 5.2 Candidate Task Types

The implementation plan should choose concrete tasks from these categories:

- repo-local docs consistency task;
- repo-local test/harness improvement task;
- repo-local small bugfix or parser robustness task;
- real dogfood task that exercises a live roundtable without touching external services;
- real dogfood task that exercises report/memory handoff behavior.

Tasks must be small enough that a failed run can be inspected in minutes. Avoid tasks that require credentials, browser login, publishing, spending, or private external data.

---

## 6. Execution Lanes

### 6.1 Baseline Lane: Kimi

For each task, create an isolated worktree from the same base commit:

```text
baseline-kimi/<task-id>
```

The baseline lane invokes Kimi directly with:

- the task prompt;
- the allowed path boundary;
- the verify commands;
- an instruction to produce a short completion report.

The baseline lane may modify files only inside its worktree. It should not write global config, publish, or delete repo memory outside its own worktree.

### 6.2 Roundtable Lane: Loop Engine

For the same task, create another isolated worktree from the same base commit:

```text
roundtable/<task-id>
```

The roundtable lane runs Loop Engine with the same task prompt. It should use the current Phase 1 control plane:

- `.roundtable/` blackboard;
- seat contract;
- `kb-refresh.sh`;
- `report-session.py`;
- existing live seats only.

The roundtable lane may modify files only inside its worktree. It should not merge into `main`.

### 6.3 Base Commit

All lanes in one benchmark batch must start from the same commit:

```text
loop-engine-mvp-v0.1-internal
```

If the benchmark harness itself is being developed on a later commit, benchmark task worktrees should still record both:

- `harness_commit`: the commit that contains the benchmark scripts;
- `task_base_commit`: the commit from which the lane worktree started.

---

## 7. Metrics

### 7.1 Quality Metrics

Quality is primary. Each lane record should include:

- `status`: `PASS`, `BLOCK`, or `ERR`;
- `verify_passed`: boolean;
- `review_verdict`: `PASS`, `BLOCK`, `ERR`, or empty if no review ran;
- `blocking_findings`: list of high-level reasons;
- `changed_files`: list of changed tracked files;
- `diff_summary`: compact diff stat;
- `contract_valid`: boolean where applicable;
- `human_quality_score`: optional 1-5 value set after inspection.

Quality judgment order:

1. verify commands;
2. seat contract or report checks;
3. review verdicts;
4. human inspection of diffs and artifacts.

### 7.2 Efficiency Metrics

Efficiency is secondary. Each lane record should include:

- wall-clock seconds;
- number of retries;
- number of agent calls;
- timeout count;
- manual intervention count;
- final report length or artifact count.

### 7.3 Outcome Classification

Each task pair should be classified as:

- `roundtable_better`;
- `kimi_better`;
- `tie`;
- `inconclusive`.

Classification must include a short reason. A faster result is not better if it fails quality checks.

---

## 8. Artifacts

Phase 2 should write durable, repo-visible benchmark artifacts under:

```text
evals/loop-engine/phase2/
```

Recommended structure:

```text
evals/loop-engine/phase2/
  tasks.json
  runs/
    <timestamp>/
      batch.json
      records.jsonl
      summary.md
      task-<id>/
        baseline-kimi/
          result.json
          report.md
          diff.patch
          test-results.txt
        roundtable/
          result.json
          report.md
          diff.patch
          test-results.txt
```

Generated run directories may be ignored if they are noisy. The task definition, runner, summarizer, and one small sample fixture should be committed.

---

## 9. Implementation Components

### 9.1 Task Definition

Create a Phase 2 task file:

```text
evals/loop-engine/phase2/tasks.json
```

This should not replace the Phase 1 `evals/loop-engine/tasks.json` file. Phase 1 evals remain the contract smoke suite.

### 9.2 Runner

Create a runner script:

```text
skills/loop-engine/bin/benchmark-roundtable.py
```

Responsibilities:

- load Phase 2 tasks;
- create per-lane worktrees;
- run Kimi baseline lane;
- run roundtable lane;
- run verification commands;
- capture timing, exit code, diff, status, and reports;
- write one JSON record per lane;
- avoid merging or pushing.

The runner should support a dry mode that creates records without calling live agents. Dry mode is required for tests.

### 9.3 Summary Tool

Create a summary script:

```text
skills/loop-engine/bin/summarize-benchmark.py
```

Responsibilities:

- read `records.jsonl`;
- group records by task;
- compare baseline vs roundtable;
- write `summary.md`;
- count PASS/BLOCK/ERR and outcome classifications.

### 9.4 Tests

Add standard-library tests for:

- task loading and validation;
- lane record schema;
- outcome classification;
- dry-run benchmark generation;
- summary generation.

Tests must not call live Kimi, Hermes, Claude, Codex, or external network services.

---

## 10. Safety

The runner must:

- refuse to run live lanes from a dirty task base worktree unless explicitly forced;
- create lanes under an ignored worktree root;
- record the exact base commit;
- avoid deleting worktrees unless it created them;
- never run destructive cleanup outside its own benchmark worktree paths;
- never write to `~/.claude`, `~/.codex`, `~/.kimi-code`, or Hermes config paths;
- preserve generated artifacts for inspection unless the user explicitly asks to clean them.

For real dogfood tasks, ask before any action that would affect external systems, publish, delete, spend money, or change non-repo business state.

---

## 11. Reporting

The final Phase 2 memo should live at:

```text
docs/loop-engine/phase2-benchmark-report.md
```

It should include:

- task list;
- baseline vs roundtable table;
- quality outcomes;
- efficiency outcomes;
- examples of where roundtable helped;
- examples of where Kimi alone was enough or better;
- risks and confidence level;
- recommendation: continue, pivot, or stop Agent-level MoA investment.

---

## 12. Acceptance Criteria

Phase 2 design is implemented when:

- `evals/loop-engine/phase2/tasks.json` exists and defines five tasks;
- dry-run benchmark mode can produce a full run directory and summary;
- summary tool compares Kimi vs roundtable records;
- tests cover task loading, dry run, and summary classification;
- at least one controlled live task pair has been run and reported;
- the Phase 2 memo states whether the roundtable is better, worse, tied, or inconclusive against Kimi baseline.

Full Phase 2 is complete only after all five task pairs are run or explicitly marked blocked with reasons.

---

## 13. Risks

- Live agent provider drift can make runs incomparable. Mitigation: record CLI versions, timestamps, model/provider hints, and exit codes.
- Kimi may outperform the roundtable on simple tasks. This is a valid outcome, not a failure.
- Roundtable may produce better review coverage but slower completion. The scoring should treat quality as primary and speed as secondary.
- Worktree artifacts can become clutter. Mitigation: generated runs live under a known directory and are summarized.
- Dogfood tasks may introduce subjective judgment. Mitigation: keep two dogfood tasks only and require explicit human quality notes.

---

## 14. Next Step

After this design is accepted, write an implementation plan with small TDD tasks:

1. schema and dry-run tests;
2. benchmark runner dry mode;
3. summary classifier;
4. worktree lane orchestration;
5. live Kimi lane;
6. live roundtable lane;
7. first controlled live benchmark run;
8. final Phase 2 memo.
