#!/usr/bin/env bash
# seat-kimi.sh - Run Kimi Code as a native Concilium seat.
# Usage: seat-kimi.sh <repo> plan|exec|review "<brief>" [provider] [model]
#   plan  : commander; read KB + roster and emit a JSON assignment plan.
#   exec  : executor; implement a subtask with kimi -p.
#   review: reviewer; read-only review and final VERDICT.
# Verified Kimi behavior to preserve:
#   - kimi -p is mutually exclusive with --plan, -y, and --auto.
#   - kimi -p is non-interactive and can read/write with default permissions.
#   - read-only plan/review relies on prompt constraints, matching Hermes without --yolo.
#   - VERDICT lines may be indented; loop_verdict_exit tolerates leading whitespace.
#   - provider is ignored because Kimi exposes managed:kimi-code; model is honored via -m.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "${SCRIPT_DIR}/_lib.sh"
loop_need kimi

REPO="$(loop_resolve_repo "${1:-}")"
MODE="${2:-exec}"
BRIEF="${3:-}"
MODEL="${5:-${LOOP_SEAT_MODEL:-}}"
TABLE="$(loop_table_dir "${REPO}")"
ITER="$(loop_iter "${REPO}")"
PRE="$(loop_seat_preamble "${REPO}")"

KM_OPTS=()
[ -n "${MODEL}" ] && KM_OPTS+=(-m "${MODEL}")

# Concilium stores seat output in minutes, so Kimi-side sessions from this run
# are redundant. Kimi has no official delete command, so this removes only the
# session id created by this run under ~/.kimi-code/sessions/.
_km_clean() {
  [ -n "${LOOP_KIMI_KEEP_SESSION:-}" ] && return 0
  local out="${1:-}" sid
  [ -f "${out}" ] || return 0
  sid="$(grep -oiE 'session_[0-9a-f-]{30,}' "${out}" 2>/dev/null | tail -1 || true)"
  [ -n "${sid}" ] || return 0
  python3 - "${HOME}/.kimi-code/session_index.jsonl" "${sid}" "${HOME}/.kimi-code/sessions" <<'PY' || return 0
import json, os, sys, shutil
idx, sid, sroot = sys.argv[1], sys.argv[2], os.path.realpath(sys.argv[3])
if not os.path.exists(idx):
    sys.exit(0)
keep, removed = [], False
for line in open(idx, encoding="utf-8"):
    s = line.rstrip("\n")
    if not s.strip():
        continue
    try:
        d = json.loads(s)
    except Exception:
        keep.append(s); continue
    if d.get("sessionId") == sid:
        sd = os.path.realpath(d.get("sessionDir", ""))
        if sd.startswith(sroot + os.sep):
            if os.path.isdir(sd):
                shutil.rmtree(sd, ignore_errors=True)
            removed = True
        else:
            keep.append(s)
    else:
        keep.append(s)
if removed:
    with open(idx, "w", encoding="utf-8") as f:
        f.write("".join(l + "\n" for l in keep))
PY
  loop_log "cleaned leftover Kimi session ${sid}"
}

case "${MODE}" in
  plan)
    OUT="${TABLE}/minutes/iter-${ITER}-kimi-plan.md"
    INSTR="${PRE}

Your role: project commander. Read-only: inspect and plan only; do not modify files. Read KB/task.md, KB/project.md, KB/roster.md, and the repository. Break the task into implementation subtasks and assign them according to each agent's strengths and operational profile.
Available seats: claude, codex, hermes, kimi.
Principle: prefer hermes and kimi for execution because they are faster executor seats. Claude and Codex should plan or review only; do not assign implementation work to them.
${BRIEF:+Additional context: ${BRIEF}}

Output requirements: briefly summarize the plan, then end with exactly one fenced json block shaped like:
```json
[{\"agent\":\"hermes\",\"subtask\":\"...\"},{\"agent\":\"kimi\",\"subtask\":\"...\"}]
```
Only put the assignment plan in that JSON block. The agent field must be one of claude, codex, hermes, or kimi. Assign implementation subtasks only to hermes or kimi."
    loop_log "kimi commander seat starting iter=${ITER} (plan, read-only)"
    RAW="${OUT}.tmp"
    set +e
    ( cd "${REPO}" && kimi -p "${INSTR}" ${KM_OPTS[@]+"${KM_OPTS[@]}"} ) >"${RAW}" 2>&1
    rc=$?
    set -e
    loop_publish_minutes "${RAW}" "${OUT}"
    rm -f "${RAW}"
    cat "${OUT}"
    loop_log "kimi exit code=${rc}; minutes: ${OUT}"
    _km_clean "${OUT}"
    exit "${rc}"
    ;;
  exec)
    [ -n "${BRIEF}" ] || loop_die "exec mode requires a third argument: subtask brief"
    OUT="${TABLE}/minutes/iter-${ITER}-kimi-exec.md"
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
    loop_log "kimi executor seat starting iter=${ITER} (exec via kimi -p)"
    RAW="${OUT}.tmp"
    set +e
    ( cd "${REPO}" && kimi -p "${INSTR}" ${KM_OPTS[@]+"${KM_OPTS[@]}"} ) >"${RAW}" 2>&1
    rc=$?
    set -e
    loop_publish_minutes "${RAW}" "${OUT}"
    rm -f "${RAW}"
    cat "${OUT}"
    loop_log "kimi exit code=${rc}; minutes: ${OUT}"
    _km_clean "${OUT}"
    exit "${rc}"
    ;;
  review)
    OUT="${TABLE}/minutes/iter-${ITER}-kimi-review.md"
    INSTR="${PRE}

Your role: independent reviewer. Read-only: do not modify files and do not run commands with side effects. Review the current uncommitted changes for correctness, safety, acceptance criteria coverage, and regressions.
If the brief mentions seat failures or skipped subtasks, judge whether task completeness was harmed; do not mechanically BLOCK if other seats completed the task.
${BRIEF:+Additional focus: ${BRIEF}}
Label findings by severity: [CRITICAL], [HIGH], [MEDIUM], or [LOW].
End with one standalone line: VERDICT: PASS if there are no HIGH or CRITICAL findings; otherwise VERDICT: BLOCK."
    loop_log "kimi reviewer seat starting iter=${ITER} (review, read-only)"
    RAW="${OUT}.tmp"
    set +e
    ( cd "${REPO}" && kimi -p "${INSTR}" ${KM_OPTS[@]+"${KM_OPTS[@]}"} ) >"${RAW}" 2>&1
    rc=$?
    set -e
    loop_publish_minutes "${RAW}" "${OUT}"
    rm -f "${RAW}"
    cat "${OUT}"
    loop_log "kimi exit code=${rc}; minutes: ${OUT}"
    _km_clean "${OUT}"
    [ "${rc}" -ne 0 ] && { loop_warn "kimi process exited non-zero rc=${rc}; treating as ERR"; exit 1; }
    loop_verdict_exit "${OUT}"; exit $?
    ;;
  *)
    loop_die "unknown MODE: ${MODE} (expected plan|exec|review)"
    ;;
esac
