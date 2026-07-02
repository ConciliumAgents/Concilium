# Concilium Open Source Tool Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare and launch the current Phase 4 Concilium codebase as an open-source developer tool, while explicitly reserving "product" positioning for the future Phase 5 front end.

**Architecture:** Treat the repository itself as the release surface: public docs, launch copy, demo commands, safety policy, and community files must all point to the same tool-level story. Concilium remains a local CLI/service/debug-console control plane in this release; Phase 5 menu-bar UI, setup UX, and product packaging stay out of scope. A native-seat Concilium plan review must pass before any release-package execution starts.

**Tech Stack:** Existing Bash launcher, Python standard library, existing Concilium runtime modules, GitHub public repository features, Markdown docs, local shell verification, native Concilium seats `claude`, `hermes`, and `kimi`.

---

## Source Inputs

- User decision on 2026-07-02: publish the current version as a "tool", not a "product"; Phase 5 completion is the product threshold.
- Current launcher verification on 2026-07-02:
  - `./roundtable --version`: entrypoint `/Users/melee/Documents/agents/roundtable`, branch `main`, commit `1a9e9e4`.
  - `./roundtable --doctor`: available seats `claude`, `codex`, `hermes`, `kimi`; native review seats for this plan are `claude`, `hermes`, and `kimi`.
- Phase 4 backend closeout: `docs/loop-engine/phase4-closeout-2026-06-29.md`.
- Phase 5 readiness self-audit: `docs/audits/concilium-phase5-readiness-self-audit-2026-07-01.md`.
- Phase 5 UI boundary contract: `docs/loop-engine/concilium-menu-bar-contract.md`.
- Dogfood closure rule: `docs/loop-engine/dogfood-closure-hardening-2026-07-02.md`.
- Historical positioning risk: `docs/loop-engine/agent-moa-positioning.md` still says the repo is a private prototype and not ready to publish; this must be reconciled before public launch.
- External publication requirements checked on 2026-07-02:
  - GitHub community profile files: <https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories>
  - GitHub licensing guidance: <https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository>
  - Show HN guidelines: <https://news.ycombinator.com/showhn.html>
  - Product Hunt launch guide: <https://www.producthunt.com/launch>

## First-Principles Constraints

1. Tool, not product: public copy must say "developer tool", "CLI/local service", or "developer preview". It must not claim a finished desktop product, polished UI, hosted service, or end-user app.
2. Truthful scope: Phase 4 gives a routed live control plane, Budget Guard, local service, Debug Console, run evidence, and menu-bar contract. Phase 5 UI and config-write setup UX are not shipped yet.
3. Evidence before claims: every public claim must trace to a repo file, command output, or an explicit future-roadmap item.
4. Safety before reach: no broad launch until private session artifacts, local memory, provider details, and user/project-specific materials are scanned and either removed, ignored, or clearly marked non-public.
5. One public story: `Concilium` is the outward name. `Loop Engine`, `roundtable`, TUI, legacy conductor, and Debug Console are implementation or history terms, not parallel products.
6. Review gate: this plan must pass native-seat Concilium review before Task 1 starts. A failed or retry-required review blocks execution.

## Release Definition

This release is:

- `Concilium`, an open-source developer tool for local agent-level MoA orchestration.
- A CLI plus local service/debug-console control plane.
- A developer preview for people comfortable with local agent CLIs and command-line setup.

This release is not:

- A finished desktop product.
- A Phase 5 menu-bar app.
- A cloud service.
- A managed multi-agent platform.
- A guarantee that every provider seat is available on every machine.

## Public Positioning

Primary one-liner:

> Concilium is a local developer tool for agent-level MoA: it routes work across native agent CLIs, gates risky runs with budget/capacity checks, and records auditable run summaries.

Chinese one-liner:

> Concilium 是一个本地 agent-level MoA 开发者工具：它协调真实 agent CLI seat，在执行前做路由和预算守门，在执行后留下可审计的 run summary。

Do not use this wording before Phase 5:

