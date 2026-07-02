# Concilium Public-Readiness Privacy Audit - 2026-07-02

## Conclusion

Status: PASS WITH REVIEW

Concilium can continue toward an open-source developer-tool preview. The previously required publication-readiness fixes have been closed in this branch. The remaining requirement is owner review before any public GitHub publish or push.

## Scope

- Repository: `/Users/melee/Documents/agents`
- Execution worktree: `/Users/melee/.config/superpowers/worktrees/agents/codex-concilium-open-source-tool-launch`
- Release type: open-source developer tool preview
- Excluded from public collateral: `.roundtable/sessions/**`, `.venv/**`, `evals/**`, `__pycache__/**`

## Checks

| Check | Result | Evidence |
|---|---|---|
| Secret/token scan | PASS WITH REVIEW | Initial `rg` returned 789 broad matches; final post-README/community-file scan returned 808 broad matches. Matches are dominated by token plumbing, redaction tests, test fixtures, provider names, plan/docs references, and security warnings. No high-confidence live credential was identified from reviewed output. |
| Private session artifact boundary | PASS | `git ls-files .roundtable` returned 0 tracked files. `.roundtable/sessions/**` remains excluded from launch collateral. |
| Stale product/private-prototype wording | PASS | `docs/loop-engine/agent-moa-positioning.md` now carries a 2026-07-02 supersession note above the historical private-prototype wording. |
| GitHub community files | PASS | `README.md`, `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, issue templates, and PR template are present. |
| License readiness | PASS | `LICENSE` uses Apache-2.0 for the developer-tool preview. |

## Required Fixes Before Public Launch

- Owner approval is required before creating, renaming, pushing to, or making public the GitHub repository at `https://github.com/ConciliumAgents/Concilium.git`.
- Re-run the privacy scan after any new launch collateral or demo assets are added.

## Non-Blocking Follow-Ups

- Keep broad provider names such as Anthropic, OpenAI, Moonshot, and DeepSeek in docs/tests when they describe supported local seats or redaction fixtures.
- Consider adding a shorter `docs/launch/release-checklist.md` after the first public launch if this report becomes too detailed for future releases.
