#!/usr/bin/env bash
# kb-refresh.sh — 刷新知识库滚动部分：重生成 diff.patch、捕获测试输出
# 用法: kb-refresh.sh <repo> ["<测试命令>"]
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

REPO="$(loop_resolve_repo "${1:-}")"
TESTCMD="${2:-$LOOP_TEST_CMD}"
TABLE="$(loop_table_dir "${REPO}")"

# --- diff.patch：本轮改动（已跟踪 vs HEAD + 未跟踪文件清单）---
{
  echo "# 本轮改动快照（kb-refresh 生成）"
  echo "## git diff（已跟踪文件 vs HEAD）"
  git -C "${REPO}" diff HEAD 2>/dev/null || git -C "${REPO}" diff 2>/dev/null || echo "（无提交或无改动）"
  echo
  echo "## 未跟踪文件（untracked）"
  git -C "${REPO}" ls-files --others --exclude-standard 2>/dev/null || true
} > "${TABLE}/KB/diff.patch"
loop_log "已刷新 KB/diff.patch"

# --- test-results.txt ---
if [ -n "${TESTCMD}" ]; then
  loop_log "运行测试: ${TESTCMD}"
  set +e
  out="$( cd "${REPO}" && eval "${TESTCMD}" 2>&1 )"; rc=$?
  set -e
  { echo "# 测试命令: ${TESTCMD}"; echo "---"; echo "${out}"; echo "---"; echo "# 退出码: ${rc}"; } > "${TABLE}/KB/test-results.txt"
  loop_log "测试退出码=${rc}，已写入 KB/test-results.txt"
else
  echo "（未配置 LOOP_TEST_CMD / 未传测试命令，本轮跳过自动测试，由主持判断）" > "${TABLE}/KB/test-results.txt"
  loop_log "未配置测试命令，跳过"
fi
