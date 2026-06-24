#!/usr/bin/env bash
# seat-chat.sh — 纯脑评审席：把 diff/任务直接喂给一个 chat 接口，无 agentic 手脚，快。
# 适合"只要脑子、不要 codex 翻代码跑命令"的验证场景。默认走 DeepSeek 直连；
# 端点通用（OpenAI 兼容），有别家 key 时设 LOOP_CHAT_BASE_URL/KEY/MODEL 即可（含将来的 gpt-5.5）。
# 用法: seat-chat.sh <repo> review
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

REPO="$(loop_resolve_repo "${1:-}")"
MODE="${2:-review}"
[ "${MODE}" = "review" ] || loop_die "seat-chat 只支持 review（纯脑评审）"
TABLE="$(loop_table_dir "${REPO}")"
ITER="$(loop_iter "${REPO}")"
OUT="${TABLE}/minutes/iter-${ITER}-chat-review.md"

# 端点配置：默认 DeepSeek（从 ~/.hermes/.env 读 key/url），可被 LOOP_CHAT_* 覆盖
ENVF="${HOME}/.hermes/.env"
KEY="${LOOP_CHAT_KEY:-$(grep -E '^DEEPSEEK_API_KEY=' "${ENVF}" 2>/dev/null | cut -d= -f2-)}"
URL="${LOOP_CHAT_BASE_URL:-$(grep -E '^DEEPSEEK_BASE_URL=' "${ENVF}" 2>/dev/null | cut -d= -f2-)}"
URL="${URL:-https://api.deepseek.com}"
MODEL="${LOOP_CHAT_MODEL:-deepseek-reasoner}"
[ -n "${KEY}" ] || loop_die "无 chat API key（设 LOOP_CHAT_KEY 或 ~/.hermes/.env 的 DEEPSEEK_API_KEY）"

loop_log "chat 评审席入席 iter=${ITER}（${MODEL} 直连·纯脑无工具）…"
set +e
python3 - "${URL}" "${KEY}" "${MODEL}" "${TABLE}" "${OUT}" <<'PY'
import json, sys, pathlib, urllib.request
url, key, model, table, out = sys.argv[1:6]
kb = pathlib.Path(table) / "KB"
def rd(name, limit=200000):
    p = kb / name
    return p.read_text(encoding="utf-8", errors="replace")[:limit] if p.exists() else ""
task = rd("task.md"); diff = rd("diff.patch"); proj = rd("project.md", 4000); imp = rd("imported-memory.md", 6000)
sys_p = ("你是独立代码验证员（圆桌评审席）。只读评审——所有信息都在下面给你，不要假设能跑代码或翻仓库。"
         "审查 diff 的正确性、安全性、是否满足验收标准、有无回归。按严重度标注每条发现 [CRITICAL]/[HIGH]/[MEDIUM]/[LOW] 并指出文件:行。"
         "最后必须单独成行输出：无 HIGH 或 CRITICAL → 'VERDICT: PASS'，否则 'VERDICT: BLOCK'。")
usr = f"# 任务与验收标准\n{task}\n\n# 项目背景/记忆\n{proj}\n{imp}\n\n# 本轮改动 diff\n{diff}\n\n请评审上面的改动并给出裁决。"
body = json.dumps({"model": model, "messages": [{"role": "system", "content": sys_p},
                   {"role": "user", "content": usr}], "max_tokens": 4000, "stream": False}).encode()
req = urllib.request.Request(url.rstrip("/") + "/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
try:
    r = urllib.request.urlopen(req, timeout=180)
    d = json.loads(r.read())
    txt = d.get("choices", [{}])[0].get("message", {}).get("content", "") or "(空回复)"
except Exception as e:
    txt = f"(chat 评审请求失败: {e})\nVERDICT: BLOCK"
pathlib.Path(out).write_text(txt, encoding="utf-8")
PY
rc=$?
set -e
cat "${OUT}" 2>/dev/null
loop_log "chat 退出码=${rc}，纪要: ${OUT}"
[ "${rc}" -eq 0 ] || { loop_warn "chat 请求异常 rc=${rc}，判 ERR"; exit 1; }
loop_verdict_exit "${OUT}"; exit $?
