#!/usr/bin/env python3
"""server.py — 圆桌 WebUI 后端（纯标准库，零依赖）。

复用 conductor 的 Reporter 事件层：WebReporter 把过程事件推进队列，
SSE 端点把队列实时流给浏览器。仅 127.0.0.1，不对外。

端点：
  GET  /                 → 前端页面 index.html
  GET  /api/doctor       → 座位探测结果（roster-detect --json）
  POST /api/preflight    → 预检 Concilium lane/capacity（JSON body）
  POST /api/run          → 启动一次圆桌（JSON body），返回 {run_id}
  GET  /api/events?run=  → SSE 实时事件流
"""
from __future__ import annotations
import importlib.util, json, os, queue, secrets, subprocess, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
BIN = HERE.parent / "bin"
sys.path.insert(0, str(BIN))
import conductor  # noqa: E402
import capacity_status  # noqa: E402


def _load_bin_module(name: str, filename: str):
    module_path = BIN / filename
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


concilium_run = _load_bin_module("concilium_run", "concilium-run.py")

RUNS: dict[str, dict] = {}   # run_id -> {"q": Queue}
_seq = {"n": 0}
_lock = threading.Lock()

# 启动时生成的 CSRF token：服务 index.html 时注入页面（meta），前端 POST /api/run 必带
# X-Loop-Token。SSE（EventSource）不能带自定义头，故只校验 POST，不校验 GET /api/events。
TOKEN = secrets.token_urlsafe(32)


class WebReporter(conductor.Reporter):
    """把指挥过程事件推进队列，供 SSE 流给浏览器。"""
    def __init__(self, q: "queue.Queue"):
        self.q = q
    def _emit(self, **e): self.q.put(e)
    def start(self, repo, task, commander, reviewer, max_iters):
        self._emit(type="start", repo=repo, task=task, commander=commander, reviewer=reviewer, max_iters=max_iters)
    def round(self, it): self._emit(type="round", it=it)
    def plan(self, plan): self._emit(type="plan", plan=plan)
    def seat(self, agent, mode, subtask="", rc=None, phase="start"):
        self._emit(type="seat", agent=agent, mode=mode, subtask=subtask, rc=rc, phase=phase)
    def verdict(self, reviewer, v): self._emit(type="verdict", reviewer=reviewer, verdict=v)
    def finish(self, status, it): self._emit(type="finish", status=status, it=it)
    def transcript(self, agent, mode, text):
        t = (text or "").strip()
        if t:
            self._emit(type="transcript", agent=agent, mode=mode, text=t[:8000])
    def log(self, msg):
        import re
        for line in str(msg).splitlines():
            line = re.sub(r"\033\[[0-9;]*m", "", line).strip()
            if line and ("loop-engine]" in line or "conductor]" in line):
                self._emit(type="log", msg=line.replace("[loop-engine] ", "· ").replace("[conductor] ", "» "))


def _run_thread(params: dict, q: "queue.Queue"):
    rep = WebReporter(q)
    try:
        os.environ["LOOP_DRY_RUN"] = "1" if params.get("dry_run") else ""
        if params.get("codex_effort"):
            os.environ["LOOP_CODEX_EFFORT"] = str(params["codex_effort"])
        os.environ["LOOP_SEAT_TIMEOUT"] = str(params.get("seat_timeout", 600))
        rc = conductor.run(
            params["repo"], params["task"],
            params.get("commander", "claude"), params.get("reviewer", "codex"),
            int(params.get("max_iters", 5)), params.get("test_cmd", ""), rep,
            seats=params.get("seats") or None,
            seat_models=params.get("seat_models") or None,
        )
        q.put({"type": "done", "rc": rc})
    except Exception as e:
        q.put({"type": "error", "msg": f"{type(e).__name__}: {e}"})
        q.put({"type": "done", "rc": -1})


