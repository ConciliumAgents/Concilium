# Seat Field Profiles

> These profiles are based on limited local evidence. Treat them as current tendencies, not permanent model labels.
> Environment failures, such as a CLI being unreachable, are date- and machine-specific observations.
> The chair may merge these profiles into `KB/roster.md` during planning.

## claude (Anthropic)

- Observed strengths: high-context planning, synthesis, and review.
- Best role: chair, planner, final synthesis, and read-only reviewer.
- Watch out: large headless execution tasks can timeout; keep high-context core edits in the main chair conversation when needed.

## hermes (NousResearch)

- Observed strengths: fast execution, broad tool use, and provider flexibility.
- Best role: executor, environment checker, and heterogeneous reviewer.
- Watch out: subjective sufficiency reviews should be cross-checked on high-risk work.

## kimi (Moonshot)

- Observed strengths: strict boundary review, implementation, and independent reasoning.
- Best role: strict reviewer, core executor, and heterogeneous cross-checker.
- Watch out: long headless output can approach seat timeout budgets on large tasks.

## codex (OpenAI)

- Observed strengths: code review, issue finding, and focused implementation when reachable.
- Best role: additional code verifier.
- Watch out: if the local CLI or backend is unreachable, remove it from the active roster for that run.
