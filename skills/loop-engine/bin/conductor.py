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
import argparse, datetime, hashlib, json, os, re, signal, subprocess, sys, time
from pathlib import Path

BIN = Path(__file__).resolve().parent
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import concilium_artifacts  # noqa: E402

AGENTS = {"claude", "codex", "hermes", "kimi"}
# 慢/不宜执行的座位：claude=Opus 易超时；codex=慢且连接坏。这些座位只指挥/验证、不进 exec。
EXEC_EXCLUDE = {"claude", "codex"}
# 飞毛腿执行兜底优先级（kimi=K2.7 强编码优先执行）。注意：reviewer 选座优先级另在
# _resolve_reviewer 内单独定（异质 hermes=deepseek 优先复审），与此处执行优先级有意不同。
FAST_PRIORITY = ["kimi", "hermes"]
REVIEW_FALLBACK_PRIORITY = ["claude", "hermes", "kimi", "codex"]
VERDICT_MAP = {0: "PASS", 2: "BLOCK", 1: "ERR"}
AUDIT_TERMS = (
    "audit",
    "review",
    "inspect",
    "审计",
    "审查",
    "审核",
    "复审",
    "检查",
)
READ_ONLY_TERMS = (
    "read-only",
    "read only",
    "readonly",
    "do not modify",
    "do not edit",
    "no changes",
    "只读",
    "不要修改",
    "不修改",
    "不要改",
    "不改动",
    "不写入",
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


# ---------------- Reporter：过程事件接口 ----------------
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
    def transcript(self, agent, mode, text):
        t = (text or "").strip()
        if t:
            print(f"\n\033[2m┄┄ {agent} [{mode}] 发言 ┄┄\033[0m\n{t[:4000]}", flush=True)


# ---------------- 座位调用 ----------------
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
    # 每座位的「用哪个脑子」经环境变量下传给座位脚本（不污染全局，仅本次子进程）
    child_env = dict(os.environ)
    child_env["LOOP_SEAT_PROVIDER"] = provider or ""
    child_env["LOOP_SEAT_MODEL"] = model or ""
    # 每个座位调用都设超时 + 进程组强杀：一个 agent 卡死不得拖垮整个循环。
    # start_new_session 让座位脚本及其子孙（codex/hermes node 进程）同属一个进程组，
    # 超时时整组 SIGKILL，避免 codex 等孙进程变孤儿继续空跑。
    timeout = resolve_seat_timeout(agent, mode, env=child_env)
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, start_new_session=True, env=child_env)
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
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _dry_seat(agent: str, mode: str, brief: str) -> tuple[int, str]:
    if mode == "plan":
        plan = [{"agent": "kimi", "subtask": "实施核心改动"},
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


def _load_profiles(repo: str) -> dict:
    """读 roundtable-memory/ROSTER-PROFILES.md，返回 {seat: 画像正文}。
    文件不存在=正常（返回 {} → 退化纯出厂层）；读/解析异常 → 整体回退 {} + 警告（绝不半合并）。"""
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
        print(f"\033[33m[loop-engine] ROSTER-PROFILES 解析失败，退化纯出厂层: {e}\033[0m", file=sys.stderr)
        return {}


def write_roster(repo: str, seats=None, seat_models=None) -> list[str]:
    """探测本地座位，写本会议在座成员的 KB/roster.md（标注各自本次用的脑子），返回在座座位名列表。
    seats=None 表示所有可用都上桌；否则按白名单。seat_models={agent:{provider,model}}。"""
    seat_models = seat_models or {}
    detect = BIN / "roster-detect.py"
    try:
        p = subprocess.run([sys.executable, str(detect), "--json"], capture_output=True, text=True, timeout=60)
        detected = json.loads(p.stdout)
    except Exception:
        return []
    profiles = _load_profiles(repo)   # {} 时退化为纯出厂层（零回归）
    lines = ["# 座位花名册（KB · 本会议在座成员，总指挥按出厂特长 + 实战画像派活）", ""]
    seated = []
    for s in detected:
        name = s["seat"]
        if not s.get("available"):
            continue
        if seats is not None and name not in seats:
            lines += [f"## ~~{name}~~（本次未勾选上桌）", ""]
            continue
        seated.append(name)
        chosen = seat_models.get(name, {})
        prov = chosen.get("provider") or s.get("provider", "")
        mod = chosen.get("model") or s.get("model", "")
        eff = f" [{s.get('effort')}]" if s.get("effort") else ""
        block = [f"## {name}（本次用 {mod} via {prov}{eff}）",
                 f"- 出厂特长：{s.get('strength','')}",
                 f"- 可任模式：{', '.join(s.get('modes', []))}"]
        prof = profiles.get(name)
        if prof:
            block.append("- 实战画像（据此选席派活）：")
            block += ["  " + ln for ln in prof.splitlines() if ln.strip()]
        lines += block + [""]
    try:
        (session_dir(repo) / "KB" / "roster.md").write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass
    return seated


def _claude_project_memory(repo: str) -> Path:
    """Claude 按项目存记忆的目录：路径 / → - 映射。"""
    mapped = repo.replace("/", "-")
    return Path.home() / ".claude" / "projects" / mapped / "memory"


def import_memory(repo: str) -> int:
    """记忆桥（进）：把仓库外的项目记忆汇集进本会话 KB/imported-memory.md，
    让 codex/hermes 这些读不到 Claude 私库的座位也看到完整项目。只读拉取。
    各源各自 try/except 加固：单文件读失败只跳过该源，不拖垮整桥（正常路径行为不变）。"""
    parts = ["# 导入的项目记忆（memory-bridge 汇集 · 所有座位自取）", ""]
    n = 0
    cm = Path(repo) / "CLAUDE.md"
    if cm.exists():
        try:
            parts += ["## 仓库 CLAUDE.md", cm.read_text(encoding="utf-8", errors="replace")[:4000], ""]; n += 1
        except OSError:
            pass
    md = _claude_project_memory(repo)
    if md.is_dir():
        for f in sorted(md.glob("*.md")):
            try:
                parts += [f"## Claude 项目记忆 · {f.name}", f.read_text(encoding="utf-8", errors="replace")[:3000], ""]; n += 1
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
                    parts += [f"## 过往会话结论 · {sd.name}", c.read_text(encoding="utf-8", errors="replace")[:1500], ""]; n += 1
                except OSError:
                    pass
    # 新源：git 化的中立持久记忆 roundtable-memory/。默认关（LOOP_USE_ROUNDTABLE_MEMORY=0）；
    # 关时此块不执行 → 输出与改造前逐字一致（零回归死线）。开时追加在末尾，不动既有字节。
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
    """标题行匹配：精确相等，或 header 后紧跟 全/半角括号 或 空格
    （容忍 '## 通用铁律（说明…）' 这类带后缀标题，但不误匹配 '## 通用铁律X'）。"""
    s = line.strip()
    return s == header or s.startswith(header + "（") or s.startswith(header + "(") or s.startswith(header + " ")


def _extract_section(text: str, header: str) -> str:
    """取 markdown 中 header（## 级）到下一个 ## 之间的正文，strip。容忍带后缀标题。"""
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
    """在一段正文里取 h3（### 级）子节到下一个 ###/## 之间的正文，strip。"""
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
    """读 git 化的中立持久记忆 roundtable-memory/：成果 INDEX + 教训分层召回
    （## 通用铁律 全量 + 仅当前 project 的 ### <project> 节，不读他项目、不读原始纪要）。
    返回 (parts, n)。整体只读、容错。"""
    root = Path(repo) / "roundtable-memory"
    parts: list[str] = []
    n = 0
    if not root.is_dir():
        return parts, n
    idx = root / "INDEX.md"
    if idx.exists():
        try:
            parts += ["## 圆桌成果索引（roundtable-memory/INDEX.md · 主源）",
                      idx.read_text(encoding="utf-8", errors="replace")[:4000], ""]; n += 1
        except OSError:
            pass
    lessons = root / "LESSONS.md"
    if lessons.exists():
        try:
            text = lessons.read_text(encoding="utf-8", errors="replace")
            general = _extract_section(text, "## 通用铁律")
            proj_sec = _extract_section(text, "## 分项目教训")
            proj = _extract_subsection(proj_sec, f"### {project}") if proj_sec else ""
            body = []
            if general:
                body.append("### 通用铁律\n" + general)
            if proj:
                body.append(f"### 本项目（{project}）教训\n" + proj)
            if body:
                parts += ["## 圆桌教训库（LESSONS · 通用铁律全量 + 本项目，开会必读）",
                          "\n\n".join(body), ""]; n += 1
        except OSError:
            pass
    return parts, n


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


def archive_to_memory(repo: str, task: str, status: str, rounds: int, verdicts: list) -> None:
    """记忆桥（出）：散会归档到 git 化的 roundtable-memory/。
      - status==PASS：成果落 <project>/<topic>.md 叶子 + 更新 INDEX.md（档案馆只收定稿）
      - 任何成败：抽各执行席纪要 minutes/iter-*-*-exec.md 的 `## 教训` 节 → LESSONS.md
    纯标准库、指挥进程内执行、不调任何座位 → 天然 agent 无关。受 LOOP_ARCHIVE 控制（默认 '1'）。失败不抛。"""
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
    """从 LOOP_SESSION 前缀 'YYYYMMDD-...' 取会话日期；解析不出回退今天。"""
    m = re.match(r"(\d{4})(\d{2})(\d{2})", sid or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else datetime.date.today().isoformat()


def _archive_result(root: Path, project: str, task: str, status: str,
                    rounds: int, verdicts: list, sid: str) -> None:
    """PASS 成果落叶子（不存在则建模板，存在则历次更新表 append）+ 更新 INDEX。"""
    topic = _slug(task)
    date = _sid_date(sid)
    pdir = root / project
    pdir.mkdir(parents=True, exist_ok=True)
    leaf = pdir / f"{topic}.md"
    if not leaf.exists():
        leaf.write_text("\n".join([
            f"# {task}", "",
            f"- **日期**：{date}",
            f"- **项目**：{project}",
            f"- **圆桌会话**：{sid}",
            f"- **状态**：定稿（{status}，共 {rounds} 轮：{', '.join(verdicts) or '—'}）", "",
            "## 议题", task, "",
            "## 结论", "本议题圆桌定稿；完整结论与各轮裁决见源指针 conclusion.md（可人工提炼补充本节）。", "",
            "## 关键决策", "- （见 conclusion.md / minutes；可人工提炼补充）", "",
            "## 源指针", "> 路径以仓库根为基准",
            f"- KB 结论：`.roundtable/sessions/{sid}/KB/conclusion.md`",
            f"- 座位发言：`.roundtable/sessions/{sid}/minutes/`", "",
            "## 历次更新",
            "| 日期 | 圆桌会话 | 变更摘要 |",
            "|------|---------|---------|",
            f"| {date} | {sid} | 初始定稿（{status}） |", "",
        ]), encoding="utf-8")
    else:
        txt = leaf.read_text(encoding="utf-8", errors="replace")
        row = f"| {date} | {sid} | 再次圆桌定稿（{status}） |"
        if row not in txt:
            leaf.write_text(txt.rstrip() + "\n" + row + "\n", encoding="utf-8")
    _update_index(root, project, topic, task, date, status)


def _update_index(root: Path, project: str, topic: str, task: str, date: str, status: str) -> None:
    """在 INDEX.md 的 `## <project>` 节追加指向叶子的行，并删该节 '（尚无归档）' 占位。"""
    idx = root / "INDEX.md"
    if not idx.exists():
        return
    lines = idx.read_text(encoding="utf-8", errors="replace").splitlines()
    target = f"]({project}/{topic}.md)"
    if any(target in ln for ln in lines):
        return  # 已索引
    new_line = f"- [{task}]({project}/{topic}.md) — {date} · 定稿（{status}）"
    res, in_sec, inserted = [], False, False
    for ln in lines:
        if _hmatch(ln, f"## {project}"):
            res.append(ln); in_sec = True; continue
        if in_sec and ln.startswith("## "):
            if not inserted:
                res.append(new_line); inserted = True
            in_sec = False
            res.append(ln); continue
        if in_sec and ln.strip() == "- （尚无归档）":
            continue  # 删占位
        res.append(ln)
    if in_sec and not inserted:
        res.append(new_line); inserted = True
    if inserted:
        idx.write_text("\n".join(res) + "\n", encoding="utf-8")


def _archive_lessons(root: Path, project: str, sd: Path) -> None:
    """抽各执行席纪要（iter-*-*-exec.md）的 `## 教训` 节（### 通用 / ### <项目>）→ LESSONS.md 对应区，SHA-256 去重。"""
    lessons_path = root / "LESSONS.md"
    mdir = sd / "minutes"
    if not lessons_path.exists() or not mdir.is_dir():
        return
    general_new, proj_new = [], []
    for m in sorted(mdir.glob("iter-*-*-exec.md")):
        try:
            sec = _extract_section(m.read_text(encoding="utf-8", errors="replace"), "## 教训")
        except OSError:
            continue
        if not sec:
            continue
        general_new += _lesson_items(_extract_subsection(sec, "### 通用"))
        proj_new += _lesson_items(_extract_subsection(sec, f"### {project}"))
    if not general_new and not proj_new:
        return
    text = lessons_path.read_text(encoding="utf-8", errors="replace")
    if general_new:
        text = _append_to_section(text, "## 通用铁律", None, general_new)
    if proj_new:
        text = _append_to_section(text, "## 分项目教训", f"### {project}", proj_new)
    lessons_path.write_text(text, encoding="utf-8")


def _lesson_items(section_text: str) -> list[str]:
    """从子节正文挑真条目（'- ' 开头、非模板占位）。"""
    items = []
    for ln in section_text.splitlines():
        s = ln.strip()
        if not s.startswith("- "):
            continue
        body = s[2:].strip()
        if not body or body[0] in "（(":  # 跳过 （本次…）/（无） 这类占位
            continue
        items.append(s)
    return items


def _append_to_section(text: str, h2: str, h3, items: list[str]) -> str:
    """把 items 追加到 h2 节（h3=None）或 h2 内 h3 子节末尾；SHA-256 文本去重。"""
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
    """解析验证席：用户显式指定且在座 → 用之；否则动态选。
    在座飞毛腿(seated ∩ ¬EXEC_EXCLUDE) ≥2 → 选异质飞毛腿(优先 hermes)当 reviewer，其余执行；
    ≤1 个飞毛腿 → 把飞毛腿留给执行，claude 兜底当 reviewer(纯脑只读，仍 maker≠checker)；
    都没有 → 返回任意在座(调用方据空 executors fail-fast)。"""
    if requested and requested in seated:
        return requested
    fast = [a for a in seated if a not in EXEC_EXCLUDE]
    if len(fast) >= 2:
        for cand in ("hermes", "kimi"):   # 异质优先：hermes=deepseek 血统利于复审
            if cand in fast:
                return cand
        return fast[0]
    if "claude" in seated:                 # 飞毛腿 ≤1：留给执行，claude 兜底验证
        return "claude"
    return fast[0] if fast else (seated[0] if seated else "")


def _fallback_plan(executors: list, task: str) -> list:
    """过滤后无可执行子任务时的兜底：整活派首个飞毛腿。executors 必非空（空则调用方已 fail-fast）。
    差异化诊断（filtered_empty vs plan_failed）由调用方据 plan_failed/is_fallback 在 log/BRIEF 体现。"""
    target = next((a for a in FAST_PRIORITY if a in executors), executors[0])
    return [{"agent": target, "subtask": task}]


def build_plan_brief(feedback: str, executors: list[str], reviewer: str) -> str:
    """给总指挥的本轮角色约束，避免把实施派给验证席或生成只读复审子任务。"""
    lines = [
        "【本轮角色约束】",
        f"- 执行池: {', '.join(executors) or '（空）'}。只有执行池座位可接收实施/修改/测试子任务。",
        f"- 验证席: {reviewer or '（无）'}。不要把实施任务派给验证席；conductor 会在执行后统一触发只读复审。",
        "- plan JSON 只输出执行池座位的实施子任务，不要输出只读复审子任务。",
    ]
    if feedback:
        lines += ["", feedback]
    return "\n".join(lines)


def _fallback_reviewers(seated: list[str], primary: str, executors: list[str]) -> list[str]:
    """reviewer 进程 ERR 时的只读备援；不选本轮执行席，避免 maker=checker。"""
    return [
        agent for agent in REVIEW_FALLBACK_PRIORITY
        if agent in seated and agent != primary and agent not in executors
    ]


def _plan_note(plan_failed: bool, is_fallback: bool) -> str:
    """plan 异常的准确措辞：区分「真兜底（kept 空）」与「plan 进程报错但仍采用其计划」。"""
    if is_fallback:
        why = "总指挥 plan 失败/超时" if plan_failed else "过滤后无现成可执行子任务"
        return f"{why}，本轮整活兜底派单个飞毛腿"
    if plan_failed:
        return "总指挥 plan 进程异常退出（rc≠0）但已采用其解析出的计划，可能不全"
    return ""


def build_brief(dropped: list, exec_failures: list, plan_failed: bool, is_fallback: bool = False) -> str:
    """汇总本轮异常给验证席：完整性裁决前缀 + plan 异常 + 被移出子任务 + 失败座位。无异常返回空串。"""
    if not (dropped or exec_failures or plan_failed or is_fallback):
        return ""
    lines = ["【本轮执行情况：请据「任务完整性是否受损」裁决；若任务已由其余座位完成，"
             "勿因下列失败机械判 BLOCK】"]
    note = _plan_note(plan_failed, is_fallback)
    if note:
        lines.append(f"- ⚠ {note}")
    for a, rc in exec_failures:
        tag = "超时" if rc == 124 else f"rc={rc}"
        lines.append(f"- ✗ {a}[exec] 失败（{tag}）")
    for p in dropped:
        lines.append(f"- ⚠ 子任务未执行（派给了非执行座位 {p['agent']}）：{p['subtask'][:50]}")
    return "\n".join(lines)


def _write_round_notes(repo: str, dropped: list, exec_failures: list,
                       plan_failed: bool, is_fallback: bool = False) -> None:
    """本轮异常追加进 KB/state.md（验证席必读），review 前写入，不覆盖座位自写内容。失败不抛。"""
    if not (dropped or exec_failures or plan_failed or is_fallback):
        return
    try:
        sp = session_dir(repo) / "KB" / "state.md"
        sp.parent.mkdir(parents=True, exist_ok=True)
        out = ["", "## ⚠ 本轮异常（conductor 记录）"]
        note = _plan_note(plan_failed, is_fallback)
        if note:
            out.append(f"- {note}")
        for a, rc in exec_failures:
            out.append(f"- ✗ {a}[exec] 失败（{'超时 124' if rc == 124 else f'rc={rc}'}）")
        for p in dropped:
            out.append(f"- ⚠ 子任务被移出未执行（非执行座位 {p['agent']}）：{p['subtask'][:60]}")
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
    reporter.start(repo, task, commander, "read-only-audit", 1)
    if not review_seats:
        reporter.log("[loop-engine] ⚠ 只读审计无可用座位")
        reporter.finish("ERR", 0)
        return 1

    nimp = import_memory(repo)
    if nimp:
        reporter.log(f"[loop-engine] 记忆桥：导入 {nimp} 份仓库外项目记忆到黑板")
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
        reporter.seat(seat, "review", "只读审计", phase="start")
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


# ---------------- 主循环（渲染无关）----------------
def run(repo, task, commander="claude", reviewer="", max_iters=5, test_cmd="",
        reporter=None, seats=None, seat_models=None, audit_only=False,
        required_artifact_paths=None, allowed_write_paths=None) -> int:
    reporter = reporter or TextReporter()
    repo = str(Path(repo).expanduser().resolve())
    seat_models = seat_models or {}

    def sm(agent):
        c = seat_models.get(agent, {})
        return c.get("provider", ""), c.get("model", "")

    # 会话 id：项目内按会话隔离记忆（除非外部已指定 LOOP_SESSION 以续接）
    if not os.environ.get("LOOP_SESSION"):
        os.environ["LOOP_SESSION"] = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + _slug(task)
    reporter.log(f"[conductor] 会话: {os.environ['LOOP_SESSION']}")
    _, o = sh_capture("roundtable-init.sh", repo, task); reporter.log(o)
    # 写在座花名册（探测 ∩ 勾选），并跑护栏校验
    seated = write_roster(repo, seats, seat_models)
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
    # 验证席动态解析（留空=异质飞毛腿优先、claude 兜底）；可执行座位 = 在座 ∩ 非慢座位 ∩ 非验证席。
    reviewer = _resolve_reviewer(seated, reviewer)
    executors = [a for a in seated if a not in EXEC_EXCLUDE and a != reviewer]
    reporter.start(repo, task, commander, reviewer, max_iters)
    # 修复座位漂移：用实际在座覆盖 roundtable.json 的 participants。
    # roundtable-init 写的是硬编码默认 ["claude","codex","hermes"]，会让后续轮的总指挥
    # 误判谁在座（iter-2 曾据此把活派给已下桌、且连接故障的 codex，导致裁决失准）。
    try:
        _sf = session_dir(repo) / "roundtable.json"
        if _sf.exists():
            _d = json.loads(_sf.read_text())
            _d["participants"] = seated
            _sf.write_text(json.dumps(_d, ensure_ascii=False, indent=2))
    except Exception:
        pass
    if seated:
        reporter.log(f"[loop-engine] 在座: {', '.join(seated)}；验证席: {reviewer or '（无）'}；"
                     f"执行池: {', '.join(executors) or '（空）'}")
    if commander not in seated:
        reporter.log(f"[loop-engine] ⚠ 总指挥 '{commander}' 不在座（未勾选/未安装），可能失败")
    # maker≠checker：仅当验证席本身会执行（∉EXEC_EXCLUDE）且 == 总指挥时才不独立；
    # claude 既指挥又验证但不 exec → maker(飞毛腿)独立，不告警。
    if commander == reviewer and reviewer not in EXEC_EXCLUDE:
        reporter.log("[loop-engine] ⚠ 总指挥=验证席且其会执行：验证不独立")
    # 空执行池 fail-fast：无飞毛腿可执行 → 不进迭代空烧，直接交还人工。
    if not executors:
        reporter.log("[loop-engine] ⚠ 无飞毛腿可执行（在座飞毛腿不可用或被占为验证席）；"
                     "圆桌需≥1 飞毛腿，纯 claude 请走主对话带外亲写")
        write_conclusion(repo, task, "CAP", 0, [])
        reporter.finish("CAP", 0)
        return 2
    nimp = import_memory(repo)
    if nimp:
        reporter.log(f"[loop-engine] 记忆桥：导入 {nimp} 份仓库外项目记忆到黑板")
    _, o = sh_capture("kb-refresh.sh", repo, test_cmd); reporter.log(o)

    feedback, verdicts, status, final_it = "", [], None, max_iters
    for it in range(1, max_iters + 1):
        reporter.round(it)

        # 总指挥派活
        cp, cm = sm(commander)
        reporter.seat(commander, "plan", "读花名册分派", phase="start")
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
        dropped = [p for p in raw if p["agent"] not in executors]   # 派给 claude/codex/验证席的
        for p in dropped:
            reporter.log(f"[conductor] 移出非执行座位子任务：{p['agent']} ← {p['subtask'][:30]}")
        is_fallback = not kept
        if is_fallback:
            plan = _fallback_plan(executors, task)
            why = "plan 失败/超时" if plan_failed else "过滤后无可执行子任务"
            reporter.log(f"[conductor] {why}，整活兜底派飞毛腿 {plan[0]['agent']}")
        else:
            plan = kept
        reporter.plan(plan)

        # 分派执行（串行；验证留到统一一步）。单座位失败/超时不阻断后续（run_seat 不抛、返回码区分）。
        # plan 已只含 executors（过滤+fallback 保证），故不会派到验证席/慢座位。
        exec_failures = []
        for p in plan:
            ep, em = sm(p["agent"])
            reporter.seat(p["agent"], "exec", p["subtask"], phase="start")
            erc, eout = timed_run_seat(repo, it, p["agent"], "exec", brief=p["subtask"], provider=ep, model=em)
            reporter.seat(p["agent"], "exec", p["subtask"], erc, phase="done")
            reporter.transcript(p["agent"], "exec", eout)
            if erc != 0:
                exec_failures.append((p["agent"], erc))

        # 本轮异常写黑板（review 前）；并构建注入验证席的 BRIEF（双通道：state.md + brief）
        _write_round_notes(repo, dropped, exec_failures, plan_failed, is_fallback)
        _, o = sh_capture("kb-refresh.sh", repo, test_cmd); reporter.log(o)

        # 验证
        rbrief = build_brief(dropped, exec_failures, plan_failed, is_fallback)
        active_reviewer = reviewer
        verdict = "ERR"
        review_chain = [reviewer] + _fallback_reviewers(seated, reviewer, executors)
        for idx, candidate in enumerate(review_chain):
            rp, rm = sm(candidate)
            reporter.seat(candidate, "review", "独立验证", phase="start")
            vrc, vout = timed_run_seat(repo, it, candidate, "review", brief=rbrief, provider=rp, model=rm)
            verdict = VERDICT_MAP.get(vrc, "ERR")
            reporter.seat(candidate, "review", "", vrc, phase="done")
            reporter.transcript(candidate, "review", vout)
            active_reviewer = candidate
            if verdict != "ERR":
                break
            if idx + 1 < len(review_chain):
                reporter.log(f"[loop-engine] ⚠ 验证席 {candidate} ERR，改派备用验证席 {review_chain[idx + 1]}")
        reviewer = active_reviewer
        reporter.verdict(reviewer, verdict)
        verdicts.append(verdict)

        _, o = sh_capture("checkpoint.sh", repo, f"{commander}指挥第{it}轮 裁决{verdict}"); reporter.log(o)

        if verdict in ("PASS", "ERR"):
            status, final_it = verdict, it
            break
        feedback = "上一轮验证 BLOCK，请读 minutes/ 里验证席的发现并修正。"

    status = status or "CAP"
    write_conclusion(repo, task, status, final_it, verdicts)
    archive_to_memory(repo, task, status, final_it, verdicts)  # 记忆桥（出）：归档到 git 化的 roundtable-memory/
    reporter.finish(status, final_it)
    return {"PASS": 0, "ERR": 1, "CAP": 2}[status]


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="圆桌指挥程序")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--commander", default="claude", choices=sorted(AGENTS), help="项目总指挥（你指派）")
    ap.add_argument("--reviewer", default="", choices=sorted(AGENTS) + [""],
                    help="验证席（留空=自动解析：异质飞毛腿优先，claude 兜底）")
    ap.add_argument("--max-iters", type=int, default=int(os.environ.get("LOOP_MAX_ITERS", "5")))
    ap.add_argument("--test-cmd", default=os.environ.get("LOOP_TEST_CMD", ""))
    ap.add_argument("--seats", default="", help="只让这些座位上桌，逗号分隔（默认全部可用）")
    ap.add_argument(
        "--audit-only",
        action="store_true",
        default=os.environ.get("LOOP_AUDIT_ONLY", "").strip().lower() in {"1", "true", "yes", "on"},
        help="只读审计：只调用 review 座位，不进入 plan/exec",
    )
    ap.add_argument(
        "--required-artifact-paths",
        default=os.environ.get("LOOP_REQUIRED_ARTIFACT_PATHS", ""),
        help="必须存在/变化的产物路径，逗号或冒号分隔",
    )
    ap.add_argument(
        "--allowed-write-paths",
        default=os.environ.get("LOOP_ALLOWED_WRITE_PATHS", ""),
        help="允许新增/修改的路径，逗号或冒号分隔；只读审计默认不允许项目写入",
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
