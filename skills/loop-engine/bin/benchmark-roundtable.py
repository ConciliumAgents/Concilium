#!/usr/bin/env python3
"""Phase 2 benchmark runner for Loop Engine vs Kimi baseline."""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / ".git").exists() and (path / "skills" / "loop-engine").is_dir():
            return path
    raise RuntimeError(f"cannot find repo root from {start}")


ROOT = find_repo_root(Path(__file__).resolve())
DEFAULT_TASKS = ROOT / "evals" / "loop-engine" / "phase2" / "tasks.json"
RUNS_DIR = ROOT / "evals" / "loop-engine" / "phase2" / "runs"
WORKTREES_DIR = ROOT / "evals" / "loop-engine" / "phase2" / "worktrees"
REQUIRED_TASK_KEYS = {
    "id",
    "category",
    "prompt",
    "allowed_paths",
    "verify_cmds",
    "quality_checks",
    "expected_artifacts",
}
LANES = ("baseline-kimi", "roundtable")


def run_cmd(args: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or ""
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        return 124, out + f"\n(timeout after {timeout}s)"


def run_shell(cmd: str, cwd: Path, timeout: int) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout or ""


def git_output(args: list[str], cwd: Path = ROOT) -> str:
    rc, out = run_cmd(["git", *args], cwd)
    if rc != 0:
        raise RuntimeError(out.strip() or f"git {' '.join(args)} failed")
    return out.strip()


def resolve_commit(ref: str, cwd: Path = ROOT) -> str:
    return git_output(["rev-parse", f"{ref}^{{commit}}"], cwd)


def run_verify_cmds(repo: Path, commands: list[str], timeout: int) -> dict:
    results = []
    passed = True
    for cmd in commands:
        rc, out = run_shell(cmd, repo, timeout)
        results.append({"command": cmd, "returncode": rc, "output": out[-4000:]})
        if rc != 0:
            passed = False
    return {"passed": passed, "commands": results}


def git_status_porcelain(repo: Path) -> str:
    rc, out = run_cmd(["git", "status", "--porcelain"], repo)
    if rc != 0:
        raise RuntimeError(out.strip() or "git status failed")
    return out.strip()


def ensure_clean_repo(repo: Path, force: bool) -> None:
    status = git_status_porcelain(repo)
    if status and not force:
        raise RuntimeError(f"dirty repository: {repo}")


def changed_files(repo: Path) -> list[str]:
    rc, tracked = run_cmd(["git", "diff", "--name-only", "HEAD"], repo)
    rc2, untracked = run_cmd(["git", "ls-files", "--others", "--exclude-standard"], repo)
    if rc != 0 or rc2 != 0:
        return []
    return sorted({*(x for x in tracked.splitlines() if x), *(x for x in untracked.splitlines() if x)})


def changed_files_since(repo: Path, base_ref: str) -> list[str]:
    rc, tracked = run_cmd(["git", "diff", "--name-only", base_ref], repo)
    rc2, untracked = run_cmd(["git", "ls-files", "--others", "--exclude-standard"], repo)
    if rc != 0 or rc2 != 0:
        return []
    return sorted({*(x for x in tracked.splitlines() if x), *(x for x in untracked.splitlines() if x)})


def diff_stat(repo: Path) -> str:
    rc, out = run_cmd(["git", "diff", "--stat", "HEAD"], repo)
    return out.strip() if rc == 0 else ""


def diff_stat_since(repo: Path, base_ref: str) -> str:
    rc, out = run_cmd(["git", "diff", "--stat", base_ref], repo)
    return out.strip() if rc == 0 else ""


def diff_patch(repo: Path) -> str:
    rc, out = run_cmd(["git", "diff", "HEAD"], repo)
    return out if rc == 0 else ""


def diff_patch_since(repo: Path, base_ref: str) -> str:
    rc, out = run_cmd(["git", "diff", base_ref], repo)
    return out if rc == 0 else ""


def now_stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def output_path_for(stamp: str) -> Path:
    return RUNS_DIR / stamp


def load_tasks(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("tasks file must contain a list")
    for item in data:
        if not isinstance(item, dict):
            raise ValueError(f"task must be an object: {item}")
        missing = sorted(REQUIRED_TASK_KEYS - set(item))
        if missing:
            raise ValueError(f"task missing {', '.join(missing)}: {item}")
        for key in ("allowed_paths", "verify_cmds", "quality_checks", "expected_artifacts"):
            if not isinstance(item[key], list) or not all(isinstance(v, str) for v in item[key]):
                raise ValueError(f"task {item.get('id', '<unknown>')} field {key} must be a list of strings")
    return data


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def lane_worktree_path(stamp: str, lane: str, task_id: str) -> Path:
    return WORKTREES_DIR / stamp / lane / task_id


def create_lane_worktree(path: Path, base_ref: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"lane worktree already exists: {path}")
    rc, out = run_cmd(["git", "worktree", "add", "--detach", str(path), base_ref], ROOT, timeout=120)
    if rc != 0:
        raise RuntimeError(out.strip() or f"git worktree add failed: {path}")


def lane_prompt(task: dict, lane: str) -> str:
    return "\n".join([
        f"You are running the Loop Engine Phase 2 benchmark lane: {lane}.",
        "Work only inside the current git worktree.",
        "Do not publish, delete external data, change global config, or spend money.",
        "Allowed paths:",
        *[f"- {p}" for p in task["allowed_paths"]],
        "",
        "Task:",
        task["prompt"],
        "",
        "After changes, write a concise report to BENCHMARK-REPORT.md with what changed, verification, and risks.",
    ])


def classify_changed_files(task: dict, files: list[str]) -> dict:
    allowed = task.get("allowed_paths", [])
    allowed_target_changes = []
    violations = []
    for file in files:
        if file == "BENCHMARK-REPORT.md":
            continue
        if any(file == item or file.startswith(item.rstrip("/") + "/") for item in allowed):
            allowed_target_changes.append(file)
        else:
            violations.append(file)
    return {
        "allowed_target_changes": sorted(allowed_target_changes),
        "violations": sorted(violations),
    }


def path_violations(task: dict, files: list[str]) -> list[str]:
    return classify_changed_files(task, files)["violations"]


def roundtable_env(timeout: int, session: str) -> dict:
    env = dict(os.environ)
    env["LOOP_SESSION"] = session
    env["LOOP_SEAT_TIMEOUT"] = str(timeout)
    env["LOOP_ARCHIVE"] = "0"
    return env


def cleanup_kimi_session(output: str) -> None:
    matches = re.findall(r"session_[0-9a-f-]{30,}", output, flags=re.I)
    if not matches:
        return
    sid = matches[-1]
    idx = Path.home() / ".kimi-code" / "session_index.jsonl"
    sroot = (Path.home() / ".kimi-code" / "sessions").resolve()
    if not idx.exists():
        return
    keep: list[str] = []
    removed = False
    for line in idx.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            keep.append(line)
            continue
        if data.get("sessionId") == sid:
            session_dir = Path(data.get("sessionDir", "")).expanduser().resolve()
            if str(session_dir).startswith(str(sroot) + os.sep) and session_dir.is_dir():
                shutil.rmtree(session_dir, ignore_errors=True)
                removed = True
            elif not str(session_dir).startswith(str(sroot) + os.sep):
                keep.append(line)
        else:
            keep.append(line)
    if removed:
        idx.write_text("".join(item + "\n" for item in keep), encoding="utf-8")


def lane_record(
    task: dict,
    lane: str,
    status: str,
    verify: dict,
    repo: Path,
    lane_dir: Path,
    started: float,
    returncode: int,
    harness_commit: str,
    task_base_commit: str,
) -> dict:
    elapsed = time.time() - started
    timeout_count = 1 if returncode == 124 else 0
    changed = changed_files_since(repo, task_base_commit)
    classification = classify_changed_files(task, changed)
    allowed_target_changes = classification["allowed_target_changes"]
    violations = classification["violations"]
    findings = []
    warnings = []
    if not verify["passed"]:
        findings.append("verify failed")
    if not allowed_target_changes:
        findings.append("no changed files inside allowed_paths")
    if violations:
        findings.append("changed files outside allowed_paths: " + ", ".join(violations))
    if returncode != 0:
        warnings.append(f"lane returncode {returncode}")
    quality_passed = verify["passed"] and bool(allowed_target_changes) and not violations
    final_status = "PASS" if quality_passed else "ERR"
    return {
        "task_id": task["id"],
        "category": task.get("category", ""),
        "lane": lane,
        "status": final_status,
        "verify_passed": verify["passed"],
        "review_verdict": "",
        "blocking_findings": findings,
        "warnings": warnings,
        "changed_files": changed,
        "allowed_target_changes": allowed_target_changes,
        "diff_summary": diff_stat_since(repo, task_base_commit),
        "contract_valid": True,
        "human_quality_score": None,
        "wall_seconds": round(elapsed, 3),
        "lane_returncode": returncode,
        "retries": 0,
        "agent_calls": 1,
        "timeout_count": timeout_count,
        "manual_intervention_count": 0,
        "artifact_count": 4,
        "harness_commit": harness_commit,
        "task_base_commit": task_base_commit,
        "report_path": str(lane_dir / "report.md"),
    }


def run_kimi_lane(
    task: dict,
    lane_repo: Path,
    lane_dir: Path,
    timeout: int,
    harness_commit: str,
    task_base_commit: str,
) -> dict:
    started = time.time()
    prompt = lane_prompt(task, "baseline-kimi")
    rc, out = run_cmd(["kimi", "-p", prompt], lane_repo, timeout=timeout)
    cleanup_kimi_session(out)
    verify = run_verify_cmds(lane_repo, task["verify_cmds"], timeout=timeout)
    report_src = lane_repo / "BENCHMARK-REPORT.md"
    report_text = report_src.read_text(encoding="utf-8", errors="replace") if report_src.exists() else out[-4000:]
    write_text(lane_dir / "report.md", report_text)
    write_text(lane_dir / "diff.patch", diff_patch_since(lane_repo, task_base_commit))
    write_text(lane_dir / "test-results.txt", json.dumps(verify, ensure_ascii=False, indent=2))
    status = "PASS" if rc == 0 and verify["passed"] else "ERR"
    record = lane_record(
        task, "baseline-kimi", status, verify, lane_repo, lane_dir, started, rc, harness_commit, task_base_commit
    )
    write_json(lane_dir / "result.json", record)
    return record


def run_roundtable_lane(
    task: dict,
    lane_repo: Path,
    lane_dir: Path,
    timeout: int,
    harness_commit: str,
    task_base_commit: str,
) -> dict:
    started = time.time()
    session = f"phase2-{task['id']}"
    env = roundtable_env(timeout, session)
    test_cmd = " && ".join(task["verify_cmds"])
    cmd = [
        "python3",
        str(ROOT / "skills" / "loop-engine" / "bin" / "conductor.py"),
        "--repo",
        str(lane_repo),
        "--task",
        task["prompt"],
        "--test-cmd",
        test_cmd,
        "--max-iters",
        "2",
        "--seats",
        "claude,hermes,kimi",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout * 4,
        )
        rc, out = proc.returncode, proc.stdout or ""
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        rc = 124
    verify = run_verify_cmds(lane_repo, task["verify_cmds"], timeout=timeout)
    session_path = lane_repo / ".roundtable" / "sessions" / session
    report_path = session_path / "KB" / "report.md"
    run_cmd(
        [
            "python3",
            str(ROOT / "skills" / "loop-engine" / "bin" / "report-session.py"),
            str(session_path),
            "--out",
            str(report_path),
        ],
        ROOT,
        timeout=60,
    )
    report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else out[-4000:]
    write_text(lane_dir / "report.md", report_text)
    write_text(lane_dir / "diff.patch", diff_patch_since(lane_repo, task_base_commit))
    write_text(lane_dir / "test-results.txt", json.dumps(verify, ensure_ascii=False, indent=2))
    status = "PASS" if rc == 0 and verify["passed"] else "ERR"
    record = lane_record(
        task, "roundtable", status, verify, lane_repo, lane_dir, started, rc, harness_commit, task_base_commit
    )
    write_json(lane_dir / "result.json", record)
    return record


def run_dry_lane(task: dict, lane: str, lane_dir: Path, harness_commit: str, task_base_commit: str) -> dict:
    started = time.time()
    lane_dir.mkdir(parents=True, exist_ok=True)
    report = [
        f"# Dry Benchmark Report: {task['id']} / {lane}",
        "",
        "This is a dry-run artifact. No live agent was called.",
        "",
        "## Prompt",
        task["prompt"],
        "",
    ]
    write_text(lane_dir / "report.md", "\n".join(report))
    write_text(lane_dir / "diff.patch", "# dry run: no diff\n")
    write_text(lane_dir / "test-results.txt", "# dry run: verify commands skipped\n")
    elapsed = time.time() - started
    record = {
        "task_id": task["id"],
        "category": task.get("category", ""),
        "lane": lane,
        "status": "PASS",
        "verify_passed": True,
        "review_verdict": "",
        "blocking_findings": [],
        "warnings": [],
        "changed_files": [],
        "allowed_target_changes": [],
        "diff_summary": "",
        "contract_valid": True,
        "human_quality_score": None,
        "wall_seconds": round(elapsed, 3),
        "lane_returncode": 0,
        "retries": 0,
        "agent_calls": 0,
        "timeout_count": 0,
        "manual_intervention_count": 0,
        "artifact_count": 4,
        "harness_commit": harness_commit,
        "task_base_commit": task_base_commit,
        "report_path": str(lane_dir / "report.md"),
    }
    write_json(lane_dir / "result.json", record)
    return record


def run_dry_batch(tasks: list[dict], run_dir: Path, harness_commit: str, task_base_commit: str) -> list[dict]:
    records = []
    for task in tasks:
        for lane in LANES:
            lane_dir = run_dir / f"task-{task['id']}" / lane
            records.append(run_dry_lane(task, lane, lane_dir, harness_commit, task_base_commit))
    return records


def run_live_batch(tasks: list[dict], run_dir: Path, stamp: str, base_ref: str, timeout: int, harness_commit: str) -> list[dict]:
    records = []
    task_base_commit = resolve_commit(base_ref)
    for task in tasks:
        for lane in LANES:
            lane_repo = lane_worktree_path(stamp, lane, task["id"])
            lane_dir = run_dir / f"task-{task['id']}" / lane
            create_lane_worktree(lane_repo, base_ref)
            if lane == "baseline-kimi":
                records.append(run_kimi_lane(task, lane_repo, lane_dir, timeout, harness_commit, task_base_commit))
            else:
                records.append(run_roundtable_lane(task, lane_repo, lane_dir, timeout, harness_commit, task_base_commit))
    return records


def write_records(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_summary(run_dir: Path) -> None:
    module_path = ROOT / "skills" / "loop-engine" / "bin" / "summarize-benchmark.py"
    spec = importlib.util.spec_from_file_location("summarize_benchmark", module_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    records = mod.read_records(run_dir / "records.jsonl")
    write_text(run_dir / "summary.md", mod.build_summary(records))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Loop Engine Phase 2 benchmark tasks.")
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS))
    parser.add_argument("--out", default="")
    parser.add_argument("--base", default="loop-engine-mvp-v0.1-internal")
    parser.add_argument("--dry-run", action="store_true", help="Write comparable records without live agent calls.")
    parser.add_argument("--live", action="store_true", help="Run live Kimi and roundtable lanes in isolated worktrees.")
    parser.add_argument("--task-id", default="", help="Limit execution to one task id.")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--force-dirty-base", action="store_true", help="Allow live runs from a dirty harness repo.")
    args = parser.parse_args()

    if args.dry_run == args.live:
        raise SystemExit("choose exactly one of --dry-run or --live")

    tasks = load_tasks(Path(args.tasks))
    if args.task_id:
        tasks = [task for task in tasks if task["id"] == args.task_id]
        if not tasks:
            raise SystemExit(f"unknown task id: {args.task_id}")
    stamp = now_stamp()
    run_dir = Path(args.out).resolve() if args.out else output_path_for(stamp)
    harness_commit = git_output(["rev-parse", "HEAD"])
    task_base_commit = resolve_commit(args.base)
    mode = "dry-run" if args.dry_run else "live"
    write_json(run_dir / "batch.json", {
        "stamp": stamp,
        "mode": mode,
        "harness_commit": harness_commit,
        "task_base_commit": task_base_commit,
        "task_count": len(tasks),
    })
    if args.dry_run:
        records = run_dry_batch(tasks, run_dir, harness_commit, task_base_commit)
    else:
        ensure_clean_repo(ROOT, force=args.force_dirty_base)
        records = run_live_batch(tasks, run_dir, stamp, args.base, args.timeout, harness_commit)
    write_records(run_dir / "records.jsonl", records)
    write_summary(run_dir)
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