- "desktop product"
- "menu-bar product"
- "finished app"
- "consumer-ready"
- "one-click multi-agent automation"
- "complete product release"

Allowed wording:

- "open-source developer tool"
- "developer preview"
- "local CLI/service"
- "Phase 4 backend/control-plane release"
- "Phase 5 UI planned"

## File Responsibility Map

- Create: `README.md`
  - Public entry point, quickstart, truthful release status, architecture summary, safety model, roadmap.
- Create: `LICENSE`
  - Open-source license. Default recommendation is Apache-2.0 unless the owner explicitly chooses MIT before implementation.
- Create: `CONTRIBUTING.md`
  - Narrow contribution rules for early tool preview: bug reports, docs fixes, reproducible demos, and small runtime patches.
- Create: `CODE_OF_CONDUCT.md`
  - Standard contributor conduct policy.
- Create: `SECURITY.md`
  - Vulnerability and sensitive-artifact reporting policy; includes local session and provider-token warning.
- Create: `.github/ISSUE_TEMPLATE/bug_report.md`
  - Reproducible command, environment, expected result, actual result, sanitized logs.
- Create: `.github/ISSUE_TEMPLATE/feature_request.md`
  - Problem, user type, proposed behavior, non-goals.
- Create: `.github/pull_request_template.md`
  - Scope, verification, privacy check, docs update.
- Create: `docs/launch/open-source-tool-release-2026-07-02.md`
  - One-file launch brief, channel plan, asset checklist, release gates, and copy bank.
- Create: `docs/launch/privacy-and-publication-audit-2026-07-02.md`
  - Public-readiness audit result and remediation checklist.
- Modify: `docs/loop-engine/agent-moa-positioning.md`
  - Add a current-status note that supersedes the old "private working prototype" statement for this tool-preview launch.
- Modify: `docs/loop-engine/phase4-closeout-2026-06-29.md`
  - Add a public-status note: Phase 4 can be discussed as a backend/tool release, not as product completion.
- Modify: `docs/loop-engine/concilium-menu-bar-contract.md`
  - Add a Phase 5 product-boundary note if it is not already clear enough after README drafting.
- Do not modify: `.roundtable/sessions/**`
  - Session artifacts are private/local evidence and must not be committed as launch collateral.
- Do not create: landing page, paid ad campaign, Product Hunt launch, or native app packaging in this plan.

---

## Task 0: Native-Seat Plan Review Gate

**Files:**
- Review: `docs/superpowers/plans/2026-07-02-concilium-open-source-tool-launch.md`
- Output: `.roundtable/sessions/<generated-session>/run-summary.json`
- Optional report path if the lane requires one: `docs/audits/concilium-open-source-tool-launch-plan-review-2026-07-02.md`

- [ ] **Step 1: Confirm launcher and seat availability**

Run:

```bash
git status --short
./roundtable --version
./roundtable --doctor
```

Expected:

```text
./roundtable --version includes branch: main
./roundtable --version includes commit: 1a9e9e4 or a later intentionally accepted commit
./roundtable --doctor lists claude, hermes, and kimi as available seats
```

- [ ] **Step 2: Run a read-only native-seat review of this plan**

Run from `/Users/melee/Documents/agents`:

```bash
./roundtable \
  --repo /Users/melee/Documents/agents \
  --task "Read-only plan review. Review docs/superpowers/plans/2026-07-02-concilium-open-source-tool-launch.md before any release-package execution. Required reviewer seats: claude, hermes, kimi. Do not modify files except an allowed audit report if the artifact gate requires it. Check whether the plan correctly positions the current Phase 4 codebase as an open-source developer tool rather than a product, preserves Phase 5 as the product threshold, includes adequate privacy/publication gates, and avoids overclaiming public launch channels. Return PASS only if execution may start; BLOCK for factual, safety, or sequencing issues; ERR/retry_required for technical seat failures." \
  --test-cmd "python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'" \
  --seats claude,hermes,kimi
```

Expected:

```text
run-summary.json final_verdict is pass
required seats include claude, hermes, kimi
backend_type for those seats is external_cli or the native seat backend reported by the launcher
Budget Guard state is recorded
artifact gate state is recorded
```

