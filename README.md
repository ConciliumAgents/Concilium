# Concilium

English | [zh-CN](README.zh-CN.md)

Run real local AI agents as an auditable roundtable.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Concilium is a local developer tool for coordinating multiple agent CLIs. It does not ask one model to imitate a team. It routes work to actual local seats such as Claude Code, Codex CLI, Hermes Agent, or Kimi Code when they are installed, then records what was requested, which lane ran, which seats participated, what checks ran, and how the run settled.

[Quickstart](#quickstart) | [Core Concepts](#core-concepts) | [Safety](#safety-and-privacy) | [From Source](#from-source) | [Contributing](#contributing)

## Why

Single-agent workflows are fast, but they can be hard to trust on larger changes:

- The agent may act without making its assumptions visible.
- Review and execution often blur together.
- A failure can look like a completed answer if the final message is polished.
- Multi-agent demos often merge opinions without proving which agents actually ran.

Concilium treats agent work as an operation that needs routing, capacity checks, execution boundaries, and evidence. The goal is simple: before you trust the result, you should be able to see how it was produced.

## Highlights

- Detects locally available agent seats.
- Routes work through lanes such as fast execution, review, audit, plan review, and roundtable review.
- Runs a Budget Guard before live execution so missing quota, unknown capacity, or risky seat selection is visible.
- Starts a local service/API for tools that want to inspect status or run history.
- Writes machine-readable run summaries for completed runs.
- Keeps sensitive run artifacts local by default.

## How It Works

```text
task
  -> route selection
  -> seat and capacity check
  -> lane execution
  -> tests or review gates
  -> run-summary.json
```

The top-level `roundtable` launcher is the main CLI entrypoint. Most runtime code lives under `skills/loop-engine/bin`. The `loop-engine` path is a historical name for the Concilium runtime and is kept during the tool preview to avoid breaking scripts, tests, and local workflows. The local service can be started with `roundtable service` when you want API access or the current debug console.

## Quickstart

Prerequisites:

- Python 3.11 or newer.
- `git` and `ripgrep`.
- At least one supported local agent CLI if you want live runs.

```bash
git clone https://github.com/ConciliumAgents/Concilium.git
cd Concilium

./roundtable --version
./roundtable --doctor

python3 skills/loop-engine/bin/concilium-run.py \
  --repo "$PWD" \
  --task "Preview a README review route without calling live seats." \
  --test-cmd "true" \
  --dry-run

./roundtable service --no-open
```

The quickstart uses dry-run commands first. Commands that run live seats may consume provider quota or depend on your local agent subscriptions.

## CLI Quick Reference

```bash
./roundtable --version          # Show launcher, repository, branch, and commit.
./roundtable --doctor           # Detect available local seats.
./roundtable --task "..."       # Run a routed Concilium task.
./roundtable service --no-open  # Start the local service/API without opening a browser.
```

## Core Concepts

**Seat**

A local agent CLI that Concilium can call, such as Claude Code, Codex CLI, Hermes Agent, or Kimi Code. Seat availability depends on your machine.

**Lane**

An execution mode with a specific intent, such as fast implementation, review, audit, or roundtable-style consensus.

**Budget Guard**

A preflight check that makes seat availability and capacity risk visible before live execution.

**Run Summary**

A machine-readable record of the run result. For completed runs, `run-summary.json` is the settled status source.

**Local Service**

A localhost API/debug surface for inspecting status and running local workflows. It is not a hosted service.

## Docs By Goal

| Goal | Start Here |
|---|---|
| Understand the project | `README.md` |
| Understand agent-level MoA | `docs/loop-engine/agent-moa-positioning.md` |
| Learn seat input/output rules | `docs/loop-engine/seat-contract.md` |
| Publish or update the public repository | `docs/RELEASE.md` |
| Report a security issue | `SECURITY.md` |
| Contribute a patch | `CONTRIBUTING.md` |

## Supported Agents

Concilium is designed around native local CLIs. The exact roster depends on what is installed and authenticated on your machine.

Run:

```bash
./roundtable --doctor
```

to see which seats Concilium can currently use.

## Safety And Privacy

Concilium treats run evidence as local and sensitive by default.

- `.roundtable/sessions/**` can contain task context, local paths, test output, and seat transcripts.
- Do not publish raw provider logs, credentials, private memory, or unsanitized run artifacts.
- Prefer dry-run or review-only workflows before live execution on a new machine.
- Review generated artifacts before sharing them in public issues, pull requests, or demos.

## Project Status

Concilium is usable as a developer preview for local CLI and service workflows. It is intentionally not presented as a hosted platform or polished end-user app.

The current focus is reliability, clear execution boundaries, reproducible local setup, and public examples that are safe to run.

## From Source

Run the test suite:

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
git diff --check
```

## Contributing

Bug reports, documentation fixes, reproducible setup notes, and small runtime patches are welcome. See `CONTRIBUTING.md` before opening a pull request.

For security-sensitive issues or accidental secret exposure, follow `SECURITY.md` and do not open a public issue containing private logs or credentials.

## Community

- Open an issue for reproducible bugs or documentation gaps.
- Keep setup/support questions sanitized: no raw transcripts, provider tokens, local account data, or private memory.
- Pull requests should include the command output or evidence used to verify the change.

## License

MIT
