#!/usr/bin/env bash
# seat-claude.sh — 请 Claude Code（Opus，原生壳）以 headless 方式入席圆桌
# Claude 在这里是与 codex/hermes 平级的"一个座位"，由独立指挥程序调用，从黑板自取上下文。
# 用法: seat-claude.sh <repo> plan|exec|review "<brief>"
#   plan  : 充当"项目总指挥"——读 KB+花名册，输出 JSON 派活计划（只读，不改文件）
#   exec  : 执行席——实施子任务（acceptEdits 自动接受文件改动）
#   review: 验证席——只读评审，出 VERDICT
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

# 可选模型覆盖（默认用会话/配置的 Opus）
CL_OPTS=(--add-dir "${REPO}")
CL_MODEL="${LOOP_SEAT_MODEL:-${LOOP_CLAUDE_MODEL:-}}"
[ -n "${CL_MODEL}" ] && CL_OPTS+=(--model "${CL_MODEL}")

# 跨目录只读盘点：LOOP_ADD_DIRS（空格分隔的绝对路径）仅在【只读模式 plan/review】接入 --add-dir。
# 红线（实测固化）：acceptEdits（exec 写模式）+ --add-dir 能写到仓外目录 → 故 exec 绝不接入 LOOP_ADD_DIRS，
# 跨目录一律走 plan 模式（物理只读，写操作被模式拦截），保证座位无法改动 ~/.claude 等仓外文件。
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

你的角色：**项目总指挥**。请阅读 KB/task.md、KB/project.md、KB/roster.md（各 agent 的特长花名册）与仓库，
把本任务拆成若干子任务，并**按每个 agent 的特长**分派。可用座位：claude、codex、hermes。
原则：握全上下文/改坏东西代价高的活留给 claude；代码验证派 codex；工具/环境广度活派 hermes。
${BRIEF:+补充：${BRIEF}}

**输出要求**：先简述思路，最后用一个 \`\`\`json 代码块输出派活计划，形如：
\`\`\`json
[{\"agent\":\"claude\",\"subtask\":\"……\"},{\"agent\":\"codex\",\"subtask\":\"……\"}]
\`\`\`
只在该 JSON 块里放计划，agent 字段必须是 claude/codex/hermes 之一。"
    loop_log "Claude 总指挥席入席 iter=${ITER}（plan，只读）"
    set +e
    ( cd "${REPO}" && claude -p "${INSTR}" "${CL_OPTS[@]}" ${RO_DIRS[@]+"${RO_DIRS[@]}"} --permission-mode plan ) >"${OUT}" 2>&1
    rc=$?
    set -e
    cat "${OUT}"
    loop_log "claude 退出码=${rc}，纪要: ${OUT}"
    exit "${rc}"
    ;;
  exec)
    [ -n "${BRIEF}" ] || loop_die "exec 模式需要第三个参数：子任务 brief"
    OUT="${TABLE}/minutes/iter-${ITER}-claude-exec.md"
    INSTR="${PRE}

你的角色：**执行席**。请完成下述子任务，直接在仓库里实施改动（干净、符合现有风格）。
完成后在 KB/state.md 简述你做了什么。删除/不可逆/对外/花钱类操作不要做，留给人工。
子任务：${BRIEF}"
    loop_log "Claude 执行席入席 iter=${ITER}（exec, acceptEdits）"
    set +e
    ( cd "${REPO}" && claude -p "${INSTR}" "${CL_OPTS[@]}" --permission-mode acceptEdits ) >"${OUT}" 2>&1
    rc=$?
    set -e
    cat "${OUT}"
    loop_log "claude 退出码=${rc}，纪要: ${OUT}"
    exit "${rc}"
    ;;
  review)
    OUT="${TABLE}/minutes/iter-${ITER}-claude-review.md"
    INSTR="${PRE}

你的角色：**验证席**（只读）。审查本轮未提交改动的正确性/安全性/是否满足验收标准。
按严重度标注：[CRITICAL]/[HIGH]/[MEDIUM]/[LOW]。
${BRIEF:+额外关注：${BRIEF}}
**最后单独成行输出**：无 HIGH/CRITICAL → VERDICT: PASS；否则 → VERDICT: BLOCK"
    loop_log "Claude 验证席入席 iter=${ITER}（review，只读）"
    set +e
    ( cd "${REPO}" && claude -p "${INSTR}" "${CL_OPTS[@]}" ${RO_DIRS[@]+"${RO_DIRS[@]}"} --permission-mode plan ) >"${OUT}" 2>&1
    rc=$?
    set -e
    cat "${OUT}"
    loop_log "claude 退出码=${rc}，纪要: ${OUT}"
    [ "${rc}" -eq 0 ] || { loop_warn "claude 进程非零退出 rc=${rc}，判 ERR"; exit 1; }
    loop_verdict_exit "${OUT}"; exit $?
    ;;
  *)
    loop_die "未知 MODE: ${MODE}（应为 plan|exec|review）"
    ;;
esac
