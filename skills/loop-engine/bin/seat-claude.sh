#!/usr/bin/env bash
# seat-claude.sh - Run Claude Code as a native Concilium seat.
# Usage: seat-claude.sh <repo> plan|exec|review "<brief>"
#   plan  : project commander; reads KB + roster and emits a JSON assignment plan.
#   exec  : executor; implements a subtask with acceptEdits enabled.
#   review: reviewer; read-only review and final VERDICT.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "${SCRIPT_DIR}/_lib.sh"
loop_need claude

REPO="$(loop_resolve_repo "${1:-}")"
MODE="${2:-exec}"
BRIEF="${3:-}"
TABLE="$(loop_table_dir "${REPO}")"
ITER="$(loop_iter "${REPO}")"
PRE="$(loop_seat_preamble "${REPO}")"

CL_OPTS=(--add-dir "${REPO}")
CL_MODEL="${LOOP_SEAT_MODEL:-${LOOP_CLAUDE_MODEL:-}}"
[ -n "${CL_MODEL}" ] && CL_OPTS+=(--model "${CL_MODEL}")

# LOOP_ADD_DIRS is allowed only for read-only plan/review mode. acceptEdits plus
# --add-dir can write outside the repository, so exec never receives extra dirs.
RO_DIRS=()
if [ -n "${LOOP_ADD_DIRS:-}" ]; then
  for _d in ${LOOP_ADD_DIRS}; do
    [ -e "${_d}" ] && RO_DIRS+=(--add-dir "${_d}")
  done
fi

case "${MODE}" in
  plan)
    OUT="${TABLE}/minutes/iter-${ITER}-claude-plan.md"
    INSTR="${PRE}

Your role: project commander. Read KB/task.md, KB/project.md, KB/roster.md, and the repository. Break the task into implementation subtasks and assign them according to each agent's strengths and operational profile.
Available seats: claude, codex, hermes, kimi.
Principle: prefer hermes and kimi for execution because they are faster executor seats. Claude and Codex should plan or review only; do not assign implementation work to them.
${BRIEF:+Additional context: ${BRIEF}}

Output requirements: briefly summarize the plan, then end with exactly one fenced json block shaped like:
```json
[{\"agent\":\"hermes\",\"subtask\":\"...\"},{\"agent\":\"kimi\",\"subtask\":\"...\"}]
```
Only put the assignment plan in that JSON block. The agent field must be one of claude, codex, hermes, or kimi. Assign implementation subtasks only to hermes or kimi."
    loop_log "claude commander seat starting iter=${ITER} (plan, read-only)"
    RAW="${OUT}.tmp"
    set +e
    ( cd "${REPO}" && claude -p "${INSTR}" "${CL_OPTS[@]}" ${RO_DIRS[@]+"${RO_DIRS[@]}"} --permission-mode plan ) >"${RAW}" 2>&1
    rc=$?
    set -e
    loop_publish_minutes "${RAW}" "${OUT}"
    rm -f "${RAW}"
    cat "${OUT}"
    loop_log "claude exit code=${rc}; minutes: ${OUT}"
    exit "${rc}"
    ;;
  exec)
    [ -n "${BRIEF}" ] || loop_die "exec mode requires a third argument: subtask brief"
    OUT="${TABLE}/minutes/iter-${ITER}-claude-exec.md"
    INSTR="${PRE}

Your role: executor. Complete the subtask below and modify the repository directly. Keep the implementation clean and consistent with the existing style.
After finishing, summarize what you changed in KB/state.md. Do not perform deletion, irreversible, external, or paid actions; leave those to the operator.
Subtask: ${BRIEF}

At the end of the minutes, add a section exactly like this:
## Lessons
### General
- General collaboration or process lessons worth archiving, one per line; otherwise write \"None.\"
### <project>
- Project-specific lessons; otherwise write \"None.\"
"
    loop_log "claude executor seat starting iter=${ITER} (exec, acceptEdits)"
    RAW="${OUT}.tmp"
    set +e
    ( cd "${REPO}" && claude -p "${INSTR}" "${CL_OPTS[@]}" --permission-mode acceptEdits ) >"${RAW}" 2>&1
    rc=$?
    set -e
    loop_publish_minutes "${RAW}" "${OUT}"
    rm -f "${RAW}"
    cat "${OUT}"
    loop_log "claude exit code=${rc}; minutes: ${OUT}"
    exit "${rc}"
    ;;
  review)
    OUT="${TABLE}/minutes/iter-${ITER}-claude-review.md"
    INSTR="${PRE}

Your role: reviewer. Read-only: do not modify files and do not run commands with side effects. Review the current uncommitted changes for correctness, safety, acceptance criteria coverage, and regressions.
Label findings by severity: [CRITICAL], [HIGH], [MEDIUM], or [LOW].
If the brief mentions seat failures or skipped subtasks, judge whether task completeness was harmed; do not mechanically BLOCK if other seats completed the task.
${BRIEF:+Additional focus: ${BRIEF}}
End with one standalone line: VERDICT: PASS if there are no HIGH or CRITICAL findings; otherwise VERDICT: BLOCK."
    loop_log "claude reviewer seat starting iter=${ITER} (review, read-only)"
    RAW="${OUT}.tmp"
    set +e
    ( cd "${REPO}" && claude -p "${INSTR}" "${CL_OPTS[@]}" ${RO_DIRS[@]+"${RO_DIRS[@]}"} --permission-mode plan ) >"${RAW}" 2>&1
    rc=$?
    set -e
    loop_publish_minutes "${RAW}" "${OUT}"
    rm -f "${RAW}"
    cat "${OUT}"
    loop_log "claude exit code=${rc}; minutes: ${OUT}"
    [ "${rc}" -eq 0 ] || { loop_warn "claude process exited non-zero rc=${rc}; treating as ERR"; exit 1; }
    loop_verdict_exit "${OUT}"; exit $?
    ;;
  *)
    loop_die "unknown MODE: ${MODE} (expected plan|exec|review)"
    ;;
esac
