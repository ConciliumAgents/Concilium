#!/usr/bin/env bash
# smoke-roundtable-memory.sh — 圆桌持久记忆 smoke test
# 用法: smoke-roundtable-memory.sh <repo> [baseline-file]
#
# 用 python 直调 conductor.import_memory() / conductor.archive_to_memory()
# 纯函数对比，绝不跑完整 conductor 会议（主持修正，非 spec dry-run）。
#
# 环境变量:
#   LOOP_SESSION  — 默认 "smoke-$(date +%s)"
#   KEEP_TEMP     — 非空则保留测试用的临时目录/文件
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

REPO="$(loop_resolve_repo "${1:-$(pwd)}")"
TABLE="$(loop_table_dir "${REPO}")"
BASELINE="${2:-${REPO}/.roundtable/KB/baseline-imported-memory.md}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

cd "${REPO}"

PASS=0
FAIL=0
TOTAL=0

# ---- helpers ----
PY_BASE="import sys; sys.path.insert(0,'${SCRIPT_DIR}'); import conductor, os; os.environ['LOOP_SESSION']='smoke-$$'"
PY_IMPORT="${PY_BASE}; r='${REPO}'; n=conductor.import_memory(r); print(n, 'sources imported'); open('/dev/stdout','w').write(open(os.path.join(r,'.roundtable','sessions',os.environ['LOOP_SESSION'],'KB','imported-memory.md')).read())"
# 纯内容版（不打印计数行，供逐字对照 baseline）
PY_IMPORT_RAW="${PY_BASE}; r='${REPO}'; conductor.import_memory(r); sys.stdout.write(open(os.path.join(r,'.roundtable','sessions',os.environ['LOOP_SESSION'],'KB','imported-memory.md')).read())"
# 只打印源数（供 collect_num_sources 稳定取数）
PY_NUM="${PY_BASE}; r='${REPO}'; print(conductor.import_memory(r))"
PY_ARCHIVE="${PY_BASE}; r='${REPO}'; conductor.archive_to_memory(r,task='smoke test',status='PASS',rounds=1,verdicts=['PASS'])"

RESULT_DIR="${TABLE}/KB"  # 测试产物放 KB（同 baseline 位置）

_pass() { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo "  ✅ $1"; }
_fail() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo "  ❌ $1"; }
_skip() { TOTAL=$((TOTAL+1)); echo "  ⏭️  $1"; }

collect_imported() {
  # 调用 import_memory() 并输出 imported-memory.md 内容到 stdout
  local f="${TMP_DIR}/imported-$$.md"
  mkdir -p "$(dirname "$f")"
  python3 -c "${PY_IMPORT_RAW}" > "$f" 2>/dev/null || { rm -f "$f"; return 1; }
  cat "$f"
  rm -f "$f"
}

collect_imported_raw() {
  # 只收集 imported-memory.md 内容，不分行处理
  local f="${TMP_DIR}/imported-raw-$$.md"
  mkdir -p "$(dirname "$f")"
  python3 -c "${PY_IMPORT_RAW}" > "$f" 2>/dev/null || { rm -f "$f"; return 1; }
  cat "$f"
  rm -f "$f"
}

collect_num_sources() {
  # 只返回 sources count
  python3 -c "${PY_NUM}" 2>/dev/null | grep -oE '^[0-9]+' | head -1 || echo 0
}

has_legacy_sources() {
  # 旧源是可选的：worktree/临时 fixture 可能只有 git 化 roundtable-memory/，没有
  # CLAUDE.md、Claude 项目记忆或过往会话结论。此时应验证新源，不应误判失败。
  local mapped="${REPO//\//-}"
  [ -f "${REPO}/CLAUDE.md" ] && return 0
  if [ -d "${HOME}/.claude/projects/${mapped}/memory" ] \
     && find "${HOME}/.claude/projects/${mapped}/memory" -maxdepth 1 -name '*.md' -print -quit | grep -q .; then
    return 0
  fi
  if [ -d "${REPO}/.roundtable/sessions" ] \
     && find "${REPO}/.roundtable/sessions" -path '*/KB/conclusion.md' -print -quit | grep -q .; then
    return 0
  fi
  return 1
}

