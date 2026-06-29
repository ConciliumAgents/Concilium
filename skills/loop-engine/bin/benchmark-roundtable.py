#!/usr/bin/env python3
"""Phase 2 benchmark runner for Loop Engine vs Kimi baseline."""
from __future__ import annotations

import argparse
import datetime
import json
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
    proc = subprocess.run(
        args,
        cwd=cwd,
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
        "changed_files": [],
        "diff_summary": "",
        "contract_valid": True,
        "human_quality_score": None,
        "wall_seconds": round(elapsed, 3),
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


def write_records(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Loop Engine Phase 2 benchmark tasks.")
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS))
    parser.add_argument("--out", default="")
    parser.add_argument("--base", default="loop-engine-mvp-v0.1-internal")
    parser.add_argument("--dry-run", action="store_true", help="Write comparable records without live agent calls.")
    args = parser.parse_args()

    if not args.dry_run:
        raise SystemExit("--dry-run is required until live lanes are implemented")

    tasks = load_tasks(Path(args.tasks))
    stamp = now_stamp()
    run_dir = Path(args.out).resolve() if args.out else output_path_for(stamp)
    harness_commit = git_output(["rev-parse", "HEAD"])
    task_base_commit = git_output(["rev-parse", args.base])
    write_json(run_dir / "batch.json", {
        "stamp": stamp,
        "mode": "dry-run",
        "harness_commit": harness_commit,
        "task_base_commit": task_base_commit,
        "task_count": len(tasks),
    })
    records = run_dry_batch(tasks, run_dir, harness_commit, task_base_commit)
    write_records(run_dir / "records.jsonl", records)
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
