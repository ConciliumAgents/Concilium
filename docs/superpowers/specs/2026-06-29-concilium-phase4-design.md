# Concilium Phase 4 Design

## Summary

Phase 4 turns Concilium from a routed prototype into a trustworthy routed live control plane.

The product promise is simple:

> Concilium shows the cheapest safe lane, warns before spending agent time or hitting capacity risk, and then runs the exact lane it showed.

Phase 4 is not a polished menu bar product release. It is the service/runtime contract that makes a CodexBar-like menu bar front end possible without moving routing, capacity, or execution logic into the UI.

## Current Baseline

Phase 3 completed:

- layered config: bundled defaults, user config, project config;
- capacity status records and redaction;
- preflight evaluation;
- pure Fast / Review / Roundtable lane routing;
- `concilium-run.py` dry-run preview and live wrappers;
- WebUI `/api/preflight`;
- router-aware benchmark records;
- Phase 3 smoke matrix.

The known trust gap is that WebUI `/api/preflight` previews Concilium routing, while WebUI `/api/run` still starts the older direct roundtable path through `conductor.run()`.

## First Principles

1. **Trust beats polish.** A rough UI that tells the truth is better than a native menu bar app whose preview and run behavior diverge.
2. **Routing is an execution contract, not a label.** Once Concilium selects Fast, Review, or Roundtable, the run path must use that same lane unless the system re-preflights and exposes the changed decision.
3. **Capacity is a live-run gate.** Unknown capacity may be allowed, but only after explicit per-run confirmation. Unavailable or hard-exhausted required seats block before agent calls.
4. **The service is the source of truth.** Menu bar UI, WebUI debug console, CLI, and future clients should talk to the same local Concilium service contracts.
5. **Do not move orchestration into UI code.** Routing, preflight, execution, config validation, and redaction remain in Python core modules.

## Goals

### G1: Runtime Adapter

Introduce a small runtime adapter around Concilium execution. The adapter owns the contract between route/preflight decisions, budget confirmation, lane execution, and emitted events.

It must handle:

- request normalization;
- config overlays from request-level seat/model choices;
- preview and run consistency;
- server-side Budget Guard enforcement;
- stable event emission for Fast, Review, and Roundtable lanes;
- timeout and process cleanup policy;
- final result shape for CLI, WebUI, and future menu bar clients.

### G2: Route-Run Consistency

`/api/preflight` and `/api/run` must use the same decision inputs:

- repo;
- task;
- test command;
- requested seats;
- seat model overrides;
- lane/risk overrides if introduced;
- timeout or execution mode;
- dry-run/stub-run/live-run mode.

If any decision input changes after preflight, `/api/run` must re-preflight. If the selected lane or preflight status changes, the run must not silently proceed under the old preview.

### G3: Budget Guard

Live execution must require a server-side guard, not only frontend button state.

Policy per required seat:

| Status | Policy |
|---|---|
| `ok` and fresh | Allow. Show provider, model, source, checked time, and reset time when known. |
| `soft_limited` | Warn and require explicit per-run confirmation. Limit to tiny smoke or user-approved live task. |
| `unknown` | Warn and require explicit per-run confirmation. Unknown is not green. |
| `hard_exhausted` | Block when fresh and explicit. If stale and re-check is unavailable, treat as `unknown` only for tiny smoke after confirmation. |
| `unavailable` | Block. A missing CLI or unavailable seat cannot run. |
| missing required seat record | Block as `seat unresolved`. |

The guard must never downgrade Review to Fast to avoid a blocked reviewer.

### G4: Local Service Contract

Evolve the existing localhost service into a framework-neutral Concilium service. The WebUI becomes a debug console; the future menu bar app becomes a thin client.

Minimum Phase 4 service endpoints:

- `GET /api/status`
- `POST /api/preflight`
- `POST /api/run`
- `GET /api/events?run=<id>`
- `GET /api/config/effective?repo=<path>`

Config write endpoints may be designed but should only be implemented if the runtime adapter and guard are already stable:

- `POST /api/config/user`
- `POST /api/config/project`

### G5: Menu Bar Contract

Define a small client/view-model contract before choosing a native app framework.

`ConciliumClient` methods:

