# Security Policy

Concilium runs local agent CLIs and can create local run artifacts. Treat `.roundtable/sessions/**`, raw seat transcripts, provider logs, and token files as sensitive unless they have been deliberately redacted.

## Reporting

Please report vulnerabilities or accidental secret exposure through a private channel selected by the repository owner. Do not open a public issue containing live tokens, private session logs, provider account details, or user-specific memory.

## Supported Status

The current public release is a developer tool preview. Security fixes for the CLI/runtime, Budget Guard, artifact gates, local service, and documentation are in scope. Phase 5 front-end hardening begins after the product UI exists.
