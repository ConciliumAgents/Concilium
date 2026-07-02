#!/usr/bin/env bash
# Offline smoke checks for Concilium planner/reviewer routing behavior.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0; FAIL=0
_ok(){ PASS=$((PASS+1)); echo "  PASS $1"; }
_no(){ FAIL=$((FAIL+1)); echo "  FAIL $1"; }

echo ""
echo "=========================================="
echo "  Concilium speedup offline smoke"
echo "=========================================="

echo ""; echo "=== T1: helper decisions ==="
python3 - "$SCRIPT_DIR" <<'PY' && _ok "T1 helper decisions pass" || _no "T1 helper decisions fail"
import sys; sys.path.insert(0, sys.argv[1])
import conductor as c
errs=[]
def eq(name,got,exp):
    if got!=exp: errs.append(f"{name}: got {got!r} exp {exp!r}")
ex=lambda seated,rev:[a for a in seated if a not in c.EXEC_EXCLUDE and a!=rev]
eq("requested reviewer is seated", c._resolve_reviewer(["claude","hermes","kimi"],"kimi"), "kimi")
eq("default two fast seats chooses hermes", c._resolve_reviewer(["claude","hermes","kimi"],""), "hermes")
eq("bad requested codex falls back", c._resolve_reviewer(["claude","hermes","kimi"],"codex"), "hermes")
eq("one fast seat keeps claude reviewer", c._resolve_reviewer(["claude","kimi"],""), "claude")
eq("only claude returns claude", c._resolve_reviewer(["claude"],""), "claude")
eq("default executor pool", ex(["claude","hermes","kimi"],"hermes"), ["kimi"])
eq("only claude pool empty", ex(["claude"],"claude"), [])
eq("claude excluded", "claude" in ex(["claude","hermes","kimi"],"hermes"), False)
eq("codex excluded", "codex" in ex(["claude","codex","hermes","kimi"],"hermes"), False)
eq("fallback prefers kimi", c._fallback_plan(["kimi","hermes"],"T")[0]["agent"], "kimi")
eq("no anomalies yields empty brief", c.build_brief([],[],False,False), "")
eq("fallback creates brief", c.build_brief([],[],False,True)!="", True)
b_fb=c.build_brief([],[],True,True)
b_kept=c.build_brief([],[],True,False)
eq("fallback brief mentions fallback", "fallback" in b_fb, True)
eq("planner error brief mentions non-zero", "non-zero" in b_kept, True)
eq("brief variants differ", b_fb!=b_kept, True)
b=c.build_brief([{"agent":"claude","subtask":"x"}],[("kimi",124)],True,True)
eq("brief has completeness context", "task completeness" in b, True)
eq("brief has timeout", "timeout" in b, True)
eq("brief has skipped subtask", "not executed" in b, True)
if errs:
    print("  FAIL:"); [print("   -",e) for e in errs]; sys.exit(1)
PY

echo ""; echo "=== T2: plan filtering ==="
python3 - "$SCRIPT_DIR" <<'PY' && _ok "T2 filtering passes" || _no "T2 filtering fails"
import sys; sys.path.insert(0, sys.argv[1])
import conductor as c
seated=["claude","hermes","kimi"]; reviewer="kimi"
executors=[a for a in seated if a not in c.EXEC_EXCLUDE and a!=reviewer]
raw=[{"agent":"claude","subtask":"core"},{"agent":"hermes","subtask":"tooling"},{"agent":"kimi","subtask":"review"}]
kept=[p for p in raw if p["agent"] in executors]
dropped=[p for p in raw if p["agent"] not in executors]
assert [p["agent"] for p in kept]==["hermes"], kept
assert {p["agent"] for p in dropped}=={"claude","kimi"}, dropped
print("  kept=hermes, dropped=claude+kimi")
PY

