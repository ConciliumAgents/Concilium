# Concilium Open-Source Tool Release Brief - 2026-07-02

## Conclusion

Release Concilium as an open-source developer tool preview, not as a product.

## Audience

- Developers experimenting with local coding agents.
- Agent-tooling builders who care about auditability and routing.
- People comparing native CLI orchestration with model-output-only MoA.

## Core Message

Concilium coordinates real native agent seats, gates execution with budget/capacity checks, and leaves machine-readable run evidence.

## Repository

- Public name: `Concilium`
- Intended URL: `https://github.com/ConciliumAgents/Concilium.git`
- Do not publish the tool preview under the old `loop-engine` repository name.

## Do Not Claim

- Finished product.
- Hosted service.
- One-click app.
- Guaranteed provider availability.
- Phase 5 UI shipped.

## Channel Plan

| Channel | Timing | Goal | Gate |
|---|---|---|---|
| GitHub public repo | Launch day | Source of truth | README, license, privacy audit, quickstart pass |
| X / LinkedIn | Launch day | Awareness | Demo GIF or screenshot plus repo link |
| Technical article | Launch day or D+1 | Explain architecture | README stable and claims sourced |
| Hacker News Show HN | D+1 to D+7 | Developer feedback | Fresh clone quickstart works |
| Product Hunt | After Phase 5 product/UI release | Product-style discovery | Out of scope for this tool-only release |

## Copy Bank

### Short Post

Concilium is now open as a developer tool preview: a local control plane for agent-level MoA. It routes work across native agent CLIs, checks budget/capacity risk before live runs, and records auditable run summaries. Phase 4 is the tool/control-plane release; Phase 5 is where it becomes a product UI.

### Show HN Title

Show HN: Concilium, a local control plane for native multi-agent coding workflows

### Repository Description

Local developer tool for agent-level MoA: native agent CLI routing, Budget Guard, artifact gates, and auditable run summaries.

## Launch Gates

- Native-seat plan review PASS.
- Privacy audit PASS or PASS WITH FIXES with all required fixes closed.
- README quickstart verified from a clean checkout.
- No committed `.roundtable/sessions/**`, token files, raw provider logs, or private memory.
- Public copy says tool preview, not product.
