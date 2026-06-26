#!/usr/bin/env python3
"""tui.py — 圆桌的 TUI 仪表盘（Phase 2，rich.Live）。

它是 conductor.run() 的一个 Reporter 实现：把指挥过程渲染成实时面板
（座位状态、当前轮次、裁决、日志）。控制流仍在 conductor，TUI 只负责画面。
需在项目内 .venv 里跑（含 rich）：  .venv/bin/python skills/loop-engine/tui/tui.py --repo … --task …
"""
from __future__ import annotations
import sys
from collections import deque
from pathlib import Path

# 让 tui 能 import 同仓 bin/conductor.py
BIN = Path(__file__).resolve().parent.parent / "bin"
sys.path.insert(0, str(BIN))
import conductor  # noqa: E402

from rich.console import Console, Group  # noqa: E402
from rich.live import Live  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402
from rich.spinner import Spinner  # noqa: E402
from rich.text import Text  # noqa: E402

ROLE_DESC = {
    "claude": "Opus · 编排/重构/综合",
    "codex": "gpt-5.5 · 代码验证",
    "hermes": "工具广度 · 可切DeepSeek",
    "kimi": "K2.7 · 异质评审/强编码",
}
STATUS_STYLE = {"idle": "dim", "working": "yellow", "done": "green", "block": "red", "err": "red"}


class RichReporter(conductor.Reporter):
    def __init__(self, live: Live):
        self.live = live
        self.info = {}
        self.round_no = 0
        self.seats = {a: {"status": "idle", "detail": "", "role": ""} for a in sorted(conductor.AGENTS)}
        self.last_verdict = "—"
        self.final = ""
        self.logs: deque[str] = deque(maxlen=200)

    # ---- 渲染 ----
    def _header(self):
        i = self.info
        t = Text()
        t.append("圆桌会议 · Loop Engine\n", style="bold cyan")
        t.append(f"任务: {i.get('task','')}\n")
        t.append(f"总指挥: {i.get('commander','')}   验证席: {i.get('reviewer','')}   ")
        t.append(f"轮次: {self.round_no}/{i.get('max_iters','')}   ")
        t.append("最近裁决: ")
        t.append(self.last_verdict, style="bold " + ("green" if self.last_verdict == "PASS" else "red" if self.last_verdict in ("BLOCK", "ERR") else "white"))
        if self.final:
            t.append("\n" + self.final, style="bold")
        return Panel(t, border_style="cyan")

    def _seats(self):
        tbl = Table(expand=True, show_edge=False)
        tbl.add_column("座位", style="bold", width=10)
        tbl.add_column("特长", width=24)
        tbl.add_column("状态", width=28)
        for a, s in self.seats.items():
            st = s["status"]
            if st == "working":
                status = Spinner("dots", text=Text(f" {s['detail'][:24]}", style="yellow"))
            else:
                status = Text(("● " if st != "idle" else "○ ") + st + (f" {s['detail'][:20]}" if s["detail"] else ""),
                              style=STATUS_STYLE.get(st, "white"))
            role = s["role"] + (" " if s["role"] else "") + ROLE_DESC.get(a, "")
            tbl.add_row(a, role, status)
        return Panel(tbl, title="座位", border_style="blue")

    def _log(self):
        body = Text("\n".join(list(self.logs)[-12:]), style="dim")
        return Panel(body, title="会议日志", border_style="grey50")

    def _refresh(self):
        self.live.update(Group(self._header(), self._seats(), self._log()))

    # ---- Reporter 钩子 ----
    def start(self, repo, task, commander, reviewer, max_iters):
        self.info = dict(repo=repo, task=task, commander=commander, reviewer=reviewer, max_iters=max_iters)
        self.seats[commander]["role"] = "[总指挥]"
        self.seats[reviewer]["role"] = ("[验证]" if not self.seats[reviewer]["role"] else self.seats[reviewer]["role"] + "[验证]")
        self.logs.append(f"开桌：{task}")
        self._refresh()

    def round(self, it):
        self.round_no = it
        for s in self.seats.values():
            if s["status"] in ("done", "block", "err"):
                s["status"], s["detail"] = "idle", ""
        self.logs.append(f"——— 第 {it} 轮 ———")
        self._refresh()

    def plan(self, plan):
        self.logs.append("派活：" + "; ".join(f"{p['agent']}←{p['subtask'][:24]}" for p in plan))
        self._refresh()

    def seat(self, agent, mode, subtask="", rc=None, phase="start"):
        s = self.seats.get(agent)
        if not s:
            return
        if phase == "start":
            s["status"], s["detail"] = "working", f"{mode} {subtask[:20]}"
            self.logs.append(f"→ {agent} [{mode}] {subtask[:30]}")
        else:
            if mode == "review":
                v = conductor.VERDICT_MAP.get(rc, "ERR")
                s["status"] = "done" if v == "PASS" else ("block" if v == "BLOCK" else "err")
                s["detail"] = v
            else:
                s["status"], s["detail"] = ("done" if rc == 0 else "err"), f"rc={rc}"
            self.logs.append(f"✓ {agent} [{mode}] rc={rc}")
        self._refresh()

    def verdict(self, reviewer, v):
        self.last_verdict = v
        self.logs.append(f"裁决：{reviewer} → {v}")
        self._refresh()

    def finish(self, status, it):
        self.final = {"PASS": f"✅ 第 {it} 轮通过，收工",
                      "ERR": "⛔ 验证 ERR，交还人工",
                      "CAP": f"⛔ 触顶 {it} 轮，交还人工"}.get(status, status)
        self.logs.append(self.final)
        self._refresh()

    def log(self, msg):
        for line in str(msg).splitlines():
            line = line.strip()
            # 去掉 ANSI 转义，挑有信息量的行
            import re
            line = re.sub(r"\033\[[0-9;]*m", "", line)
            if line and ("loop-engine]" in line or line.startswith(("error", "warning", "Error"))):
                self.logs.append(line.replace("[loop-engine] ", "· "))
        self._refresh()


def main() -> int:
    a = conductor.build_argparser().parse_args()
    console = Console()
    is_tty = console.is_terminal
    with Live(console=console, screen=is_tty, auto_refresh=True, refresh_per_second=8, transient=False) as live:
        rep = RichReporter(live)
        rc = conductor.run(a.repo, a.task, a.commander, a.reviewer, a.max_iters, a.test_cmd, rep)
    console.print(f"[bold]指挥程序退出码: {rc}[/bold]")
    return rc


if __name__ == "__main__":
    sys.exit(main())
