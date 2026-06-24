#!/usr/bin/env bash
# seat-hermes.sh — 请 hermes（工具广度；可切 DeepSeek 异质血统）入席圆桌
# 用法: seat-hermes.sh <repo> exec|review "<brief>" [provider] [model]
#   exec  : hermes -z ... --yolo，让它在仓库里干工具/环境活
#   review: hermes -z ...（不加 --yolo，只读评审），出 VERDICT；可指定 provider/model 做异质复审
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

# 组装 provider/model 覆盖参数
EXTRA=()
[ -n "${PROV}" ]  && EXTRA+=(--provider "${PROV}")
[ -n "${MODEL}" ] && EXTRA+=(-m "${MODEL}")

case "${MODE}" in
  review)
    [ -n "${BRIEF}" ] || BRIEF="审查本轮改动的正确性与潜在风险。"
    OUT="${TABLE}/minutes/iter-${ITER}-hermes-review${PROV:+-${PROV}}.md"
    INSTR="${PRE}

你的角色：**第二评审席**（独立复审）。**只读、不要修改任何文件、不要运行有副作用的命令。**
请就本轮改动给出独立意见：${BRIEF}
按严重度标注发现：[CRITICAL]/[HIGH]/[MEDIUM]/[LOW]。

**最后必须单独成行输出**：
- 若无 HIGH 或 CRITICAL 级问题 → VERDICT: PASS
- 否则 → VERDICT: BLOCK"
    loop_log "hermes 评审席入席 iter=${ITER} provider=${PROV:-默认}，只读评审"
    set +e
    ( cd "${REPO}" && hermes ${EXTRA[@]+"${EXTRA[@]}"} -z "${INSTR}" ) >"${OUT}" 2>&1
    rc=$?
    set -e
    cat "${OUT}"
    loop_log "hermes 退出码=${rc}，纪要: ${OUT}"
    if [ "${rc}" -ne 0 ]; then
      loop_warn "hermes 进程非零退出 rc=${rc}，判 ERR（多半是用法/网络问题，请人工读 minutes）"
      exit 1
    fi
    loop_verdict_exit "${OUT}"; exit $?
    ;;
  exec)
    [ -n "${BRIEF}" ] || loop_die "exec 模式需要第三个参数：任务 brief"
    OUT="${TABLE}/minutes/iter-${ITER}-hermes-exec.md"
    INSTR="${PRE}

你的角色：**执行席**（工具/环境活）。请完成下述任务：
${BRIEF}"
    loop_log "hermes 执行席入席 iter=${ITER}，hermes -z --yolo"
    set +e
    ( cd "${REPO}" && hermes ${EXTRA[@]+"${EXTRA[@]}"} -z "${INSTR}" --yolo ) >"${OUT}" 2>&1
    rc=$?
    set -e
    cat "${OUT}"
    loop_log "hermes 退出码=${rc}，纪要: ${OUT}"
    exit "${rc}"
    ;;
  *)
    loop_die "未知 MODE: ${MODE}（应为 exec|review）"
    ;;
esac
