---
name: loop-engine
description: "Run an Addy-Osmani-style Loop Engineering roundtable from Claude Code: Claude chairs a plan -> act -> verify -> iterate loop on a shared blackboard (.roundtable/), while heterogeneous fast seats such as Hermes and Kimi execute in their own native CLIs; maker != checker, verified by an independent seat. Also runnable through the Concilium runtime via roundtable or concilium-run.py."
---

# Loop Engine Roundtable Protocol

Claude is the chair for this roundtable: it plans, coordinates, and verifies work while sharing context through `.roundtable/`. Execution seats such as Hermes, Kimi, and reachable Codex instances run in their own native shells. The governing rule is maker != checker: the seat that changes files should not be the only seat that verifies the result.

Related public docs:

- Agent-level MoA positioning: `docs/loop-engine/agent-moa-positioning.md`
- Seat input/output contract: `docs/loop-engine/seat-contract.md`
- Offline validators and reports: `bin/seat-contract-validate.py`, `bin/eval-roundtable.py`, `bin/report-session.py`

## Two Modes

- Chair mode: drive plan -> act -> verify in the conversation, using `bin/seat-*.sh` to call seats. Large core edits that require full context should be made by the chair in the main conversation, then independently reviewed.
- Automatic mode: use `roundtable --task "<task and acceptance criteria>"` or `bin/concilium-run.py --repo <repo> --task "<task and acceptance criteria>" --live`. This path enters the Concilium runtime first: lane routing, Budget Guard, seat provenance, artifact gates, and runtime events are handled there. `bin/conductor.py` remains a legacy/debug entrypoint.

## Rules

1. **Maker != checker.** A seat that writes code must be verified by an independent seat. Prefer heterogeneous review through Hermes or Kimi; use Codex as an extra verifier when reachable.
2. **Do not hoard context.** Task goals, decisions, architecture notes, and verification facts belong in `.roundtable/KB/` so every seat reads the same blackboard.
3. **Use seats for the right work.** Send bounded execution tasks to fast seats. Keep large core edits with the chair when timeout or context loss would make headless execution unreliable.
4. **Autonomy has limits.** Deletion, overwrites, spending, external publishing, permission changes, or global configuration changes require explicit human approval.
5. **Stay inside the project.** Do not modify global Claude/Codex/Kimi/Hermes configuration as part of a roundtable run.

## Preparation

Confirm available seats before starting:

```bash
hermes --version
kimi --version
codex --version
```

Useful environment variables:

- `LOOP_MAX_ITERS`: maximum loop iterations.
- `LOOP_SEAT_TIMEOUT`: default hard timeout for headless seats.
- `LOOP_SEAT_TIMEOUT_<SEAT>` and `LOOP_SEAT_TIMEOUT_<SEAT>_<MODE>`: per-seat or per-mode overrides.
- `LOOP_TEST_CMD`: command written into the blackboard and run by `kb-refresh.sh`.
- `LOOP_REVIEW_PROVIDER` / `LOOP_REVIEW_MODEL`: optional Hermes review backend override.
- `LOOP_USE_ROUNDTABLE_MEMORY`: enables git-versioned roundtable memory import when set.

## Flow

### 0. Open The Table

- Confirm the target repository, task, verification command, and risk level.
- Run `bin/roundtable-init.sh <repo> "<task>"`.
- Fill `.roundtable/KB/project.md` and `.roundtable/KB/task.md` before delegating work.

### 1. Plan

- Read the repository and KB files.
- Break the task into bounded subtasks.
- Write the current plan and acceptance criteria into `KB/task.md` and `KB/state.md`.
- For high-risk or ambiguous work, ask another seat for a read-only plan review before execution.

### 2. Act

- Keep large, context-heavy edits in the chair conversation when needed.
- Send bounded execution subtasks to `bin/seat-hermes.sh <repo> exec "<task>"` or `bin/seat-kimi.sh <repo> exec "<task>"`.
- Do not rely on the executor's final message as proof of correctness.

### 3. Refresh The Blackboard

Run:

```bash
bin/kb-refresh.sh <repo> "<test command>"
```

This regenerates `KB/diff.patch`, runs the test command, and writes `KB/test-results.txt` so review seats can verify against current facts.

### 4. Verify

- Call an independent review seat with `bin/seat-hermes.sh <repo> review` or `bin/seat-kimi.sh <repo> review`.
- For high-risk work, run a second heterogeneous review.
- Read the full minutes, not only the `VERDICT` line.
- Treat `PASS` as valid only when the required tests and review gates actually support it.

### 5. Decide And Iterate

- `PASS`: no critical/high blockers and verification evidence is present.
- `BLOCK`: return to plan/act with the blocker and fix path written into `KB/state.md`.
- At the end of each loop, run `bin/checkpoint.sh <repo> "<iteration summary>"`.

### 6. Stop Conditions

Stop and return to the user when:

- verification passes;
- `LOOP_MAX_ITERS` is reached;
- the same blocker repeats across iterations;
- no usable executor or reviewer remains;
- agreed time, token, or cost budget is exceeded;
- a requested action needs explicit human approval.

### 7. Final Report

Report:

- what changed;
- which seats reviewed it and what they concluded;
- which tests or checks ran;
- remaining risks;
- the next decision trigger.

## Degradation And Safety

- If no independent reviewer is available, say so and do not pretend the work had independent verification.
- If a seat is unreachable, remove it from the current roster and continue only when the remaining seats can satisfy the task.
- If Hermes model selection fails, inspect the configured provider/model and update `LOOP_REVIEW_PROVIDER` or `LOOP_REVIEW_MODEL`.
- Any deletion, overwrite, external publishing, permission change, or spending must stop for human approval.
