#!/usr/bin/env python3
"""conductor.py — 圆桌的独立指挥程序（本体，不住在任何 agent 里）。

哑指挥：只管控制流（init→总指挥派活→分派执行→验证→迭代→停止），不内嵌大脑，
智力全外包给被调用的座位（bin/seat-*.sh，各 agent 在自己原生壳里 headless 跑）。
所有座位从共享黑板 .roundtable/KB 自取上下文。

渲染与控制分离：run() 把过程通过 Reporter 事件发出；
  - TextReporter（默认）→ 纯文本进度
  - tui.py 的 RichReporter → rich.Live 仪表盘
依赖：仅 Python 标准库。
"""
from __future__ import annotations
import argparse, json, os, re, signal, subprocess, sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
AGENTS = {"claude", "codex", "hermes"}
VERDICT_MAP = {0: "PASS", 2: "BLOCK", 1: "ERR"}


# ---------------- Reporter：过程事件接口 ----------------
class Reporter:
    def start(self, repo, task, commander, reviewer, max_iters): ...
    def round(self, it): ...
    def plan(self, plan): ...
    def seat(self, agent, mode, subtask="", rc=None, phase="start"): ...
    def verdict(self, reviewer, v): ...
    def finish(self, status, it): ...
    def log(self, msg): ...


class TextReporter(Reporter):
    def start(self, repo, task, commander, reviewer, max_iters):
        print(f"\033[36m[conductor]\033[0m 开桌 repo={repo}", file=sys.stderr)
        print(f"\033[36m[conductor]\033[0m 总指挥={commander} 验证席={reviewer} 上限={max_iters}轮 任务={task}", file=sys.stderr)
    def round(self, it):
        print(f"\n\033[1m===== 第 {it} 轮 =====\033[0m", flush=True)
    def plan(self, plan):
        print("\033[36m[conductor]\033[0m 派活：" + "; ".join(f"{p['agent']}←{p['subtask'][:30]}" for p in plan), flush=True)
    def seat(self, agent, mode, subtask="", rc=None, phase="start"):
        if phase == "start":
            print(f"\033[36m[conductor]\033[0m → {agent} [{mode}] {subtask[:40]}", file=sys.stderr, flush=True)
        else:
            print(f"\033[36m[conductor]\033[0m ✓ {agent} [{mode}] rc={rc}", file=sys.stderr, flush=True)
    def verdict(self, reviewer, v):
        print(f"\033[36m[conductor]\033[0m 验证席 {reviewer} 裁决：{v}", flush=True)
    def finish(self, status, it):
        msg = {"PASS": f"\033[32m✅ 第 {it} 轮验证通过，收工。\033[0m",
               "ERR": f"\033[31m⛔ 验证 ERR（需人工读 minutes），停。\033[0m",
               "CAP": f"\033[33m⛔ 触顶 {it} 轮仍未通过，交还人工。\033[0m"}.get(status, status)
        print("\n" + msg, flush=True)
    def log(self, msg):
        if msg.strip():
            print(f"\033[2m{msg.rstrip()}\033[0m", file=sys.stderr, flush=True)


# ---------------- 座位调用 ----------------
def run_seat(agent: str, mode: str, repo: str, brief: str = "", extra: list[str] | None = None) -> tuple[int, str]:
    extra = extra or []
    if os.environ.get("LOOP_DRY_RUN") == "1":
        return _dry_seat(agent, mode, brief)
    script = BIN / f"seat-{agent}.sh"
    if not script.exists():
        return 1, f"(no seat script for {agent})"
    cmd = [str(script), repo, mode]
    if brief or mode in ("exec", "review"):
        cmd.append(brief)
    cmd += extra
    # 每个座位调用都设超时 + 进程组强杀：一个 agent 卡死不得拖垮整个循环。
    # start_new_session 让座位脚本及其子孙（codex/hermes node 进程）同属一个进程组，
    # 超时时整组 SIGKILL，避免 codex 等孙进程变孤儿继续空跑。
    timeout = int(os.environ.get("LOOP_SEAT_TIMEOUT", "600"))
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, start_new_session=True)
    except OSError as e:
        return 1, f"(座位 {agent} 启动失败: {e})"
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out or ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
        try:
            out, _ = p.communicate(timeout=5)
        except Exception:
            out = ""
        return 124, (out or "") + f"\n(⏱ 座位 {agent} [{mode}] 超时 {timeout}s，已强杀整组)"


def _dry_seat(agent: str, mode: str, brief: str) -> tuple[int, str]:
    if mode == "plan":
        plan = [{"agent": "claude", "subtask": "实施核心改动"},
                {"agent": "hermes", "subtask": "环境排雷"}]
        return 0, f"[dry] 派活\n```json\n{json.dumps(plan, ensure_ascii=False)}\n```"
    if mode == "review":
        v = os.environ.get("LOOP_DRY_VERDICT", "PASS")
        return (0 if v == "PASS" else 2), f"[dry] {agent} → VERDICT: {v}"
    return 0, f"[dry] {agent} 执行: {brief[:60]}"