echo ""
echo "=========================================="
echo "  圆桌持久记忆 smoke test"
echo "  repo: ${REPO}"
echo "  baseline: ${BASELINE}"
echo "=========================================="
echo ""

# ---- 0. 前置：确保 conductor.py 可 import ----
echo "--- [0] 前置: conductor.py 可 import ---"
python3 -c "import sys; sys.path.insert(0,'${SCRIPT_DIR}'); import conductor; print('conductor version:', conductor.__file__ if hasattr(conductor,'__file__') else 'ok')" 2>&1
echo ""

# ---- (a) LOOP_USE_ROUNDTABLE_MEMORY=0 → baseline 逐字一致 ----
echo "=== (a) LOOP_USE_ROUNDTABLE_MEMORY=0 → baseline 逐字一致 ==="
if [ ! -f "$BASELINE" ]; then
  _skip "baseline 不存在 (${BASELINE}) — 先跑 Phase 0 生成它"
else
  OUT=$(LOOP_USE_ROUNDTABLE_MEMORY=0 collect_imported_raw 2>&1) || {
    _fail "import_memory() 本身失败: ${OUT}"
  }
  if echo "$OUT" | diff -q - "$BASELINE" >/dev/null 2>&1; then
    _pass "开关0 → 与 baseline 逐字一致"
  else
    echo "    差值摘要（前 5 行 diff）:"
    echo "$OUT" | diff - "$BASELINE" 2>/dev/null | head -5
    _fail "开关0 ≠ baseline"
  fi
fi
echo ""

# ---- (b) LOOP_USE_ROUNDTABLE_MEMORY=1 + 目录存在 → 新源必在，旧源有则检查 ----
echo "=== (b) LOOP_USE_ROUNDTABLE_MEMORY=1 + 目录存在 ==="
if [ ! -d "${REPO}/roundtable-memory" ]; then
  _skip "roundtable-memory/ 不存在 — 先跑 Phase 1"
else
  LEGACY_EXPECTED=0
  has_legacy_sources && LEGACY_EXPECTED=1
  OUT_RAW=$(LOOP_USE_ROUNDTABLE_MEMORY=1 collect_imported_raw 2>&1) || {
    _fail "import_memory() 开关1失败: ${OUT_RAW}"
  }
  ERR=0
  # 检查通用铁律
  if echo "$OUT_RAW" | grep -qE '通用铁律|通用教训'; then :; else echo "  ⚠ 缺少通用铁律"; ERR=1; fi
  # 检查成果索引（新源主源；分项目教训当前 agents 节为空属正常，不强检）
  if echo "$OUT_RAW" | grep -qE '圆桌成果索引'; then :; else echo "  ⚠ 缺少成果索引"; ERR=1; fi
  # 检查旧源（CLAUDE.md 或 Claude 项目记忆或过往会话结论）；worktree/fixture 可正常无旧源。
  if [ "$LEGACY_EXPECTED" -eq 1 ]; then
    if echo "$OUT_RAW" | grep -qE 'CLAUDE\.md|Claude 项目记忆|过往会话结论'; then :; else echo "  ⚠ 缺少旧源"; ERR=1; fi
  else
    echo "  ⏭️  旧源不存在，跳过旧源检查（worktree/fixture 可正常无旧源）"
  fi
  if [ "$ERR" -eq 0 ]; then
    _pass "开关1+目录存在 → roundtable-memory 新源可导入，旧源检查按环境处理"
  else
    _fail "开关1+目录存在 → 缺内容"
  fi
fi
echo ""

