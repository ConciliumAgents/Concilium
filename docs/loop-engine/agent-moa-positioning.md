# Agent MoA Positioning

Loop Engine is an Agent-level Mixture of Agents system.

It does not only combine model outputs. It combines native agent shells: each seat keeps its own CLI, model routing, permissions, memory behavior, tool habits, timeout profile, and review style.

## Core Claim

Model-level MoA asks several models for answers and asks an aggregator to synthesize them.

Agent-level MoA coordinates complete working environments:

- `claude`: planning and synthesis when full context matters.
- `kimi`: fast execution and strict boundary review.
- `hermes`: fast execution and heterogeneous DeepSeek-family review.
- `codex`: code review when reachable in the local environment.

The shared blackboard `.roundtable/` is the source of truth. Seats pull context from the same KB, write minutes, and are coordinated by `conductor.py`.

## Current Product Boundary

This repo is a private working prototype. It is not ready to publish as a complete public product.

Public-facing work should first prove:

- repeatable seat contracts;
- eval results against single-agent baselines;
- readable reports for each session;
- clear separation between demo assets and private operational memory.

## Phase 1 Success Criteria

- A new worker can understand the architecture from docs without reading every historical session.
- Seat outputs can be checked offline.
- Eval tasks can run in dry mode without calling live models.
- A roundtable session can produce a compact report for human review.
