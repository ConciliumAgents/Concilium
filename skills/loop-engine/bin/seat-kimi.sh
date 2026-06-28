#!/usr/bin/env bash
# seat-kimi.sh — 请 Kimi Code（K2.7，Moonshot 异质血统，原生壳）以 headless 方式入席圆桌
# kimi 与 claude/codex/hermes 平级，由独立指挥程序调用，从黑板自取上下文。
# 用法: seat-kimi.sh <repo> plan|exec|review "<brief>" [provider] [model]
#   plan  : 总指挥——读 KB+花名册，输出 JSON 派活计划（只读：不给 -y）
#   exec  : 执行席——实施子任务（kimi -y 自动批准，可落盘）
#   review: 验证席——只读评审（不给 -y + prompt 约束只读），出 VERDICT
# 实测固化的非显然事实（改脚本务必照办）：
#   - kimi 的 `-p`（headless 单轮）与 `--plan`/`-y`/`--auto` 全部互斥（"Cannot combine --prompt with ..."）。
#     `-p` 本身即非交互自动执行模式：默认权限下既能读、也能写/落盘，无需任何提权标志。
#     故 exec 用纯 `kimi -p`；plan/review 的「只读」纯靠 prompt 约束（同 hermes 不给 --yolo 的信任模型）。
#   - kimi headless 文本输出整体带前导缩进，VERDICT 行非顶格 → 裁决靠 _lib 的 loop_verdict_exit（已容忍行首空白）。
#   - kimi 只有 managed:kimi-code 一个 provider，故忽略 provider 参数，仅吃 model（-m）。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "${SCRIPT_DIR}/_lib.sh"
loop_need kimi

REPO="$(loop_resolve_repo "${1:-}")"
MODE="${2:-exec}"
BRIEF="${3:-}"
MODEL="${5:-${LOOP_SEAT_MODEL:-}}"
TABLE="$(loop_table_dir "${REPO}")"
ITER="$(loop_iter "${REPO}")"
PRE="$(loop_seat_preamble "${REPO}")"

# 模型覆盖（默认用 config.toml 的 default_model）
KM_OPTS=()
[ -n "${MODEL}" ] && KM_OPTS+=(-m "${MODEL}")

# 清理 kimi 会话残留：圆桌产出已存进黑板 minutes，kimi 侧那条会话是冗余「垃圾」。
# kimi 无官方删除命令 → 从本次输出抓 session id（"To resume: kimi -r session_…"），
# 删其 sessionDir + 从 session_index.jsonl 移除该行。
# 安全护栏：只删 ~/.kimi-code/sessions/ 子树内、且 sessionId 精确匹配本次的那条，绝不碰你的其他会话。
# 设 LOOP_KIMI_KEEP_SESSION 非空可保留。
_km_clean() {
  [ -n "${LOOP_KIMI_KEEP_SESSION:-}" ] && return 0
  local out="${1:-}" sid
  [ -f "${out}" ] || return 0
  sid="$(grep -oiE 'session_[0-9a-f-]{30,}' "${out}" 2>/dev/null | tail -1 || true)"
  [ -n "${sid}" ] || return 0
  python3 - "${HOME}/.kimi-code/session_index.jsonl" "${sid}" "${HOME}/.kimi-code/sessions" <<'PY' || return 0
import json, os, sys, shutil
idx, sid, sroot = sys.argv[1], sys.argv[2], os.path.realpath(sys.argv[3])
if not os.path.exists(idx):
    sys.exit(0)
keep, removed = [], False
for line in open(idx, encoding="utf-8"):
    s = line.rstrip("\n")
    if not s.strip():
        continue
    try:
        d = json.loads(s)
    except Exception:
        keep.append(s); continue
    if d.get("sessionId") == sid:
        sd = os.path.realpath(d.get("sessionDir", ""))
        if sd.startswith(sroot + os.sep):        # 只删 sessions/ 子树内，路径异常则保守保留
            if os.path.isdir(sd):
                shutil.rmtree(sd, ignore_errors=True)
            removed = True
        else:
            keep.append(s)
    else:
        keep.append(s)
if removed:
    with open(idx, "w", encoding="utf-8") as f:
        f.write("".join(l + "\n" for l in keep))
PY
  loop_log "已清理 kimi 残留会话 ${sid}"
}

case "${MODE}" in
  plan)
    OUT="${TABLE}/minutes/iter-${ITER}-kimi-plan.md"
    INSTR="${PRE}

