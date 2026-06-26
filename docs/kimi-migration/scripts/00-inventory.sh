#!/usr/bin/env bash
#
# 00-inventory.sh —— Kimi 承接迁移 · 阶段 0 只读补盘脚本（PLAN §D 阶段 0）
#
# 目的：在一个对 ~/.claude 与 ~/Documents 有【只读】权限的会话里跑一次，
#       把 PLAN §A 的盘点从"快照"刷新成"执行当下的实测事实"，并产出可
#       机读的 inventory.json（消除 PLAN v1 对本脚本的悬空引用）。
#
# ── 只读red线（本脚本对任何 Claude/源文件零写）──────────────────────
#   本脚本只用只读命令：ls / find / du / wc / shasum / cat / grep / stat / df / readlink。
#   grep/stat/df/readlink 同属只读探测（task 的 "仅 ls/find/du/wc/shasum/cat" 是
#   "纯只读"的示例清单，核心约束是"零写"——本脚本不创建/修改/删除任何被盘点的文件）。
#   唯一的写动作是：当显式传入 --json <PATH> 时，把盘点结果写到 <PATH>（一个全新的
#   迁移目录文件，不在任何 Claude/源路径下）。不传 --json 则纯打印、零副作用。
#
# 用法：
#   bash 00-inventory.sh                      # 只打印人类可读报告（零写）
#   bash 00-inventory.sh --json /path/out.json  # 同时写结构化清单
#
# 退出码：0 正常；非 0 仅出现在脚本自身错误（找不到被盘点项不算错，标 [MISSING]）。
# ─────────────────────────────────────────────────────────────────────

set -uo pipefail   # 不用 -e：被盘点项"找不到"是正常情形，要据实标注而非中断

# ── 0. 参数 & 选定哈希命令（修硬伤#1：本机无 sha256sum，且别靠管道短路）──
JSON_OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --json) JSON_OUT="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

