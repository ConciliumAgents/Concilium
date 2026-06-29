# Concilium Menu Bar Contract

Phase 4 defines the service, client, and view-model contract for a future menu bar shell. It does not choose SwiftUI, AppKit, Electron, Tauri, or any other native framework.

The current browser panel is the Concilium Debug Console. It remains a local API smoke and raw-event surface, not the final product UI.

## Service Endpoints

- `GET /api/status`
- `POST /api/preflight`
- `POST /api/run`
- `GET /api/events?run=<id>`
- `GET /api/config/effective?repo=<path>`

Mutation requests send `X-Loop-Token`. `GET /api/events` returns SSE text.

## Token Handoff

The service may be launched with `--token-file PATH`. When supplied, it writes a user-only JSON token file:

```json
{"base_url": "http://127.0.0.1:8765/", "token": "...", "created_at": "2026-06-29T00:00:00Z"}
```

No token file is written unless the caller explicitly supplies `--token-file`.

## Client Methods

- `status()`
- `preflight(request)`
- `run(request, confirmation=None)`
- `events(run_id)`
- `effective_config(repo)`
- `save_config(target, patch)`

`save_config` returns `not_implemented` in Phase 4 because config write endpoints are deferred to Phase 5.

## View Model Order

1. Service and project header
2. Active decision
3. Verdict or block reason
4. Primary action
5. Seat capacity and role assignment
6. Config summary
7. Execution snapshot
8. Debug Console action

The menu bar shell owns lifecycle, presentation, and user intent only. Routing, capacity policy, maker-checker review, and execution stay in the Concilium service/runtime.
