#!/usr/bin/env bash
# checkpoint.sh — 一轮收尾：追加 state.md、提交代码检查点、bump 轮次
# 用法: checkpoint.sh <repo> "<本轮小结>"
# 说明: .roundtable/ 已被 .git/info/exclude 排除，提交只含真实代码改动。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

REPO="$(loop_resolve_repo "${1:-}")"
SUMMARY="${2:-iteration}"
TABLE="$(loop_table_dir "${REPO}")"
ITER="$(loop_iter "${REPO}")"

# 追加到 state.md（鲜活记忆，留在磁盘黑板上）
printf '\n### iter %s — %s\n' "${ITER}" "${SUMMARY}" >> "${TABLE}/KB/state.md"

# 提交代码检查点（.roundtable/ 被 exclude，不会进提交）
set +e
git -C "${REPO}" add -A
if git -C "${REPO}" diff --cached --quiet; then
  loop_log "无代码改动可提交 iter=${ITER}"
else
  git -C "${REPO}" commit -q -m "loop-engine: iter ${ITER} — ${SUMMARY}"
  loop_log "已提交代码检查点 iter=${ITER}"
fi
set -e

# bump 轮次
NEXT=$(( ITER + 1 ))
loop_state_set "${REPO}" iter "${NEXT}"
loop_log "本轮收尾完成，下一轮=${NEXT}"
