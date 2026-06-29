# Concilium Capacity Probe Notes

## Principle

Capacity probes are best-effort local signals. They can block only when the signal is fresh and explicit.

## CodexBar Reference

CodexBar is a reference for provider-specific quota shapes, reset windows, and privacy-first source reuse. Concilium Phase 3 does not depend on CodexBar.

The current local `codexbar --help` output exposes a `usage` command with text and JSON formats, provider filters, account selection, and provider-specific source choices such as web, CLI, OAuth, and API. Concilium should treat that as an optional future adapter surface, not a required runtime dependency.

## Local Commands Checked

| Tool | Installed | Useful quota command | Notes |
|---|---:|---|---|
| codexbar | yes | `codexbar usage --format json --provider <provider>` | Help output advertises machine-readable usage and provider/source selection. Not used as a Phase 3 dependency. |
| claude | yes | none observed in Claude CLI help | Version observed. CLI help exposes auth and doctor commands, but no direct quota percentage command. |
| hermes | yes | none observed | `hermes status` shows provider/model and configured key presence, but not remaining quota. Credential fragments were not saved. |
| kimi | yes | none observed in Kimi CLI help | Version observed. CLI help exposes provider/login/doctor commands, but no direct quota percentage command. |
| codex | yes | none observed in Codex CLI help | Version observed. CLI help exposes doctor/login/review/exec commands, but no direct quota percentage command. |

## Initial Adapter Decision

- `roster`: always available, no quota percentage, can mark unavailable if CLI missing.
- `codexbar`: optional future source if local CLI exposes machine-readable usage for a configured provider.
- `provider_api`: not implemented until official endpoint and credential source are verified.
