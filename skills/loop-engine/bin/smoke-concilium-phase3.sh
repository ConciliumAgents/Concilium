#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TMP="${TMPDIR:-/tmp}/concilium-phase3-smoke"

git -C "$ROOT" worktree remove --force "$TMP" >/dev/null 2>&1 || true
rm -rf "$TMP"
git -C "$ROOT" worktree add --detach "$TMP" HEAD >/dev/null
cleanup() {
  git -C "$ROOT" worktree remove --force "$TMP" >/dev/null 2>&1 || true
}
trap cleanup EXIT

python3 "$ROOT/skills/loop-engine/bin/concilium-run.py" \
  --repo "$TMP" \
  --task "Fix one typo in docs/loop-engine/agent-moa-positioning.md." \
  --test-cmd "true" \
  --dry-run \
  --print-route \
  | python3 -m json.tool >/tmp/concilium-phase3-fast-preview.json

python3 "$ROOT/skills/loop-engine/bin/concilium-run.py" \
  --repo "$TMP" \
  --task "Change config routing behavior and update tests." \
  --test-cmd "true" \
  --dry-run \
  --print-route \
  | python3 -m json.tool >/tmp/concilium-phase3-review-preview.json

python3 "$ROOT/skills/loop-engine/bin/concilium-run.py" \
  --repo "$TMP" \
  --task "Design a security-sensitive migration across multiple modules." \
  --test-cmd "true" \
  --dry-run \
  --print-route \
  | python3 -m json.tool >/tmp/concilium-phase3-roundtable-preview.json

rg -n '"lane": "fast"' /tmp/concilium-phase3-fast-preview.json
rg -n '"lane": "review"' /tmp/concilium-phase3-review-preview.json
rg -n '"lane": "roundtable"' /tmp/concilium-phase3-roundtable-preview.json

echo "Concilium Phase 3 smoke passed"
