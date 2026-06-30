#!/usr/bin/env bash
# _lib.sh — loop-engine 圆桌共享库。被其余脚本 source，勿单独执行。
# 职责：参数校验、目标仓库定位、会议桌(.roundtable)目录、日志、VERDICT 解析、配置默认。

set -euo pipefail

# 强制 UTF-8 locale：否则中文（多字节）紧邻 $变量 时，C locale 下 bash 会把
# 多字节首字节误并入变量名，导致 "unbound variable"。各脚本均先 source 本库，
# 故此 export 在后续行被解析前已生效。
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="en_US.UTF-8"

# ---- 配置默认值（可被环境变量覆盖，见 spec §8）----
: "${LOOP_MAX_ITERS:=5}"
: "${LOOP_STUCK_LIMIT:=2}"
: "${LOOP_REVIEW_PROVIDER:=deepseek}"
: "${LOOP_REVIEW_MODEL:=deepseek-reasoner}"
: "${LOOP_TEST_CMD:=}"

# 会议桌目录名（黑板）
LOOP_TABLE_DIRNAME=".roundtable"

# 当前 loop-engine/bin 目录。函数可能被 source 到不同调用脚本里，故在库内自算。
LOOP_BIN_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---- 日志：一律走 stderr，stdout 留给 agent 原始输出 ----
loop_log()  { printf '\033[2m[loop-engine] %s\033[0m\n' "$*" >&2; }
loop_warn() { printf '\033[33m[loop-engine] %s\033[0m\n' "$*" >&2; }
loop_die()  { printf '\033[31m[loop-engine] 错误: %s\033[0m\n' "$*" >&2; exit 1; }

# ---- 定位目标仓库：第一个参数，必须是 git 仓库 ----
loop_resolve_repo() {
  local repo="${1:-}"
  [ -n "$repo" ] || loop_die "缺少目标仓库路径（第一个参数）"
  [ -d "$repo" ] || loop_die "目标仓库不存在: $repo"
  repo="$(cd "$repo" && pwd)"
  git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || loop_die "目标不是 git 仓库: ${repo} (圆桌依赖 git 历史当记忆)"
  printf '%s' "$repo"
}

# ---- 会议桌根目录：<repo>/.roundtable/ ----
loop_root() { printf '%s' "$1/$LOOP_TABLE_DIRNAME"; }

# ---- 会话目录：<repo>/.roundtable/sessions/<会话id>/（含 KB / minutes）----
# 会话 id 由 conductor 经 LOOP_SESSION 下传；standalone 调用回退到 default。
# 记忆按「项目（仓库）」+「会话」两级隔离。
loop_table_dir() {
  local repo="$1" sid="${LOOP_SESSION:-default}"
  local dir="$repo/$LOOP_TABLE_DIRNAME/sessions/$sid"
  mkdir -p "$dir/KB" "$dir/minutes"
  printf '%s' "$dir"
}

# ---- 当前轮次：从会话的 roundtable.json 读，缺省 1 ----
loop_iter() {
  local sf; sf="$(loop_table_dir "$1")/roundtable.json"
  if [ -f "$sf" ] && command -v python3 >/dev/null 2>&1; then
    python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('iter',1))" "$sf" 2>/dev/null || echo 1
  else
    echo 1
  fi
}

# ---- 用 python3 安全更新 roundtable.json 的某个键（值按字面写入）----
# 用法: loop_state_set <repo> <key> <value-as-python-literal>
loop_state_set() {
  local repo="$1" key="$2" val="$3" sf; sf="$(loop_table_dir "$repo")/roundtable.json"
  command -v python3 >/dev/null 2>&1 || { loop_warn "无 python3，跳过 state 更新"; return 0; }
  python3 - "$sf" "$key" "$val" <<'PY'
import json,sys,os
sf,key,val=sys.argv[1],sys.argv[2],sys.argv[3]
d={}
if os.path.exists(sf):
    try: d=json.load(open(sf))
    except Exception: d={}
try: v=json.loads(val)        # 尝试当 JSON 解析（数字/bool/列表）
except Exception: v=val       # 否则当字符串
d[key]=v
json.dump(d,open(sf,'w'),ensure_ascii=False,indent=2)
PY
}

