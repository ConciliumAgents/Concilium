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
import argparse, datetime, json, os, re, signal, subprocess, sys
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


def _slug(text: str, n: int = 24) -> str:
    s = re.sub(r"[^0-9A-Za-z一-鿿]+", "-", text).strip("-")
    return s[:n] or "task"


def session_dir(repo: str) -> Path:
    """当前会话目录 .roundtable/sessions/<LOOP_SESSION>/。"""
    sid = os.environ.get("LOOP_SESSION", "default")
    return Path(repo) / ".roundtable" / "sessions" / sid


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
        (session_dir(repo) / "KB" / "roster.md").write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass
    return avail


def _claude_project_memory(repo: str) -> Path:
    """Claude 按项目存记忆的目录：路径 / → - 映射。"""
    mapped = repo.replace("/", "-")
    return Path.home() / ".claude" / "projects" / mapped / "memory"


def import_memory(repo: str) -> int:
    """记忆桥（进）：把仓库外的项目记忆汇集进本会话 KB/imported-memory.md，
    让 codex/hermes 这些读不到 Claude 私库的座位也看到完整项目。只读拉取。"""
    parts = ["# 导入的项目记忆（memory-bridge 汇集 · 所有座位自取）", ""]
    n = 0
    cm = Path(repo) / "CLAUDE.md"
    if cm.exists():
        parts += ["## 仓库 CLAUDE.md", cm.read_text(encoding="utf-8", errors="replace")[:4000], ""]; n += 1
    md = _claude_project_memory(repo)
    if md.is_dir():
        for f in sorted(md.glob("*.md")):
            parts += [f"## Claude 项目记忆 · {f.name}", f.read_text(encoding="utf-8", errors="replace")[:3000], ""]; n += 1
    cur = os.environ.get("LOOP_SESSION", "")
    sroot = Path(repo) / ".roundtable" / "sessions"
    if sroot.is_dir():
        for sd in sorted(sroot.iterdir()):
            if sd.name == cur:
                continue
            c = sd / "KB" / "conclusion.md"
            if c.exists():
                parts += [f"## 过往会话结论 · {sd.name}", c.read_text(encoding="utf-8", errors="replace")[:1500], ""]; n += 1
    try:
        (session_dir(repo) / "KB" / "imported-memory.md").write_text("\n".join(parts), encoding="utf-8")
    except OSError:
        pass
    return n


def write_conclusion(repo: str, task: str, status: str, rounds: int, verdicts: list) -> None:
    """会议结论落盘到本会话 KB/conclusion.md（供人看 + 下次跨会话继承）。"""
    sd = session_dir(repo)
    def _git(*a):
        try:
            return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            return ""
    diffstat = _git("diff", "--stat", "HEAD")
    log = _git("log", "--oneline", "--grep", "loop-engine", "-n", "20")
    minutes = sorted((sd / "minutes").glob("*.md")) if (sd / "minutes").is_dir() else []
    minute_lines = [f"- {m.name}" for m in minutes] or ["（无）"]
    lines = [
        f"# 圆桌会议结论 · {os.environ.get('LOOP_SESSION', '')}", "",
        f"- 任务：{task}",
        f"- 结论：**{status}**（共 {rounds} 轮）",
        f"- 各轮裁决：{', '.join(verdicts) or '—'}", "",
        "## 改动文件（git diff --stat HEAD）", "```", diffstat or "（无未提交改动；见下方 checkpoint 提交）", "```", "",
        "## checkpoint 提交", "```", log or "（无）", "```", "",
        "## 座位发言纪要（详见 minutes/）", *minute_lines, "",
        "## 剩余风险 / 下一步", "如结论为 BLOCK/CAP，请读 minutes/ 中验证席的发现。",
    ]
    try:
        (sd / "KB" / "conclusion.md").write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass


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
    # 会话 id：项目内按会话隔离记忆（除非外部已指定 LOOP_SESSION 以续接）
    if not os.environ.get("LOOP_SESSION"):
        os.environ["LOOP_SESSION"] = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + _slug(task)
    reporter.log(f"[conductor] 会话: {os.environ['LOOP_SESSION']}")
    reporter.start(repo, task, commander, reviewer, max_iters)

    _, o = sh_capture("roundtable-init.sh", repo, task); reporter.log(o)
    # 用真实探测覆盖花名册模板，并校验指派的总指挥/验证席确实可用
    avail = write_roster(repo)
    if avail:
        reporter.log(f"[loop-engine] 探测到可上桌座位: {', '.join(avail)}")
        for role, name in (("总指挥", commander), ("验证席", reviewer)):
            if name not in avail:
                reporter.log(f"[loop-engine] ⚠ {role} '{name}' 未探测到可用，可能失败")
    nimp = import_memory(repo)
    if nimp:
        reporter.log(f"[loop-engine] 记忆桥：导入 {nimp} 份仓库外项目记忆到黑板")
    _, o = sh_capture("kb-refresh.sh", repo, test_cmd); reporter.log(o)

    feedback, verdicts, status, final_it = "", [], None, max_iters
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
        verdicts.append(verdict)

        _, o = sh_capture("checkpoint.sh", repo, f"{commander}指挥第{it}轮 裁决{verdict}"); reporter.log(o)

        if verdict in ("PASS", "ERR"):
            status, final_it = verdict, it
            break
        feedback = "上一轮验证 BLOCK，请读 minutes/ 里验证席的发现并修正。"

    status = status or "CAP"
    write_conclusion(repo, task, status, final_it, verdicts)
    reporter.finish(status, final_it)
    return {"PASS": 0, "ERR": 1, "CAP": 2}[status]


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
