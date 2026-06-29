# Loop Engine Roundtable Benchmark Hardening Design

## First Principles

The benchmark should measure whether a lane completes the requested task, not whether its internal orchestration looks tidy. A lane succeeds only when all of these are true:

- The task verification commands pass.
- At least one requested target path changes.
- No file outside `allowed_paths` changes, except the lane-local `BENCHMARK-REPORT.md`.

The benchmark must not hide orchestration problems. A non-zero agent or conductor return code remains recorded as evidence, but it is not by itself a blocking quality failure when the lane produced the target diff and verification passed.

## Non-Goals

- Do not change normal roundtable archiving behavior outside benchmark lanes.
- Do not weaken `allowed_paths`.
- Do not claim roundtable is better based on dry-run behavior.
- Do not turn pre-existing matching text into a PASS when the lane made no target diff.

## Design

`benchmark-roundtable.py` will separate lane quality from lane process health.

- Add a helper that classifies changed files into allowed target changes and path violations.
- Treat missing allowed target changes as a blocking finding.
- Treat verification failure and path violations as blocking findings.
- Record non-zero lane return codes as warnings with the raw `lane_returncode`.
- Compute final status from blocking findings, not from return code alone.

Roundtable benchmark runs will set `LOOP_ARCHIVE=0` in the conductor environment. This prevents benchmark worktrees from writing `roundtable-memory/LESSONS.md` while preserving normal conductor behavior outside the benchmark runner.

## Adversarial Review Checklist

- A lane cannot pass with only `BENCHMARK-REPORT.md` changed.
- A lane cannot pass when it modifies `roundtable-memory/LESSONS.md`.
- A lane cannot pass when verification commands fail.
- A roundtable lane can pass with conductor return code `1` only if it changed an allowed target path and verification passed.
- The raw conductor return code remains visible in `records.jsonl`.

## Verification

- Add focused unit tests for target-diff classification, path violations, warning recording, and benchmark archive suppression.
- Run the existing Loop Engine unit tests, smoke tests, eval tests, and Phase 2 dry-run.
- Run one controlled live benchmark pair after the change to check that the record shape captures warnings without hiding blocking findings.