echo ""; echo "=== T3: lessons archive from multiple executor seats ==="
python3 - "$SCRIPT_DIR" <<'PY' && _ok "T3 lessons archive passes" || _no "T3 lessons archive fails"
import sys, tempfile, pathlib; sys.path.insert(0, sys.argv[1])
import conductor as c
tmp=pathlib.Path(tempfile.mkdtemp())
root=tmp/"roundtable-memory"; root.mkdir()
(root/"LESSONS.md").write_text("# LESSONS\n\n## General Rules\n\n## Project-Specific Lessons\n### proj\n", encoding="utf-8")
sd=tmp/"sessions"/"s1"; (sd/"minutes").mkdir(parents=True)
(sd/"minutes"/"iter-1-kimi-exec.md").write_text("done.\n## Lessons\n### General\n- Kimi general lesson\n### proj\n- Kimi project lesson\n", encoding="utf-8")
(sd/"minutes"/"iter-1-hermes-exec.md").write_text("done.\n## Lessons\n### General\n- Hermes general lesson\n", encoding="utf-8")
c._archive_lessons(root, "proj", sd)
txt=(root/"LESSONS.md").read_text(encoding="utf-8")
for needle in ("Kimi general lesson","Kimi project lesson","Hermes general lesson"):
    assert needle in txt, f"missing {needle}"
print("  kimi and hermes lessons archived")
PY

echo ""; echo "=== T4: seat-claude can assign kimi ==="
SC="$SCRIPT_DIR/seat-claude.sh"
if grep -q "Available seats: claude, codex, hermes, kimi" "$SC" \
   && grep -q "agent field must be one of claude, codex, hermes, or kimi" "$SC" \
   && grep -q "prefer hermes and kimi" "$SC"; then
  _ok "T4 seat-claude prompt includes kimi and fast executors"
else
  _no "T4 seat-claude prompt missing expected routing guidance"
fi

echo ""; echo "=== T5: default reviewer is auto-selected ==="
if grep -qE '"--reviewer", default="", ' "$SCRIPT_DIR/conductor.py"; then
  _ok "T5 reviewer default remains auto-select"
else
  _no "T5 reviewer default is not auto-select"
fi

echo ""; echo "=== T6: round notes append state.md ==="
python3 - "$SCRIPT_DIR" <<'PY' && _ok "T6 round notes pass" || _no "T6 round notes fail"
import sys, os, tempfile, pathlib; sys.path.insert(0, sys.argv[1])
import conductor as c
tmp=pathlib.Path(tempfile.mkdtemp()); os.environ["LOOP_SESSION"]="smoketest-notes"
c._write_round_notes(str(tmp), [{"agent":"claude","subtask":"core work"}], [("kimi",124)], True, True)
sp=tmp/".roundtable"/"sessions"/"smoketest-notes"/"KB"/"state.md"
assert sp.exists(), "state.md was not written"
t=sp.read_text(encoding="utf-8")
for needle in ("Round Anomalies", "kimi", "core work", "fallback"):
    assert needle in t, f"state.md missing {needle}"
c._write_round_notes(str(tmp), [], [("hermes",1)], False, False)
t2=sp.read_text(encoding="utf-8")
assert t2.count("Round Anomalies")==2 and "core work" in t2, "append did not preserve prior content"
print("  state.md contains failures, dropped subtasks, and fallback wording")
PY

echo ""; echo "=== T7: seat contract validator unit tests ==="
if python3 "$SCRIPT_DIR/../tests/test_seat_contract_validate.py" >/tmp/loop-seat-contract-test.out 2>&1; then
  _ok "T7 seat contract validator tests pass"
else
  cat /tmp/loop-seat-contract-test.out
  _no "T7 seat contract validator tests fail"
fi

echo ""
echo "=========================================="
echo "  summary: ${PASS} passed, ${FAIL} failed"
echo "=========================================="
exit "$([ "$FAIL" -eq 0 ] && echo 0 || echo 1)"
