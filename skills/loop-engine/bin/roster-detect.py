#!/usr/bin/env python3
"""Concilium seat detector.

Detect locally available agents, their configured model options, current
default model, and supported modes. Outputs a human table by default or --json
for the TUI, Web UI, and conductor. Pure local probing only.
"""
from __future__ import annotations
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import capacity_status  # noqa: E402

HOME = Path.home()


def _run(cmd, timeout=15):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return f"(probe failed: {e})"


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
    d["strength"] = "orchestration/planning/synthesis, long context, multi-file refactoring"
    return d


def detect_codex():
    path = shutil.which("codex")
    d = {"seat": "codex", "available": bool(path), "path": path or "",
         "modes": ["review"], "provider": "openai", "models": []}
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
    # Codex is hard to enumerate fully; use the current model plus cached
    # alternatives from the same backend when available.
    opts = [model]
    cache = HOME / ".hermes" / "provider_models_cache.json"
    if cache.exists():
        try:
            c = json.load(open(cache)).get("openai-codex", {}).get("models", [])
            opts += [m for m in c if m not in opts]
        except Exception:
            pass
    d["models"] = [{"provider": "openai", "model": m, "default": (m == model)} for m in opts[:6]]
    d["strength"] = "code review and critical bug finding; review-only by default"
    return d


def _hermes_credentialed(status: str):
    """Parse credentialed backend display names from hermes status."""
    creds, sec = set(), None
    for line in status.splitlines():
        if "API Keys" in line: sec = "k"
        elif "Auth Providers" in line: sec = "a"
        elif line.strip().startswith("\u25c6"): sec = None
        elif sec and "\u2713" in line and "file" not in line.lower():
            creds.add(re.sub(r"\u2713.*", "", line).strip().lower())
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
    # Map credential display names to cache provider ids.
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
    # If the cache misses the current default, include it at least.
    if cur_model and not any(x["default"] for x in models):
        models.insert(0, {"provider": cur_pid, "model": cur_model, "default": True})
    d["models"] = models
    d["strength"] = "broad tool access; can switch to heterogeneous backends for review"
    return d


def detect_kimi():
    # Kimi is often installed under ~/.kimi-code/bin, which may not be on PATH.
    path = shutil.which("kimi")
    if not path:
        cand = HOME / ".kimi-code" / "bin" / "kimi"
        path = str(cand) if cand.exists() else None
    d = {"seat": "kimi", "available": bool(path), "path": path or "",
         "modes": ["plan", "exec", "review"], "provider": "moonshot", "models": []}
    if not path:
        return d
    ver = (_run([path, "--version"], 8).strip().splitlines() or [""])[0]
    d["version"] = f"Kimi Code {ver}".strip()
    cfg = HOME / ".kimi-code" / "config.toml"
    default_model, models_tbl = "kimi-code/kimi-for-coding", {}
    if cfg.exists():
        try:
            import tomllib
            t = tomllib.loads(cfg.read_text())
            default_model = str(t.get("default_model", default_model))
            models_tbl = t.get("models", {}) or {}
        except Exception:
            m = re.search(r'default_model\s*=\s*"([^"]+)"', cfg.read_text())
            default_model = m.group(1) if m else default_model
    d["model"] = default_model
    aliases = list(models_tbl.keys()) or [default_model]
    if default_model not in aliases:
        aliases.insert(0, default_model)
    d["models"] = [{"provider": "moonshot", "model": a, "default": (a == default_model)} for a in aliases]
    d["strength"] = "Moonshot K2.7 lineage, strong coding, independent review"
    return d


def attach_default_capacity(seat):
    out = dict(seat)
    out["capacity"] = capacity_status.make_record(
        seat=out.get("seat", ""),
        provider=out.get("provider", ""),
        model=out.get("model", ""),
        status="unknown",
        source="not_checked",
        reason="capacity-status not requested",
    )
    return out


def detect_all():
    return [
        attach_default_capacity(seat)
        for seat in [detect_claude(), detect_codex(), detect_hermes(), detect_kimi()]
    ]



def print_table(seats):
    print("\nConcilium seat probe results")
    print("=" * 64)
    for s in seats:
        mark = "+" if s.get("available") else "-"
        print(f"{mark} {s['seat']:<8} {s.get('version','') or '(not installed)'}")
        if not s.get("available"):
            continue
        print(f"    current default : {s.get('model','')} via {s.get('provider','')}"
              + (f"  [{s['effort']}]" if s.get("effort") else ""))
        print(f"    supported modes : {', '.join(s.get('modes', []))}")
        ms = s.get("models", [])
        if ms:
            shown = ", ".join((("*" if x.get("default") else "") + x["model"]) for x in ms)
            print(f"    available models : {shown}")
        print(f"    strength     : {s.get('strength','')}")
    print("=" * 64)
    avail = [s["seat"] for s in seats if s.get("available")]
    print(f"available seats: {', '.join(avail) or 'none; install at least one agent first'}")


def main():
    ap = argparse.ArgumentParser(description="Concilium seat detector")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    seats = detect_all()
    print(json.dumps(seats, ensure_ascii=False, indent=2) if a.json else "", end="")
    if not a.json:
        print_table(seats)
    return 0 if any(s.get("available") for s in seats) else 1


if __name__ == "__main__":
    sys.exit(main())