- [ ] **Step 3: Block execution unless the review is clean**

Inspect the latest session summary:

```bash
summary_path="$(find .roundtable/sessions -maxdepth 3 -name run-summary.json -print | sort | tail -1)"
printf '%s\n' "$summary_path"
```

Then read the selected file:

```bash
python3 -m json.tool "$summary_path"
```

Expected execution gate:

```text
final_verdict: pass -> Task 1 may start
final_verdict: block -> revise this plan and rerun Task 0
final_verdict: retry_required -> rerun after capacity refresh or explicitly change required seats with user approval
final_verdict: artifact_failed or error -> debug the run before touching public-release files
```

## Task 1: Public-Readiness And Privacy Audit

**Files:**
- Create: `docs/launch/privacy-and-publication-audit-2026-07-02.md`
- Inspect only: `.roundtable/`, `roundtable-memory/`, `docs/`, `skills/`, `config/`, `.gitignore`

- [ ] **Step 1: Create the launch docs directory**

Run:

```bash
mkdir -p docs/launch
```

Expected:

```text
docs/launch exists
```

- [ ] **Step 2: Scan for obvious sensitive material**

Run:

```bash
rg -n --hidden --glob '!.git/**' --glob '!.venv/**' --glob '!__pycache__/**' --glob '!evals/**' --glob '!.roundtable/sessions/**' '(api[_-]?key|token|secret|password|authorization|bearer|cookie|session|provider[_-]?key|anthropic|moonshot|deepseek|openai)' .
```

Expected:

```text
Only documentation, test fixtures, redacted examples, or intended provider names appear.
Any live credential, private token, raw cookie, or user-specific account detail blocks public launch.
```

- [ ] **Step 3: Scan public docs for stale product claims**

Run:

```bash
rg -n 'product|menu-bar product|finished app|private working prototype|not ready to publish|recommended UI|WebUI' docs skills roundtable
```

Expected:

```text
Every remaining "product" or "WebUI" mention is either historical, explicitly Phase 5, or marked Debug Console.
If the old private-prototype statement in docs/loop-engine/agent-moa-positioning.md is not yet marked superseded, record it as a required fix for Task 2 and keep the audit status at PASS WITH FIXES or BLOCKED until Task 2 closes it.
```

- [ ] **Step 4: Write the privacy audit report**

Create `docs/launch/privacy-and-publication-audit-2026-07-02.md` with this structure:

