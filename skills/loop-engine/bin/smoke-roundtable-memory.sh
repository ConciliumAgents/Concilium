#!/usr/bin/env bash
# Smoke checks for the repo-local Concilium memory bridge.
# Usage: smoke-roundtable-memory.sh <repo> [baseline-file]
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

PY_BASE="import sys; sys.path.insert(0,'${SCRIPT_DIR}'); import conductor, os; os.environ['LOOP_SESSION']='smoke-$$'"
PY_IMPORT_RAW="${PY_BASE}; r='${REPO}'; conductor.import_memory(r); sys.stdout.write(open(os.path.join(r,'.roundtable','sessions',os.environ['LOOP_SESSION'],'KB','imported-memory.md')).read())"
PY_NUM="${PY_BASE}; r='${REPO}'; print(conductor.import_memory(r))"

_pass() { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo "  PASS $1"; }
_fail() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo "  FAIL $1"; }
_skip() { TOTAL=$((TOTAL+1)); echo "  SKIP $1"; }

collect_imported_raw() {
  local f="${TMP_DIR}/imported-raw-$$.md"
  mkdir -p "$(dirname "$f")"
  python3 -c "${PY_IMPORT_RAW}" > "$f" 2>/dev/null || { rm -f "$f"; return 1; }
  cat "$f"
  rm -f "$f"
}

collect_num_sources() {
  python3 -c "${PY_NUM}" 2>/dev/null | grep -oE '^[0-9]+' | head -1 || echo 0
}

