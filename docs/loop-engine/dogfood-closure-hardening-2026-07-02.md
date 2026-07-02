# Concilium Dogfood Closure Hardening - 2026-07-02

## First-Principles Rule

A Concilium run is not complete because a markdown report exists. It is complete when the default launcher version is known, required seats are accounted for, Budget Guard state is recorded, artifact gate state is recorded, and `run-summary.json` gives a machine-readable final verdict.

## Closure States

| final_verdict | Meaning | User Action |
| --- | --- | --- |
| pass | Required seats passed and gates passed. | Safe to treat as closed. |
| block | At least one required reviewer returned BLOCK. | Fix and rerun. |
| retry_required | A required seat failed for quota, timeout, or technical error. | Rerun after capacity refresh or explicitly change required seats. |
| artifact_failed | Output or write-boundary requirements failed. | Fix artifact path/scope and rerun. |
| error | Runtime failed outside normal review semantics. | Debug runtime. |

## Dogfood Lessons Applied

- FBA reached stable PASS with native `claude`, `hermes`, and `kimi` seats.
- Agent-search showed why a final Kimi quota ERR must not be collapsed into either PASS or BLOCK.
- Both dogfood runs showed that human reports are not enough for Phase 5 UI; `run-summary.json` is the UI source of truth.
- Session retention must be explicit because `.roundtable/sessions` can preserve sensitive context.
