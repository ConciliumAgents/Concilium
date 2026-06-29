#!/usr/bin/env python3
"""server.py — 圆桌 WebUI 后端（纯标准库，零依赖）。

复用 conductor 的 Reporter 事件层：WebReporter 把过程事件推进队列，
SSE 端点把队列实时流给浏览器。仅 127.0.0.1，不对外。

端点：
  GET  /                 → 前端页面 index.html
  GET  /api/status       → Concilium 服务状态
  GET  /api/doctor       → 座位探测结果（roster-detect --json）
  GET  /api/config/effective?repo= → 脱敏后的有效配置
  POST /api/preflight    → 预检 Concilium lane/capacity（JSON body）
  POST /api/run          → 启动一次圆桌（JSON body），返回 {run_id}
  GET  /api/events?run=  → SSE 实时事件流
"""
from __future__ import annotations
import datetime, json, os, queue, secrets, subprocess, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
BIN = HERE.parent / "bin"
sys.path.insert(0, str(BIN))
import conductor  # noqa: E402
import capacity_status  # noqa: E402
import concilium_config  # noqa: E402
import concilium_events  # noqa: E402
import concilium_runtime  # noqa: E402

RUNS: dict[str, dict] = {}   # run_id -> {"q": Queue}
_seq = {"n": 0}
_lock = threading.Lock()

# 启动时生成的 CSRF token：服务 index.html 时注入页面（meta），前端 POST /api/run 必带
# X-Loop-Token。SSE（EventSource）不能带自定义头，故只校验 POST，不校验 GET /api/events。
TOKEN = secrets.token_urlsafe(32)


def _adapter_params(params: dict, *, preview: bool = False) -> dict:
    run_params = dict(params)
    if preview:
        run_params["mode"] = "preview"
    elif not run_params.get("mode"):
        run_params["mode"] = "stub_run" if run_params.get("dry_run") else "live_run"
    if ("timeout" not in run_params or run_params.get("timeout") is None) and run_params.get("seat_timeout") is not None:
        run_params["timeout"] = run_params["seat_timeout"]
    return run_params


def _result_rc(result: dict) -> int:
    if "returncode" in result:
        return int(result["returncode"])
    if "rc" in result:
        return int(result["rc"])
    return 0


def _run_thread(params: dict, q: "queue.Queue"):
    sink = concilium_events.QueueEventSink(q)
    try:
        confirmation = params.get("confirmation") if isinstance(params.get("confirmation"), dict) else None
        result = concilium_runtime.run_concilium_adapter(
            _adapter_params(params),
            confirmation=confirmation,
            event_sink=sink,
        )
        if not sink.done_emitted:
            concilium_events.emit_done(sink, _result_rc(result))
    except Exception as e:
        sink.emit("error", msg=capacity_status.redact(f"{type(e).__name__}: {e}"))
        if not sink.done_emitted:
            concilium_events.emit_done(sink, -1)


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
    return concilium_runtime.run_concilium_adapter(_adapter_params(params, preview=True))


def preflight_response(params: dict) -> dict:
    result = build_preflight(params)
    response = {
        "route": result.get("route", {}),
        "preflight": result.get("preflight", {}),
        "capacity": result.get("capacity", []),
        "signals": result.get("signals", {}),
        "guard": result.get("guard", {}),
    }
    for key in ("request_fingerprint", "expected_max_agent_calls"):
        if key in result:
            response[key] = result[key]
    return _redact_response(response)


def status_response() -> dict:
    return {
        "product": "Concilium",
        "service": "ok",
        "bind": "127.0.0.1",
        "token_required": True,
        "endpoints": [
            "/api/status",
            "/api/doctor",
            "/api/project",
            "/api/config/effective?repo=...",
            "/api/preflight",
            "/api/run",
            "/api/events",
        ],
    }


def effective_config_response(repo: str) -> dict:
    config = concilium_config.load_config(repo)
    return _redact_response(concilium_config.redact_for_render(config))


def write_token_file(path: Path, base_url: str, token: str) -> None:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    created_at = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {"base_url": base_url, "token": token, "created_at": created_at}
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


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
        if u.path == "/api/status":
            return self._send(200, json.dumps(status_response(), ensure_ascii=False).encode("utf-8"))
        if u.path == "/api/project":
            repo = parse_qs(u.query).get("repo", [""])[0]
            return self._send(200, json.dumps(project_info(repo), ensure_ascii=False).encode("utf-8"))
        if u.path == "/api/config/effective":
            repo = parse_qs(u.query).get("repo", [""])[0]
            if not repo:
                return self._send(400, b'{"error":"repo required"}')
            try:
                body = effective_config_response(repo)
                return self._send(200, json.dumps(body, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                body = {"error": f"{type(e).__name__}: {capacity_status.redact(str(e))}"}
                return self._send(500, json.dumps(body, ensure_ascii=False).encode("utf-8"))
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
    ap.add_argument("--token-file", default="")
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    if a.token_file:
        write_token_file(Path(a.token_file).expanduser(), url, TOKEN)
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
