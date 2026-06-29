#!/usr/bin/env python3
"""Concilium lane executors."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import capacity_status  # noqa: E402
import conductor  # noqa: E402
import process_runner  # noqa: E402


def _load_bin_module(name: str, filename: str):
    module_path = BIN / filename
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


review_lane_module = _load_bin_module("review_lane", "review-lane.py")


def _slug(text: str, n: int = 24) -> str:
    value = re.sub(r"[^0-9A-Za-z一-鿿]+", "-", text).strip("-")
    return value[:n] or "task"


def _run_shell(cmd: str, cwd: Path, timeout: int) -> tuple[int, str]:
    if not cmd:
        return 0, ""
    result = process_runner.run_process_group(cmd, cwd=cwd, env=None, timeout=timeout, shell=True)
    return int(result["returncode"]), str(result["output"])


def _run_bin(args: list[str], env: dict, timeout: int) -> tuple[int, str]:
    result = process_runner.run_process_group(args, cwd=BIN, env=env, timeout=timeout)
    return int(result["returncode"]), str(result["output"])


def collect_capacity(repo: str | Path, config: dict) -> list[dict]:
    del repo
    result = process_runner.run_process_group(
        [sys.executable, str(BIN / "roster-detect.py"), "--json"],
        cwd=BIN,
        env=None,
        timeout=60,
    )
    if int(result["returncode"]) != 0:
        raise RuntimeError(str(result["output"]).strip() or "roster-detect.py failed")
    detected = json.loads(str(result["output"]) or "[]")
    return capacity_status.collect_capacity_from_roster(detected, config)


def run_fast_lane(
    repo: str | Path,
    task: str,
    test_cmd: str,
    agent: str,
    timeout: int,
    seat_models: dict | None = None,
) -> dict:
    repo_path = Path(repo).expanduser().resolve()
    env = dict(os.environ)
    env["LOOP_SESSION"] = env.get("LOOP_SESSION") or f"fast-{_slug(task)}"
    env["LOOP_SEAT_TIMEOUT"] = str(timeout)
    env["LOOP_ARCHIVE"] = "0"

    rc, out = _run_bin([str(BIN / "roundtable-init.sh"), str(repo_path), task], env, timeout)
    if rc != 0:
        raise RuntimeError(out.strip() or "roundtable-init.sh failed")
    conductor.write_roster(str(repo_path), seats=[agent], seat_models=seat_models or {})
    refresh_rc, refresh_out = _run_bin([str(BIN / "kb-refresh.sh"), str(repo_path), test_cmd], env, timeout)
    if refresh_rc != 0:
        raise RuntimeError(refresh_out.strip() or "kb-refresh.sh failed")

    script = BIN / f"seat-{agent}.sh"
    proc = process_runner.run_process_group(
        [str(script), str(repo_path), "exec", task],
        cwd=BIN,
        env=env,
        timeout=timeout,
    )
    verify_rc, verify_out = _run_shell(test_cmd, repo_path, timeout)
    agent_rc = int(proc["returncode"])
    return {
        "status": "ran",
        "lane": "fast",
        "agent": agent,
        "returncode": agent_rc if agent_rc != 0 else verify_rc,
        "agent_output": str(proc["output"])[-4000:],
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
        seat_models=config.get("seat_models", {}),
    )
    result = dict(result)
    result["status"] = "ran"
    result["lane"] = "review"
    return result


def run_roundtable_lane(
    repo: str | Path,
    task: str,
    test_cmd: str,
    config: dict,
    timeout: int,
    reporter=None,
) -> dict:
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
            reporter=reporter,
            seats=roundtable.get("seats") or None,
            seat_models=config.get("seat_models", {}),
        )
    finally:
        if old_timeout is None:
            os.environ.pop("LOOP_SEAT_TIMEOUT", None)
        else:
            os.environ["LOOP_SEAT_TIMEOUT"] = old_timeout
    return {"status": "ran", "lane": "roundtable", "returncode": rc}
