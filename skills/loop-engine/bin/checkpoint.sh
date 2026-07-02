#!/usr/bin/env bash
# checkpoint.sh - End one iteration: append state.md, commit checkpoint, bump iteration
# Usage: checkpoint.sh <repo> "<iteration summary>"
# .roundtable/ is excluded via .git/info/exclude, so commits contain only real code changes.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

REPO="$(loop_resolve_repo "${1:-}")"
SUMMARY="${2:-iteration}"
TABLE="$(loop_table_dir "${REPO}")"
ITER="$(loop_iter "${REPO}")"

# Append to state.md, the live on-disk blackboard memory
printf '\n### iter %s - %s\n' "${ITER}" "${SUMMARY}" >> "${TABLE}/KB/state.md"

# Commit code checkpoint; .roundtable/ is excluded
set +e
git -C "${REPO}" add -A
if git -C "${REPO}" diff --cached --quiet; then
  loop_log "No code changes to commit iter=${ITER}"
else
  git -C "${REPO}" commit -q -m "loop-engine: iter ${ITER} - ${SUMMARY}"
  loop_log "Committed code checkpoint iter=${ITER}"
fi
set -e

# bump round
NEXT=$(( ITER + 1 ))
loop_state_set "${REPO}" iter "${NEXT}"
loop_log "Iteration complete; next iteration=${NEXT}"
