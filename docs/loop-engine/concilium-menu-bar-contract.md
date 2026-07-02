# Concilium Menu Bar Contract

Phase 4 defines the service, client, and view-model contract for a future menu bar shell. It does not choose SwiftUI, AppKit, Electron, Tauri, or any other native framework.

The current browser panel is the Concilium Debug Console. It remains a local API smoke and raw-event surface, not the final product UI.

The launcher should expose the localhost API as `roundtable service`. The old `roundtable web` wording is deprecated because the browser panel is only a Debug Console, not the product surface. Service startup should not open a browser unless the caller passes an explicit `--open`.

## Service Endpoints

- `GET /api/status`
- `POST /api/preflight`
- `POST /api/run`
- `GET /api/events?run=<id>`
- `GET /api/config/effective?repo=<path>`

Mutation requests send `X-Loop-Token`. `GET /api/events` returns SSE text.

`GET /api/config/effective` returns `{repo, config}`. Consumers should read the inner `config` object when present; older raw-config fixtures may omit the envelope.

## Token Handoff

The service may be launched with `--token-file PATH`. When supplied, it writes a user-only JSON token file:

```json
{"base_url": "http://127.0.0.1:8765/", "token": "...", "created_at": "2026-06-29T00:00:00Z"}
```

No token file is written unless the caller explicitly supplies `--token-file`.

## Client Methods

- `from_token_file(path)`
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

The menu-bar product should treat `run-summary.json` as the durable status source for completed runs. Runtime events are the live stream; `run-summary.json` is the settled ledger.

## Seat Provenance

Seat display names are not enough to explain quota usage. Runtime events and popover summaries should preserve:

- `seat`
- `backend_type`: `codex_subagent`, `external_cli`, or `configured_seat`
- `provider`
- `model`
- `capacity_status`
- `capacity_source`
- `status`
- `reason`

This lets the user distinguish a Codex-hosted subagent audit from a real `seat-*.sh` CLI seat, including `seat-codex.sh`. The menu bar should show backend type near the seat name when it differs from the user's expected roster.

When a runtime slice has not actually dispatched a reviewer seat, it must emit `status: not_invoked` instead of implying quota was consumed.

### Quota Exhaustion And Provisional Closure

Seat quota exhaustion is not the same as reviewer disagreement. Runtime summaries classify rate-limit, quota, usage-limit, and refresh-window failures as `quota_exhausted` and set `final_verdict: retry_required` unless the failed seat is not required for the current lane. The UI must not display this as PASS. It should display the passing seats and the exact retry seat, for example `kimi retry required after capacity refresh`.

If a seat previously raised a BLOCK in the same implementation closure sequence, a later quota failure by that same seat cannot close the sequence as PASS. The sequence remains `retry_required` until that seat passes or the user explicitly removes it from the required seat set.

## Audit Artifact Gate

Read-only Audit Lane runs must expose artifact-gate status in the event stream. A run can be operationally useful but still incomplete when the required report was not written, was empty or stale, or when new workspace delta escaped the allowed report paths. The UI should treat `artifact_gate.status != "passed"` as a blocked/completion-failed state and surface `missing`, `empty`, `unchanged_required`, `disallowed`, and `disallowed_delta` without showing secret-bearing raw logs.

Strict artifact failures may also include invalid paths. The UI should display these as configuration or request errors, not as reviewer findings, because the orchestrator rejected the write boundary before trusting any generated report path.

For read-only Audit Lane and Plan Review Lane runs, `run_guard.confirmation_payload.files_may_be_modified` means target project files may be edited outside the declared review boundary. It must be `false` when the route is read-only and no caller explicitly overrides it. Report/artifact writes are represented separately through `read_only_task`, `allowed_write_paths`, and `required_artifact_paths` so the UI can say "review is read-only; this report path may be written" instead of warning about arbitrary file edits.

## Plan Review Loop

Plan Review Lane runs should surface:

- current round and max rounds;
- reviewer seat results and backend provenance;
- `unresolved_blockers`;
- whether the next action is retry reviewer, revise plan, approved, or max rounds reached.

The menu bar should not present Plan Review Lane as implementation progress. It is a pre-implementation gate: reviewers only review, and any plan revision is a host/user action that may change only the reviewed plan artifact.