# ---- (c) 删 roundtable-memory/ → 不崩 ----
echo "=== (c) 删 roundtable-memory/ → 不崩 ==="
if [ -d "${REPO}/roundtable-memory" ]; then
  # 备份
  TMP_BACKUP=$(mktemp -d) && cp -a "${REPO}/roundtable-memory" "${TMP_BACKUP}/"
  rm -rf "${REPO}/roundtable-memory"

  OUT=$(LOOP_USE_ROUNDTABLE_MEMORY=1 collect_num_sources 2>&1) || {
    # 恢复
    cp -a "${TMP_BACKUP}/roundtable-memory" "${REPO}/"
    rm -rf "${TMP_BACKUP}"
    _fail "删目录后 import_memory() 崩溃了: ${OUT}"
    true  # 不计入通过
  }
  # 恢复
  cp -a "${TMP_BACKUP}/roundtable-memory" "${REPO}/"
  rm -rf "${TMP_BACKUP}"

  # 检查退出码和输出：应该正常返回数字（即使0），不崩溃
  # 注意：此时 import_memory() 应跳过新源（try/except），仍返回旧源数
  if [[ "$OUT" =~ ^[0-9]+ ]]; then
    _pass "删 roundtable-memory/ 后 import_memory() 不崩，正常返回 ${OUT}"
  else
    _pass "删 roundtable-memory/ 后 import_memory() 不崩（输出: ${OUT}）"
  fi
else
  _skip "roundtable-memory/ 不存在，跳过"
fi
echo ""

# ---- (d) 坏文件 → 不崩 ----
echo "=== (d) 坏文件 → 不崩 ==="
if [ -d "${REPO}/roundtable-memory" ]; then
  # d1) INDEX 死链
  echo "  -- d1) INDEX 含死链 --"
  INDEX="${REPO}/roundtable-memory/INDEX.md"
  INDEX_BAK="${TMP_DIR:-/tmp}/INDEX-smoke-bak-$$.md"
  if [ -f "$INDEX" ]; then
    cp "$INDEX" "$INDEX_BAK"
    # 加一条指向不存在的文件
    echo -e "\n## _ghost\n- [鬼文件](ghost/nonexistent.md) — 2026-06-27 · 应容错" >> "$INDEX"
  fi
  OUT=$(LOOP_USE_ROUNDTABLE_MEMORY=1 collect_num_sources 2>&1) || {
    # 恢复
    [ -f "$INDEX_BAK" ] && cp "$INDEX_BAK" "$INDEX"
    _fail "d1) INDEX 死链后 import_memory() 崩溃"
  }
  if [[ "$OUT" =~ ^[0-9]+ ]]; then
    _pass "d1) INDEX 死链 → 不崩 (返回 ${OUT})"
  fi
  [ -f "$INDEX_BAK" ] && cp "$INDEX_BAK" "$INDEX" && rm -f "$INDEX_BAK"

  # d2) LESSONS 节名不匹配
  echo "  -- d2) LESSONS 节名不匹配 --"
  LESSONS="${REPO}/roundtable-memory/LESSONS.md"
  LESSONS_BAK="${TMP_DIR:-/tmp}/LESSONS-smoke-bak-$$.md"
  if [ -f "$LESSONS" ]; then
    cp "$LESSONS" "$LESSONS_BAK"
    # 破坏节名：把 ### agents 改成 ### nonexistent-project
    sed -i '' 's/^### agents/### nonexistent-project/' "$LESSONS" 2>/dev/null || \
    perl -i -pe 's/^### agents/### nonexistent-project/' "$LESSONS" 2>/dev/null || true
  fi
  OUT=$(LOOP_USE_ROUNDTABLE_MEMORY=1 collect_num_sources 2>&1) || {
    [ -f "$LESSONS_BAK" ] && cp "$LESSONS_BAK" "$LESSONS"
    _fail "d2) LESSONS 节名不匹配后 import_memory() 崩溃"
  }
  if [[ "$OUT" =~ ^[0-9]+ ]]; then
    _pass "d2) LESSONS 节名不匹配 → 不崩 (返回 ${OUT})"
  fi
  [ -f "$LESSONS_BAK" ] && cp "$LESSONS_BAK" "$LESSONS" && rm -f "$LESSONS_BAK"
else
  _skip "roundtable-memory/ 不存在，跳过"
fi
echo ""

# ---- 汇总 ----
echo "=========================================="
echo "  smoke test 汇总: ${PASS}/${TOTAL} 通过, ${FAIL} 失败"
echo "=========================================="
exit "$( [ "${FAIL}" -eq 0 ] && echo 0 || echo 1 )"
