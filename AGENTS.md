# AGENTS.md

Guidance for agents working on Concilium.

<!-- SHARED-STARTUP:BEGIN -->
## Concilium Startup Contract

### Runtime Safety
1. Verify the active launcher with `roundtable --version` before relying on any run.
2. Treat the public repository as a sanitized release surface. Private memory, raw transcripts, provider logs, account details, local paths, and business/project context belong outside the public repository.
3. Public releases use the explicit `concilium` remote. Do not use `git push --all`, and do not mirror-push all internal branches or commits.
4. Local private context is opt-in through user-local config such as `~/.config/concilium/config.json`; project `.concilium.json` must not select private context paths or archive destinations.
5. Keep this `SHARED-STARTUP` block identical in `AGENTS.md` and `CLAUDE.md`. Put tool-specific guidance outside the block.

### Commands
- Check active runtime: `roundtable --version`
- Check seats: `roundtable --doctor`
- Run tests: `python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'`
<!-- SHARED-STARTUP:END -->

## Agent Notes

- Keep changes small, public-safe, and backed by local command evidence.
- Do not commit `.roundtable/sessions/**`, raw transcripts, provider logs, credentials, or private local memory.
- Use `docs/RELEASE.md` before publishing public changes.
