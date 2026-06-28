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

# 清理 hermes 会话残留：圆桌的产出已存进黑板 minutes，hermes 侧那条会话是冗余「垃圾」。
# 调用前记最新会话 id，调用后删掉新冒出来的那条（精准，只删本次新建，绝不碰你的真会话）。
# 设 LOOP_HERMES_KEEP_SESSION 非空可保留。
_hs_id() { hermes sessions list --limit 1 2>/dev/null | grep -oE '[0-9]{8}_[0-9]{6}_[0-9a-fA-F]+' | head -1 || true; }
_hs_clean() {
  [ -n "${LOOP_HERMES_KEEP_SESSION:-}" ] && return 0
  local post; post="$(_hs_id)"
  if [ -n "${post}" ] && [ "${post}" != "${1:-}" ]; then
    hermes sessions delete "${post}" --yes >/dev/null 2>&1 && loop_log "已清理 hermes 残留会话 ${post}"
  fi
}
HS_PRE="$(_hs_id)"

case "${MODE}" in
  review)
    [ -n "${BRIEF}" ] || BRIEF="审查本轮改动的正确性与潜在风险。"
    OUT="${TABLE}/minutes/iter-${ITER}-hermes-review${PROV:+-${PROV}}.md"
    INSTR="${PRE}

你的角色：**第二评审席**（独立复审）。**只读、不要修改任何文件、不要运行有副作用的命令。**
请就本轮改动给出独立意见：${BRIEF}
若上文标明有座位失败/子任务未执行，请据**任务完整性是否受损**裁决：任务已由其余座位完成则不应因个别失败机械 BLOCK。
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
    _hs_clean "${HS_PRE}"
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
${BRIEF}

**完成后请在纪要末尾另起一节，写入：**
## 教训
### 通用
- （本次值得归档的通用协作/流程教训，一条一行；无则写\"（无）\"）
### <项目名>
- （本次项目专属教训；无则写\"（无）\"）
"
    loop_log "hermes 执行席入席 iter=${ITER}，hermes -z --yolo"
    set +e
    ( cd "${REPO}" && hermes ${EXTRA[@]+"${EXTRA[@]}"} -z "${INSTR}" --yolo ) >"${OUT}" 2>&1
    rc=$?
    set -e
    cat "${OUT}"
    loop_log "hermes 退出码=${rc}，纪要: ${OUT}"
    _hs_clean "${HS_PRE}"
    exit "${rc}"
    ;;
  *)
    loop_die "未知 MODE: ${MODE}（应为 exec|review）"
    ;;
esac
