#!/usr/bin/env python3
"""Run Concilium through Fast, Review, or Roundtable lanes."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import capacity_status  # noqa: E402
import concilium_config  # noqa: E402
import concilium_preflight  # noqa: E402
import conductor  # noqa: E402
import lane_router  # noqa: E402


def _load_bin_module(name: str, filename: str):
    module_path = BIN / filename
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


review_lane_module = _load_bin_module("review_lane", "review-lane.py")


def _run_shell(cmd: str, cwd: Path, timeout: int) -> tuple[int, str]:
    if not cmd:
        return 0, ""
    try:
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
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        return 124, out + f"\n(timeout after {timeout}s)"


def collect_capacity(repo: str | Path, config: dict) -> list[dict]:
    del repo
    proc = subprocess.run(
        [sys.executable, str(BIN / "roster-detect.py"), "--json"],
        cwd=BIN,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout.strip() or "roster-detect.py failed")
    detected = json.loads(proc.stdout or "[]")
    return capacity_status.collect_capacity_from_roster(detected, config)


def run_fast_lane(repo: str | Path, task: str, test_cmd: str, agent: str, timeout: int) -> dict:
    repo_path = Path(repo).expanduser().resolve()
    env = dict(os.environ)
    env["LOOP_SEAT_TIMEOUT"] = str(timeout)
    script = BIN / f"seat-{agent}.sh"
    started = [str(script), str(repo_path), "exec", task]
    proc = subprocess.run(
        started,
        cwd=BIN,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    verify_rc, verify_out = _run_shell(test_cmd, repo_path, timeout)
    return {
        "status": "ran",
        "lane": "fast",
        "agent": agent,
        "returncode": proc.returncode if proc.returncode != 0 else verify_rc,
        "agent_output": (proc.stdout or "")[-4000:],
        "verify": {"returncode": verify_rc, "output": verify_out[-4000:]},
    }


def run_review_lane(repo: str | Path, task: str, test_cmd: str, config: dict, timeout: int) -> dict:
    review = config.get("lanes", {}).get("review", {})
    result = review_lane_module.run_review_lane(
        repo,
        task,
        test_cmd=test_cmd,
        executor=review.get("default_review_executor", "kimi"),
        reviewer=review.get("default_review_reviewer", "hermes"),
        repair_limit=int(review.get("review_repair_limit", 1)),
        timeout=timeout,
    )
    result = dict(result)
    result["status"] = "ran"
    result["lane"] = "review"
    return result


def run_roundtable_lane(repo: str | Path, task: str, test_cmd: str, config: dict, timeout: int) -> dict:
    roundtable = config.get("lanes", {}).get("roundtable", {})
    old_timeout = os.environ.get("LOOP_SEAT_TIMEOUT")
    os.environ["LOOP_SEAT_TIMEOUT"] = str(timeout)
    try:
        rc = conductor.run(
            str(Path(repo).expanduser().resolve()),
            task,
            commander=roundtable.get("commander", "claude"),
            reviewer=roundtable.get("reviewer", ""),
            max_iters=int(roundtable.get("max_iters", 5)),
            test_cmd=test_cmd,
            seats=roundtable.get("seats") or None,
        )
    finally:
        if old_timeout is None:
            os.environ.pop("LOOP_SEAT_TIMEOUT", None)
        else:
            os.environ["LOOP_SEAT_TIMEOUT"] = old_timeout
    return {"status": "ran", "lane": "roundtable", "returncode": rc}


def run_concilium(
    repo: str | Path,
    task: str,
    test_cmd: str = "",
    dry_run: bool = False,
    print_route: bool = False,
    signals: dict | None = None,
    timeout: int = 300,
) -> dict:
    config = concilium_config.load_config(repo)
    capacity = collect_capacity(repo, config)
    task_signals = signals if signals is not None else lane_router.infer_task_signals(task, repo)
    route = lane_router.route_task(task, task_signals, config)
    preflight = concilium_preflight.evaluate_preflight(
        route["required_seats"],
        capacity,
        allow_auto_escalation=bool(config.get("routing", {}).get("allow_auto_escalation", True)),
    )
    decision = lane_router.apply_preflight(route, preflight, config)
    preview = {
        "status": "preview",
        "route": route,
        "decision": decision,
        "preflight": preflight,
        "capacity": capacity,
        "signals": task_signals,
    }
    if dry_run or print_route:
        return preview
    if preflight["status"] == "blocked":
        return {
            "status": "blocked",
            "route": route,
            "decision": decision,
            "preflight": preflight,
            "capacity": capacity,
        }

    lane = route["lane"]
    if lane == "fast":
        result = run_fast_lane(repo, task, test_cmd, route["required_seats"][0], timeout)
    elif lane == "review":
        result = run_review_lane(repo, task, test_cmd, config, timeout)
    elif lane == "roundtable":
        result = run_roundtable_lane(repo, task, test_cmd, config, timeout)
    else:
        raise ValueError(f"unknown lane: {lane}")
    result["route"] = route
    result["preflight"] = preflight
    return result


def _exit_code(result: dict) -> int:
    if result.get("status") == "preview":
        return 0
    if result.get("status") == "blocked":
        return 3
    rc = int(result.get("returncode", 0))
    if rc == 0:
        return 0
    if rc == 2:
        return 2
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Concilium lane routing and execution.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--test-cmd", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-route", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--signals-json", default="")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)

    if args.live and args.dry_run:
        print("ValueError: --live and --dry-run cannot be combined", file=sys.stderr)
        return 4
    signals = json.loads(args.signals_json) if args.signals_json else None
    try:
        result = run_concilium(
            args.repo,
            args.task,
            test_cmd=args.test_cmd,
            dry_run=args.dry_run or not args.live,
            print_route=args.print_route,
            signals=signals,
            timeout=args.timeout,
        )
    except (ValueError, json.JSONDecodeError) as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 4
    except Exception as e:
        print(json.dumps({"status": "error", "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return _exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
