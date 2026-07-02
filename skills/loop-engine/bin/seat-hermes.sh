#!/usr/bin/env bash
# seat-hermes.sh - Run Hermes as a native Concilium seat.
# Usage: seat-hermes.sh <repo> exec|review "<brief>" [provider] [model]
#   exec  : hermes -z ... --yolo for tooling and environment work.
#   review: hermes -z ... without --yolo for read-only review.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "${SCRIPT_DIR}/_lib.sh"
loop_need hermes

REPO="$(loop_resolve_repo "${1:-}")"
MODE="${2:-exec}"
BRIEF="${3:-}"
PROV="${4:-${LOOP_SEAT_PROVIDER:-}}"
MODEL="${5:-${LOOP_SEAT_MODEL:-}}"
TABLE="$(loop_table_dir "${REPO}")"
ITER="$(loop_iter "${REPO}")"
PRE="$(loop_seat_preamble "${REPO}")"

EXTRA=()
[ -n "${PROV}" ]  && EXTRA+=(--provider "${PROV}")
[ -n "${MODEL}" ] && EXTRA+=(-m "${MODEL}")

# Concilium stores seat output in minutes, so Hermes-side sessions from this
# run are redundant. Delete only the new session created by this invocation.
_hs_id() { hermes sessions list --limit 1 2>/dev/null | grep -oE '[0-9]{8}_[0-9]{6}_[0-9a-fA-F]+' | head -1 || true; }
_hs_clean() {
  [ -n "${LOOP_HERMES_KEEP_SESSION:-}" ] && return 0
  local post; post="$(_hs_id)"
  if [ -n "${post}" ] && [ "${post}" != "${1:-}" ]; then
    hermes sessions delete "${post}" --yes >/dev/null 2>&1 && loop_log "cleaned leftover Hermes session ${post}"
  fi
}
HS_PRE="$(_hs_id)"

case "${MODE}" in
  review)
    [ -n "${BRIEF}" ] || BRIEF="Review the current diff for correctness and potential risk."
    OUT="${TABLE}/minutes/iter-${ITER}-hermes-review${PROV:+-${PROV}}.md"
    INSTR="${PRE}

Your role: independent reviewer. Read-only: do not modify files and do not run commands with side effects.
Give an independent review of the current diff: ${BRIEF}
If prior context mentions seat failures or skipped subtasks, judge whether task completeness was harmed; do not mechanically BLOCK if other seats completed the task.
Label findings by severity: [CRITICAL], [HIGH], [MEDIUM], or [LOW].

End with one standalone line:
- If there are no HIGH or CRITICAL issues: VERDICT: PASS
- Otherwise: VERDICT: BLOCK"
    loop_log "hermes reviewer seat starting iter=${ITER} provider=${PROV:-default} (read-only)"
    RAW="${OUT}.tmp"
    set +e
    ( cd "${REPO}" && hermes ${EXTRA[@]+"${EXTRA[@]}"} -z "${INSTR}" ) >"${RAW}" 2>&1
    rc=$?
    set -e
    loop_publish_minutes "${RAW}" "${OUT}"
    rm -f "${RAW}"
    cat "${OUT}"
    loop_log "hermes exit code=${rc}; minutes: ${OUT}"
    _hs_clean "${HS_PRE}"
    if [ "${rc}" -ne 0 ]; then
      loop_warn "hermes process exited non-zero rc=${rc}; treating as ERR"
      exit 1
    fi
    loop_verdict_exit "${OUT}"; exit $?
    ;;
  exec)
    [ -n "${BRIEF}" ] || loop_die "exec mode requires a third argument: task brief"
    OUT="${TABLE}/minutes/iter-${ITER}-hermes-exec.md"
    INSTR="${PRE}

Your role: executor for tooling and environment work. Complete the task below:
${BRIEF}

At the end of the minutes, add a section exactly like this:
## Lessons
### General
- General collaboration or process lessons worth archiving, one per line; otherwise write \"None.\"
### <project>
- Project-specific lessons; otherwise write \"None.\"
"
    loop_log "hermes executor seat starting iter=${ITER}; running hermes -z --yolo"
    RAW="${OUT}.tmp"
    set +e
    ( cd "${REPO}" && hermes ${EXTRA[@]+"${EXTRA[@]}"} -z "${INSTR}" --yolo ) >"${RAW}" 2>&1
    rc=$?
    set -e
    loop_publish_minutes "${RAW}" "${OUT}"
    rm -f "${RAW}"
    cat "${OUT}"
    loop_log "hermes exit code=${rc}; minutes: ${OUT}"
    _hs_clean "${HS_PRE}"
    exit "${rc}"
    ;;
  *)
    loop_die "unknown MODE: ${MODE} (expected exec|review)"
    ;;
esac
