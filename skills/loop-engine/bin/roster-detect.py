#!/usr/bin/env python3
"""roster-detect.py — 圆桌座位探测器（地基）。

探测本地有哪些 agent 可上桌，各自**实际配置可用**的模型列表（不是全量目录）、
当前默认模型、支持哪些 mode。输出人类表格（默认）或 `--json`（供 TUI/WebUI/conductor 消费）。
纯本地探测，不调用任何 agent 干活。仅 Python 标准库。

每个座位的 JSON 含 models: [{"provider":..., "model":..., "default":bool}]，供 UI 做下拉。
"""
from __future__ import annotations
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path

HOME = Path.home()


def _run(cmd, timeout=15):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return f"(探测失败: {e})"


def detect_claude():
    path = shutil.which("claude")
    d = {"seat": "claude", "available": bool(path), "path": path or "",
         "modes": ["plan", "exec", "review"], "provider": "anthropic", "models": []}
    if not path:
        return d
    d["version"] = (_run([path, "--version"], 8).strip().splitlines() or [""])[0]
    tiers = ["opus", "sonnet", "haiku", "fable"]
    d["models"] = [{"provider": "anthropic", "model": m, "default": (m == "opus")} for m in tiers]
    d["model"] = "opus"
    d["strength"] = "编排/规划/综合、长上下文、多文件重构"
    return d


def detect_codex():
    path = shutil.which("codex")
    d = {"seat": "codex", "available": bool(path), "path": path or "",
         "modes": ["exec", "review"], "provider": "openai", "models": []}
    if not path:
        return d
    d["version"] = (_run([path, "--version"], 8).strip().splitlines() or [""])[0]
    cfg = HOME / ".codex" / "config.toml"
    model, effort = "gpt-5.5", ""
    if cfg.exists():
        try:
            import tomllib
            t = tomllib.loads(cfg.read_text())
            model = str(t.get("model", model)); effort = str(t.get("model_reasoning_effort", ""))
        except Exception:
            txt = cfg.read_text()
            m = re.search(r'model\s*=\s*"([^"]+)"', txt); model = m.group(1) if m else model
            e = re.search(r'model_reasoning_effort\s*=\s*"([^"]+)"', txt); effort = e.group(1) if e else ""
    d["model"] = model; d["effort"] = effort
    # codex 不好枚举全量；给当前模型 + 同后端缓存里的几个备选（若有）
    opts = [model]
    cache = HOME / ".hermes" / "provider_models_cache.json"
    if cache.exists():
        try:
            c = json.load(open(cache)).get("openai-codex", {}).get("models", [])
            opts += [m for m in c if m not in opts]
        except Exception:
            pass
    d["models"] = [{"provider": "openai", "model": m, "default": (m == model)} for m in opts[:6]]
    d["strength"] = "代码验证/挑致命缺陷（codex exec review）、强编码"
    return d


def _hermes_credentialed(status: str):
    """从 hermes status 里解析「有凭证/已登录」的后端显示名（只看 API Keys / Auth Providers 段）。"""
    creds, sec = set(), None
    for line in status.splitlines():
        if "API Keys" in line: sec = "k"
        elif "Auth Providers" in line: sec = "a"
        elif line.strip().startswith("◆"): sec = None
        elif sec and "✓" in line and "file" not in line.lower():
            creds.add(re.sub(r"✓.*", "", line).strip().lower())
    return creds


def detect_hermes():
    path = shutil.which("hermes")
    d = {"seat": "hermes", "available": bool(path), "path": path or "",
         "modes": ["exec", "review"], "models": []}
    if not path:
        return d
    d["version"] = (_run([path, "--version"], 8).strip().splitlines() or [""])[0]
    status = _run([path, "status"], 20)
    m = re.search(r"Model:\s*([^\n]+)", status); cur_model = (m.group(1).strip() if m else "")
    p = re.search(r"Provider:\s*([^\n]+)", status); cur_prov = (p.group(1).strip() if p else "")
    d["model"] = cur_model; d["provider"] = cur_prov
    creds = _hermes_credentialed(status)
    # 凭证显示名 → cache provider id
    alias = {"openai codex": "openai-codex", "deepseek": "deepseek", "anthropic": "anthropic",
             "gemini": "gemini", "copilot": "copilot", "openrouter": "openrouter", "xai / grok": "xai"}
    cache = {}
    cf = HOME / ".hermes" / "provider_models_cache.json"
    if cf.exists():
        try: cache = json.load(open(cf))
        except Exception: cache = {}
    models = []
    cur_pid = alias.get(cur_prov.lower(), cur_prov.lower())
    for cred in creds:
        pid = alias.get(cred)
        if not pid or pid not in cache:
            continue
        for mod in (cache[pid].get("models", []) or [])[:6]:
            models.append({"provider": pid, "model": mod, "default": (pid == cur_pid and mod == cur_model)})
    # 若缓存没覆盖到当前默认，至少把默认放进去
    if cur_model and not any(x["default"] for x in models):
        models.insert(0, {"provider": cur_pid, "model": cur_model, "default": True})
    d["models"] = models
    d["strength"] = "工具广度（浏览器/computer-use/消息/记忆）；可切异质后端做复审"
    return d


def detect_all():
    return [detect_claude(), detect_codex(), detect_hermes()]


def print_table(seats):
    print("\n圆桌座位探测结果")
    print("=" * 64)
    for s in seats:
        mark = "✓" if s.get("available") else "✗"
        print(f"{mark} {s['seat']:<8} {s.get('version','') or '(未装)'}")
        if not s.get("available"):
            continue
        print(f"    当前默认 : {s.get('model','')} via {s.get('provider','')}"
              + (f"  [{s['effort']}]" if s.get("effort") else ""))
        print(f"    可任模式 : {', '.join(s.get('modes', []))}")
        ms = s.get("models", [])
        if ms:
            shown = ", ".join((("●" if x.get("default") else "") + x["model"]) for x in ms)
            print(f"    可选模型 : {shown}")
        print(f"    特长     : {s.get('strength','')}")
    print("=" * 64)
    avail = [s["seat"] for s in seats if s.get("available")]
    print(f"可上桌座位: {', '.join(avail) or '（无！请先安装至少一个 agent）'}")


def main():
    ap = argparse.ArgumentParser(description="圆桌座位探测器")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    seats = detect_all()
    print(json.dumps(seats, ensure_ascii=False, indent=2) if a.json else "", end="")
    if not a.json:
        print_table(seats)
    return 0 if any(s.get("available") for s in seats) else 1


if __name__ == "__main__":
    sys.exit(main())
