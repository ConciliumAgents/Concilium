#!/usr/bin/env bash
# roundtable-init.sh - Initialize a Concilium table in the target repository .roundtable/
# Usage: roundtable-init.sh <repo> "<task description>"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$SCRIPT_DIR/_lib.sh"

REPO="$(loop_resolve_repo "${1:-}")"
TASK="${2:-}"
TABLE="$(loop_table_dir "$REPO")"     # Current session directory: .roundtable/sessions/<id>/
TPL="$SCRIPT_DIR/../templates"

# Session-level isolation: record current pointer and maintain session index for Web UI history.
ROOT="$(loop_root "$REPO")"
SID="${LOOP_SESSION:-default}"
printf '%s' "$SID" > "$ROOT/current"
if command -v python3 >/dev/null 2>&1; then
  python3 - "$ROOT/index.json" "$SID" "$TASK" <<'PY'
import json, os, sys
idx, sid, task = sys.argv[1], sys.argv[2], sys.argv[3]
d = []
if os.path.exists(idx):
    try: d = json.load(open(idx))
    except Exception: d = []
if not any(e.get("id") == sid for e in d):
    d.append({"id": sid, "task": task})
    json.dump(d, open(idx, "w"), ensure_ascii=False, indent=2)
PY
fi

# KB templates: preserve existing content.
[ -f "$TABLE/KB/project.md" ] || cp "$TPL/project.md" "$TABLE/KB/project.md"
[ -f "$TABLE/KB/task.md" ]    || cp "$TPL/task.md"    "$TABLE/KB/task.md"
[ -f "$TABLE/KB/state.md" ]   || cp "$TPL/state.md"   "$TABLE/KB/state.md"
[ -f "$TABLE/KB/roster.md" ]  || cp "$TPL/roster.md"  "$TABLE/KB/roster.md"
[ -f "$TABLE/KB/diff.patch" ] || echo "(Not refreshed yet; run kb-refresh.sh)" > "$TABLE/KB/diff.patch"
[ -f "$TABLE/KB/test-results.txt" ] || echo "(Tests have not run yet)" > "$TABLE/KB/test-results.txt"

# Write this run's task.
if [ -n "$TASK" ]; then
  printf '\n## Task (written by init)\n\n%s\n' "$TASK" >> "$TABLE/KB/task.md"
fi

# Machine-readable state.
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

# Keep the table out of target-repo commits by using local exclude.
EXCL="$REPO/.git/info/exclude"
if [ -f "$EXCL" ] && ! grep -qxF "$LOOP_TABLE_DIRNAME/" "$EXCL" 2>/dev/null; then
  printf '%s/\n' "$LOOP_TABLE_DIRNAME" >> "$EXCL"
  loop_log "added $LOOP_TABLE_DIRNAME/ to .git/info/exclude (not included in commits)"
fi

# Loop branch suggestion only when the repository has commits; do not switch automatically.
if git -C "$REPO" rev-parse HEAD >/dev/null 2>&1; then
  slug="$(printf '%s' "${TASK:-task}" | tr ' ' '-' | tr -cd '[:alnum:]-' | cut -c1-30)"
  [ -n "$slug" ] || slug="task"
  br="loop-engine/${slug}"
  if ! git -C "$REPO" rev-parse --verify "$br" >/dev/null 2>&1; then
    git -C "$REPO" branch "$br" >/dev/null 2>&1 || true
  fi
  loop_log "Suggested isolated branch: ${br} (manual: git -C '${REPO}' switch ${br})"
fi

loop_log "Concilium table is ready: $TABLE"
loop_log "Next step: Fill KB/project.md and KB/task.md, then start the plan-act-verify loop"
