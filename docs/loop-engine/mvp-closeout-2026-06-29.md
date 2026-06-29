# Loop Engine MVP Closeout - 2026-06-29

## Conclusion

Loop Engine Phase 1 is closed as an internal MVP candidate.

This means the current system is good enough for private dogfood use and controlled iteration inside this repo. It does not mean the project is ready for public release or external users.

## Scope Closed

Phase 1 turned Loop Engine from a personal working prototype into a reproducible Agent-level MoA prototype with:

- repo-visible Agent MoA positioning;
- a human-readable seat contract;
- offline validation for seat outputs;
- fixed dry-mode eval tasks;
- a compact session report generator;
- smoke tests for speedup, lesson archival, memory import, and verdict parsing;
- read-only dogfood review by live Kimi and Hermes seats.

## Evidence

The closeout state is based on `main` at commit `da2faf7` plus this closeout note.

Latest verification commands:

```bash
python3 -m unittest discover -s skills/loop-engine/tests
bash skills/loop-engine/bin/smoke-roundtable-speedup.sh
python3 skills/loop-engine/bin/eval-roundtable.py --timeout 180
python3 skills/loop-engine/bin/eval-roundtable.py --timeout 180 --include-optional
```

Latest observed result:

- 19 unit tests passed.
- Speedup smoke passed 7/7 checks.
- Default eval passed 3/3 tasks.
- Optional eval passed 4/4 tasks, including `memory_smoke`.
- Live Kimi review returned `VERDICT: PASS`.
- Live Hermes review returned `VERDICT: PASS` after the parser was tightened to accept a single Markdown-bold verdict line.

## Product Boundary

This MVP proves the internal control plane:

- seats can share a blackboard;
- outputs can be checked against a contract;
- dry evals can run without live model calls;
- session output can be summarized for human review;
- memory import does not require legacy Claude-only sources in isolated worktrees.

This MVP does not prove public-product readiness.

Public-facing work still needs:

- single-agent baseline comparisons;
- repeated live roundtable runs across varied tasks;
- clearer demo/private-memory separation;
- publishing and install guidance;
- failure-mode documentation for unavailable CLIs, network errors, and provider drift.

## Known Limitations

- The eval suite is small and mostly contract-oriented.
- Live dogfood has positive evidence but not statistical evidence.
- `memory_smoke` still temporarily mutates repo-local `roundtable-memory/` during its destructive checks and relies on backup/restore.
- Seat behavior depends on local CLI availability and provider state.
- Historical `.roundtable/` sessions remain private local artifacts and are not part of a clean public demo bundle.

## Next Phase Trigger

Start Phase 2 only after preserving this closeout point with a tag.

Recommended Phase 2 goal:

> Prove whether the roundtable produces better operational outcomes than a single strong agent on the same task set.

Phase 2 should focus on:

- live roundtable benchmark tasks;
- single-agent baseline tasks;
- run reports with comparable outcome, time, retries, and blocked-reason fields;
- a small decision memo on whether Agent-level MoA is measurably useful for this workflow.

## Cleanup Policy

Safe cleanup after closeout:

- remove Superpowers-created worktrees that have already been merged;
- delete merged `codex/` feature branches;
- keep historical `loop-engine/` branches unless explicitly reviewed;
- do not delete `.roundtable/`, `roundtable-memory/`, or local private memory artifacts;
- do not touch unrelated `.DS_Store` files.