```markdown
# Concilium Public-Readiness Privacy Audit - 2026-07-02

## Conclusion

Status: BLOCKED | PASS WITH FIXES | PASS

## Scope

- Repository: /Users/melee/Documents/agents
- Release type: open-source developer tool preview
- Excluded from public collateral: .roundtable/sessions/**, .venv/**, evals/**, __pycache__/**

## Checks

| Check | Result | Evidence |
|---|---|---|
| Secret/token scan | Pending until Step 2 runs | `rg` command from this task |
| Private session artifact boundary | Pending until Step 2 runs | `.roundtable/sessions/**` excluded from collateral |
| Stale product/private-prototype wording | Pending until Step 3 runs | `rg` command from this task |
| GitHub community files | Pending until Task 3 runs | README/LICENSE/CONTRIBUTING/SECURITY checks |
| License readiness | Pending until Task 3 owner decision | Apache-2.0 recommended unless owner chooses MIT |

## Required Fixes Before Public Launch

- Pending until Steps 2 and 3 run.

## Non-Blocking Follow-Ups

- Pending until Steps 2 and 3 run.
```

The final implementation must replace every `Pending` entry with concrete results from Steps 2 and 3 before committing. If there are no required fixes or follow-ups, write `None.` under that section.

- [ ] **Step 5: Commit only the audit report after review**

Run:

```bash
git add docs/launch/privacy-and-publication-audit-2026-07-02.md
git commit -m "docs: add concilium public-readiness privacy audit"
```

Expected:

```text
Commit contains only the audit report unless Task 1 discovered and fixed launch-blocking stale wording.
```

## Task 2: Reconcile Public Positioning In Existing Docs

**Files:**
- Modify: `docs/loop-engine/agent-moa-positioning.md`
- Modify: `docs/loop-engine/phase4-closeout-2026-06-29.md`
- Optionally modify: `docs/loop-engine/concilium-menu-bar-contract.md`

- [ ] **Step 1: Add supersession note to `agent-moa-positioning.md`**

Add this note near the top, below the title:

```markdown
> Current status note (2026-07-02): the earlier "private working prototype" language is superseded for the Phase 4 open-source tool preview. Concilium may be published as a developer tool with CLI/local-service boundaries, but it should not be described as a finished product until Phase 5 front-end work is complete.
```

Expected:

```text
The historical section remains available, but no reader can mistake it for the current release status.
```

- [ ] **Step 2: Add public-status note to Phase 4 closeout**

Add this note under the conclusion in `docs/loop-engine/phase4-closeout-2026-06-29.md`:

```markdown
Public release boundary: this closeout supports an open-source developer-tool preview of Concilium's backend control plane. It does not support calling Concilium a finished product; Phase 5 front-end work remains the product threshold.
```

- [ ] **Step 3: Verify no contradictory public-status language remains**

Run:

```bash
rg -n 'private working prototype|not ready to publish|finished product|developer tool|product threshold|Debug Console' docs/loop-engine README.md 2>/dev/null || true
```

Expected:

```text
Any "private working prototype" hit appears with the 2026-07-02 supersession note nearby.
Any "finished product" hit says Concilium is not one yet.
```

- [ ] **Step 4: Commit the positioning reconciliation**

Run:

```bash
git add docs/loop-engine/agent-moa-positioning.md docs/loop-engine/phase4-closeout-2026-06-29.md docs/loop-engine/concilium-menu-bar-contract.md
git commit -m "docs: clarify concilium tool preview boundary"
```

Expected:

```text
Commit includes only public positioning docs.
```

## Task 3: Create GitHub Community Profile Files

**Files:**
- Create: `LICENSE`
- Create: `CONTRIBUTING.md`
- Create: `CODE_OF_CONDUCT.md`
- Create: `SECURITY.md`
- Create: `.github/ISSUE_TEMPLATE/bug_report.md`
- Create: `.github/ISSUE_TEMPLATE/feature_request.md`
- Create: `.github/pull_request_template.md`

- [ ] **Step 1: Choose license before writing license text**

Default recommendation:

```text
Apache-2.0 for this developer tool preview, because it is permissive and includes an explicit patent grant.
```

Owner decision gate:

```text
Use Apache-2.0 unless the owner explicitly chooses MIT before implementation.
```

- [ ] **Step 2: Create contributor scope**

Create `CONTRIBUTING.md` with:

```markdown
# Contributing to Concilium

Concilium is currently an open-source developer tool preview. Phase 5 front-end work is not part of this release unless an issue explicitly says so.

## Good First Contributions

- Reproducible bug reports with sanitized command output.
- Documentation fixes that make the CLI/local-service setup clearer.
- Small tests around routing, Budget Guard, artifact gates, run summaries, and session retention.

## Before Opening a Pull Request

Run:

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
git diff --check
```

Do not commit `.roundtable/sessions/**`, provider credentials, private memory, local account details, or raw seat transcripts.
```

- [ ] **Step 3: Create security policy**

Create `SECURITY.md` with:

```markdown
# Security Policy

Concilium runs local agent CLIs and can create local run artifacts. Treat `.roundtable/sessions/**`, raw seat transcripts, provider logs, and token files as sensitive unless they have been deliberately redacted.

## Reporting

Please report vulnerabilities or accidental secret exposure through a private channel selected by the repository owner. Do not open a public issue containing live tokens, private session logs, provider account details, or user-specific memory.

## Supported Status

The current public release is a developer tool preview. Security fixes for the CLI/runtime, Budget Guard, artifact gates, local service, and documentation are in scope. Phase 5 front-end hardening begins after the product UI exists.
```

- [ ] **Step 4: Create issue and PR templates**

Create `.github/ISSUE_TEMPLATE/bug_report.md` with:

```markdown
---
name: Bug report
about: Report a reproducible Concilium tool issue
title: "[bug] "
labels: bug
---

## Summary

## Environment

- OS:
- Python:
- Concilium command:
- `./roundtable --version` output:

## Reproduction

```bash

```

## Expected Result

## Actual Result

## Sanitized Logs

Do not paste tokens, raw provider logs, private `.roundtable/sessions/**` content, or account details.
```

Create `.github/ISSUE_TEMPLATE/feature_request.md` with:

```markdown
---
name: Feature request
about: Suggest a Concilium tool improvement
title: "[feature] "
labels: enhancement
---

## Problem

## Proposed Tool Behavior

## Non-Goals

## Why This Belongs Before Or After Phase 5
```

Create `.github/pull_request_template.md` with:

```markdown
## Summary

## Scope

- [ ] CLI/runtime
- [ ] Local service/debug console
- [ ] Docs
- [ ] Tests
- [ ] Other:

## Verification

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
git diff --check
```

## Privacy Check

- [ ] No `.roundtable/sessions/**` content committed
- [ ] No tokens, credentials, private memory, or raw provider logs committed
- [ ] Public wording treats the current release as a tool preview, not a finished product
```

- [ ] **Step 5: Commit community files**

Run:

```bash
git add LICENSE CONTRIBUTING.md CODE_OF_CONDUCT.md SECURITY.md .github
git commit -m "docs: add open source community files"
```

Expected:

```text
GitHub community profile has the core files needed for a public repository.
```

## Task 4: Write The Public README And Quickstart

**Files:**
- Create: `README.md`

- [ ] **Step 1: Draft README with tool-preview status**

Create `README.md` with these required sections:

```markdown
# Concilium

Concilium is a local developer tool for agent-level MoA: it routes work across native agent CLIs, gates risky runs with budget/capacity checks, and records auditable run summaries.

> Status: developer tool preview. Phase 4 backend/control-plane work is complete; Phase 5 front-end work is the threshold for calling Concilium a product.

## Why Concilium Exists

## What It Does Today

## What It Is Not Yet

## Quickstart

## Architecture

## Safety Model

## Current Limitations

## Roadmap

## Contributing
```

- [ ] **Step 2: Add exact quickstart commands**

Before writing the clone command, resolve the public repository URL:

```bash
git remote get-url origin
```

Expected:

```text
The origin URL is the owner-approved public GitHub repository URL.
If origin is local, private, missing, or not the intended public repo, stop and ask the owner for the exact public URL before committing README.
```

The Quickstart must then include the exact owner-approved public URL and repository directory name. For example, if the approved URL is `https://github.com/acme/concilium.git`, use:

```bash
git clone https://github.com/acme/concilium.git
cd concilium
./roundtable --version
./roundtable --doctor
python3 skills/loop-engine/bin/concilium-run.py --repo "$PWD" --task "Preview a README review route without calling live seats." --test-cmd "true" --dry-run
./roundtable service --no-open
```

Do not publish README with placeholder clone commands or a private local path.

- [ ] **Step 3: Add honest limitations**

The README must explicitly say:

```text
Concilium depends on local native agent CLIs. Seat availability, provider models, and quota behavior vary by machine.
The browser surface is a Debug Console, not the Phase 5 product UI.
Phase 5 menu-bar/front-end setup is planned but not included in this release.
Commands that use `./roundtable --task ...` or `concilium-run.py --live` may consume real provider quota. The default README quickstart uses preview/dry-run commands first.
```

- [ ] **Step 4: Verify README claims against local evidence**

Run:

```bash
rg -n 'product|finished|menu-bar|Debug Console|developer tool|Phase 5|Budget Guard|run-summary' README.md docs/loop-engine docs/audits
```

Expected:

```text
README product wording matches the Phase 4/Phase 5 boundary.
Claims about Budget Guard, Debug Console, and run summaries have supporting docs in docs/loop-engine or docs/audits.
```

- [ ] **Step 5: Commit README**

Run:

```bash
git add README.md
git commit -m "docs: add concilium public readme"
```

## Task 5: Build The Launch Brief And Copy Bank

**Files:**
- Create: `docs/launch/open-source-tool-release-2026-07-02.md`

- [ ] **Step 1: Create launch brief**

Create `docs/launch/open-source-tool-release-2026-07-02.md` with:

```markdown
# Concilium Open-Source Tool Release Brief - 2026-07-02

## Conclusion

Release Concilium as an open-source developer tool preview, not as a product.

## Audience

- Developers experimenting with local coding agents.
- Agent-tooling builders who care about auditability and routing.
- People comparing native CLI orchestration with model-output-only MoA.

## Core Message

Concilium coordinates real native agent seats, gates execution with budget/capacity checks, and leaves machine-readable run evidence.

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
```

- [ ] **Step 2: Commit launch brief**

Run:

```bash
git add docs/launch/open-source-tool-release-2026-07-02.md
git commit -m "docs: add concilium open source launch brief"
```

## Task 6: Verify A Fresh-Clone Style Demo

**Files:**
- Modify only if needed: `README.md`, `docs/launch/open-source-tool-release-2026-07-02.md`

- [ ] **Step 1: Create a temporary local clone**

Run:

```bash
tmpdir="$(mktemp -d)"
git clone /Users/melee/Documents/agents "$tmpdir/concilium-preview"
cd "$tmpdir/concilium-preview"
```

Expected:

```text
Clone succeeds without relying on untracked local files.
```

- [ ] **Step 2: Run README quickstart commands that do not spend provider quota**

Run:

```bash
./roundtable --version
./roundtable --doctor
./roundtable service --no-open --port 8766 &
server_pid=$!
sleep 2
curl -s http://127.0.0.1:8766/api/status
kill "$server_pid"
```

Expected:

```text
version prints launcher info
doctor lists available seats or clear unavailable-seat diagnostics
service status returns JSON
```

- [ ] **Step 3: Run unit verification**

Run:

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
git diff --check
```

Expected:

```text
unittest exits 0
git diff --check prints no output
```

- [ ] **Step 4: Update docs if fresh-clone quickstart differs from README**

If any command differs, update `README.md` in the source repo with the observed working command. Do not edit docs to match an intended command that did not run.

## Task 7: Soft Launch

**Files:**
- Modify only from feedback: `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/launch/open-source-tool-release-2026-07-02.md`

- [ ] **Step 1: Make repository public or prepare the public remote**

Run the owner-approved GitHub operation outside this plan only after Tasks 0-6 pass. Do not publish if the privacy audit is blocked.

- [ ] **Step 2: Send the repo to 5-10 trusted technical reviewers**

Message:

```text
I am soft-launching Concilium as an open-source developer tool preview, not a finished product. Could you try the README quickstart and tell me where setup, positioning, or safety boundaries are unclear?
```

- [ ] **Step 3: Triage feedback into three buckets**

Use:

```text
Launch blocker: prevents clone, setup, privacy, or truthful positioning.
Docs fix: improves clarity without changing behavior.
Roadmap: real idea, but not needed for this tool-preview launch.
```

- [ ] **Step 4: Commit only launch blockers and docs fixes**

Run:

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
git diff --check
git add README.md CONTRIBUTING.md SECURITY.md docs/launch/open-source-tool-release-2026-07-02.md
git commit -m "docs: incorporate concilium soft launch feedback"
```

Expected:

```text
No feature creep enters the launch branch during soft launch.
```

## Task 8: Public Launch

**Files:**
- Read: `docs/launch/open-source-tool-release-2026-07-02.md`
- Read: `README.md`

- [ ] **Step 1: Publish GitHub repository metadata**

Set:

```text
Description: Local developer tool for agent-level MoA: native agent CLI routing, Budget Guard, artifact gates, and auditable run summaries.
Topics: agentic-ai, coding-agents, multi-agent, cli, local-first, developer-tools
Website: empty until a real public docs or demo page exists
```

- [ ] **Step 2: Publish short social post**

Use the copy bank short post from `docs/launch/open-source-tool-release-2026-07-02.md`. Include:

```text
repo link
one screenshot or terminal GIF if available
"tool preview, not product" boundary
```

- [ ] **Step 3: Publish technical article**

Article outline:

```text
1. The problem with role-play multi-agent demos
2. Agent-level MoA: native seats, not just model answers
3. Concilium's route -> guard -> execute -> summarize loop
4. Why Phase 4 is a tool release, not a product
5. What Phase 5 will add
6. How to try it
```

- [ ] **Step 4: Delay Show HN until quickstart is externally confirmed**

Gate:

```text
At least one trusted reviewer outside the development machine completes the README quickstart or gives a precise environment failure that README now documents.
```

Use title:

```text
Show HN: Concilium, a local control plane for native multi-agent coding workflows
```

- [ ] **Step 5: Do not launch Product Hunt in this plan**

Reason:

```text
Product Hunt is better aligned with the Phase 5 product/UI release. Do not use it for the Phase 4 tool preview because it would blur the tool/product boundary and risk poor conversion.
```

## Task 9: Post-Launch Feedback Loop

**Files:**
- Modify as needed: `README.md`, `docs/launch/open-source-tool-release-2026-07-02.md`, issue templates

- [ ] **Step 1: Review issues daily for the first 7 days**

Classify each issue:

```text
P0: privacy, secret exposure, destructive behavior, false public claim
P1: quickstart broken, install blocked, runtime crash on documented path
P2: docs confusion, unclear error, missing environment note
P3: roadmap or Phase 5 product idea
```

- [ ] **Step 2: Fix P0/P1 before adding features**

Verification before each fix merge:

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
git diff --check
```

- [ ] **Step 3: Update launch brief with observed reception**

Append:

```markdown
## Post-Launch Notes

| Date | Signal | Action |
|---|---|---|
| 2026-07-02 | No public signal yet | Start table when launch happens |
```

Replace the seed row with concrete public feedback after launch, or write `No action needed.` if there is no actionable signal.

## Task 10: Phase 5 Product Handoff

**Files:**
- Create or modify only after launch stabilization: `docs/superpowers/plans/<phase5-plan>.md`

- [ ] **Step 1: Convert tool-launch feedback into Phase 5 inputs**

Collect:

```text
top 5 setup confusions
top 5 status/progress display needs
top 5 safety/privacy questions
top 5 feature requests that require UI
```

- [ ] **Step 2: Preserve the product threshold**

Phase 5 may call Concilium a product only after it has:

```text
native or polished front end
setup/config-write UX
clear run history and status display
safe handling of sensitive run artifacts
documented onboarding path for non-repo authors
```

- [ ] **Step 3: Run a new native-seat plan review before Phase 5 implementation**

Use the same rule as Task 0:

```text
required seats: claude, hermes, kimi
final_verdict must be pass
retry_required does not count as approval
```

---

## Self-Review

Spec coverage:

- Tool-not-product positioning is covered in Release Definition, Public Positioning, Task 2, Task 4, Task 5, Task 8, and Task 10.
- Native-seat review before execution is covered in Task 0.
- Privacy/publication risk is covered in Task 1 and Task 9.
- GitHub open-source readiness is covered in Task 3 and Task 8.
- Launch copy and channel sequencing are covered in Task 5 and Task 8.
- Phase 5 product threshold is covered in Release Definition, Task 4, Task 5, Task 8, and Task 10.

Placeholder scan:

- No unresolved placeholder markers are intentionally present.
- Blank cells appear only inside a template that Task 1 explicitly requires the implementer to replace before commit.

Scope check:

- This plan does not implement the Phase 5 front end, native packaging, Product Hunt campaign, or paid promotion.
- This plan is one release-preparation effort, not a mixed implementation of product UI and marketing.

Execution gate:

- Do not begin Task 1 until Task 0 returns `final_verdict: pass` from native-seat review.