- `status()`
- `preflight(request)`
- `run(request, confirmation)`
- `events(run_id)`
- `effectiveConfig(repo)`
- `saveConfig(target, patch)`

The menu bar shell must own only lifecycle, presentation, and user intent. It must not reimplement routing, capacity rules, maker-checker review, or conductor behavior.

### G6: Tiny Live Smoke

Phase 4 may include one tiny gated live smoke after the guard is implemented.

The required live smoke is not a real-human test. It is one controlled local agent/model CLI call on a disposable task.

Default live smoke scope:

- Fast Lane live smoke: allowed if required seat is `ok`, or `unknown` with explicit confirmation.
- Review Lane live smoke: optional manual acceptance only if both executor and reviewer pass the guard or are explicitly confirmed.
- Roundtable live smoke: deferred from the required Phase 4 gate unless all required seats are fresh `ok` and the user explicitly approves the higher call count.

## Non-Goals

Phase 4 must not:

- build a polished native menu bar product;
- choose or commit to SwiftUI, AppKit, Electron, Tauri, or any other app framework;
- make the browser WebUI the final product surface;
- integrate CodexBar as a runtime dependency;
- scrape provider dashboards, browser cookies, or OAuth stores;
- store provider credentials;
- write global Claude, Codex, Kimi, Hermes, or CodexBar config without an explicit user command;
- implement multi-project queues, cloud sync, history analytics, or remote control;
- run full Roundtable live as an automated gate.

## Architecture

### Layer 1: Concilium Core

Existing Python modules remain source of truth:

- `concilium_config.py`
- `capacity_status.py`
- `concilium_preflight.py`
- `lane_router.py`
- `concilium-run.py`
- `review-lane.py`
- `conductor.py`

Phase 4 may refactor `concilium-run.py` into smaller modules if needed, but behavior must remain covered by tests.

### Layer 2: Runtime Adapter

Add a framework-neutral adapter that coordinates a full run:

```text
request -> normalize -> load effective config -> apply request overlay
        -> collect capacity -> infer/accept signals -> route
        -> preflight -> guard decision -> execute selected lane
        -> emit events -> final result
```

The adapter should distinguish three modes:

- `preview`: route and preflight only; never calls agents.
- `stub_run`: emits run events through stubbed/dry seat behavior; no live model calls.
- `live_run`: may call agents after Budget Guard allows or confirms.

This removes the current ambiguity where WebUI dry-run means stubbed execution while `concilium-run.py --dry-run` means preview-only.

### Layer 3: Local Service

The local service exposes the adapter over localhost with token-protected mutation endpoints.

The service should keep `127.0.0.1` binding and existing `X-Loop-Token` semantics, but Phase 4 must define how a menu bar client obtains that token:

- service writes a token file with user-only permissions; or
- menu bar launches the service and receives the token on stdout; or
- service exposes a local-only launch handshake.

The selected mechanism must be explicit before building a menu bar shell.

### Layer 4: Clients

Clients consume the same service:

- CLI: direct module/command invocation remains supported.
- WebUI: becomes Debug Console and API smoke surface.
- Menu bar shell: thin control surface using `ConciliumClient`.

## Event Model

The adapter must emit a stable minimal event stream for every lane.

Required events:

- `start`: request accepted, includes repo, task summary, selected lane, required seats.
- `preflight`: preflight status, warnings, blocking seats.
- `guard`: allowed, blocked, or confirmation required.
- `seat`: seat started/done for actual agent calls.
- `verify`: verification command result when applicable.
- `verdict`: review or final verdict when applicable.
- `finish`: final lane status.
- `done`: terminal event with return code.

Roundtable Lane should preserve existing `WebReporter` events where possible. Fast and Review lanes may emit a smaller adapter-native stream, but must still end in `done`.

## Request Overlay

Phase 4 must define how UI-provided choices affect config without writing config files.

Request overlay may include:

- selected seats;
- seat model overrides;
- commander;
- reviewer;
- max iterations;
- timeout;
- test command;
- execution mode.

Overlay precedence for one run:

1. bundled defaults;
2. user config;
3. project config;
4. request overlay.

Request overlay must not persist unless the user explicitly saves it to user or project config.

## Budget Guard Details

The guard confirmation payload must show:

