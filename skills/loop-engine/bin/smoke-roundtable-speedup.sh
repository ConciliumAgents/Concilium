#!/usr/bin/env bash
# smoke-roundtable-speedup.sh — 圆桌提速(claude退出exec + 降级容错)离线冒烟
# 纯函数/离线验证 conductor 的决策逻辑，绝不跑完整 conductor 会议（不调 LLM、不 git commit）。
# 端到端(真变快/真降级/fail-fast 实际返回)留正式冒烟，需真座位、会触发 checkpoint commit。
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0; FAIL=0
_ok(){ PASS=$((PASS+1)); echo "  ✅ $1"; }
_no(){ FAIL=$((FAIL+1)); echo "  ❌ $1"; }

echo ""
echo "=========================================="
echo "  圆桌提速 离线冒烟"
echo "=========================================="

# ---- T1: helper 决策逻辑（reviewer 解析 / executors / fallback / brief） ----
echo ""; echo "=== T1: 决策逻辑（纯函数） ==="
python3 - "$SCRIPT_DIR" <<'PY' && _ok "T1 决策逻辑全绿" || _no "T1 决策逻辑有错"
import sys; sys.path.insert(0, sys.argv[1])
import conductor as c
errs=[]
def eq(name,got,exp):
    if got!=exp: errs.append(f"{name}: got {got} exp {exp}")
ex=lambda seated,rev:[a for a in seated if a not in c.EXEC_EXCLUDE and a!=rev]
# reviewer 解析
eq("用户指定且在座", c._resolve_reviewer(["claude","hermes","kimi"],"kimi"), "kimi")
eq("默认2飞毛腿→异质hermes", c._resolve_reviewer(["claude","hermes","kimi"],""), "hermes")
eq("用户指定坏codex→自动hermes", c._resolve_reviewer(["claude","hermes","kimi"],"codex"), "hermes")
eq("仅1飞毛腿→claude兜底", c._resolve_reviewer(["claude","kimi"],""), "claude")
eq("仅claude→claude(待fail-fast)", c._resolve_reviewer(["claude"],""), "claude")
# executors
eq("默认池(rev=hermes)", ex(["claude","hermes","kimi"],"hermes"), ["kimi"])
eq("仅claude池空", ex(["claude"],"claude"), [])
eq("claude被排除", "claude" in ex(["claude","hermes","kimi"],"hermes"), False)
eq("codex被排除", "codex" in ex(["claude","codex","hermes","kimi"],"hermes"), False)
# fallback
eq("fallback优先kimi", c._fallback_plan(["kimi","hermes"],"T")[0]["agent"], "kimi")
# brief
eq("无异常空串", c.build_brief([],[],False), "")
b=c.build_brief([{"agent":"claude","subtask":"x"}],[("kimi",124)],True)
eq("brief含完整性前缀", "任务完整性" in b, True)
eq("brief含超时", "超时" in b, True)
eq("brief含未执行子任务", "未执行" in b, True)
if errs:
    print("  FAIL:"); [print("   -",e) for e in errs]; sys.exit(1)
PY

# ---- T2: plan 过滤——claude/codex/reviewer 被移出，飞毛腿保留 ----
echo ""; echo "=== T2: plan 过滤 + dropped 记账 ==="
python3 - "$SCRIPT_DIR" <<'PY' && _ok "T2 过滤逻辑正确" || _no "T2 过滤逻辑错"
import sys; sys.path.insert(0, sys.argv[1])
import conductor as c
seated=["claude","hermes","kimi"]; reviewer="kimi"
executors=[a for a in seated if a not in c.EXEC_EXCLUDE and a!=reviewer]  # → [hermes]
raw=[{"agent":"claude","subtask":"核心"},{"agent":"hermes","subtask":"工具"},
     {"agent":"kimi","subtask":"验证活"}]
kept=[p for p in raw if p["agent"] in executors]
dropped=[p for p in raw if p["agent"] not in executors]
assert [p["agent"] for p in kept]==["hermes"], kept
assert {p["agent"] for p in dropped}=={"claude","kimi"}, dropped   # claude=慢、kimi=验证席→都移出
print("  kept=hermes, dropped=claude+kimi（reviewer 不进 exec）")
PY

# ---- T3: CRITICAL 归档——抽所有座位 exec 纪要，非仅 claude ----
echo ""; echo "=== T3: 归档抽多座位 exec 教训（CRITICAL 修复） ==="
python3 - "$SCRIPT_DIR" <<'PY' && _ok "T3 多座位教训均被归档" || _no "T3 归档断流/未覆盖"
import sys, tempfile, pathlib; sys.path.insert(0, sys.argv[1])
import conductor as c
tmp=pathlib.Path(tempfile.mkdtemp())
root=tmp/"roundtable-memory"; root.mkdir()
(root/"LESSONS.md").write_text("# LESSONS\n\n## 通用铁律\n\n## 分项目教训\n### proj\n", encoding="utf-8")
sd=tmp/"sessions"/"s1"; (sd/"minutes").mkdir(parents=True)
(sd/"minutes"/"iter-1-kimi-exec.md").write_text(
    "干完了。\n## 教训\n### 通用\n- KIMI通用教训X\n### proj\n- KIMI项目教训Y\n", encoding="utf-8")
(sd/"minutes"/"iter-1-hermes-exec.md").write_text(
    "done.\n## 教训\n### 通用\n- HERMES通用教训Z\n", encoding="utf-8")
# 旧行为：只 glob claude-exec → 上面两条都抽不到。新行为：iter-*-*-exec.md 全抽。
c._archive_lessons(root, "proj", sd)
txt=(root/"LESSONS.md").read_text(encoding="utf-8")
for needle in ("KIMI通用教训X","KIMI项目教训Y","HERMES通用教训Z"):
    assert needle in txt, f"缺 {needle}（归档没覆盖该座位）"
print("  kimi+hermes 的通用/项目教训均进 LESSONS（claude 不 exec 也不断流）")
PY

# ---- T4: seat-claude.sh plan prompt 已含 kimi（主修复不半失效） ----
echo ""; echo "=== T4: seat-claude.sh 可派 kimi ==="
SC="$SCRIPT_DIR/seat-claude.sh"
if grep -q "可用座位：claude、codex、hermes、kimi" "$SC" \
   && grep -q "claude/codex/hermes/kimi 之一" "$SC" \
   && grep -q "优先派 hermes/kimi" "$SC"; then
  _ok "T4 seat-claude 含 kimi + 优先飞毛腿"
else
  _no "T4 seat-claude 仍缺 kimi 或未改原则"
fi

# ---- T5: 默认 reviewer 不再硬编码 codex ----
echo ""; echo "=== T5: 默认 reviewer 不再 codex ==="
if grep -qE '"--reviewer", default="", ' "$SCRIPT_DIR/conductor.py"; then
  _ok "T5 默认 reviewer 改为自动解析（不再 codex）"
else
  _no "T5 默认 reviewer 仍是 codex"
fi

echo ""
echo "=========================================="
echo "  汇总: ${PASS} 通过, ${FAIL} 失败"
echo "=========================================="
exit "$([ "$FAIL" -eq 0 ] && echo 0 || echo 1)"
