# CLAUDE.md

Claude-specific startup notes for Concilium.

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

## Claude Notes

- Treat repository files and command output as the source of truth for this project.
- Keep Claude-specific workflow preferences outside the shared startup block.
- Do not place private project memory or local-only operational notes in this public repository.