def project_info(repo: str) -> dict:
    """项目自检：是不是 git 仓库、能桥接到几份该项目的 Claude 记忆。"""
    p = Path(repo).expanduser()
    out = {"exists": p.is_dir(), "is_git": False, "claude_memory": 0, "memory_files": []}
    if not p.is_dir():
        return out
    repo_abs = str(p.resolve())
    try:
        r = subprocess.run(["git", "-C", repo_abs, "rev-parse", "--is-inside-work-tree"],
                           capture_output=True, text=True, timeout=5)
        out["is_git"] = (r.returncode == 0 and "true" in r.stdout)
    except Exception:
        pass
    md = conductor._claude_project_memory(repo_abs)
    if md.is_dir():
        files = [f.name for f in md.glob("*.md")]
        out["claude_memory"] = len(files)
        out["memory_files"] = files[:10]
    return out


def _redact_response(value):
    if isinstance(value, dict):
        return {key: _redact_response(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_response(item) for item in value]
    if isinstance(value, str):
        return capacity_status.redact(value)
    return value


def build_preflight(params: dict) -> dict:
    return concilium_run.run_concilium(
        params["repo"],
        params["task"],
        test_cmd=params.get("test_cmd", ""),
        dry_run=True,
        print_route=True,
    )


def preflight_response(params: dict) -> dict:
    result = build_preflight(params)
    return _redact_response({
        "route": result.get("route", {}),
        "preflight": result.get("preflight", {}),
        "capacity": result.get("capacity", []),
        "signals": result.get("signals", {}),
    })


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass  # 静音默认访问日志

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            html = (HERE / "index.html").read_bytes()
            html = html.replace(b"__LOOP_TOKEN__", TOKEN.encode("utf-8"))
            return self._send(200, html, "text/html; charset=utf-8")
        if u.path == "/api/doctor":
            p = subprocess.run([sys.executable, str(BIN / "roster-detect.py"), "--json"],
                               capture_output=True, text=True, timeout=60)
            return self._send(200, p.stdout.encode("utf-8"))
        if u.path == "/api/project":
            repo = parse_qs(u.query).get("repo", [""])[0]
            return self._send(200, json.dumps(project_info(repo), ensure_ascii=False).encode("utf-8"))
        if u.path == "/api/events":
            run_id = (parse_qs(u.query).get("run", [""])[0])
            run = RUNS.get(run_id)
            if not run:
                return self._send(404, b'{"error":"no such run"}')
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q = run["q"]
            while True:
                try:
                    ev = q.get(timeout=30)
                except queue.Empty:
                    try:
                        self.wfile.write(b": keepalive\n\n"); self.wfile.flush()
                        continue
                    except Exception:
                        break
                try:
                    self.wfile.write(f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    break
                if ev.get("type") == "done":
                    break
            return
        return self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        u = urlparse(self.path)
        if u.path not in ("/api/run", "/api/preflight"):
            return self._send(404, b'{"error":"not found"}')
        if not secrets.compare_digest(self.headers.get("X-Loop-Token", ""), TOKEN):
            return self._send(403, b'{"error":"bad or missing token"}')
        n = int(self.headers.get("Content-Length", "0"))
        params = json.loads(self.rfile.read(n) or b"{}")
        if not params.get("repo") or not params.get("task"):
            return self._send(400, '{"error":"repo 和 task 必填"}'.encode("utf-8"))
        if u.path == "/api/preflight":
            try:
                return self._send(
                    200,
                    json.dumps(preflight_response(params), ensure_ascii=False).encode("utf-8"),
                )
            except Exception as e:
                body = {"error": f"{type(e).__name__}: {capacity_status.redact(str(e))}"}
                return self._send(500, json.dumps(body, ensure_ascii=False).encode("utf-8"))
        with _lock:
            _seq["n"] += 1
            run_id = f"run{_seq['n']}"
        q: "queue.Queue" = queue.Queue()
        RUNS[run_id] = {"q": q}
        threading.Thread(target=_run_thread, args=(params, q), daemon=True).start()
        return self._send(200, json.dumps({"run_id": run_id}).encode("utf-8"))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"圆桌 WebUI: {url}  (Ctrl+C 退出)", flush=True)
    if not a.no_open:
        try: webbrowser.open(url)
        except Exception: pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")


if __name__ == "__main__":
    main()
