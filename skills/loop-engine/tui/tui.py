#!/usr/bin/env python3
"""Rich TUI reporter for Concilium.

This implements the conductor.Reporter interface and renders seat status,
current round, verdict, and logs. Control flow remains in conductor.py.
"""
from __future__ import annotations
import sys
from collections import deque
from pathlib import Path

# Deprecated product path: this TUI drives legacy conductor behavior directly.
# Phase 5 clients should use concilium-run.py / web/server.py service contracts.

# Allow the TUI to import the sibling bin/conductor.py module.
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
    "claude": "Opus | orchestration/refactoring/synthesis",
    "codex": "gpt-5.5 | code review",
    "hermes": "broad tools | heterogeneous backend capable",
    "kimi": "K2.7 | heterogeneous review/strong coding",
}
STATUS_STYLE = {"idle": "dim", "working": "yellow", "done": "green", "block": "red", "err": "red"}


class RichReporter(conductor.Reporter):
    def __init__(self, live: Live):
        self.live = live
        self.info = {}
        self.round_no = 0
        self.seats = {a: {"status": "idle", "detail": "", "role": ""} for a in sorted(conductor.AGENTS)}
        self.last_verdict = "-"
        self.final = ""
        self.logs: deque[str] = deque(maxlen=200)

    # ---- Rendering ----
    def _header(self):
        i = self.info
        t = Text()
        t.append("Concilium | Loop Engine\n", style="bold cyan")
        t.append(f"task: {i.get('task','')}\n")
        t.append(f"commander: {i.get('commander','')}   Reviewer: {i.get('reviewer','')}   ")
        t.append(f"round: {self.round_no}/{i.get('max_iters','')}   ")
        t.append("latest verdict: ")
        t.append(self.last_verdict, style="bold " + ("green" if self.last_verdict == "PASS" else "red" if self.last_verdict in ("BLOCK", "ERR") else "white"))
        if self.final:
            t.append("\n" + self.final, style="bold")
        return Panel(t, border_style="cyan")

    def _seats(self):
        tbl = Table(expand=True, show_edge=False)
        tbl.add_column("seat", style="bold", width=10)
        tbl.add_column("strength", width=24)
        tbl.add_column("status", width=28)
        for a, s in self.seats.items():
            st = s["status"]
            if st == "working":
                status = Spinner("dots", text=Text(f" {s['detail'][:24]}", style="yellow"))
            else:
                status = Text(("* " if st != "idle" else "- ") + st + (f" {s['detail'][:20]}" if s["detail"] else ""),
                              style=STATUS_STYLE.get(st, "white"))
            role = s["role"] + (" " if s["role"] else "") + ROLE_DESC.get(a, "")
            tbl.add_row(a, role, status)
        return Panel(tbl, title="seat", border_style="blue")

    def _log(self):
        body = Text("\n".join(list(self.logs)[-12:]), style="dim")
        return Panel(body, title="Meeting Log", border_style="grey50")

    def _refresh(self):
        self.live.update(Group(self._header(), self._seats(), self._log()))

    # ---- Reporter hooks ----
    def start(self, repo, task, commander, reviewer, max_iters):
        self.info = dict(repo=repo, task=task, commander=commander, reviewer=reviewer, max_iters=max_iters)
        self.seats[commander]["role"] = "[commander]"
        self.seats[reviewer]["role"] = ("[reviewer]" if not self.seats[reviewer]["role"] else self.seats[reviewer]["role"] + "[reviewer]")
        self.logs.append(f"open table: {task}")
        self._refresh()

    def round(self, it):
        self.round_no = it
        for s in self.seats.values():
            if s["status"] in ("done", "block", "err"):
                s["status"], s["detail"] = "idle", ""
        self.logs.append(f"--- Round {it} ---")
        self._refresh()

    def plan(self, plan):
        self.logs.append("Assignments: " + "; ".join(f"{p['agent']} <- {p['subtask'][:24]}" for p in plan))
        self._refresh()

    def seat(self, agent, mode, subtask="", rc=None, phase="start"):
        s = self.seats.get(agent)
        if not s:
            return
        if phase == "start":
            s["status"], s["detail"] = "working", f"{mode} {subtask[:20]}"
            self.logs.append(f"-> {agent} [{mode}] {subtask[:30]}")
        else:
            if mode == "review":
                v = conductor.VERDICT_MAP.get(rc, "ERR")
                s["status"] = "done" if v == "PASS" else ("block" if v == "BLOCK" else "err")
                s["detail"] = v
            else:
                s["status"], s["detail"] = ("done" if rc == 0 else "err"), f"rc={rc}"
            self.logs.append(f"done {agent} [{mode}] rc={rc}")
        self._refresh()

    def verdict(self, reviewer, v):
        self.last_verdict = v
        self.logs.append(f"verdict: {reviewer} -> {v}")
        self._refresh()

    def finish(self, status, it):
        self.final = {"PASS": f"Round {it} passed review",
                      "ERR": "Review returned ERR; handoff required",
                      "CAP": f"Reached round cap at {it}; handoff required"}.get(status, status)
        self.logs.append(self.final)
        self._refresh()

    def log(self, msg):
        for line in str(msg).splitlines():
            line = line.strip()
            # Strip ANSI escapes and keep high-signal log lines.
            import re
            line = re.sub(r"\033\[[0-9;]*m", "", line)
            if line and ("loop-engine]" in line or line.startswith(("error", "warning", "Error"))):
                self.logs.append(line.replace("[loop-engine] ", "- "))
        self._refresh()


def main() -> int:
    a = conductor.build_argparser().parse_args()
    console = Console()
    is_tty = console.is_terminal
    with Live(console=console, screen=is_tty, auto_refresh=True, refresh_per_second=8, transient=False) as live:
        rep = RichReporter(live)
        rc = conductor.run(a.repo, a.task, a.commander, a.reviewer, a.max_iters, a.test_cmd, rep)
    console.print(f"[bold]Conductor exit code: {rc}[/bold]")
    return rc


if __name__ == "__main__":
    sys.exit(main())