# ---- 从 agent 输出文件抽 VERDICT 行，落实退出码约定（0=PASS 2=BLOCK 1=ERR）----
# 注：行首容忍空白；整行 Markdown 加粗也容忍，避免只读席位把最终裁决写成 **VERDICT: PASS**。
loop_verdict_exit() {
  local f="$1" line
  line="$(grep -aiE '^[[:space:]]*(\*\*)?VERDICT:[[:space:]]*(PASS|BLOCK)(\*\*)?[[:space:]]*$' "$f" | tail -1 || true)"
  if   printf '%s' "$line" | grep -qiE 'PASS';  then loop_log "裁决: PASS";  return 0
  elif printf '%s' "$line" | grep -qiE 'BLOCK'; then loop_warn "裁决: BLOCK"; return 2
  else loop_warn "未找到 VERDICT 行——按 ERR 处理，请人工读完整 minutes"; return 1
  fi
}

# ---- codex review 专用裁决：codex 有自己的输出格式([P0]/[P1] 优先级)，不理会 VERDICT 行 ----
# 退出码约定 0=PASS 2=BLOCK 1=ERR。调用前应确认 codex 进程已成功(rc=0)。
loop_codex_verdict() {
  local f="$1"
  # 1) 若 codex 某版本听话给了显式 VERDICT 行，优先
  if grep -aiqE '^[[:space:]]*(\*\*)?VERDICT:[[:space:]]*BLOCK(\*\*)?[[:space:]]*$' "$f"; then loop_warn "裁决: BLOCK (显式 VERDICT)"; return 2; fi
  if grep -aiqE '^[[:space:]]*(\*\*)?VERDICT:[[:space:]]*PASS(\*\*)?[[:space:]]*$'  "$f"; then loop_log  "裁决: PASS (显式 VERDICT)"; return 0; fi
  # 2) 回退解析 codex 原生高危标记 [P0]/[P1]（=Critical/High）→ BLOCK
  if grep -aqE '\[P[01]\]' "$f"; then loop_warn "裁决: BLOCK (codex 标出 P0/P1 高危)"; return 2; fi
  # 3) 无高危标记 → PASS
  loop_log "裁决: PASS (codex 未标出 P0/P1 高危)"; return 0
}

# ---- 通用：要求某命令存在 ----
loop_need() { command -v "$1" >/dev/null 2>&1 || loop_die "找不到依赖命令: $1"; }

# ---- 发布座位纪要：默认写脱敏版本；仅显式 LOOP_KEEP_RAW_MINUTES=1 时保留 .raw ----
loop_publish_minutes() {
  local raw="$1" out="$2" tmp
  [ -f "$raw" ] || loop_die "待发布纪要不存在: $raw"
  if [ "${LOOP_KEEP_RAW_MINUTES:-0}" = "1" ]; then
    cp "$raw" "${out}.raw"
  fi
  tmp="${out}.redacted.$$"
  if command -v python3 >/dev/null 2>&1 && python3 "${LOOP_BIN_DIR}/redact-text.py" <"$raw" >"$tmp" 2>/dev/null; then
    mv "$tmp" "$out"
  else
    rm -f "$tmp"
    {
      printf '%s\n' "[loop-engine] minutes redaction failed; raw transcript withheld."
      printf '%s\n' "[loop-engine] Re-run with LOOP_KEEP_RAW_MINUTES=1 only for local debugging."
    } >"$out"
  fi
}

# ---- 给座位发言的统一头部（让外脑知道黑板在哪、规矩是什么）----
# 用法: loop_seat_preamble <repo>
loop_seat_preamble() {
  local repo="$1" rel=".roundtable/sessions/${LOOP_SESSION:-default}"
  cat <<EOF
你正受邀参加一个"圆桌会议"（Loop Engineering 黑板架构）。这是一次性发言，不是对话。
共享知识库（黑板）在仓库内 \`${rel}/KB/\`：
  - project.md          项目背景/架构/约定
  - task.md             本轮任务与验收标准
  - state.md            当前进度/已做决策/开放问题
  - roster.md           在座各 agent 的特长
  - imported-memory.md  从仓库外汇集的项目记忆（CLAUDE.md / Claude 项目记忆 / 过往会话结论）
  - diff.patch          本轮改动
  - test-results.txt    最新测试输出
请**自行读取**这些文件以及仓库源码来获取你需要的信息（self-serve），不要假设上下文已在本 prompt 里给全。
EOF
}
