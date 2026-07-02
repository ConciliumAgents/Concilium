# Concilium Phase 3 Closeout

> Historical note: Phase 3 is superseded by the Phase 4 runtime/service contract. Keep this document as dated evidence, not as the current entrypoint contract.

## Conclusion

Phase 3 is complete. Concilium now has a tested local path for layered configuration, capacity status, preflight, pure lane routing, routed dry/live execution, benchmark visibility, WebUI preflight, and smoke coverage.

## What Phase 3 Added

- Layered configuration: bundled defaults, user config, project config.
- Capacity status model with redaction and blocking semantics.
- Preflight gate before agent execution.
- Pure lane router for Fast, Review, and Roundtable.
- Routed `concilium-run.py` wrapper.
- Router-aware benchmark path.
- WebUI preflight and visible capacity status.
- Phase 3 smoke matrix for representative Fast, Review, and Roundtable prompts.

## Evidence

| Check | Result | Evidence Path |
|---|---|---|
| Unit tests | PASS: `Ran 79 tests in 2.515s OK` | `python3 -m unittest discover -s skills/loop-engine/tests` |
| Roundtable smoke | PASS: `Summary: 7 passed, 0 failed` | `bash skills/loop-engine/bin/smoke-roundtable-speedup.sh` |
| Phase 3 smoke | PASS: `Concilium Phase 3 smoke passed` | `bash skills/loop-engine/bin/smoke-concilium-phase3.sh` |
| Dry benchmark | PASS: 5 tasks, Kimi/Review/Roundtable all `PASS`; router remains opt-in and default column is `-` | `/tmp/concilium-phase3-final-dry/summary.md` |
| Whitespace check | PASS: no output | `git diff --check` |

## Acceptance Criteria

- `concilium_config.py` loads bundled defaults, user config, and project config with project overrides taking priority.
- `capacity_status.py` emits redacted machine-readable status records and blocks only explicit unavailable or hard-exhausted required seats.
- `lane_router.py` routes representative tasks into Fast, Review, or Roundtable from signals and config.
- `concilium-run.py --dry-run --print-route` shows route, preflight, capacity, and signals without starting agents.
- `concilium-run.py --live` has wrappers for Fast, Review, and Roundtable execution.
- WebUI exposes token-protected `/api/preflight` and shows route plus capacity before starting a run.
- Dry benchmark still compares baseline Kimi, Review Lane, and Roundtable by default; router lane is opt-in with `--include-router`.
- No Phase 3 task writes global Claude, Codex, Kimi, Hermes, or CodexBar config.

## Assumptions

- Capacity probes are best-effort unless a provider exposes a fresh, explicit quota source.
- Unknown capacity warns but does not block.
- Hard-exhausted or unavailable required seats block before execution.
- CodexBar is a reference for signal shape and source failure modes, not a required Concilium dependency.

## Risks

- Some providers may not expose reliable local quota information.
- WebUI status can become stale after the configured status age.
- Provider APIs and CLI outputs can change without notice.
- WebUI preflight currently previews Concilium routing, while `/api/run` still starts the existing roundtable execution path.

## Next Decision Trigger

Phase 4 should start only after a user can run `concilium-run.py --dry-run --print-route` and see the same route/preflight decision in WebUI.
