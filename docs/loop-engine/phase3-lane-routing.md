# Loop Engine Phase 3 Lane Routing

## Decision

Phase 3 should optimize routing before optimizing the roundtable internals.

The Phase 2 result shows the full roundtable can match single-agent quality on small scoped tasks, but it costs about 10x more wall time. That means the product should not send every task through the full loop. It should choose the cheapest lane that provides enough confidence for the task risk.

## Product Lanes

### Fast Lane

Fast Lane is single-agent execution.

Use it when the task is small, clear, low-risk, and easy to verify. The chosen agent thinks, edits, and verifies in one flow.

Product rule: this lane must not be hardcoded to Kimi. In the current local benchmark, Kimi is the strongest default single-agent baseline, but product configuration should expose this as `default_single_agent`.

First-run setup should ask:

- Which agent/model should handle simple tasks by default?
- Should that default be changed per project?
- Which verification command or evidence standard should Fast Lane run before completion?

### Review Lane

Review Lane is maker-checker without full roundtable planning.

One configured executor performs the task. A separate reviewer reads the diff, task goal, and verification evidence. If the reviewer passes, the task closes. If the reviewer blocks once, the executor gets one repair pass. If the reviewer blocks again, or if the reviewer finds an unclear requirement or architecture-level issue, the task escalates to Roundtable Lane.

Use it when the task is still bounded but a single agent may miss an important edge:

- small code change with user-visible behavior;
- documentation or policy wording where semantic accuracy matters;
- config, routing, or evaluation changes where tests may be too shallow;
- low-to-medium risk refactors with clear files and rollback boundaries.

Product configuration should expose this as:

- `default_review_executor`
- `default_review_reviewer`
- `review_repair_limit`

The reviewer must not be the same seat that executed the change.

### Roundtable Lane

Roundtable Lane is the full planner-executor-reviewer loop.

Use it for high-risk or ambiguous work where the extra planning and review cost can plausibly prevent expensive mistakes:

- architecture design;
- security review or security-sensitive fixes;
- cross-file or cross-project migrations;
- unclear product requirements;
- business or operational decisions with multiple failure modes;
- repeated Review Lane blocks.

This lane uses the existing conductor loop: planner assigns work, executor implements, independent reviewer verifies, and BLOCK feedback can drive another round.

### Audit Lane

Audit Lane is reviewer-only, read-only roundtable work.

Use it when the task is to inspect architecture, security, business state, memory boundaries, or a finished project without modifying the target system. This lane must not dispatch maker/executor seats. It should collect independent reviewer outputs, run explicit evidence commands, and close only when the required report artifact exists and the final workspace delta matches the allowed write paths.

Product configuration should expose this as:

- `audit.seats`
- `audit.default_reviewer`
- `audit.allowed_report_paths`

Bundled defaults use native heterogeneous reviewer seats:

- `audit.default_reviewer`: `claude`
- `audit.seats`: `claude`, `hermes`, `kimi`

`codex` remains a valid explicit seat, but it is not part of the bundled Audit Lane default. This prevents a host Codex session from accidentally presenting same-source Codex review as a heterogeneous Concilium audit.

Each seat event must identify its actual backend, not only its display seat name. A Codex-hosted subagent review is `codex_subagent`; a real `seat-*.sh` native CLI seat, including `seat-codex.sh`, is `external_cli`; a configured ordinary lane seat is `configured_seat`.

Current implementation status: the runtime now routes read-only audit tasks to Audit Lane, dispatches configured reviewer seats through the existing external `seat-*.sh` runner, exposes seat backend provenance, writes a combined audit report when `required_artifact_paths` is supplied, and enforces the report artifact gate. A Claude/Kimi/Hermes/Codex audit seat marked `external_cli` means the native CLI runner was invoked; a Codex-hosted internal review must be marked separately as `codex_subagent`.

### Legacy Roundtable Read-Only Audit Guard

Direct legacy `roundtable` / `conductor.py` invocations now apply the same first-principles boundary when the task is explicitly read-only audit or review work:

- no commander planning step;
- no `exec` subtasks;
- selected seats run in `review` mode only;
- `participants` is rewritten from the hardcoded initializer default to the actual seated reviewer list;
- strict artifact gate fails the run on any project delta outside explicit allowed paths.

The guard exists for backward compatibility. Concilium Audit Lane remains the preferred product entry point because it has structured routing, preflight, seat provenance, and report artifact semantics.

### Plan Review Lane

Plan Review Lane is reviewer-only review of an execution plan before implementation starts.

Use it when the work is to approve or block a plan, not to implement the plan. Each reviewer must either PASS or return a BLOCK with enough detail for the plan owner to patch the plan artifact. Reviewers must not modify files.

The host loop is:

1. run one `plan_review` reviewer round;
2. if any reviewer ERRs, retry or mark that reviewer unavailable before changing the plan;
3. if reviewers BLOCK and the round cap is not reached, the plan owner patches only the plan artifact;
4. re-run review until all available reviewers PASS or `plan_review.max_rounds` is reached.

Default `plan_review.max_rounds` is `3`. The runtime enforces that review rounds do not change the plan file or other project files, and the host-loop helper enforces that revision steps change only the reviewed plan artifact.

