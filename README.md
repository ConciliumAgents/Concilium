# Concilium

Concilium is a local developer tool for agent-level MoA: it routes work across native agent CLIs, gates risky runs with budget/capacity checks, and records auditable run summaries.

> Status: developer tool preview. Phase 4 backend/control-plane work is complete; Phase 5 front-end work is the threshold for calling Concilium a product.

## Why Concilium Exists

Most multi-agent demos combine model outputs. Concilium coordinates complete local agent environments instead: each seat can keep its own CLI, model routing, permission model, timeout profile, and review style.

The goal is truthful orchestration. Concilium should show the selected lane, required seats, capacity risk, write boundary, and final run evidence before you treat a run as closed.

## What It Does Today

- Routes work across Fast, Review, Audit, Plan Review, and Roundtable-style lanes.
- Uses native agent seats such as Claude, Hermes, Kimi, and Codex when they are available locally.
- Runs a Budget Guard before live execution so unknown or limited capacity is visible.
- Exposes a local CLI plus localhost service/API.
- Keeps the browser surface as a Debug Console, not the final product UI.
- Writes machine-readable run summaries so closure is based on evidence, not just a markdown report.

## What It Is Not Yet

- It is not a finished desktop product.
- It is not a Phase 5 menu-bar app.
- It is not a hosted service.
- It does not guarantee provider, model, or quota availability on every machine.
- It does not replace local review of sensitive `.roundtable/sessions/**` artifacts before sharing output publicly.

## Quickstart

```bash
git clone https://github.com/liting0216/Concilium.git
cd Concilium
./roundtable --version
./roundtable --doctor
python3 skills/loop-engine/bin/concilium-run.py --repo "$PWD" --task "Preview a README review route without calling live seats." --test-cmd "true" --dry-run
./roundtable service --no-open
```

The quickstart uses preview/dry-run commands first. Commands that use `./roundtable --task ...` or `concilium-run.py --live` may consume real provider quota.

## Architecture

Concilium keeps routing, Budget Guard, lane execution, event emission, artifact gates, and run summaries in the Python backend under `skills/loop-engine/bin`.

The top-level `roundtable` launcher is the user-facing CLI entrypoint. `roundtable service` starts the local API and optional Debug Console. The future Phase 5 UI should remain a thin client over this service; it should not reimplement routing, budget policy, seat execution, or closure rules.

Key references:

- `docs/loop-engine/phase4-closeout-2026-06-29.md`
- `docs/loop-engine/concilium-menu-bar-contract.md`
- `docs/loop-engine/dogfood-closure-hardening-2026-07-02.md`
- `docs/audits/concilium-phase5-readiness-self-audit-2026-07-01.md`

## Safety Model

Concilium treats run evidence as local and sensitive by default.

- `.roundtable/sessions/**` can contain task context, seat minutes, test output, and local paths.
- Token files, provider logs, raw transcripts, and private memory should not be committed or pasted into public issues.
- Read-only audit/report flows rely on artifact gates and delta checks; underlying native seats may still have their own local capabilities.
- `run-summary.json` is the settled status source for completed runs.

## Current Limitations

Concilium depends on local native agent CLIs. Seat availability, provider models, and quota behavior vary by machine.

The browser surface is a Debug Console, not the Phase 5 product UI.

Phase 5 menu-bar/front-end setup is planned but not included in this release.

## Roadmap

- Finish the Phase 4 open-source developer-tool release package.
- Harden public docs and examples around dry-run-first usage.
- Use early feedback to shape Phase 5 setup, config-write UX, run history, and native front-end behavior.
- Call Concilium a product only after the Phase 5 UI and onboarding path exist.

## Contributing

See `CONTRIBUTING.md` for contribution scope and verification commands. For security-sensitive issues or accidental secret exposure, follow `SECURITY.md` and do not open a public issue containing private logs or credentials.
