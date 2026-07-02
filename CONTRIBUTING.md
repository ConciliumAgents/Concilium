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
