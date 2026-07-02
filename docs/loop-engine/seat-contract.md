# Loop Engine Seat Contract

This document defines the minimum contract for native-shell seats called by `skills/loop-engine/bin/conductor.py`.

Current seat mode support:

- `claude`: `plan`, `exec`, `review`
- `kimi`: `plan`, `exec`, `review`
- `hermes`: `exec`, `review`
- `codex`: `review` in conductor-managed runs

`plan` mode applies only to plan-capable commander seats. The conductor can technically be invoked with any agent as `--commander`, but a commander without `plan` support will fail and may trigger fallback behavior.

`seat-codex.sh` has a direct `exec` branch for manual use, but `conductor.py` excludes `codex` from the executor pool because it is slow and currently connection-unstable in this environment.

## Shared Context

Each seat receives a prompt containing `loop_seat_preamble`, which points it at the session blackboard:

- `.roundtable/sessions/<session>/KB/project.md`
- `.roundtable/sessions/<session>/KB/task.md`
- `.roundtable/sessions/<session>/KB/state.md`
- `.roundtable/sessions/<session>/KB/roster.md`
- `.roundtable/sessions/<session>/KB/imported-memory.md`
- `.roundtable/sessions/<session>/KB/diff.patch`
- `.roundtable/sessions/<session>/KB/test-results.txt`

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
## Lessons
### General
- None.
### <project>
- None.
```

Rules:

- If there is no lesson, write `- None.`.
- If work is incomplete, state that directly in the minute output and `KB/state.md`.
- Exit code `0` means the seat process completed. It does not mean the task is correct; review decides that.

## Mode: review

Purpose: independently check the work.

Allowed side effects: none.

Required verdict line:

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

## Timeout Budget

Timeout is a task budget, not a model capability score.

The default hard timeout is `LOOP_SEAT_TIMEOUT`. More specific overrides take precedence:

- `LOOP_SEAT_TIMEOUT_<SEAT>_<MODE>`
- `LOOP_SEAT_TIMEOUT_<SEAT>`
- `LOOP_SEAT_TIMEOUT`

For example, `LOOP_SEAT_TIMEOUT_CLAUDE_REVIEW=600` gives Claude review seats a longer window without marking Claude as degraded. Concilium defaults keep ordinary seats on the base timeout and give Claude/Codex `plan` and `review` seats a longer budget because they are slow but valuable for deep planning, review, and synthesis. Capacity and availability are judged by quota/auth/preflight status, not by latency alone.

## Exit Code Mapping

- `0`: process succeeded; for `claude`, `kimi`, and `hermes` review this maps to PASS only when `loop_verdict_exit` finds PASS.
- `2`: review found a blocking issue.
- `1`: seat process or parsing error.
- `124`: conductor timeout killed the process group.

Codex review uses `loop_codex_verdict`: an explicit `VERDICT` line wins, then `[P0]` or `[P1]` findings map to BLOCK, and otherwise Codex review maps to PASS.

## Privacy Boundary

Seat outputs may be archived into `roundtable-memory/`. Do not write API keys, tokens, private customer data, payment data, or unsupported-region workarounds into minutes or lessons.
