# Concilium Phase 5 Readiness Self-Audit

Date: 2026-07-01
Target repo: `/Users/melee/Documents/agents`
Audit mode: Concilium Audit Lane, read-only review seats
Allowed write path: `docs/audits/concilium-phase5-readiness-self-audit-2026-07-01.md`

## 1. Executive Conclusion

Status: PASS WITH FIXES

Concilium is ready to enter Phase 5 after a small cleanup pass. The backend control plane is coherent enough for a desktop menu-bar product: CLI/runtime routing, Budget Guard, lane execution, artifact gate, event model, effective config, client contract, and menu-bar view model are all present and tested. No reviewer found a HIGH or CRITICAL blocker around true external seats, read-only audit safety, verdict metadata, or same-source Codex degradation.

The main Phase 5 risk is not backend correctness. It is product-boundary clarity: the browser `index.html` Debug Console and historical `conductor.py`/TUI/benchmark paths can still look like product entry points. They should be demoted, renamed, or routed through Concilium before Phase 5 UI work starts.

## 2. Round Evidence

| Round | Claude | Hermes | Kimi | Result |
|---|---:|---:|---:|---|
| 1 | ERR, rc=124, 600.011s timeout | PASS, 105.422s | PASS, 269.780s | Not accepted: one seat timed out |
| 2 | PASS, 364.575s | PASS, 141.213s | PASS, 124.526s | Accepted: all members PASS |

Round 2 `roundtable.json` evidence:

- `participants`: `["claude", "hermes", "kimi"]`
- `seat_verdicts`: Claude PASS, Hermes PASS, Kimi PASS
- `verdicts`: `["PASS", "PASS", "PASS"]`
- backend path: native `seat-*.sh` review seats, not Codex subagents

