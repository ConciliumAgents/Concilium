#!/usr/bin/env python3
"""Standalone Concilium conductor.

The conductor owns control flow only: initialize the table, ask the commander
to plan, dispatch executor seats, run review, iterate, and stop. Model work is
delegated to native headless seats in bin/seat-*.sh. All seats read shared
context from .roundtable/KB.

Rendering is separated from control: run() emits Reporter events.
  - TextReporter (default): plain text progress
  - tui.py RichReporter: rich.Live dashboard
Dependencies: Python standard library only.
"""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, re, signal, subprocess, sys, time
from pathlib import Path

BIN = Path(__file__).resolve().parent
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import concilium_artifacts  # noqa: E402

AGENTS = {"claude", "codex", "hermes", "kimi"}
# Slow or execution-unsafe seats stay in plan/review mode only.
EXEC_EXCLUDE = {"claude", "codex"}
# Fast executor fallback priority. Reviewer selection is handled separately in
# _resolve_reviewer so the maker/checker split can prefer heterogeneous review.
FAST_PRIORITY = ["kimi", "hermes"]
REVIEW_FALLBACK_PRIORITY = ["claude", "hermes", "kimi", "codex"]
VERDICT_MAP = {0: "PASS", 2: "BLOCK", 1: "ERR"}
AUDIT_TERMS = (
    "audit",
    "review",
    "inspect",
)
READ_ONLY_TERMS = (
    "read-only",
    "read only",
    "readonly",
    "do not modify",
    "do not edit",
    "no changes",
)


def is_read_only_audit_task(task: str) -> bool:
    text = str(task or "").lower()
    return any(term in text for term in AUDIT_TERMS) and any(term in text for term in READ_ONLY_TERMS)


def split_path_list(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        raw_items = [str(item) for item in value]
    else:
        raw_items = re.split(r"[,:]", str(value))
    return [item.strip() for item in raw_items if item.strip()]


def _env_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "")).strip("_").upper()
    return token or "UNKNOWN"


def seat_timeout_env_key(agent: str, mode: str = "") -> str:
    parts = ["LOOP_SEAT_TIMEOUT", _env_token(agent)]
    if mode:
        parts.append(_env_token(mode))
    return "_".join(parts)


def _parse_timeout_seconds(value: str, source: str) -> int:
    try:
        timeout = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source} must be a positive integer") from exc
    if timeout <= 0:
        raise ValueError(f"{source} must be positive")
    return timeout


def resolve_seat_timeout(
    agent: str,
    mode: str,
    default: int | None = None,
    env: dict[str, str] | None = None,
) -> int:
    source_env = env if env is not None else os.environ
    candidates = [
        seat_timeout_env_key(agent, mode),
        seat_timeout_env_key(agent),
        "LOOP_SEAT_TIMEOUT",
    ]
    for key in candidates:
        value = source_env.get(key)
        if value:
            return _parse_timeout_seconds(value, key)
    return _parse_timeout_seconds(default if default is not None else 600, "default seat timeout")


# ---------------- Reporter event interface ----------------
class Reporter:
    def start(self, repo, task, commander, reviewer, max_iters): ...
    def round(self, it): ...
    def plan(self, plan): ...
    def seat(self, agent, mode, subtask="", rc=None, phase="start"): ...
    def verdict(self, reviewer, v): ...
    def finish(self, status, it): ...
    def log(self, msg): ...
    def transcript(self, agent, mode, text): ...


class TextReporter(Reporter):
    def start(self, repo, task, commander, reviewer, max_iters):
        print(f"\033[36m[conductor]\033[0m table opened repo={repo}", file=sys.stderr)
        print(f"\033[36m[conductor]\033[0m commander={commander} reviewer={reviewer} max_rounds={max_iters} task={task}", file=sys.stderr)
    def round(self, it):
        print(f"\n\033[1m===== Round {it} =====\033[0m", flush=True)
    def plan(self, plan):
        print("\033[36m[conductor]\033[0m assignments: " + "; ".join(f"{p['agent']} <- {p['subtask'][:30]}" for p in plan), flush=True)
    def seat(self, agent, mode, subtask="", rc=None, phase="start"):
        if phase == "start":
            print(f"\033[36m[conductor]\033[0m -> {agent} [{mode}] {subtask[:40]}", file=sys.stderr, flush=True)
        else:
            print(f"\033[36m[conductor]\033[0m done {agent} [{mode}] rc={rc}", file=sys.stderr, flush=True)
    def verdict(self, reviewer, v):
        print(f"\033[36m[conductor]\033[0m reviewer {reviewer} verdict: {v}", flush=True)
    def finish(self, status, it):
        msg = {"PASS": f"\033[32mRound {it} passed review.\033[0m",
               "ERR": f"\033[31mReview returned ERR. Inspect minutes manually.\033[0m",
               "CAP": f"\033[33mReached round cap at {it}; handing back to the operator.\033[0m"}.get(status, status)
        print("\n" + msg, flush=True)
    def log(self, msg):
        if msg.strip():
            print(f"\033[2m{msg.rstrip()}\033[0m", file=sys.stderr, flush=True)
    def transcript(self, agent, mode, text):
        t = (text or "").strip()
        if t:
            print(f"\n\033[2m---- {agent} [{mode}] transcript ----\033[0m\n{t[:4000]}", flush=True)


