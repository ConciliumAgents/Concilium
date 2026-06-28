#!/usr/bin/env python3
"""Offline-first eval runner for Loop Engine Phase 1."""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / ".git").exists() and (path / "skills" / "loop-engine").is_dir():
            return path
    raise RuntimeError(f"cannot find repo root from {start}")


ROOT = find_repo_root(Path(__file__).resolve())
DEFAULT_TASKS = ROOT / "evals" / "loop-engine" / "tasks.json"
OUT_DIR = ROOT / "evals" / "loop-engine" / "runs"


def load_tasks(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("tasks file must contain a list")
    for item in data:
        if not isinstance(item, dict):
            raise ValueError(f"task must be an object: {item}")
        for key in ("id", "task", "expected_status"):
            if key not in item:
                raise ValueError(f"task missing {key}: {item}")
    return data


def run_cmd(cmd: str, timeout: int) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout


def eval_task(task: dict, timeout: int) -> dict:
    cmd = task.get("test_cmd", "")
    if not cmd:
        return {
            "id": task["id"],
            "status": "ERR",
            "passed": False,
            "output": "missing test_cmd",
        }
    rc, output = run_cmd(cmd, timeout)
    status = "PASS" if rc == 0 else "ERR"
    return {
        "id": task["id"],
        "category": task.get("category", ""),
        "status": status,
        "expected_status": task["expected_status"],
        "passed": status == task["expected_status"],
        "returncode": rc,
        "command": cmd,
        "output": output[-4000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Loop Engine eval tasks.")
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS))
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    tasks = load_tasks(Path(args.tasks))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = OUT_DIR / f"{stamp}.jsonl"

    failed = 0
    with out_path.open("w", encoding="utf-8") as out:
        for task in tasks:
            result = eval_task(task, args.timeout)
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            mark = "PASS" if result["passed"] else "FAIL"
            print(f"{mark} {result['id']} status={result['status']} expected={result['expected_status']}")
            if not result["passed"]:
                failed += 1

    print(f"wrote {out_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