- selected lane;
- routing reason;
- required seats;
- provider/model per required seat;
- capacity status;
- capacity source;
- reason;
- checked time;
- reset time when known;
- expected maximum agent calls when estimable;
- whether files may be modified;
- whether global config may be touched.

Unknown and soft-limited confirmations are per-run only. A previous confirmation must not silently authorize a later task with a different route, required seat set, repo, or task.

## Menu Bar Information Hierarchy

The Phase 4 menu bar work should define a view model, not a polished app.

Top-to-bottom popover model:

1. Service and project header: Concilium status, selected repo, service health, refresh action.
2. Active decision: lane, routing reason, preflight status, required seats, primary action.
3. Verdict or BLOCK reason: always visible near the top when present.
4. Seat capacity and role assignment:
   - Fast default agent;
   - Review executor and reviewer;
   - Roundtable commander, seats, reviewer;
   - capacity status and checked/reset times.
5. Config summary:
   - risk posture;
   - auto-escalation stance;
   - auto-downgrade stance;
   - whether project override is active.
6. Execution snapshot:
   - current lane;
   - active seat;
   - iteration or phase;
   - latest event;
   - elapsed time.
7. Debug action: open WebUI Debug Console for raw logs and transcripts.

## Testing Strategy

Unit tests:

- request normalization and overlay precedence;
- preflight/run parity;
- guard block/warn/confirm policies;
- stale or changed preflight rejection;
- missing required seat record blocks;
- unknown capacity requires confirmation for live run;
- event stream always terminates with `done`;
- Fast/Review timeout cleanup uses process-group behavior or equivalent;
- no global provider config write occurs during setup or smoke.

Service tests:

- `/api/preflight` and `/api/run` pass identical decision inputs;
- `/api/run` uses the runtime adapter, not direct `conductor.run()`;
- blocked run returns blocked event/result without seat calls;
- warn run is rejected without confirmation;
- confirmed warn run proceeds only when confirmation matches the current preflight;
- CLI preview and API preflight agree on lane, required seats, preflight status, and redacted capacity.

Smoke tests:

- stub-run Fast, Review, and Roundtable event streams;
- tiny live Fast smoke gated by Budget Guard;
- optional manual Review smoke;
- deferred manual Roundtable smoke only after explicit user approval.

## Acceptance Criteria

Phase 4 is complete when all are true:

- `/api/run` and future menu bar run action execute through the runtime adapter.
- A run uses the same lane as the accepted preflight decision, or blocks and reports that the decision changed.
- `preview`, `stub_run`, and `live_run` are distinct modes.
- Server-side Budget Guard blocks unavailable, hard-exhausted, and unresolved required seats.
- Server-side Budget Guard requires explicit confirmation for unknown or soft-limited required seats before live execution.
- Fast, Review, and Roundtable produce a stable event stream ending in `done`.
- WebUI is labeled and treated as Debug Console, not the final product surface.
- `ConciliumClient` and menu bar view-model fixtures exist without choosing a native framework.
- Effective config can be previewed for a repo.
- No Phase 4 action writes global provider config without explicit user command.
- Tests cover the minimum matrix in this spec.
- One tiny live Fast smoke is either completed with redacted evidence or explicitly skipped because capacity guard blocks it.

## Rollout Order

1. Runtime adapter design and tests.
2. Budget Guard state machine.
3. `/api/preflight` and `/api/run` parity through the adapter.
4. Event adapter for Fast, Review, and Roundtable.
5. Debug Console relabel and service status/effective config endpoints.
6. Menu bar client contract and view-model fixtures.
7. Tiny gated live smoke.
8. Phase 4 closeout report.

## Open Decisions

The implementation plan must choose:

- token handoff mechanism for a future menu bar client;
- whether Fast Lane initializes `.roundtable` KB or uses a standalone prompt contract;
- exact process-group cleanup helper shared by Fast, Review, and Roundtable;
- whether config save endpoints are included in Phase 4 or deferred to Phase 5.

These are implementation choices, not unresolved product requirements.

## Implementation Status

Implemented by `docs/superpowers/plans/2026-06-29-concilium-phase4-implementation.md`.

Closeout evidence: `docs/loop-engine/phase4-closeout-2026-06-29.md`.
