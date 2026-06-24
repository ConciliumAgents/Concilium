#!/usr/bin/env bash
# roundtable-init.sh — 在目标仓库初始化圆桌会议桌 .roundtable/
# 用法: roundtable-init.sh <repo> "<task 描述>"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$SCRIPT_DIR/_lib.sh"

REPO="$(loop_resolve_repo "${1:-}")"
TASK="${2:-}"
TABLE="$(loop_table_dir "$REPO")"
TPL="$SCRIPT_DIR/../templates"

# KB 模板（已存在则不覆盖，保护你已写的内容）
[ -f "$TABLE/KB/project.md" ] || cp "$TPL/project.md" "$TABLE/KB/project.md"
[ -f "$TABLE/KB/task.md" ]    || cp "$TPL/task.md"    "$TABLE/KB/task.md"
[ -f "$TABLE/KB/state.md" ]   || cp "$TPL/state.md"   "$TABLE/KB/state.md"
[ -f "$TABLE/KB/roster.md" ]  || cp "$TPL/roster.md"  "$TABLE/KB/roster.md"
[ -f "$TABLE/KB/diff.patch" ] || echo "（尚未刷新；运行 kb-refresh.sh）" > "$TABLE/KB/diff.patch"
[ -f "$TABLE/KB/test-results.txt" ] || echo "（尚未运行测试）" > "$TABLE/KB/test-results.txt"

# 写入本次任务
if [ -n "$TASK" ]; then
  printf '\n## 本次任务（init 写入）\n\n%s\n' "$TASK" >> "$TABLE/KB/task.md"
fi

# 机读状态
if [ ! -f "$TABLE/roundtable.json" ]; then
  cat > "$TABLE/roundtable.json" <<'JSON'
{
  "iter": 1,
  "stuck": 0,
  "participants": ["claude", "codex", "hermes"],
  "verdicts": []
}
JSON
fi

# 让会议桌不污染目标仓库：用本地 exclude（不改任何被跟踪文件，非侵入）
EXCL="$REPO/.git/info/exclude"
if [ -f "$EXCL" ] && ! grep -qxF "$LOOP_TABLE_DIRNAME/" "$EXCL" 2>/dev/null; then
  printf '%s/\n' "$LOOP_TABLE_DIRNAME" >> "$EXCL"
  loop_log "已把 $LOOP_TABLE_DIRNAME/ 加入 .git/info/exclude（不进你的提交）"
fi

# loop 分支（仅当仓库已有提交时；init 不自动切，避免打断你当前工作）
if git -C "$REPO" rev-parse HEAD >/dev/null 2>&1; then
  slug="$(printf '%s' "${TASK:-task}" | tr ' ' '-' | tr -cd '[:alnum:]-' | cut -c1-30)"
  [ -n "$slug" ] || slug="task"
  br="loop-engine/${slug}"
  if ! git -C "$REPO" rev-parse --verify "$br" >/dev/null 2>&1; then
    git -C "$REPO" branch "$br" >/dev/null 2>&1 || true
  fi
  loop_log "建议在隔离分支工作: ${br} (手动 git -C '${REPO}' switch ${br} 切入)"
fi

loop_log "圆桌会议桌已就绪: $TABLE"
loop_log "下一步: 填好 KB/project.md 与 KB/task.md，再开始 plan→act→verify 循环"