你的角色：**项目总指挥**（只读：仅阅读与规划，不要修改任何文件）。请阅读 KB/task.md、KB/project.md、KB/roster.md（各 agent 的特长花名册）与仓库，
把本任务拆成若干子任务，并**按每个 agent 的特长**分派。可用座位：claude、codex、hermes、kimi。
原则：**执行一律优先派 hermes/kimi（飞毛腿，快）；claude、codex 只指挥/验证、不执行**（claude 揽 exec 会超时空转）。
${BRIEF:+补充：${BRIEF}}

**输出要求**：先简述思路，最后用一个 \`\`\`json 代码块输出派活计划，形如：
\`\`\`json
[{\"agent\":\"hermes\",\"subtask\":\"……\"},{\"agent\":\"kimi\",\"subtask\":\"……\"}]
\`\`\`
只在该 JSON 块里放计划，agent 字段必须是 claude/codex/hermes/kimi 之一；执行子任务请只派 hermes/kimi。"
    loop_log "Kimi 总指挥席入席 iter=${ITER}（plan，只读）"
    set +e
    ( cd "${REPO}" && kimi -p "${INSTR}" ${KM_OPTS[@]+"${KM_OPTS[@]}"} ) >"${OUT}" 2>&1
    rc=$?
    set -e
    cat "${OUT}"
    loop_log "kimi 退出码=${rc}，纪要: ${OUT}"
    _km_clean "${OUT}"
    exit "${rc}"
    ;;
  exec)
    [ -n "${BRIEF}" ] || loop_die "exec 模式需要第三个参数：子任务 brief"
    OUT="${TABLE}/minutes/iter-${ITER}-kimi-exec.md"
    INSTR="${PRE}

你的角色：**执行席**。请完成下述子任务，直接在仓库里实施改动（干净、符合现有风格）。
完成后在 KB/state.md 简述你做了什么。删除/不可逆/对外/花钱类操作不要做，留给人工。
子任务：${BRIEF}

**完成后请在纪要末尾另起一节，写入：**
## 教训
### 通用
- （本次值得归档的通用协作/流程教训，一条一行；无则写\"（无）\"）
### <项目名>
- （本次项目专属教训；无则写\"（无）\"）
"
    loop_log "Kimi 执行席入席 iter=${ITER}（exec，-p 默认权限即可落盘）"
    set +e
    ( cd "${REPO}" && kimi -p "${INSTR}" ${KM_OPTS[@]+"${KM_OPTS[@]}"} ) >"${OUT}" 2>&1
    rc=$?
    set -e
    cat "${OUT}"
    loop_log "kimi 退出码=${rc}，纪要: ${OUT}"
    _km_clean "${OUT}"
    exit "${rc}"
    ;;
  review)
    OUT="${TABLE}/minutes/iter-${ITER}-kimi-review.md"
    INSTR="${PRE}

你的角色：**第二评审席**（独立复审）。**只读、不要修改任何文件、不要运行有副作用的命令。**
审查本轮未提交改动的正确性/安全性/是否满足验收标准。
若 BRIEF 标明有座位失败/子任务未执行，请据**任务完整性是否受损**裁决：任务已由其余座位完成则不应因个别失败机械 BLOCK。${BRIEF:+额外关注：${BRIEF}}
按严重度标注：[CRITICAL]/[HIGH]/[MEDIUM]/[LOW]。
**最后必须单独成行输出**：无 HIGH/CRITICAL → VERDICT: PASS；否则 → VERDICT: BLOCK"
    loop_log "Kimi 验证席入席 iter=${ITER}（review，只读）"
    set +e
    ( cd "${REPO}" && kimi -p "${INSTR}" ${KM_OPTS[@]+"${KM_OPTS[@]}"} ) >"${OUT}" 2>&1
    rc=$?
    set -e
    cat "${OUT}"
    loop_log "kimi 退出码=${rc}，纪要: ${OUT}"
    _km_clean "${OUT}"
    [ "${rc}" -ne 0 ] && { loop_warn "kimi 进程非零退出 rc=${rc}，判 ERR（多半用法/网络问题，请人工读 minutes）"; exit 1; }
    loop_verdict_exit "${OUT}"; exit $?
    ;;
  *)
    loop_die "未知 MODE: ${MODE}（应为 plan|exec|review）"
    ;;
esac