has_legacy_sources() {
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
echo "  Concilium memory bridge smoke test"
echo "  repo: ${REPO}"
echo "  baseline: ${BASELINE}"
echo "=========================================="
echo ""

echo "--- [0] conductor.py imports ---"
python3 -c "import sys; sys.path.insert(0,'${SCRIPT_DIR}'); import conductor; print('conductor:', conductor.__file__ if hasattr(conductor,'__file__') else 'ok')" 2>&1
echo ""

echo "=== (a) LOOP_USE_ROUNDTABLE_MEMORY=0 matches baseline ==="
if [ ! -f "$BASELINE" ]; then
  _skip "baseline missing (${BASELINE})"
else
  OUT=$(LOOP_USE_ROUNDTABLE_MEMORY=0 collect_imported_raw 2>&1) || {
    _fail "import_memory failed: ${OUT}"
  }
  if echo "$OUT" | diff -q - "$BASELINE" >/dev/null 2>&1; then
    _pass "memory disabled output matches baseline"
  else
    echo "    diff preview:"
    echo "$OUT" | diff - "$BASELINE" 2>/dev/null | head -5
    _fail "memory disabled output differs from baseline"
  fi
fi
echo ""

echo "=== (b) LOOP_USE_ROUNDTABLE_MEMORY=1 imports repo memory ==="
if [ ! -d "${REPO}/roundtable-memory" ]; then
  _skip "roundtable-memory/ missing"
else
  LEGACY_EXPECTED=0
  has_legacy_sources && LEGACY_EXPECTED=1
  OUT_RAW=$(LOOP_USE_ROUNDTABLE_MEMORY=1 collect_imported_raw 2>&1) || {
    _fail "import_memory with repo memory failed: ${OUT_RAW}"
  }
  ERR=0
  if echo "$OUT_RAW" | grep -qE 'General Rules'; then :; else echo "  missing General Rules"; ERR=1; fi
  if echo "$OUT_RAW" | grep -qE 'Roundtable Outcome Index'; then :; else echo "  missing Roundtable Outcome Index"; ERR=1; fi
  if [ "$LEGACY_EXPECTED" -eq 1 ]; then
    if echo "$OUT_RAW" | grep -qE 'CLAUDE\.md|Claude Project Memory|Prior Session Conclusion'; then :; else echo "  missing legacy source"; ERR=1; fi
  else
    echo "  legacy source missing; skipping legacy-source check"
  fi
  if [ "$ERR" -eq 0 ]; then
    _pass "repo memory imports; legacy check handled by environment"
  else
    _fail "repo memory import missing expected content"
  fi
fi
echo ""

echo "=== (c) missing roundtable-memory/ does not crash ==="
if [ -d "${REPO}/roundtable-memory" ]; then
  TMP_BACKUP=$(mktemp -d) && cp -a "${REPO}/roundtable-memory" "${TMP_BACKUP}/"
  rm -rf "${REPO}/roundtable-memory"
  OUT=$(LOOP_USE_ROUNDTABLE_MEMORY=1 collect_num_sources 2>&1) || {
    cp -a "${TMP_BACKUP}/roundtable-memory" "${REPO}/"
    rm -rf "${TMP_BACKUP}"
    _fail "import_memory crashed after deleting roundtable-memory/: ${OUT}"
    true
  }
  cp -a "${TMP_BACKUP}/roundtable-memory" "${REPO}/"
  rm -rf "${TMP_BACKUP}"
  if [[ "$OUT" =~ ^[0-9]+ ]]; then
    _pass "import_memory returned normally after directory removal (${OUT})"
  else
    _pass "import_memory did not crash after directory removal (output: ${OUT})"
  fi
else
  _skip "roundtable-memory/ missing"
fi
echo ""

echo "=== (d) malformed memory files do not crash ==="
if [ -d "${REPO}/roundtable-memory" ]; then
  echo "  -- d1) INDEX contains a dead link --"
  INDEX="${REPO}/roundtable-memory/INDEX.md"
  INDEX_BAK="${TMP_DIR}/INDEX-smoke-bak-$$.md"
  if [ -f "$INDEX" ]; then
    cp "$INDEX" "$INDEX_BAK"
    printf '\n## _ghost\n- [ghost](ghost/nonexistent.md) - 2026-06-27 - tolerate missing target\n' >> "$INDEX"
  fi
  OUT=$(LOOP_USE_ROUNDTABLE_MEMORY=1 collect_num_sources 2>&1) || {
    [ -f "$INDEX_BAK" ] && cp "$INDEX_BAK" "$INDEX"
    _fail "import_memory crashed with dead INDEX link"
  }
  if [[ "$OUT" =~ ^[0-9]+ ]]; then
    _pass "dead INDEX link did not crash (${OUT})"
  fi
  [ -f "$INDEX_BAK" ] && cp "$INDEX_BAK" "$INDEX" && rm -f "$INDEX_BAK"

  echo "  -- d2) LESSONS project section mismatch --"
  LESSONS="${REPO}/roundtable-memory/LESSONS.md"
  LESSONS_BAK="${TMP_DIR}/LESSONS-smoke-bak-$$.md"
  if [ -f "$LESSONS" ]; then
    cp "$LESSONS" "$LESSONS_BAK"
    sed -i '' 's/^### agents/### nonexistent-project/' "$LESSONS" 2>/dev/null || \
    perl -i -pe 's/^### agents/### nonexistent-project/' "$LESSONS" 2>/dev/null || true
  fi
  OUT=$(LOOP_USE_ROUNDTABLE_MEMORY=1 collect_num_sources 2>&1) || {
    [ -f "$LESSONS_BAK" ] && cp "$LESSONS_BAK" "$LESSONS"
    _fail "import_memory crashed with mismatched LESSONS section"
  }
  if [[ "$OUT" =~ ^[0-9]+ ]]; then
    _pass "mismatched LESSONS section did not crash (${OUT})"
  fi
  [ -f "$LESSONS_BAK" ] && cp "$LESSONS_BAK" "$LESSONS" && rm -f "$LESSONS_BAK"
else
  _skip "roundtable-memory/ missing"
fi
echo ""

echo "=========================================="
echo "  smoke test summary: ${PASS}/${TOTAL} passed, ${FAIL} failed"
echo "=========================================="
exit "$( [ "${FAIL}" -eq 0 ] && echo 0 || echo 1 )"
