# Concilium Phase 4 Closeout

## Conclusion

Phase 4 is complete. Concilium now has a routed live control plane: CLI, WebUI Debug Console, and the future menu bar client contract share the same runtime adapter, request fingerprint, Budget Guard, and event model.

The tiny live Fast smoke was intentionally guard-skipped, not force-confirmed: the selected Fast Lane seat was `kimi`, but its capacity source was `not_checked`, so the server-side guard returned `confirmation_required` before any live model call.

## What Phase 4 Added

- Runtime request contract for normalized requests, request overlays, and stable fingerprints.
- Server-side Budget Guard for allowed, blocked, and confirmation-required live runs.
- Shared event sinks with redaction and guaranteed terminal `done` events.
- Process-group cleanup helper for timeout-bounded lane subprocesses.
- Runtime adapter used by CLI and localhost service execution paths.
- WebUI relabeled as Concilium Debug Console with runtime adapter fields.
- Local service endpoints for status, preflight, run, events, effective config, and token-file handoff.
- Framework-neutral `ConciliumClient` and menu bar view-model fixtures.
- Phase 4 smoke script for repeatable preview, stub-run, unit, and diff checks.

## Evidence

| Check | Result | Evidence |
|---|---|---|
| Unit suite | PASS: `Ran 145 tests OK` | `python3 -m unittest discover -s skills/loop-engine/tests` |
| Phase 4 smoke script | PASS: unit suite, CLI preview, CLI stub run, and diff check completed | `skills/loop-engine/bin/smoke-concilium-phase4.sh /Users/melee/Documents/agents` |
| CLI preview | PASS: `status=preview`, `lane=fast`, `guard=allowed`, request fingerprint present | `/tmp/concilium-phase4-preview.json` |
| CLI stub run | PASS: `status=stubbed`, `returncode=0`, `lane=fast`, last event `done` | `/tmp/concilium-phase4-stub.json` |
| Tiny live Fast smoke gate | GUARD-SKIPPED: `status=confirmation_required`, `returncode=3`, `lane=fast`, guard reason `live run requires confirmation for limited capacity`, last event `done` | Command and redacted summary below; transient full output at `/tmp/concilium-phase4-live-gate.json` |

## Acceptance Matrix

| Criterion | Status | Evidence |
|---|---|---|
| `/api/run` executes through the runtime adapter | PASS | `skills/loop-engine/web/server.py` uses `run_concilium_adapter`; no direct `conductor.run(` call remains in the run path. |
| Preflight and run share normalized decision inputs | PASS | Runtime request fingerprint is present in preview, stub, live-gate, service, and menu bar view-model tests. |
| `preview`, `stub_run`, and `live_run` are distinct modes | PASS | Unit suite plus Phase 4 smoke script cover all three modes. |
| Budget Guard blocks unavailable, hard-exhausted, and unresolved required seats | PASS | `skills/loop-engine/tests/test_budget_guard.py` and adapter tests. |
| Budget Guard requires confirmation for unknown or soft-limited live seats | PASS | Tiny live Fast smoke returned `confirmation_required` for unknown Kimi capacity before a seat call. |
| Fast, Review, and Roundtable emit stable terminal events | PASS | Event and adapter tests verify terminal `done`; stub smoke last event was `done`. |
| WebUI is Debug Console, not final product UI | PASS | `skills/loop-engine/web/index.html` is labeled Concilium Debug Console. |
| Menu bar client and view-model contract exist without native framework selection | PASS | `skills/loop-engine/client/concilium_client.py`, `skills/loop-engine/client/menu_bar_view_model.py`, fixtures, and `docs/loop-engine/concilium-menu-bar-contract.md`. |
| Effective config can be previewed for a repo | PASS | `/api/config/effective` service tests and `ConciliumClient.effective_config`. |
| No global provider config is written without explicit user command | PASS | Config write endpoints are deferred; request overlays are per-run only. |
| Tiny live Fast smoke completed or was guard-skipped | PASS | Guard-skipped with explicit `confirmation_required` result because capacity was unknown. |

## Assumptions

- Unknown provider quota is not treated as green for live execution.
- Guard-skipped live smoke is acceptable when the guard produces a machine-readable block or confirmation-required result before seat execution.
- The browser WebUI remains a debug console while Phase 5 decides the native menu bar shell.

## Tiny Live Gate Evidence

Command:

```bash
python3 skills/loop-engine/bin/concilium-run.py \
  --repo /Users/melee/Documents/agents \
  --task "Append no files; respond with a one-line dry confirmation for Concilium Phase 4 smoke." \
  --test-cmd "true" \
  --mode live_run \
  --signals-json '{"risk":"low","file_count":0,"security_sensitive":false,"ambiguous":false}' \
  > /tmp/concilium-phase4-live-gate.json
```

Redacted observed result on 2026-06-30:

- `status`: `confirmation_required`
- `returncode`: `3`
- `route.lane`: `fast`
- `route.required_seats`: `["kimi"]`
- `guard.status`: `confirmation_required`
- `guard.reason`: `live run requires confirmation for limited capacity`
- `capacity_source`: `not_checked`
- `expected_max_agent_calls`: `1`
- event sequence: `start`, `preflight`, `guard`, `finish`, `done`

## Risks And Unknowns

- Provider quota probes can remain unavailable or stale unless a provider exposes a reliable local status source.
- The first real confirmed live Fast Lane run still needs a capacity-confirmed seat or explicit user confirmation.
- Native menu bar lifecycle, launch, signing, and packaging are intentionally outside Phase 4.
- Config save/setup UX is deferred, so project and user config writes remain manual or future Phase 5 work.

## Next Decision Trigger

Start Phase 5 when the user wants the native menu bar shell and setup/config write UX. The Phase 5 entry gate should reuse this Phase 4 adapter and guard instead of moving routing or capacity policy into UI code.

## Post-Closeout Native Roundtable Guard

After the first dogfood audits, Concilium gained an additional guard against accidentally degrading a roundtable into same-source Codex review:

Post-closeout entrypoint hardening: the `roundtable` launcher no longer bypasses Concilium runtime for normal `--task` calls. Use `roundtable legacy ...` only when intentionally testing the old conductor loop.

- Audit Lane default seats are `claude`, `hermes`, and `kimi`; `codex` is explicit opt-in.
- Plan Review Lane default seats are `claude`, `hermes`, and `kimi`; `codex` is explicit opt-in.
- `concilium-run.py --seats claude,hermes,kimi` can override seats per run.
- Read-only Audit Lane and Plan Review Lane call selected seats in `review` mode only.
- `roundtable.json.participants` is rewritten to the actual seated native seats.
- Seat minutes are redacted by default; `LOOP_KEEP_RAW_MINUTES=1` is required to preserve `.raw` transcripts for local debugging.

Deployment verification before a dogfood run is considered current:

```bash
git status --short
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
./roundtable --version
./roundtable --doctor
/Users/melee/.local/bin/roundtable --version
/Users/melee/.local/bin/roundtable --doctor
```

Only after merge or launcher repointing should the two `--version` outputs show the same intended code line. `--doctor` must continue to probe seats; launcher diagnostics are printed on stderr so the roster output remains usable.