if command -v shasum >/dev/null 2>&1; then
  HASH() { shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'; }
  HASH_NAME="shasum -a 256"
elif command -v sha256sum >/dev/null 2>&1; then
  HASH() { sha256sum "$1" 2>/dev/null | awk '{print $1}'; }
  HASH_NAME="sha256sum"
else
  HASH() { echo "NO-HASH-TOOL"; }
  HASH_NAME="(无可用哈希工具)"
fi

# ── 收集 JSON 片段（修硬伤#6：剧本承诺 inventory.json，脚本必须真能产）──
JSON_ROWS=""
add_row() { # add_row <category> <path> <size> <count> <status>
  local esc_path; esc_path=$(printf '%s' "$2" | sed 's/\\/\\\\/g; s/"/\\"/g')
  local row
  row=$(printf '{"category":"%s","path":"%s","size":"%s","count":"%s","status":"%s"}' \
        "$1" "$esc_path" "$3" "$4" "$5")
  if [ -z "$JSON_ROWS" ]; then JSON_ROWS="$row"; else JSON_ROWS="$JSON_ROWS,$row"; fi
}

hr()  { printf '%s\n' "────────────────────────────────────────────────────────"; }
sec() { printf '\n### %s\n'  "$1"; }

# 只读探测一个路径：存在→打印体量；不存在→显式 [MISSING]（修硬伤#7/#11：找不到≠不存在，绝不静默）
probe() { # probe <category> <label> <path>
  local catg="$1" label="$2" p="$3"
  if [ -e "$p" ]; then
    local sz; sz=$(du -sh "$p" 2>/dev/null | awk '{print $1}')
    printf '  [OK]      %-34s %-8s %s\n' "$label" "${sz:-?}" "$p"
    add_row "$catg" "$p" "${sz:-?}" "" "OK"
  else
    printf '  [MISSING] %-34s %-8s %s  ← 找不到≠不存在，请人工确认\n' "$label" "-" "$p"
    add_row "$catg" "$p" "-" "" "MISSING"
  fi
}

CLAUDE="$HOME/.claude"
PROJ="$CLAUDE/projects"
DOCS="$HOME/Documents"

printf '# Kimi 承接迁移 · 阶段 0 只读盘点报告\n'
printf '生成命令：bash 00-inventory.sh %s\n' "${JSON_OUT:+--json $JSON_OUT}"
printf '哈希工具：%s\n' "$HASH_NAME"
printf '只读保证：本脚本对任何 Claude/源文件零写（唯一写动作=显式 --json 输出到迁移目录）。\n'
hr

# ── 1. 全局共享层 ~/.claude/ ──────────────────────────────────────────
sec "1. 全局共享层 ~/.claude/（三项目公共底座）"
probe global "全局行为准则 CLAUDE.md" "$CLAUDE/CLAUDE.md"
if [ -f "$CLAUDE/CLAUDE.md" ]; then
  printf '            行数 %s 行，sha256 %s\n' \
    "$(wc -l < "$CLAUDE/CLAUDE.md" | tr -d ' ')" "$(HASH "$CLAUDE/CLAUDE.md")"
fi
probe global "output-styles/（拉姆 persona）" "$CLAUDE/output-styles"
[ -d "$CLAUDE/output-styles" ] && find "$CLAUDE/output-styles" -maxdepth 1 -type f -print 2>/dev/null \
  | while IFS= read -r f; do printf '              · %s (%s)\n' "$(basename "$f")" "$(du -h "$f" 2>/dev/null | awk '{print $1}')"; done

# skills 现状（agent-reach 生态已于 2026-06-27 整体删除；据实盘当下，不假设内容）
probe global "skills/（本地 skill 真目录）" "$CLAUDE/skills"
if [ -d "$CLAUDE/skills" ]; then
  n=$(find "$CLAUDE/skills" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
  printf '            本地 skill 目录数：%s （注：满屏 superpowers:*/agent-skills:* 等命名空间者来自 plugins/，非本地资产）\n' "$n"
  [ "$n" = "0" ] && printf '            → 现状为空，与"agent-reach 生态 2026-06-27 删除"一致\n'
fi
probe global "hooks/" "$CLAUDE/hooks"
[ -d "$CLAUDE/hooks" ] && find "$CLAUDE/hooks" -maxdepth 1 -type f -print 2>/dev/null \
  | while IFS= read -r f; do printf '              · %s\n' "$(basename "$f")"; done
probe global "settings.json" "$CLAUDE/settings.json"
probe global "settings.local.json" "$CLAUDE/settings.local.json"
probe global "plugins/（非本地资产，登记不迁移）" "$CLAUDE/plugins"

# ── 2. ~/.claude/projects 全部映射目录（MANIFEST 唯一真相，修：枚举不机械反推）──
sec "2. ~/.claude/projects/ 全部映射目录（迁移 MANIFEST 以此枚举为准）"
printf '  说明：路径映射有三模式（标准 /→-、worktree 双 --、子目录无标记），反向有歧义，\n'
printf '       故只枚举不反推；预期 ~11 个目录（9 项目相关 + 2 scratchpad，体量约 403M）。\n'
if [ -d "$PROJ" ]; then
  total_dirs=0
  # 不用 head 截断（修硬伤#11）：全量枚举
  while IFS= read -r d; do
    [ -d "$d" ] || continue
    total_dirs=$((total_dirs+1))
    name=$(basename "$d")
    sz=$(du -sh "$d" 2>/dev/null | awk '{print $1}')
    root_jsonl=$(find "$d" -maxdepth 1 -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')
    all_jsonl=$(find "$d" -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')
    if [ -d "$d/memory" ]; then
      mem=$(find "$d/memory" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
      memnote="memory:${mem}md"
    else
      memnote="memory:无"
    fi
    printf '  · %-58s %-7s jsonl根级%s/递归%s  %s\n' "$name" "${sz:-?}" "$root_jsonl" "$all_jsonl" "$memnote"
    add_row projects-map "$d" "${sz:-?}" "jsonl_root=${root_jsonl};jsonl_all=${all_jsonl};${memnote}" "OK"
  done < <(find "$PROJ" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort)
  printf '  映射目录总数：%s（与预期 ~11 对账；含子目录后 jsonl"递归">"根级"即存在 subagents/workflows 嵌套）\n' "$total_dirs"
  printf '  全部 memory 目录（归并范围）：\n'
  find "$PROJ" -type d -name memory 2>/dev/null | while IFS= read -r m; do printf '      · %s\n' "$m"; done
else
  probe projects-map "projects 根目录" "$PROJ"
fi

# ── 3. 三仓 + zzz-mac 仓内实体（amazon-fba 自建记忆系统多点深挖）──────
sec "3. 项目仓内实体盘点"

probe repo "项目1 agents 仓内 CLAUDE.md" "$DOCS/agents/CLAUDE.md"   # 预期 MISSING（行为靠全局+记忆）
probe repo "项目1 .roundtable/（gitignored 圆桌活记忆，必须显式镜像）" "$DOCS/agents/.roundtable"
probe repo "项目1 loop-engine 本体" "$DOCS/agents/skills/loop-engine"

printf '\n  -- 项目2 amazon-fba 自建记忆系统（最难，多点探查，找不到≠没有）--\n'
FBA="$DOCS/amazon-fba-workflow"
probe fba "仓内 CLAUDE.md（L1 规则 + L2 自重写状态块）" "$FBA/CLAUDE.md"
probe fba "SQLite 单一真相源 data/fba.db" "$FBA/data/fba.db"
probe fba "StateMachine 强制入口 src/state_machine.py" "$FBA/src/state_machine.py"
if [ -d "$FBA/candidates" ]; then
  c=$(find "$FBA/candidates" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
  printf '  [OK]      candidates/ 派生视图目录数              %s\n' "$c"
  add_row fba "$FBA/candidates" "" "dirs=$c" "OK"
else
  probe fba "candidates/（派生视图）" "$FBA/candidates"
fi
if [ -d "$FBA/config" ]; then
  y=$(find "$FBA/config" -name '*.yaml' 2>/dev/null | wc -l | tr -d ' ')
  printf '  [OK]      config/*.yaml（含子目录 validation/）   %s 个\n' "$y"
  add_row fba "$FBA/config" "" "yaml=$y" "OK"
else
  probe fba "config/（config-as-memory）" "$FBA/config"
fi
probe fba "decisions/（decision-log + dated docs）" "$FBA/decisions"
for sub in agents commands skills; do
  if [ -d "$FBA/.claude/$sub" ]; then
    if [ "$sub" = "skills" ]; then
      n=$(find "$FBA/.claude/$sub" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
    else
      n=$(find "$FBA/.claude/$sub" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
    fi
    printf '  [OK]      .claude/%-10s（Claude 专属，需转换/重写） %s\n' "$sub" "$n"
    add_row fba "$FBA/.claude/$sub" "" "count=$n" "OK"
  else
    probe fba ".claude/$sub" "$FBA/.claude/$sub"
  fi
done
# 根级遗留（备查，迁移按 MANIFEST 枚举，勿臆断其语义）
probe fba "根级遗留 decisions.db（疑独立于 data/fba.db）" "$FBA/decisions.db"

printf '\n  -- 项目3 finance（amazon-fba 轻量同构版）--\n'
FIN="$DOCS/finance"
probe fin "仓内 CLAUDE.md" "$FIN/CLAUDE.md"
probe fin "data/finance.db" "$FIN/data/finance.db"
probe fin ".claude/（预期仅 settings，无 agents/commands/skills）" "$FIN/.claude"

printf '\n  -- 第四项目 zzz-mac（源目录已删，仅 Claude 会话史残留）--\n'
probe zzz "源目录（预期 MISSING=已删/已移动）" "$DOCS/zzz-mac"
printf '            会话史映射见 §2 的 -Users-melee-Documents-zzz-mac；迁移前需用户决定保留/丢弃\n'

# ── 4. 不变式钩子接线验证（修 hermes 关注点：CLAUDE.md 自述≠运行事实）──
sec "4. SessionStart 不变式钩子真实接线核验（grep settings，非读 CLAUDE.md 推断）"
for sf in "$CLAUDE/settings.json" "$CLAUDE/settings.local.json"; do
  if [ -f "$sf" ]; then
    printf '  %s 中的 SessionStart 接线：\n' "$sf"
    grep -niE 'SessionStart|hooks?' "$sf" 2>/dev/null | sed 's/^/      /' || printf '      （未匹配到 hooks 相关键）\n'
  fi
done
# amazon-fba 项目级 settings 的不变式扫描接线
for sf in "$FBA/.claude/settings.json" "$FBA/.claude/settings.local.json"; do
  if [ -f "$sf" ]; then
    printf '  %s 中的 SessionStart/不变式接线：\n' "$sf"
    grep -niE 'SessionStart|invariant|不变式|audit|hooks' "$sf" 2>/dev/null | sed 's/^/      /' || printf '      （未匹配，CLAUDE.md 所述 F/G/H 不变式可能仅为设计意图未接线）\n'
  fi
done

# ── 5. 软链核验（修：~/.local/bin/roundtable 软链由记忆佐证，物理 readlink 落实）──
sec "5. 关键软链核验"
if [ -L "$HOME/.local/bin/roundtable" ]; then
  printf '  [OK]      ~/.local/bin/roundtable → %s\n' "$(readlink "$HOME/.local/bin/roundtable")"
else
  probe symlink "~/.local/bin/roundtable 软链" "$HOME/.local/bin/roundtable"
fi

# ── 6. 磁盘预检（修硬伤#10：镜像目标至少需源体量×2）──────────────────
sec "6. 磁盘空间预检（镜像+过滤产物估算需 projects 体量 ×2）"
printf '  ~/.claude/projects 总体量：%s\n' "$(du -sh "$PROJ" 2>/dev/null | awk '{print $1}')"
printf '  迁移目标盘可用空间：\n'
df -h "$HOME" 2>/dev/null | sed 's/^/      /'

# ── 7. 结构化产物 inventory.json（可选）──────────────────────────────
if [ -n "$JSON_OUT" ]; then
  sec "7. 写结构化清单"
  out_dir=$(dirname "$JSON_OUT")
  if [ -d "$out_dir" ] || mkdir -p "$out_dir" 2>/dev/null; then
    printf '{"generated_by":"00-inventory.sh","hash_tool":"%s","rows":[%s]}\n' "$HASH_NAME" "$JSON_ROWS" > "$JSON_OUT"
    printf '  已写 %s\n' "$JSON_OUT"
  else
    printf '  [ERR] 无法创建输出目录 %s（仅此一处写动作失败，不影响只读盘点）\n' "$out_dir" >&2
  fi
fi

hr
printf '盘点完成。所有 [MISSING] 项请人工确认"找不到≠不存在"；JSON 见 %s\n' "${JSON_OUT:-（未指定 --json，仅打印）}"
