#!/usr/bin/env python3
"""Run a lightweight executor + independent reviewer lane."""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import conductor  # noqa: E402
import process_runner  # noqa: E402


def _slug(text: str, n: int = 24) -> str:
    value = re.sub(r"[^0-9A-Za-z]+", "-", text).strip("-")
    return value[:n] or "task"


def session_path(repo: str | Path, session: str) -> Path:
    return Path(repo) / ".roundtable" / "sessions" / session


def review_lane_env(timeout: int, session: str) -> dict:
    env = dict(os.environ)
    env["LOOP_SESSION"] = session
    env["LOOP_SEAT_TIMEOUT"] = str(timeout)
    env["LOOP_ARCHIVE"] = "0"
    return env


def filter_available_seats(requested: list[str], seated: list[str]) -> list[str]:
    available = set(seated)
    return [seat for seat in requested if seat in available]


def run_cmd(args: list[str], cwd: Path, env: dict, timeout: int) -> tuple[int, str]:
    result = process_runner.run_process_group(args, cwd=cwd, env=env, timeout=timeout)
    return int(result["returncode"]), str(result["output"])


@contextlib.contextmanager
def scoped_loop_session(session: str):
    old = os.environ.get("LOOP_SESSION")
    os.environ["LOOP_SESSION"] = session
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("LOOP_SESSION", None)
        else:
            os.environ["LOOP_SESSION"] = old


def set_iteration(repo: str | Path, iteration: int) -> None:
    state_path = Path(repo) / ".roundtable" / "sessions" / os.environ.get("LOOP_SESSION", "default") / "roundtable.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    state["iter"] = iteration
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def init_session(
    repo: str | Path,
    task: str,
    test_cmd: str,
    env: dict,
    timeout: int,
    seats: list[str],
    seat_models: dict | None = None,
    memory_config: dict | None = None,
) -> None:
    rc, out = run_cmd([str(BIN / "roundtable-init.sh"), str(repo), task], BIN, env, timeout)
    if rc != 0:
        raise RuntimeError(out.strip() or "roundtable-init.sh failed")
    conductor.import_memory(str(Path(repo).expanduser().resolve()), memory_config=dict(memory_config or {}))
    seated = filter_available_seats(seats, conductor.write_roster(str(repo), seats=seats, seat_models=seat_models or {}))
    conductor.set_participants(repo, seated)
    refresh_kb(repo, test_cmd, env, timeout)


def refresh_kb(repo: str | Path, test_cmd: str, env: dict, timeout: int) -> None:
    run_cmd([str(BIN / "kb-refresh.sh"), str(repo), test_cmd], BIN, env, timeout)


def run_seat(repo: str | Path, seat: str, mode: str, brief: str, env: dict, timeout: int) -> tuple[int, str]:
    script = BIN / f"seat-{seat}.sh"
    seat_timeout = conductor.resolve_seat_timeout(seat, mode, default=timeout, env=env)
    return run_cmd([str(script), str(repo), mode, brief], BIN, env, seat_timeout)


def review_verdict_from_returncode(rc: int) -> str:
    if rc == 0:
        return "PASS"
    if rc == 2:
        return "BLOCK"
    return "ERR"


def repair_brief(task: str, review_output: str) -> str:
    return "\n".join([
        task,
        "",
        "Previous review blocked the change. Repair the findings below, keep the change scoped, then stop.",
        "",
        review_output[-4000:],
    ])


def run_review_lane(
    repo: str | Path,
    task: str,
    test_cmd: str = "",
    executor: str = "kimi",
    reviewer: str = "hermes",
    repair_limit: int = 1,
    timeout: int = 300,
    session: str = "",
    seat_models: dict | None = None,
    memory_config: dict | None = None,
) -> dict:
    if executor == reviewer:
        raise ValueError("Review Lane requires distinct executor and reviewer")
    repo = str(Path(repo).expanduser().resolve())
    session = session or f"review-{_slug(task)}"
    env = review_lane_env(timeout, session)
    calls = 0
    retries = 0
    final_rc = 1
    review_verdict = "ERR"
    seat_results = []

    with scoped_loop_session(session):
        init_session(
            repo,
            task,
            test_cmd,
            env,
            timeout,
            [executor, reviewer],
            seat_models=seat_models,
            memory_config=memory_config,
        )
        for attempt in range(repair_limit + 1):
            set_iteration(repo, attempt + 1)
            brief = task if attempt == 0 else repair_brief(task, review_output)
            exec_rc, exec_out = run_seat(repo, executor, "exec", brief, env, timeout)
            calls += 1
            seat_results.append({
                "seat": executor,
                "mode": "exec",
                "backend_type": "external_cli",
                "status": "invoked",
                "rc": int(exec_rc),
            })
            if exec_rc != 0:
                final_rc = exec_rc
                review_verdict = "ERR"
                break

            refresh_kb(repo, test_cmd, env, timeout)
            review_rc, review_output = run_seat(
                repo,
                reviewer,
                "review",
                "Review the Review Lane executor changes against KB/task.md and KB/diff.patch.",
                env,
                timeout,
            )
            calls += 1
            review_verdict = review_verdict_from_returncode(review_rc)
            seat_results.append({
                "seat": reviewer,
                "mode": "review",
                "backend_type": "external_cli",
                "status": "invoked",
                "rc": int(review_rc),
                "verdict": review_verdict,
            })
            final_rc = review_rc
            if review_verdict != "BLOCK":
                break
            if attempt < repair_limit:
                retries += 1
                continue
            break

    return {
        "returncode": final_rc,
        "review_verdict": review_verdict,
        "retries": retries,
        "agent_calls": calls,
        "seat_results": seat_results,
        "session_path": str(session_path(repo, session)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Concilium Review Lane task.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--test-cmd", default="")
    parser.add_argument("--executor", default="kimi")
    parser.add_argument("--reviewer", default="hermes")
    parser.add_argument("--repair-limit", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--session", default="")
    args = parser.parse_args(argv)

    result = run_review_lane(
        args.repo,
        args.task,
        test_cmd=args.test_cmd,
        executor=args.executor,
        reviewer=args.reviewer,
        repair_limit=args.repair_limit,
        timeout=args.timeout,
        session=args.session,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result["returncode"])


if __name__ == "__main__":
    raise SystemExit(main())
