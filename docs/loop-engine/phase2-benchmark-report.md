# Loop Engine Phase 2 Benchmark Report

## Status

Phase 2 benchmark harness is implemented, and the first five-task live benchmark set is complete.

## Current Evidence

- Dry benchmark mode produced comparable records and a summary for all five tasks.
- Five controlled live task pairs were run against `loop-engine-mvp-v0.1-internal` as the task base commit.
- Earlier live runs `20260629-100120-151785` and `20260629-100911-561616` were used to debug evidence capture and are not part of the comparison set below.

## Live Pair Results

Controlled run set:

- `evals/loop-engine/phase2/runs/20260629-101627-153963`
- `evals/loop-engine/phase2/runs/20260629-103323-059207`
- `evals/loop-engine/phase2/runs/20260629-103759-810520`
- `evals/loop-engine/phase2/runs/20260629-104201-720231`
- `evals/loop-engine/phase2/runs/20260629-104556-954014`

| Task | Kimi | Roundtable | Outcome | Notes |
|---|---|---|---|---|
| seat_contract_bold_verdict_doc | PASS | ERR | kimi_better | Kimi completed in 11.83s. Roundtable verification passed but conductor returned ERR after 211.763s and changed `roundtable-memory/LESSONS.md` outside `allowed_paths`. |
| report_session_block_test | PASS | ERR | kimi_better | Kimi completed in 30.312s and added the focused test. Roundtable verification passed but conductor returned ERR after 226.686s and changed `roundtable-memory/LESSONS.md` outside `allowed_paths`. |
| eval_runner_missing_command_test | PASS | ERR | kimi_better | Kimi completed in 17.288s. Roundtable made the target test change and verification passed, but conductor returned ERR after 198.088s. |
| dogfood_roundtable_report_note | PASS | ERR | kimi_better | Kimi completed in 13.187s and changed the positioning doc. Roundtable verification passed but conductor returned ERR after 196.393s with no target diff. |
| dogfood_memory_boundary_note | PASS | ERR | kimi_better | Kimi completed in 12.734s and changed the positioning doc. Roundtable verification passed but conductor returned ERR after 231.35s with no target diff. |

## Counts

- roundtable_better: 0
- kimi_better: 5
- tie: 0
- inconclusive: 0

## Interpretation

This first complete live set is evidence that the harness can compare the two lanes and catch quality issues beyond simple command success.

It is evidence that the current roundtable lane is not yet competitive for these small, tightly scoped benchmark tasks. Kimi passed all five tasks, stayed within the target task changes apart from its lane-local `BENCHMARK-REPORT.md`, and completed each task in 11.83s to 30.312s.

The roundtable lane had a consistent failure pattern: task verification often passed, but the conductor still returned ERR. Two tasks also wrote `roundtable-memory/LESSONS.md` outside `allowed_paths`, and two dogfood tasks produced no target diff. That means the immediate bottleneck is not raw ability to make a change; it is roundtable completion discipline, artifact boundaries, and conductor verdict handling.

This benchmark should still not be treated as a broad claim that single-agent Kimi is always better than Agent-level MoA. It shows that, for the current Phase 2 task shape, the roundtable workflow adds latency and failure modes that are not yet offset by better results.

## Decision

Do not promote Agent-level MoA as measurably better yet. The next engineering target should be reducing roundtable false ERR outcomes and preventing out-of-scope memory writes during benchmark lanes before running a second benchmark set.

## Hardening Follow-Up

After the first five-task set, the benchmark harness was tightened so lane quality is judged by task verification, allowed target diffs, and path-boundary compliance. Raw process health is still recorded through `lane_returncode` and `warnings`.

Validation runs:

- `evals/loop-engine/phase2/runs/20260629-110226-791450`: `eval_runner_missing_command_test` stayed `kimi_better`. Roundtable verification passed, but it produced no allowed target diff, so the lane remained ERR. The conductor return code was preserved as `warnings: ["lane returncode 1"]`.
- `evals/loop-engine/phase2/runs/20260629-110711-282495`: `seat_contract_bold_verdict_doc` became a tie. Roundtable verification passed, changed only `docs/loop-engine/seat-contract.md`, and no longer wrote `roundtable-memory/LESSONS.md`; the conductor return code `1` remained visible as a warning.

Current interpretation: the original five-task result remains valid as a pre-hardening baseline, but a second full five-task benchmark set should be run before updating the overall Phase 2 decision.