def sh_capture(script: str, *args: str) -> tuple[int, str]:
    p = subprocess.run([str(BIN / script), *args], capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def write_roster(repo: str) -> list[str]:
    """探测本地座位，写动态 KB/roster.md（总指挥按此派活），返回可用座位名列表。"""
    detect = BIN / "roster-detect.py"
    try:
        p = subprocess.run([sys.executable, str(detect), "--json"], capture_output=True, text=True, timeout=60)
        seats = json.loads(p.stdout)
    except Exception:
        return []
    lines = ["# 座位花名册（KB · roster-detect 自动探测，总指挥按此派活）", ""]
    avail = []
    for s in seats:
        if not s.get("available"):
            lines += [f"## ~~{s['seat']}~~（未安装，不可上桌）", ""]
            continue
        avail.append(s["seat"])
        eff = f" [{s.get('effort')}]" if s.get("effort") else ""
        lines += [f"## {s['seat']}（{s.get('model','')} via {s.get('provider','')}{eff}）",
                  f"- 特长：{s.get('strength','')}",
                  f"- 可任模式：{', '.join(s.get('modes', []))}"]
        if s.get("alt"):
            lines.append("- 可切异质后端（异质血统复审席）：" + ", ".join(f"{a['provider']}/{a['model']}" for a in s["alt"]))
        lines.append("")
    try:
        (Path(repo) / ".roundtable" / "KB" / "roster.md").write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass
    return avail


def extract_plan(text: str) -> list[dict]:
    m = re.search(r"```json\s*(.+?)```", text, re.S)
    blob = m.group(1) if m else None
    if not blob:
        m2 = re.search(r"(\[\s*\{.*?\}\s*\])", text, re.S)
        blob = m2.group(1) if m2 else None
    if not blob:
        return []
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        a = str(item.get("agent", "")).strip().lower()
        t = str(item.get("subtask", "")).strip()
        if a in AGENTS and t:
            out.append({"agent": a, "subtask": t})
    return out


# ---------------- 主循环（渲染无关）----------------
def run(repo, task, commander="claude", reviewer="codex", max_iters=5, test_cmd="", reporter=None) -> int:
    reporter = reporter or TextReporter()
    repo = str(Path(repo).expanduser().resolve())
    reporter.start(repo, task, commander, reviewer, max_iters)

    _, o = sh_capture("roundtable-init.sh", repo, task); reporter.log(o)
    # 用真实探测覆盖花名册模板，并校验指派的总指挥/验证席确实可用
    avail = write_roster(repo)
    if avail:
        reporter.log(f"[loop-engine] 探测到可上桌座位: {', '.join(avail)}")
        for role, name in (("总指挥", commander), ("验证席", reviewer)):
            if name not in avail:
                reporter.log(f"[loop-engine] ⚠ {role} '{name}' 未探测到可用，可能失败")
    _, o = sh_capture("kb-refresh.sh", repo, test_cmd); reporter.log(o)

    feedback = ""
    for it in range(1, max_iters + 1):
        reporter.round(it)

        # 总指挥派活
        reporter.seat(commander, "plan", "读花名册分派", phase="start")
        rc, out = run_seat(commander, "plan", repo, brief=feedback)
        reporter.seat(commander, "plan", "", rc, phase="done")
        plan = extract_plan(out) or [{"agent": commander, "subtask": task}]
        reporter.plan(plan)

        # 分派执行（验证留到统一一步）
        for p in plan:
            if p["agent"] == reviewer and "验证" in p["subtask"]:
                continue
            reporter.seat(p["agent"], "exec", p["subtask"], phase="start")
            erc, _ = run_seat(p["agent"], "exec", repo, brief=p["subtask"])
            reporter.seat(p["agent"], "exec", p["subtask"], erc, phase="done")

        _, o = sh_capture("kb-refresh.sh", repo, test_cmd); reporter.log(o)

        # 验证
        reporter.seat(reviewer, "review", "独立验证", phase="start")
        vrc, _ = run_seat(reviewer, "review", repo)
        verdict = VERDICT_MAP.get(vrc, "ERR")
        reporter.seat(reviewer, "review", "", vrc, phase="done")
        reporter.verdict(reviewer, verdict)

        _, o = sh_capture("checkpoint.sh", repo, f"{commander}指挥第{it}轮 裁决{verdict}"); reporter.log(o)

        if verdict == "PASS":
            reporter.finish("PASS", it); return 0
        if verdict == "ERR":
            reporter.finish("ERR", it); return 1
        feedback = "上一轮验证 BLOCK，请读 .roundtable/minutes 里验证席的发现并修正。"

    reporter.finish("CAP", max_iters); return 2


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="圆桌指挥程序")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--commander", default="claude", choices=sorted(AGENTS), help="项目总指挥（你指派）")
    ap.add_argument("--reviewer", default="codex", choices=sorted(AGENTS), help="验证席")
    ap.add_argument("--max-iters", type=int, default=int(os.environ.get("LOOP_MAX_ITERS", "5")))
    ap.add_argument("--test-cmd", default=os.environ.get("LOOP_TEST_CMD", ""))
    return ap


def main() -> int:
    a = build_argparser().parse_args()
    return run(a.repo, a.task, a.commander, a.reviewer, a.max_iters, a.test_cmd, TextReporter())


if __name__ == "__main__":
    sys.exit(main())
