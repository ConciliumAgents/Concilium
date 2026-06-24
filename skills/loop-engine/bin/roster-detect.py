#!/usr/bin/env python3
"""roster-detect.py — 圆桌座位探测器（地基）。

启动时探测本地有哪些 agent 可上桌，各自什么模型/后端、能切哪些 provider、支持哪些 mode。
输出人类表格（默认）或 `--json`（供 TUI 选人界面 / conductor 消费）。
纯本地探测，不调用任何 agent 干活。仅 Python 标准库。
"""
from __future__ import annotations
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path

HOME = Path.home()


def _run(cmd: list[str], timeout: int = 15) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return f"(探测失败: {e})"


def detect_claude() -> dict:
    path = shutil.which("claude")
    d = {"seat": "claude", "available": bool(path), "path": path or "",
         "modes": ["plan", "exec", "review"], "providers": [], "alt": []}
    if not path:
        return d
    ver = _run([path, "--version"], 8).strip().splitlines()
    d["version"] = ver[0] if ver else ""
    d["model"] = "Claude Code 会话默认（通常 Opus）"
    d["provider"] = "anthropic"
    d["strength"] = "编排/规划/综合、长上下文、多文件重构"
    return d


def detect_codex() -> dict:
    path = shutil.which("codex")
    d = {"seat": "codex", "available": bool(path), "path": path or "",
         "modes": ["exec", "review"], "alt": []}
    if not path:
        return d
    ver = _run([path, "--version"], 8).strip().splitlines()
    d["version"] = ver[0] if ver else ""
    cfg = HOME / ".codex" / "config.toml"
    model, effort = "", ""
    if cfg.exists():
        try:
            import tomllib
            t = tomllib.loads(cfg.read_text())
            model = str(t.get("model", ""))
            effort = str(t.get("model_reasoning_effort", ""))
        except Exception:
            txt = cfg.read_text()
            m = re.search(r'model\s*=\s*"([^"]+)"', txt); model = m.group(1) if m else ""
            e = re.search(r'model_reasoning_effort\s*=\s*"([^"]+)"', txt); effort = e.group(1) if e else ""
    d["model"] = model or "(未配置)"
    d["effort"] = effort
    d["provider"] = "openai"
    d["strength"] = "代码验证/挑致命缺陷（codex exec review）、强编码"
    return d


def detect_hermes() -> dict:
    path = shutil.which("hermes")
    d = {"seat": "hermes", "available": bool(path), "path": path or "",
         "modes": ["exec", "review"], "alt": []}
    if not path:
        return d
    ver = _run([path, "--version"], 8).strip().splitlines()
    d["version"] = ver[0] if ver else ""
    status = _run([path, "status"], 20)
    m = re.search(r"Model:\s*([^\n]+)", status); d["model"] = (m.group(1).strip() if m else "(未知)")
    p = re.search(r"Provider:\s*([^\n]+)", status); d["provider"] = (p.group(1).strip() if p else "(未知)")
    # 探测可切换的异质后端（看 .env 里有哪些 API key）
    env = HOME / ".hermes" / ".env"
    alt = []
    if env.exists():
        try:
            etxt = env.read_text()
            for name, prov, model in [
                ("DEEPSEEK_API_KEY", "deepseek", "deepseek-reasoner"),
                ("QWEN", "qwen", "qwen-coder"),
                ("XAI_API_KEY", "xai", "grok"),
                ("OPENROUTER_API_KEY", "openrouter", ""),
            ]:
                if re.search(rf"^\s*{name}\s*=\s*\S", etxt, re.M):
                    alt.append({"provider": prov, "model": model})
        except Exception:
            pass
    d["alt"] = alt  # 这些可作为「异质血统复审」座位
    d["strength"] = "工具广度（浏览器/computer-use/消息/记忆）；可切异质后端做复审"
    return d


def detect_all() -> list[dict]:
    return [detect_claude(), detect_codex(), detect_hermes()]


def print_table(seats: list[dict]) -> None:
    print("\n圆桌座位探测结果")
    print("=" * 64)
    for s in seats:
        mark = "✓" if s.get("available") else "✗"
        print(f"{mark} {s['seat']:<8} {s.get('version','') or '(未装)'}")
        if not s.get("available"):
            continue
        print(f"    模型/后端 : {s.get('model','')}  via {s.get('provider','')}"
              + (f"  [{s['effort']}]" if s.get("effort") else ""))
        print(f"    可任模式  : {', '.join(s.get('modes', []))}")
        print(f"    特长      : {s.get('strength','')}")
        if s.get("alt"):
            alts = ", ".join(f"{a['provider']}" + (f"/{a['model']}" if a['model'] else "") for a in s["alt"])
            print(f"    可切异质  : {alts}  ← 可做异质血统复审席")
    print("=" * 64)
    avail = [s["seat"] for s in seats if s.get("available")]
    print(f"可上桌座位: {', '.join(avail) or '（无！请先安装至少一个 agent）'}")


def main() -> int:
    ap = argparse.ArgumentParser(description="圆桌座位探测器")
    ap.add_argument("--json", action="store_true", help="输出 JSON（供 TUI/conductor 消费）")
    a = ap.parse_args()
    seats = detect_all()
    if a.json:
        print(json.dumps(seats, ensure_ascii=False, indent=2))
    else:
        print_table(seats)
    return 0 if any(s.get("available") for s in seats) else 1


if __name__ == "__main__":
    sys.exit(main())
