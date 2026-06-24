#!/usr/bin/env bash
# seat-codex.sh — 请 codex（GPT-5.5，原生壳）入席圆桌
# 用法: seat-codex.sh <repo> review|exec ["<额外 brief>"]
#   review: 跑 codex exec review --uncommitted，出 VERDICT；退出码 0=PASS 2=BLOCK 1=ERR
#   exec  : 跑 codex exec，让 codex 在仓库里实施子任务
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "${SCRIPT_DIR}/_lib.sh"
loop_need codex

REPO="$(loop_resolve_repo "${1:-}")"
MODE="${2:-review}"
BRIEF="${3:-}"
TABLE="$(loop_table_dir "${REPO}")"
ITER="$(loop_iter "${REPO}")"
PRE="$(loop_seat_preamble "${REPO}")"

# 可选推理强度旋钮：LOOP_CODEX_EFFORT=low|medium|high|xhigh（默认沿用 ~/.codex/config.toml）
CODEX_OPTS=()
# 默认沿用 ~/.codex/config.toml 的推理档（用户偏好 xhigh 满血）；要更快才显式设 LOOP_CODEX_EFFORT=low|medium。
# 提速的正路是给验证席换快模型（如 DeepSeek），而非把 codex 调蠢。
[ -n "${LOOP_CODEX_EFFORT:-}" ] && CODEX_OPTS+=(-c "model_reasoning_effort=${LOOP_CODEX_EFFORT}")
[ -n "${LOOP_SEAT_MODEL:-}" ] && CODEX_OPTS+=(-m "${LOOP_SEAT_MODEL}")

case "${MODE}" in
  review)
    OUT="${TABLE}/minutes/iter-${ITER}-codex-review.md"
    INSTR="${PRE}

你的角色：**独立代码验证员**（圆桌验证席）。
请审查当前工作树中**未提交的改动**（运行 git diff 查看，亦见 KB/diff.patch）的：正确性、安全性、是否满足 KB/task.md 的验收标准、是否引入回归。
每条发现按严重度标注：[CRITICAL] / [HIGH] / [MEDIUM] / [LOW]，并指出文件与行。
${BRIEF:+本轮额外关注：${BRIEF}}

**最后必须单独成行输出**（该行只放裁决，不要别的内容）：
- 若无 HIGH 或 CRITICAL 级问题 → VERDICT: PASS
- 否则 → VERDICT: BLOCK"
    loop_log "codex 验证席入席 iter=${ITER}，运行 codex exec review"
    set +e
    ( cd "${REPO}" && codex exec review ${CODEX_OPTS[@]+"${CODEX_OPTS[@]}"} "${INSTR}" ) >"${OUT}" 2>&1
    rc=$?
    set -e
    cat "${OUT}"
    loop_log "codex 退出码=${rc}，纪要: ${OUT}"
    if [ "${rc}" -ne 0 ]; then
      loop_warn "codex 进程非零退出 rc=${rc}，判 ERR（多半是用法/网络问题，请人工读 minutes）"
      exit 1
    fi
    loop_codex_verdict "${OUT}"; exit $?
    ;;
  exec)
    [ -n "${BRIEF}" ] || loop_die "exec 模式需要第三个参数：子任务 brief"
    OUT="${TABLE}/minutes/iter-${ITER}-codex-exec.md"
    INSTR="${PRE}

你的角色：**执行席**。请完成下述子任务，并直接在仓库里实施改动（写出干净、符合现有风格的代码）：
${BRIEF}"
    loop_log "codex 执行席入席 iter=${ITER}，运行 codex exec（workspace-write 沙箱）"
    set +e
    # -s workspace-write：允许在工作区写文件（否则默认 read-only 会卡在写不动）
    ( cd "${REPO}" && codex exec -s workspace-write ${CODEX_OPTS[@]+"${CODEX_OPTS[@]}"} "${INSTR}" ) >"${OUT}" 2>&1
    rc=$?
    set -e
    cat "${OUT}"
    loop_log "codex 退出码=${rc}，纪要: ${OUT}"
    exit "${rc}"
    ;;
  *)
    loop_die "未知 MODE: ${MODE}（应为 review|exec）"
    ;;
esac
