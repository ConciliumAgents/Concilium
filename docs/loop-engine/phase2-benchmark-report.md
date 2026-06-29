# Loop Engine Phase 2 Benchmark Report

## Status

Phase 2 benchmark harness is implemented. Full five-task live benchmark is not complete until all five task pairs are run or explicitly marked blocked.

## Current Evidence

- Dry benchmark mode produced comparable records and a summary for all five tasks.
- One controlled live task pair was run for `seat_contract_bold_verdict_doc`.
- The controlled live run used `loop-engine-mvp-v0.1-internal` as the task base commit.

## Live Pair Result

Latest controlled run:

`evals/loop-engine/phase2/runs/20260629-101627-153963`

| Task | Kimi | Roundtable | Outcome | Notes |
|---|---|---|---|---|
| seat_contract_bold_verdict_doc | PASS | ERR | kimi_better | Kimi completed in 11.83s. Roundtable verification passed but conductor returned ERR after 211.763s and changed `roundtable-memory/LESSONS.md` outside `allowed_paths`. |

## Interpretation

This first live pair is evidence that the harness can compare the two lanes and catch quality issues beyond simple command success.

It is not evidence that Kimi is generally better than the roundtable. It only shows that, on this small docs task, Kimi finished faster and stayed closer to the requested path boundary. The roundtable did make the requested documentation change, but it also produced a failing conductor verdict and wrote extra lesson content outside the task's `allowed_paths`.

## Next Runs

- `report_session_block_test`
- `eval_runner_missing_command_test`
- `dogfood_roundtable_report_note`
- `dogfood_memory_boundary_note`

## Current Decision

Continue Phase 2 data collection. Do not claim Agent-level MoA is better until all five task pairs are run or blocked with reasons.
