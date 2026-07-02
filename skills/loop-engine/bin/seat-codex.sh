#!/usr/bin/env bash
# seat-codex.sh - Run Codex as a native Concilium seat.
# Usage: seat-codex.sh <repo> review|exec ["<brief>"]
#   review: run codex exec review and return VERDICT.
#   exec  : run codex exec to implement a subtask in the repository.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "${SCRIPT_DIR}/_lib.sh"
loop_need codex

REPO="$(loop_resolve_repo "${1:-}")"
MODE="${2:-review}"
BRIEF="${3:-}"
TABLE="$(loop_table_dir "${REPO}")"
ITER="$(loop_iter "${REPO}")"
PRE="$(loop_seat_preamble "${REPO}")"

CODEX_OPTS=()
[ -n "${LOOP_CODEX_EFFORT:-}" ] && CODEX_OPTS+=(-c "model_reasoning_effort=${LOOP_CODEX_EFFORT}")
[ -n "${LOOP_SEAT_MODEL:-}" ] && CODEX_OPTS+=(-m "${LOOP_SEAT_MODEL}")

case "${MODE}" in
  review)
    OUT="${TABLE}/minutes/iter-${ITER}-codex-review.md"
    INSTR="${PRE}

Your role: independent code reviewer for Concilium. Review the current uncommitted changes using git diff and KB/diff.patch. Check correctness, safety, acceptance criteria coverage from KB/task.md, and regressions.
Label each finding by severity: [CRITICAL], [HIGH], [MEDIUM], or [LOW], and include file and line references when possible.
${BRIEF:+Additional focus: ${BRIEF}}

End with one standalone line containing only the verdict:
- If there are no HIGH or CRITICAL issues: VERDICT: PASS
- Otherwise: VERDICT: BLOCK"
    loop_log "codex reviewer seat starting iter=${ITER}; running codex exec review"
    RAW="${OUT}.tmp"
    set +e
    ( cd "${REPO}" && codex exec review ${CODEX_OPTS[@]+"${CODEX_OPTS[@]}"} "${INSTR}" ) >"${RAW}" 2>&1
    rc=$?
    set -e
    loop_publish_minutes "${RAW}" "${OUT}"
    rm -f "${RAW}"
    cat "${OUT}"
    loop_log "codex exit code=${rc}; minutes: ${OUT}"
    if [ "${rc}" -ne 0 ]; then
      loop_warn "codex process exited non-zero rc=${rc}; treating as ERR"
      exit 1
    fi
    loop_codex_verdict "${OUT}"; exit $?
    ;;
  exec)
    [ -n "${BRIEF}" ] || loop_die "exec mode requires a third argument: subtask brief"
    OUT="${TABLE}/minutes/iter-${ITER}-codex-exec.md"
    INSTR="${PRE}

Your role: executor. Complete the subtask below and modify the repository directly with clean code that matches the existing style.
Subtask: ${BRIEF}

At the end of the minutes, add a section exactly like this:
## Lessons
### General
- General collaboration or process lessons worth archiving, one per line; otherwise write \"None.\"
### <project>
- Project-specific lessons; otherwise write \"None.\"
"
    loop_log "codex executor seat starting iter=${ITER}; running codex exec"
    RAW="${OUT}.tmp"
    set +e
    ( cd "${REPO}" && codex exec -s workspace-write ${CODEX_OPTS[@]+"${CODEX_OPTS[@]}"} "${INSTR}" ) >"${RAW}" 2>&1
    rc=$?
    set -e
    loop_publish_minutes "${RAW}" "${OUT}"
    rm -f "${RAW}"
    cat "${OUT}"
    loop_log "codex exit code=${rc}; minutes: ${OUT}"
    exit "${rc}"
    ;;
  *)
    loop_die "unknown MODE: ${MODE} (expected review|exec)"
    ;;
esac