Bundled defaults use `claude`, `hermes`, and `kimi` for Plan Review Lane. As with Audit Lane, `codex` is explicit opt-in through config/API/CLI override, not the default. CLI callers can set native seats per run with:

```bash
python3 skills/loop-engine/bin/concilium-run.py --seats claude,hermes,kimi ...
```

Plan Review Lane is reviewer-only: selected seats must be called in `review` mode, and session metadata must reflect the actual seats that were seated and invoked.

## Routing Table

| Signal | Lane | Reason |
|---|---|---|
| Clear one-file or tiny doc/code edit | Fast Lane | Full roundtable latency is not justified. |
| Clear implementation but semantic/risk edge exists | Review Lane | Adds independent review without planner overhead. |
| Multiple plausible approaches or unclear success criteria | Roundtable Lane | Planning is part of the work. |
| Security, architecture, migration, or high-impact business decision | Roundtable Lane | The cost of a miss can exceed roundtable latency. |
| Read-only architecture/security/business/memory audit with a single allowed report | Audit Lane | Independent review is needed, but executor seats would violate the write boundary. |
| Execution-plan review or plan approval before implementation | Plan Review Lane | Reviewer-only BLOCK/PASS loop must converge before maker work starts. |
| Fast Lane fails verification | Review Lane | A second seat can diagnose before full escalation. |
| Review Lane blocks twice | Roundtable Lane | The task likely needs structured decomposition. |

## Setup/UI Requirements

The product should include an initialization step rather than assuming the local benchmark roster.

Configuration should resolve in this order:

1. Bundled defaults from `skills/loop-engine/config/concilium.defaults.json`.
2. User or machine defaults from `~/.config/concilium/config.json`.
3. Project overrides from `<repo>/.concilium.json`.

Project overrides have the highest priority so a repository can intentionally differ from the user's normal Concilium defaults.

Minimum setup questions:

1. Default simple-task agent/model (`default_single_agent`).
2. Default review executor and reviewer.
3. Roundtable seats and preferred planner/reviewer.
4. Audit seats and allowed report paths.
5. Project risk tolerance: speed-first, balanced, or review-first.
6. Required verification commands or evidence types.

The UI should make lane choice visible before execution and let users override it per task.

## Session And Scratch Privacy Contract

`roundtable.json.participants` means actual native seats for the current session, after availability filtering. It must not include host-side planning helpers, unavailable seats, or seats that were merely hardcoded by `roundtable-init.sh`.

Seat transcripts under `.roundtable/sessions/<sid>/minutes/` are redacted by default before publication. Credential-like strings are filtered through the shared Concilium redactor. Raw transcripts are only retained when `LOOP_KEEP_RAW_MINUTES=1` is explicitly set for local debugging.

## Implemented Router Contract

The Phase 3 router is a pure decision layer. It receives task signals and effective config, then returns a selected lane, required seats, and a human-readable reason. It does not start agents, probe providers, or mutate files.

Current rules:

- Fast Lane: low risk, one file or smaller, clear task, not security-sensitive.
- Review Lane: bounded medium-risk tasks, especially config, routing, or evaluation changes.
- Audit Lane: read-only audit/review tasks with explicit write boundaries.
- Plan Review Lane: explicit execution-plan review tasks, before generic audit/review/roundtable routing.
- Roundtable Lane: ambiguous, security-sensitive, architecture, migration, high-impact, or four-or-more-file tasks when execution or repair may be needed.

Preflight is applied after routing. A blocked required seat must surface as a blocked decision for the selected lane; the router must not silently change Review Lane to Fast Lane to work around a missing reviewer.

## Smoke Matrix

`skills/loop-engine/bin/smoke-concilium-phase3.sh` verifies the routed dry-run path against three representative prompts:

- clear one-file typo fix -> Fast Lane;
- bounded config/routing change -> Review Lane;
- security-sensitive migration across modules -> Roundtable Lane.

## Measurement Requirements

Every Roundtable Lane run should record per-seat timing so future optimization decisions are based on direct evidence, not file timestamp inference.

Required fields per seat call:

- iteration;
- seat;
- mode;
- backend type;
- provider and model when available;
- return code;
- duration in seconds.

Reports should surface this timing next to the minute index so the user can see where latency is spent.

Audit Lane also requires an artifact gate. The run is not complete unless every `required_artifact_paths` entry exists, each required path is non-empty and newly written or changed after the run baseline, each required path matches the allowed write patterns, and every post-baseline git delta path matches the allowed write patterns. This prevents a run from being marked complete when the reviewers produced useful private session logs, failed to create the user-visible report, reused a stale report, or changed files outside the read-only audit boundary.

## Current Phase 3 Hypothesis

For small tasks, Fast Lane should remain the default.

Review Lane is the main product gap to validate next: it may capture much of the quality benefit of independent review while avoiding the full planner cost.

Roundtable Lane should be reserved for tasks where planning, adversarial review, and multi-round convergence are themselves part of the value.

## Execution Order

The first Phase 3 implementation slice should validate Review Lane before adding capacity detection, router automation, or broad product renaming.

That order follows the Phase 2 evidence: the full roundtable is reliable but expensive, so the highest-value hypothesis is whether executor-plus-reviewer can preserve quality at lower latency. Capacity detection and preflight remain important, but they should start with a small provider-signal spike after Review Lane is measurable.