# ---------------- Seat invocation ----------------
def run_seat(agent: str, mode: str, repo: str, brief: str = "", extra: list[str] | None = None,
             provider: str = "", model: str = "") -> tuple[int, str]:
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
    # Pass per-seat model selection through the child environment only.
    child_env = dict(os.environ)
    child_env["LOOP_SEAT_PROVIDER"] = provider or ""
    child_env["LOOP_SEAT_MODEL"] = model or ""
    # Give every seat a timeout and kill its process group on timeout so one
    # stuck agent cannot stall the whole loop.
    timeout = resolve_seat_timeout(agent, mode, env=child_env)
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, start_new_session=True, env=child_env)
    except OSError as e:
        return 1, f"(failed to start seat {agent}: {e})"
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
        return 124, (out or "") + f"\n(seat {agent} [{mode}] timed out after {timeout}s; killed process group)"


def timed_run_seat(
    repo: str,
    iteration: int,
    agent: str,
    mode: str,
    brief: str = "",
    extra: list[str] | None = None,
    provider: str = "",
    model: str = "",
) -> tuple[int, str]:
    started = time.monotonic()
    rc, out = run_seat(agent, mode, repo, brief=brief, extra=extra, provider=provider, model=model)
    _append_seat_timing(repo, iteration, agent, mode, rc, time.monotonic() - started)
    return rc, out


def _record_review_verdict(state: dict, iteration: int, agent: str, mode: str, rc: int) -> None:
    if mode != "review":
        return
    verdict = VERDICT_MAP.get(int(rc), "ERR")
    row = {
        "iter": iteration,
        "seat": agent,
        "mode": mode,
        "rc": int(rc),
        "verdict": verdict,
    }
    state.setdefault("seat_verdicts", []).append(row)
    state["verdicts"] = [
        item.get("verdict", "ERR")
        for item in state.get("seat_verdicts", [])
        if item.get("mode") == "review"
    ]


def _append_seat_timing(repo: str, iteration: int, agent: str, mode: str, rc: int, duration: float) -> None:
    try:
        state_path = session_dir(repo) / "roundtable.json"
        state = {}
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        state.setdefault("seat_timings", []).append({
            "iter": iteration,
            "seat": agent,
            "mode": mode,
            "rc": rc,
            "duration_seconds": round(max(0.0, duration), 3),
        })
        _record_review_verdict(state, iteration, agent, mode, rc)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _dry_seat(agent: str, mode: str, brief: str) -> tuple[int, str]:
    if mode == "plan":
        plan = [{"agent": "kimi", "subtask": "Implement the core change"},
                {"agent": "hermes", "subtask": "Check environment risks"}]
        return 0, f"[dry] assignments\n```json\n{json.dumps(plan, ensure_ascii=False)}\n```"
    if mode == "review":
        v = os.environ.get("LOOP_DRY_VERDICT", "PASS")
        return (0 if v == "PASS" else 2), f"[dry] {agent} -> VERDICT: {v}"
    return 0, f"[dry] {agent} exec: {brief[:60]}"