Verification command:

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
```

Observed result in both rounds: `Ran 224 tests ... OK`.

Note: Round 2's automatic artifact gate returned `unchanged_required` because the first round had already created the required report path before round 2 started. The seat evidence is still valid, and this final report replaces that generated placeholder with the synthesized audit.

## 3. Phase 5 Readiness Matrix

| Area | Status | Notes |
|---|---|---|
| Backend control plane | PASS | `concilium-run.py`, `concilium_runtime.py`, lane router, Budget Guard, runtime events, and artifact gate form a coherent control path. |
| Local service/API | PASS WITH FIXES | `web/server.py` should be kept as the local service/API for the desktop client, but its WebUI framing and auto-open behavior should be demoted. |
| Menu-bar client/view-model contract | PASS | `client/concilium_client.py`, `client/menu_bar_view_model.py`, fixtures, and contract docs exist. `save_config()` is intentionally deferred to Phase 5. |
| Config/setup readiness | PASS WITH FIXES | Effective config preview exists. Phase 5 must implement config write/setup UX. |
| Audit/read-only safety | PASS WITH FIXES | Claude review is physically read-only via `--permission-mode plan`; Hermes/Kimi rely on prompt/flag discipline plus artifact-gate detection. UI copy should say disallowed writes are detected and blocked, not physically impossible. |
| Seat provenance/verdict evidence | PASS WITH FIXES | Audit/Plan Review have `backend_type`, `seat_verdicts`, and `seat_timings`. Fast/Review lanes need `seat_results` so event consumers can show per-seat provenance. |
| WebUI cleanup readiness | PASS WITH FIXES | Browser `index.html` is not the product UI. Keep only as a demoted Debug Console or remove after service/API coverage is preserved. |

## 4. Keep / Delete / Migrate Table

| Path / Surface | Current Role | Recommendation | Reason | Risk If Wrong |
|---|---|---|---|---|
| `skills/loop-engine/web/index.html` | Browser Debug Console | DEPRECATE or KEEP AS DEBUG ONLY | Useful for local SSE/API debugging, but not the Phase 5 product surface. Do not present it as recommended UI. | Deleting too early loses a proven debug surface; keeping as default UI confuses product direction. |
| `skills/loop-engine/web/server.py` | Local service/API plus Debug Console host | KEEP, then RENAME/REFRAME as service | Desktop menu-bar client needs `/api/status`, `/api/preflight`, `/api/run`, `/api/events`, `/api/config/effective`, and token handoff. | Deleting it forces Phase 5 to rebuild the same backend contract. |
| `roundtable web` | Launcher shortcut for browser surface | RENAME/DEPRECATE | Current wording says WebUI is recommended and opens a browser by default. That conflicts with Phase 5 menu-bar direction. | Users keep treating Debug Console as the product UI. |
| `skills/loop-engine/client/concilium_client.py` | Framework-neutral service client | KEEP | It is the future menu-bar client's API boundary. | Removing it moves API details into UI code. |
| `skills/loop-engine/client/menu_bar_view_model.py` | Menu-bar popover model | KEEP | It is already the thin presentation contract and should stay independent of UI framework choice. | UI may reimplement routing/capacity logic. |
| Web/service tests | API and Debug Console contract tests | MIGRATE/RENAME | Keep service/API assertions; rename tests that imply browser WebUI is the product. | Misnamed tests preserve stale product assumptions. |
| `docs/loop-engine/phase3-closeout-2026-06-29.md` | Historical closeout | KEEP AS HISTORY, MARK SUPERSEDED WHERE NEEDED | Useful provenance, but some counts and WebUI framing are old. | Readers confuse historical facts with current product state. |
| `docs/loop-engine/phase4-closeout-2026-06-29.md` | Current backend closeout | KEEP, UPDATE TEST COUNT OR ADD CURRENT NOTE | It correctly states Phase 4 is backend/service contract, not final UI. Test count is stale after later work. | Minor evidence drift. |
| `docs/loop-engine/concilium-menu-bar-contract.md` | Phase 5 contract | KEEP | This is the right boundary: UI owns lifecycle/presentation, backend owns routing/budget/execution. | Losing it invites UI to reimplement orchestration. |
| `skills/loop-engine/bin/benchmark-roundtable.py` | Benchmark harness | MIGRATE | Its Roundtable lane still calls `conductor.py` directly, bypassing Concilium runtime/Budget Guard/provenance. | Benchmark results can misrepresent product behavior. |
| `skills/loop-engine/tui/tui.py` and `roundtable legacy` | Historical direct conductor paths | DEPRECATE | They bypass current runtime routing and guard semantics. Keep only for explicit legacy testing. | Accidental users bypass the product control plane. |
| `skills/loop-engine/bin/smoke-concilium-phase3.sh` | Old smoke script | DEPRECATE | Phase 4 smoke covers the current service/runtime path. | Contributors run stale checks. |
| `evals/loop-engine/runs/` and `__pycache__/` | Ignored local artifacts | CLEAN | They are ignored and not product inputs. | Workspace clutter and confusing audit output. |

## 5. Findings

### CRITICAL

None.

### HIGH

None.

### MEDIUM

1. Browser Debug Console is still promoted as a recommended UI.
   Evidence: `roundtable` describes `web` as "推荐--比终端友好"; `server.py` opens a browser by default.
   Impact: Phase 5 users may treat the browser panel as the product UI.
   Recommendation: rename/demote `roundtable web`, default to no browser open, and make the service role explicit.

2. Fast/Review lanes do not emit per-seat `seat_results`.
   Evidence: `run_fast_lane()` and `run_review_lane()` return no `seat_results`; runtime only emits seat events when that key exists.
   Impact: menu-bar event consumers cannot reliably show active seat, provider/model, backend type, or quota provenance for Fast/Review runs.
   Recommendation: return `seat_results` from Fast and Review lane executors.

3. Benchmark Roundtable lane bypasses Concilium runtime.
   Evidence: `benchmark-roundtable.py` directly invokes `conductor.py` for the Roundtable lane.
   Impact: benchmark data can omit Budget Guard, runtime events, and provenance semantics.
   Recommendation: route benchmark Roundtable runs through `concilium-run.py` or `concilium_runtime.run_concilium_adapter`.

4. Legacy/TUI direct conductor paths remain accessible.
   Evidence: `roundtable legacy` and `tui/tui.py` call `conductor.run()` directly.
   Impact: these paths bypass current runtime routing and guard behavior if used accidentally.
   Recommendation: mark them clearly deprecated and keep only behind explicit legacy commands.

5. Default Claude review can be too slow for broad self-audits.
   Evidence: Round 1 Claude timed out after 600.011s; Round 2 succeeded after narrowing the prompt.
   Impact: a useful audit can be reported as `error` even when other seats PASS.
   Recommendation: for broad audits, either pre-split the task, improve progress visibility, or make timeout/error handling clearer in UI.

### LOW

1. `concilium_runtime.py` loads `budget_guard.py` twice via `_load_local_module()`.
   Current risk is low because `budget_guard.py` has no mutable module-level state, but a single import would be simpler.

2. `run_audit_lane()` has weaker inner baseline timing than the outer runtime gate.
   The product path is protected by the outer runtime artifact gate, but direct unit/tool calls would benefit from the same pre-seat baseline pattern used elsewhere.

3. Phase 3 smoke and older closeout docs need deprecation/superseded markers.
   This is documentation hygiene, not product safety.

4. Ignored local artifacts are present.
   `evals/loop-engine/runs/` and `__pycache__/` can be cleaned without product impact.

### INFO

- `ConciliumClient.save_config()` returning `not_implemented` is intentional Phase 4 behavior and should be implemented in Phase 5.
- `index.html` removal is a product choice, not a safety blocker. The audit consensus is: preserve service/API; demote or remove browser UI only after preserving debugging coverage.

## 6. Minimal Cleanup Plan

Step 1: Clarify service versus browser UI.

- Rename or deprecate `roundtable web`.
- Make service startup not open a browser by default.
- Update help text and docs to say browser HTML is a Debug Console only.
- Verify with `test_roundtable_launcher.py`, `test_web_runtime_adapter.py`, and full unit suite.

Step 2: Preserve provenance for all runtime lanes.

- Add `seat_results` to Fast and Review lane return payloads.
- Ensure runtime events emit seat/backend/provider/model/status for Fast, Review, Audit, and Plan Review.
- Verify with `test_concilium_runtime.py`, `test_concilium_lanes.py`, and menu-bar view-model fixtures.

Step 3: Demote legacy and historical paths.

- Mark `roundtable legacy`, `tui/tui.py`, and `smoke-concilium-phase3.sh` as deprecated.
- Migrate `benchmark-roundtable.py` Roundtable lane to the Concilium runtime path.
- Add superseded/current-note markers to historical closeout docs where evidence is stale.
- Verify with launcher, benchmark, smoke, and docs grep checks.

Step 4: Small code hygiene.

- Replace duplicate `_load_local_module()` budget guard imports with one normal import.
- Strengthen `run_audit_lane()` inner artifact baseline if it remains directly callable.
- Clean ignored local artifacts.
- Verify with full unit suite and `git diff --check`.

## 7. Adversarial Review Notes

If we delete browser UI, do we lose debugging ability?

Yes, if deletion happens before the desktop client has equivalent event/log visibility. The better near-term move is to demote it: no default browser open, no product framing, and keep it as a Debug Console until Phase 5 replaces it.

If we keep service/API, does WebUI redundancy remain?

No, if naming is fixed. `server.py` is not redundant WebUI; it is the local service contract the desktop menu-bar client needs. The redundant part is the browser product shell and launcher wording.

If we clean up now, can it slow Phase 5?

The proposed cleanup is small and should speed Phase 5 by removing ambiguous entrypoints before UI work begins.

If we do not clean up now, will historical baggage enter the desktop product?

Partly yes. The biggest risks are stale launcher language, benchmark paths that measure old behavior, and missing Fast/Review seat provenance in event streams. These should be fixed before building the menu-bar UI.

## 8. Final Verdict

Phase 5 can start after the minimal cleanup plan. The roundtable self-audit found no HIGH or CRITICAL blocker and Round 2 achieved unanimous PASS from Claude, Hermes, and Kimi.

VERDICT: PASS
