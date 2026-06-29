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

## Routing Table

| Signal | Lane | Reason |
|---|---|---|
| Clear one-file or tiny doc/code edit | Fast Lane | Full roundtable latency is not justified. |
| Clear implementation but semantic/risk edge exists | Review Lane | Adds independent review without planner overhead. |
| Multiple plausible approaches or unclear success criteria | Roundtable Lane | Planning is part of the work. |
| Security, architecture, migration, or high-impact business decision | Roundtable Lane | The cost of a miss can exceed roundtable latency. |
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
4. Project risk tolerance: speed-first, balanced, or review-first.
5. Required verification commands or evidence types.

The UI should make lane choice visible before execution and let users override it per task.

## Measurement Requirements

Every Roundtable Lane run should record per-seat timing so future optimization decisions are based on direct evidence, not file timestamp inference.

Required fields per seat call:

- iteration;
- seat;
- mode;
- return code;
- duration in seconds.

Reports should surface this timing next to the minute index so the user can see where latency is spent.

## Current Phase 3 Hypothesis

For small tasks, Fast Lane should remain the default.

Review Lane is the main product gap to validate next: it may capture much of the quality benefit of independent review while avoiding the full planner cost.

Roundtable Lane should be reserved for tasks where planning, adversarial review, and multi-round convergence are themselves part of the value.

## Execution Order

The first Phase 3 implementation slice should validate Review Lane before adding capacity detection, router automation, or broad product renaming.

That order follows the Phase 2 evidence: the full roundtable is reliable but expensive, so the highest-value hypothesis is whether executor-plus-reviewer can preserve quality at lower latency. Capacity detection and preflight remain important, but they should start with a small provider-signal spike after Review Lane is measurable.