def sh_capture(script: str, *args: str) -> tuple[int, str]:
    p = subprocess.run([str(BIN / script), *args], capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _slug(text: str, n: int = 24) -> str:
    s = re.sub(r"[^0-9A-Za-z]+", "-", text).strip("-")
    return s[:n] or "task"


def session_dir(repo: str) -> Path:
    """Current session directory: .roundtable/sessions/<LOOP_SESSION>/."""
    sid = os.environ.get("LOOP_SESSION", "default")
    return Path(repo) / ".roundtable" / "sessions" / sid


def set_participants(repo: str | Path, seats: list[str]) -> None:
    """Record actual seated participants in roundtable.json; best effort only."""
    try:
        state_path = session_dir(str(repo)) / "roundtable.json"
        state = {}
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        state["participants"] = list(seats)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _load_profiles(repo: str) -> dict:
    """Read roundtable-memory/ROSTER-PROFILES.md and return {seat: profile}."""
    p = Path(repo) / "roundtable-memory" / "ROSTER-PROFILES.md"
    if not p.is_file():
        return {}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        out, cur, buf = {}, None, []
        for line in text.splitlines():
            m = re.match(r"^##\s+([A-Za-z0-9_]+)\b", line)
            if m:
                if cur:
                    out[cur] = "\n".join(buf).strip()
                cur, buf = m.group(1).strip().lower(), []
            elif cur is not None:
                buf.append(line)
        if cur:
            out[cur] = "\n".join(buf).strip()
        return out
    except Exception as e:
        print(f"\033[33m[loop-engine] failed to parse ROSTER-PROFILES; using built-in roster only: {e}\033[0m", file=sys.stderr)
        return {}


def write_roster(repo: str, seats=None, seat_models=None) -> list[str]:
    """Detect local seats, write KB/roster.md, and return seated seat names."""
    seat_models = seat_models or {}
    detect = BIN / "roster-detect.py"
    try:
        p = subprocess.run([sys.executable, str(detect), "--json"], capture_output=True, text=True, timeout=60)
        detected = json.loads(p.stdout)
    except Exception:
        return []
    profiles = _load_profiles(repo)
    lines = [
        "# Seat Roster",
        "",
        "This file lists the seats available to the current Concilium session.",
        "",
    ]
    seated = []
    for s in detected:
        name = s["seat"]
        if not s.get("available"):
            continue
        if seats is not None and name not in seats:
            lines += [f"## ~~{name}~~ (not selected for this session)", ""]
            continue
        seated.append(name)
        chosen = seat_models.get(name, {})
        prov = chosen.get("provider") or s.get("provider", "")
        mod = chosen.get("model") or s.get("model", "")
        eff = f" [{s.get('effort')}]" if s.get("effort") else ""
        block = [f"## {name} (using {mod} via {prov}{eff})",
                 f"- Built-in strength: {s.get('strength','')}",
                 f"- Supported modes: {', '.join(s.get('modes', []))}"]
        prof = profiles.get(name)
        if prof:
            block.append("- Operational profile:")
            block += ["  " + ln for ln in prof.splitlines() if ln.strip()]
        lines += block + [""]
    try:
        (session_dir(repo) / "KB" / "roster.md").write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass
    return seated


def _claude_project_memory(repo: str) -> Path:
    """Claude stores project memory under a path-derived project directory."""
    mapped = repo.replace("/", "-")
    return Path.home() / ".claude" / "projects" / mapped / "memory"


def import_memory(repo: str) -> int:
    """Import external project memory into KB/imported-memory.md for all seats."""
    parts = [
        "# Imported Project Memory",
        "",
        "Collected by the memory bridge for the current Concilium session.",
        "",
    ]
    n = 0
    cm = Path(repo) / "CLAUDE.md"
    if cm.exists():
        try:
            parts += ["## Repository CLAUDE.md", cm.read_text(encoding="utf-8", errors="replace")[:4000], ""]; n += 1
        except OSError:
            pass
    md = _claude_project_memory(repo)
    if md.is_dir():
        for f in sorted(md.glob("*.md")):
            try:
                parts += [f"## Claude Project Memory - {f.name}", f.read_text(encoding="utf-8", errors="replace")[:3000], ""]; n += 1
            except OSError:
                pass
    cur = os.environ.get("LOOP_SESSION", "")
    sroot = Path(repo) / ".roundtable" / "sessions"
    if sroot.is_dir():
        for sd in sorted(sroot.iterdir()):
            if sd.name == cur:
                continue
            c = sd / "KB" / "conclusion.md"
            if c.exists():
                try:
                    parts += [f"## Prior Session Conclusion - {sd.name}", c.read_text(encoding="utf-8", errors="replace")[:1500], ""]; n += 1
                except OSError:
                    pass
    # Optional repo-local neutral memory source. Disabled by default.
    if os.environ.get("LOOP_USE_ROUNDTABLE_MEMORY", "0") == "1":
        try:
            project = os.environ.get("LOOP_ARCHIVE_PROJECT") or Path(repo).name
            rt_parts, rt_n = _roundtable_memory(repo, project)
            parts += rt_parts; n += rt_n
        except Exception:
            pass
    try:
        out_path = session_dir(repo) / "KB" / "imported-memory.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(parts), encoding="utf-8")
    except OSError:
        pass
    return n


def _hmatch(line: str, header: str) -> bool:
    """Match a Markdown header exactly or with a parenthetical/suffix."""
    s = line.strip()
    return s == header or s.startswith(header + "(") or s.startswith(header + " ")


def _extract_section(text: str, header: str) -> str:
    """Extract a level-2 Markdown section body."""
    out, grab = [], False
    for ln in text.splitlines():
        if _hmatch(ln, header):
            grab = True; continue
        if grab and ln.startswith("## "):
            break
        if grab:
            out.append(ln)
    return "\n".join(out).strip()


def _extract_subsection(section_text: str, h3: str) -> str:
    """Extract a level-3 Markdown subsection body."""
    out, grab = [], False
    for ln in section_text.splitlines():
        if _hmatch(ln, h3):
            grab = True; continue
        if grab and (ln.startswith("### ") or ln.startswith("## ")):
            break
        if grab:
            out.append(ln)
    return "\n".join(out).strip()


def _roundtable_memory(repo: str, project: str) -> tuple[list[str], int]:
    """Read repo-local roundtable-memory/ index and lessons for this project."""
    root = Path(repo) / "roundtable-memory"
    parts: list[str] = []
    n = 0
    if not root.is_dir():
        return parts, n
    idx = root / "INDEX.md"
    if idx.exists():
        try:
            parts += ["## Roundtable Outcome Index (roundtable-memory/INDEX.md)",
                      idx.read_text(encoding="utf-8", errors="replace")[:4000], ""]; n += 1
        except OSError:
            pass
    lessons = root / "LESSONS.md"
    if lessons.exists():
        try:
            text = lessons.read_text(encoding="utf-8", errors="replace")
            general = _extract_section(text, "## General Rules")
            proj_sec = _extract_section(text, "## Project-Specific Lessons")
            proj = _extract_subsection(proj_sec, f"### {project}") if proj_sec else ""
            body = []
            if general:
                body.append("### General Rules\n" + general)
            if proj:
                body.append(f"### Current Project ({project}) Lessons\n" + proj)
            if body:
                parts += ["## Roundtable Lessons (General Rules + Current Project)",
                          "\n\n".join(body), ""]; n += 1
        except OSError:
            pass
    return parts, n


def write_conclusion(repo: str, task: str, status: str, rounds: int, verdicts: list) -> None:
    """Write the session conclusion to KB/conclusion.md."""
    sd = session_dir(repo)
    def _git(*a):
        try:
            return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            return ""
    diffstat = _git("diff", "--stat", "HEAD")
    log = _git("log", "--oneline", "--grep", "loop-engine", "-n", "20")
    minutes = sorted((sd / "minutes").glob("*.md")) if (sd / "minutes").is_dir() else []
    minute_lines = [f"- {m.name}" for m in minutes] or ["None."]
    lines = [
        f"# Concilium Session Conclusion - {os.environ.get('LOOP_SESSION', '')}", "",
        f"- Task: {task}",
        f"- Status: **{status}** ({rounds} rounds)",
        f"- Verdicts by round: {', '.join(verdicts) or '-'}", "",
        "## Changed Files (git diff --stat HEAD)", "```", diffstat or "No uncommitted changes; see checkpoint commits below.", "```", "",
        "## Checkpoint Commits", "```", log or "None.", "```", "",
        "## Seat Minutes", *minute_lines, "",
        "## Remaining Risks / Next Steps", "If status is BLOCK or CAP, inspect the reviewer findings in minutes/.",
    ]
    try:
        (sd / "KB" / "conclusion.md").write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass


def archive_to_memory(repo: str, task: str, status: str, rounds: int, verdicts: list) -> None:
    """Archive completed outcomes and lessons into repo-local roundtable-memory/."""
    if os.environ.get("LOOP_ARCHIVE", "1") != "1":
        return
    try:
        root = Path(repo) / "roundtable-memory"
        if not root.is_dir():
            return
        project = os.environ.get("LOOP_ARCHIVE_PROJECT") or Path(repo).name
        sid = os.environ.get("LOOP_SESSION", "")
        sd = session_dir(repo)
        if status == "PASS":
            _archive_result(root, project, task, status, rounds, verdicts, sid)
        _archive_lessons(root, project, sd)
    except Exception:
        pass


def _sid_date(sid: str) -> str:
    """Derive the session date from a YYYYMMDD-* LOOP_SESSION id."""
    m = re.match(r"(\d{4})(\d{2})(\d{2})", sid or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else datetime.date.today().isoformat()


def _archive_result(root: Path, project: str, task: str, status: str,
                    rounds: int, verdicts: list, sid: str) -> None:
    """Archive a PASS result leaf and update INDEX.md."""
    topic = _slug(task)
    date = _sid_date(sid)
    pdir = root / project
    pdir.mkdir(parents=True, exist_ok=True)
    leaf = pdir / f"{topic}.md"
    if not leaf.exists():
        leaf.write_text("\n".join([
            f"# {task}", "",
            f"- **Date**: {date}",
            f"- **Project**: {project}",
            f"- **Concilium session**: {sid}",
            f"- **Status**: finalized ({status}, {rounds} rounds: {', '.join(verdicts) or '-'})", "",
            "## Topic", task, "",
            "## Conclusion", "This topic was finalized by Concilium. See the source pointers for the full conclusion and round verdicts.", "",
            "## Key Decisions", "- See conclusion.md and minutes; refine this section manually when useful.", "",
            "## Source Pointers", "> Paths are relative to the repository root.",
            f"- KB conclusion: `.roundtable/sessions/{sid}/KB/conclusion.md`",
            f"- Seat minutes: `.roundtable/sessions/{sid}/minutes/`", "",
            "## Update History",
            "| Date | Concilium Session | Change Summary |",
            "|------|---------|---------|",
            f"| {date} | {sid} | Initial finalized outcome ({status}) |", "",
        ]), encoding="utf-8")
    else:
        txt = leaf.read_text(encoding="utf-8", errors="replace")
        row = f"| {date} | {sid} | Refinalized by Concilium ({status}) |"
        if row not in txt:
            leaf.write_text(txt.rstrip() + "\n" + row + "\n", encoding="utf-8")
    _update_index(root, project, topic, task, date, status)


def _update_index(root: Path, project: str, topic: str, task: str, date: str, status: str) -> None:
    """Append a result link under the project section in INDEX.md."""
    idx = root / "INDEX.md"
    if not idx.exists():
        return
    lines = idx.read_text(encoding="utf-8", errors="replace").splitlines()
    target = f"]({project}/{topic}.md)"
    if any(target in ln for ln in lines):
        return
    new_line = f"- [{task}]({project}/{topic}.md) - {date} - finalized ({status})"
    res, in_sec, inserted = [], False, False
    for ln in lines:
        if _hmatch(ln, f"## {project}"):
            res.append(ln); in_sec = True; continue
        if in_sec and ln.startswith("## "):
            if not inserted:
                res.append(new_line); inserted = True
            in_sec = False
            res.append(ln); continue
        if in_sec and ln.strip() == "- No archived entries yet.":
            continue
        res.append(ln)
    if in_sec and not inserted:
        res.append(new_line); inserted = True
    if inserted:
        idx.write_text("\n".join(res) + "\n", encoding="utf-8")


def _archive_lessons(root: Path, project: str, sd: Path) -> None:
    """Archive ## Lessons from executor minutes into LESSONS.md."""
    lessons_path = root / "LESSONS.md"
    mdir = sd / "minutes"
    if not lessons_path.exists() or not mdir.is_dir():
        return
    general_new, proj_new = [], []
    for m in sorted(mdir.glob("iter-*-*-exec.md")):
        try:
            sec = _extract_section(m.read_text(encoding="utf-8", errors="replace"), "## Lessons")
        except OSError:
            continue
        if not sec:
            continue
        general_new += _lesson_items(_extract_subsection(sec, "### General"))
        proj_new += _lesson_items(_extract_subsection(sec, f"### {project}"))
    if not general_new and not proj_new:
        return
    text = lessons_path.read_text(encoding="utf-8", errors="replace")
    if general_new:
        text = _append_to_section(text, "## General Rules", None, general_new)
    if proj_new:
        text = _append_to_section(text, "## Project-Specific Lessons", f"### {project}", proj_new)
    lessons_path.write_text(text, encoding="utf-8")


def _lesson_items(section_text: str) -> list[str]:
    """Collect real '- ' lesson items and ignore placeholders."""
    items = []
    for ln in section_text.splitlines():
        s = ln.strip()
        if not s.startswith("- "):
            continue
        body = s[2:].strip()
        if not body or body.lower() in {"none.", "none", "n/a"} or body[0] in "(":
            continue
        items.append(s)
    return items


def _append_to_section(text: str, h2: str, h3, items: list[str]) -> str:
    """Append items to an h2/h3 section while deduplicating by SHA-256."""
    existing = {hashlib.sha256(i.strip().encode("utf-8")).hexdigest()
                for i in text.splitlines() if i.strip().startswith("- ")}
    fresh = []
    for it in items:
        h = hashlib.sha256(it.strip().encode("utf-8")).hexdigest()
        if h not in existing:
            existing.add(h); fresh.append(it)
    if not fresh:
        return text
    res, in_h2, in_target, inserted = [], False, False, False
    for ln in text.splitlines():
        if _hmatch(ln, h2):
            res.append(ln); in_h2 = True; in_target = (h3 is None); continue
        if in_h2 and ln.startswith("## "):
            if in_target and not inserted:
                res += fresh; inserted = True
            in_h2 = in_target = False
            res.append(ln); continue
        if in_h2 and h3 is not None:
            if _hmatch(ln, h3):
                res.append(ln); in_target = True; continue
            if in_target and ln.startswith("### "):
                if not inserted:
                    res += fresh; inserted = True
                in_target = False
                res.append(ln); continue
        res.append(ln)
    if in_target and not inserted:
        res += fresh; inserted = True
    return "\n".join(res) + ("\n" if text.endswith("\n") else "")


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


def _resolve_reviewer(seated: list, requested: str) -> str:
    """Resolve the reviewer seat while preserving a maker/checker split."""
    if requested and requested in seated:
        return requested
    fast = [a for a in seated if a not in EXEC_EXCLUDE]
    if len(fast) >= 2:
        for cand in ("hermes", "kimi"):
            if cand in fast:
                return cand
        return fast[0]
    if "claude" in seated:
        return "claude"
    return fast[0] if fast else (seated[0] if seated else "")


def _fallback_plan(executors: list, task: str) -> list:
    """Fallback to the first fast executor when the commander yields no task."""
    target = next((a for a in FAST_PRIORITY if a in executors), executors[0])
    return [{"agent": target, "subtask": task}]


def build_plan_brief(feedback: str, executors: list[str], reviewer: str) -> str:
    """Build role constraints for the commander."""
    lines = [
        "[Current role constraints]",
        f"- Executor pool: {', '.join(executors) or '(empty)'}. Only executor-pool seats may receive implementation, modification, or testing subtasks.",
        f"- Reviewer: {reviewer or 'None.'}. Do not assign implementation work to the reviewer; the conductor runs read-only review after execution.",
        "- The plan JSON must contain only implementation subtasks for executor-pool seats. Do not output read-only review subtasks.",
    ]
    if feedback:
        lines += ["", feedback]
    return "\n".join(lines)


def _fallback_reviewers(seated: list[str], primary: str, executors: list[str]) -> list[str]:
    """Choose read-only backup reviewers after reviewer ERR."""
    return [
        agent for agent in REVIEW_FALLBACK_PRIORITY
        if agent in seated and agent != primary and agent not in executors
    ]


def _plan_note(plan_failed: bool, is_fallback: bool) -> str:
    """Describe planner anomalies without conflating fallback cases."""
    if is_fallback:
        why = "commander plan failed or timed out" if plan_failed else "no executable subtasks remained after filtering"
        return f"{why}; assigned one fast executor as fallback"
    if plan_failed:
        return "commander plan exited non-zero, but a parsed plan was used and may be incomplete"
    return ""


def build_brief(dropped: list, exec_failures: list, plan_failed: bool, is_fallback: bool = False) -> str:
    """Summarize round anomalies for the reviewer."""
    if not (dropped or exec_failures or plan_failed or is_fallback):
        return ""
    lines = ["[Round execution context: judge whether task completeness was harmed. "
             "If the task was completed by other seats, do not BLOCK mechanically because of the following failures.]"]
    note = _plan_note(plan_failed, is_fallback)
    if note:
        lines.append(f"- WARNING: {note}")
    for a, rc in exec_failures:
        tag = "timeout" if rc == 124 else f"rc={rc}"
        lines.append(f"- FAILED: {a}[exec] failed ({tag})")
    for p in dropped:
        lines.append(f"- WARNING: subtask was not executed because it targeted non-executor seat {p['agent']}: {p['subtask'][:50]}")
    return "\n".join(lines)


def _write_round_notes(repo: str, dropped: list, exec_failures: list,
                       plan_failed: bool, is_fallback: bool = False) -> None:
    """Append round anomalies to KB/state.md before review."""
    if not (dropped or exec_failures or plan_failed or is_fallback):
        return
    try:
        sp = session_dir(repo) / "KB" / "state.md"
        sp.parent.mkdir(parents=True, exist_ok=True)
        out = ["", "## Round Anomalies (conductor record)"]
        note = _plan_note(plan_failed, is_fallback)
        if note:
            out.append(f"- {note}")
        for a, rc in exec_failures:
            out.append(f"- {a}[exec] failed ({'timeout 124' if rc == 124 else f'rc={rc}'})")
        for p in dropped:
            out.append(f"- Subtask removed and not executed; non-executor seat {p['agent']}: {p['subtask'][:60]}")
        with sp.open("a", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
    except OSError:
        pass


def _run_read_only_audit(
    repo: str,
    task: str,
    commander: str,
    reviewer: str,
    max_iters: int,
    test_cmd: str,
    reporter: Reporter,
    seated: list[str],
    seat_models: dict,
    required_artifact_paths: list[str] | None,
    allowed_write_paths: list[str] | None,
) -> int:
    del max_iters

    def sm(agent):
        c = seat_models.get(agent, {})
        return c.get("provider", ""), c.get("model", "")

    review_seats = [reviewer] if reviewer and reviewer in seated else list(seated)
    set_participants(repo, review_seats)
    reporter.start(repo, task, commander, "read-only-audit", 1)
    if not review_seats:
        reporter.log("[loop-engine] WARNING: no seats available for read-only audit")
        reporter.finish("ERR", 0)
        return 1

    nimp = import_memory(repo)
    if nimp:
        reporter.log(f"[loop-engine] memory bridge: imported {nimp} external project memory sources into KB")
    _, o = sh_capture("kb-refresh.sh", repo, test_cmd)
    reporter.log(o)
    baseline_delta = concilium_artifacts.collect_delta(repo).get("delta_paths", [])

    reporter.round(1)
    verdicts = []
    brief = (
        "Read-only Concilium audit. Inspect the project and memory surfaces, do not modify files, "
        "and return concrete findings plus VERDICT: PASS or VERDICT: BLOCK."
    )
    for seat in review_seats:
        provider, model = sm(seat)
        reporter.seat(seat, "review", "read-only audit", phase="start")
        rc, out = timed_run_seat(repo, 1, seat, "review", brief=brief, provider=provider, model=model)
        reporter.seat(seat, "review", "", rc, phase="done")
        reporter.transcript(seat, "review", out)
        verdicts.append(VERDICT_MAP.get(rc, "ERR"))

    allowed = [".roundtable/**"] + list(allowed_write_paths or [])
    gate = concilium_artifacts.evaluate_artifact_gate(
        repo,
        required_artifact_paths=list(required_artifact_paths or []),
        allowed_write_paths=allowed,
        baseline_delta_paths=baseline_delta,
        allow_unlisted_required=False,
        allow_unlisted_delta=False,
    )
    if gate.get("status") != "passed":
        reporter.log("[artifact_gate] " + json.dumps(gate, ensure_ascii=False, sort_keys=True))
        reporter.verdict("artifact_gate", "BLOCK")
        reporter.finish("BLOCK", 1)
        return 2

    if any(verdict == "BLOCK" for verdict in verdicts):
        reporter.verdict("read-only-audit", "BLOCK")
        reporter.finish("BLOCK", 1)
        return 2
    if any(verdict == "ERR" for verdict in verdicts):
        reporter.verdict("read-only-audit", "ERR")
        reporter.finish("ERR", 1)
        return 1

    reporter.verdict("read-only-audit", "PASS")
    reporter.finish("PASS", 1)
    return 0


# ---------------- Main loop (rendering-independent) ----------------
def run(repo, task, commander="claude", reviewer="", max_iters=5, test_cmd="",
        reporter=None, seats=None, seat_models=None, audit_only=False,
        required_artifact_paths=None, allowed_write_paths=None) -> int:
    reporter = reporter or TextReporter()
    repo = str(Path(repo).expanduser().resolve())
    seat_models = seat_models or {}

    def sm(agent):
        c = seat_models.get(agent, {})
        return c.get("provider", ""), c.get("model", "")

    # Session id: isolate state inside the project unless LOOP_SESSION resumes one.
    if not os.environ.get("LOOP_SESSION"):
        os.environ["LOOP_SESSION"] = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + _slug(task)
    reporter.log(f"[conductor] session: {os.environ['LOOP_SESSION']}")
    _, o = sh_capture("roundtable-init.sh", repo, task); reporter.log(o)
    # Write the seated roster and run contract checks.
    seated = write_roster(repo, seats, seat_models)
    set_participants(repo, seated)
    if audit_only or is_read_only_audit_task(task):
        return _run_read_only_audit(
            repo,
            task,
            commander,
            reviewer,
            max_iters,
            test_cmd,
            reporter,
            seated,
            seat_models,
            split_path_list(required_artifact_paths),
            split_path_list(allowed_write_paths),
        )
    # Resolve reviewer dynamically; executors are seated seats minus slow seats and reviewer.
    reviewer = _resolve_reviewer(seated, reviewer)
    executors = [a for a in seated if a not in EXEC_EXCLUDE and a != reviewer]
    reporter.start(repo, task, commander, reviewer, max_iters)
    if seated:
        reporter.log(f"[loop-engine] seated: {', '.join(seated)}; reviewer: {reviewer or 'None.'}; "
                     f"executor_pool: {', '.join(executors) or '(empty)'}")
    if commander not in seated:
        reporter.log(f"[loop-engine] WARNING: commander '{commander}' is not seated (not selected or not installed); may fail")
    # Warn only when the reviewer can also execute and equals the commander.
    if commander == reviewer and reviewer not in EXEC_EXCLUDE:
        reporter.log("[loop-engine] commander equals executable reviewer; review is not independent")
    # Fail fast when no fast executor is available.
    if not executors:
        reporter.log("[loop-engine] WARNING: no fast executor is available (not seated or occupied as reviewer); "
                     "Concilium needs at least one fast executor")
        write_conclusion(repo, task, "CAP", 0, [])
        reporter.finish("CAP", 0)
        return 2
    nimp = import_memory(repo)
    if nimp:
        reporter.log(f"[loop-engine] memory bridge: imported {nimp} external project memory sources into KB")
    _, o = sh_capture("kb-refresh.sh", repo, test_cmd); reporter.log(o)

    feedback, verdicts, status, final_it = "", [], None, max_iters
    for it in range(1, max_iters + 1):
        reporter.round(it)

        # Commander plans work
        cp, cm = sm(commander)
        reporter.seat(commander, "plan", "read roster and assign subtasks", phase="start")
        rc, out = timed_run_seat(
            repo, it, commander, "plan",
            brief=build_plan_brief(feedback, executors, reviewer),
            provider=cp, model=cm,
        )
        reporter.seat(commander, "plan", "", rc, phase="done")
        reporter.transcript(commander, "plan", out)
        plan_failed = (rc != 0)
        raw = [p for p in extract_plan(out) if p["agent"] in seated]
        kept = [p for p in raw if p["agent"] in executors]
        dropped = [p for p in raw if p["agent"] not in executors]   # targeted non-executor seats
        for p in dropped:
            reporter.log(f"[conductor] removed non-executor subtask: {p['agent']} <- {p['subtask'][:30]}")
        is_fallback = not kept
        if is_fallback:
            plan = _fallback_plan(executors, task)
            why = "plan failed or timed out" if plan_failed else "no executable subtasks remained after filtering"
            reporter.log(f"[conductor] {why}; fallback assigned fast executor {plan[0]['agent']}")
        else:
            plan = kept
        reporter.plan(plan)

        # Dispatch execution serially; review happens afterward. Seat failures
        # do not stop remaining seats.
        exec_failures = []
        for p in plan:
            ep, em = sm(p["agent"])
            reporter.seat(p["agent"], "exec", p["subtask"], phase="start")
            erc, eout = timed_run_seat(repo, it, p["agent"], "exec", brief=p["subtask"], provider=ep, model=em)
            reporter.seat(p["agent"], "exec", p["subtask"], erc, phase="done")
            reporter.transcript(p["agent"], "exec", eout)
            if erc != 0:
                exec_failures.append((p["agent"], erc))

        # Write round anomalies to KB before review and inject them into the reviewer brief.
        _write_round_notes(repo, dropped, exec_failures, plan_failed, is_fallback)
        _, o = sh_capture("kb-refresh.sh", repo, test_cmd); reporter.log(o)

        # Review
        rbrief = build_brief(dropped, exec_failures, plan_failed, is_fallback)
        active_reviewer = reviewer
        verdict = "ERR"
        review_chain = [reviewer] + _fallback_reviewers(seated, reviewer, executors)
        for idx, candidate in enumerate(review_chain):
            rp, rm = sm(candidate)
            reporter.seat(candidate, "review", "independent review", phase="start")
            vrc, vout = timed_run_seat(repo, it, candidate, "review", brief=rbrief, provider=rp, model=rm)
            verdict = VERDICT_MAP.get(vrc, "ERR")
            reporter.seat(candidate, "review", "", vrc, phase="done")
            reporter.transcript(candidate, "review", vout)
            active_reviewer = candidate
            if verdict != "ERR":
                break
            if idx + 1 < len(review_chain):
                reporter.log(f"[loop-engine] WARNING: reviewer {candidate} returned ERR; switching to backup reviewer {review_chain[idx + 1]}")
        reviewer = active_reviewer
        reporter.verdict(reviewer, verdict)
        verdicts.append(verdict)

        _, o = sh_capture("checkpoint.sh", repo, f"{commander} round {it} verdict {verdict}"); reporter.log(o)

        if verdict in ("PASS", "ERR"):
            status, final_it = verdict, it
            break
        feedback = "Previous review returned BLOCK. Read reviewer findings in minutes/ and fix them."

    status = status or "CAP"
    write_conclusion(repo, task, status, final_it, verdicts)
    archive_to_memory(repo, task, status, final_it, verdicts)  # Archive into repo-local roundtable-memory/.
    reporter.finish(status, final_it)
    return {"PASS": 0, "ERR": 1, "CAP": 2}[status]


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Concilium conductor")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--commander", default="claude", choices=sorted(AGENTS), help="commander seat")
    ap.add_argument("--reviewer", default="", choices=sorted(AGENTS) + [""],
                    help="reviewer seat (empty = auto-select)")
    ap.add_argument("--max-iters", type=int, default=int(os.environ.get("LOOP_MAX_ITERS", "5")))
    ap.add_argument("--test-cmd", default=os.environ.get("LOOP_TEST_CMD", ""))
    ap.add_argument("--seats", default="", help="only seat these comma-separated agents (default: all available)")
    ap.add_argument(
        "--audit-only",
        action="store_true",
        default=os.environ.get("LOOP_AUDIT_ONLY", "").strip().lower() in {"1", "true", "yes", "on"},
        help="read-only audit: call review seats only, no plan/exec loop",
    )
    ap.add_argument(
        "--required-artifact-paths",
        default=os.environ.get("LOOP_REQUIRED_ARTIFACT_PATHS", ""),
        help="required artifact paths, comma- or colon-separated",
    )
    ap.add_argument(
        "--allowed-write-paths",
        default=os.environ.get("LOOP_ALLOWED_WRITE_PATHS", ""),
        help="allowed write paths, comma- or colon-separated; read-only audit allows no project writes by default",
    )
    return ap


def main() -> int:
    a = build_argparser().parse_args()
    seats = [x.strip() for x in a.seats.split(",") if x.strip()] or None
    return run(
        a.repo,
        a.task,
        a.commander,
        a.reviewer,
        a.max_iters,
        a.test_cmd,
        TextReporter(),
        seats=seats,
        audit_only=a.audit_only,
        required_artifact_paths=split_path_list(a.required_artifact_paths),
        allowed_write_paths=split_path_list(a.allowed_write_paths),
    )


if __name__ == "__main__":
    sys.exit(main())
