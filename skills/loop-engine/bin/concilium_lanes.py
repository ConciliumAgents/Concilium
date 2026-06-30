#!/usr/bin/env python3
"""Concilium lane executors."""
from __future__ import annotations

import importlib.util
import contextlib
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import capacity_status  # noqa: E402
import concilium_artifacts  # noqa: E402
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


@contextlib.contextmanager
def _scoped_env(updates: dict[str, str]):
    sentinel = object()
    previous = {key: os.environ.get(key, sentinel) for key in updates}
    os.environ.update({key: str(value) for key, value in updates.items()})
    try:
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is sentinel:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(old_value)


def _slug(text: str, n: int = 24) -> str:
    value = re.sub(r"[^0-9A-Za-z一-鿿]+", "-", text).strip("-")
    return value[:n] or "task"


def _fresh_session_id(lane: str, task: str) -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return f"{lane}-{stamp}-{_slug(task)}"


def _run_shell(cmd: str, cwd: Path, timeout: int) -> tuple[int, str]:
    if not cmd:
        return 0, ""
    result = process_runner.run_process_group(cmd, cwd=cwd, env=None, timeout=timeout, shell=True)
    return int(result["returncode"]), str(result["output"])


def _run_bin(args: list[str], env: dict, timeout: int) -> tuple[int, str]:
    result = process_runner.run_process_group(args, cwd=BIN, env=env, timeout=timeout)
    return int(result["returncode"]), str(result["output"])


def _seat_timeout_env(timeout: int, config: dict) -> dict[str, str]:
    env = {"LOOP_SEAT_TIMEOUT": str(timeout)}
    timeouts = config.get("timeouts", {}) if isinstance(config, dict) else {}
    seat_modes = timeouts.get("seat_mode_seconds", {}) if isinstance(timeouts, dict) else {}
    if not isinstance(seat_modes, dict):
        return env
    for seat, modes in seat_modes.items():
        if not isinstance(modes, dict):
            continue
        for mode, seconds in modes.items():
            env[conductor.seat_timeout_env_key(str(seat), str(mode))] = str(seconds)
    return env


def _lane_env(lane: str, task: str, timeout: int, config: dict) -> dict[str, str]:
    env = dict(os.environ)
    env["LOOP_SESSION"] = _fresh_session_id(lane, task)
    env["LOOP_ARCHIVE"] = "0"
    env.update(_seat_timeout_env(timeout, config))
    return env


def _filter_available_seats(requested: list[str], seated: list[str]) -> list[str]:
    available = set(seated)
    return [seat for seat in requested if seat in available]


def _verdict_for_rc(rc: int) -> str:
    return conductor.VERDICT_MAP.get(int(rc), "ERR")


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
    timeout_config: dict | None = None,
) -> dict:
    repo_path = Path(repo).expanduser().resolve()
    env = _lane_env("fast", task, timeout, timeout_config or {})

    scoped = {key: env[key] for key in ("LOOP_SESSION", "LOOP_ARCHIVE")}
    scoped.update(_seat_timeout_env(timeout, timeout_config or {}))
    with _scoped_env(scoped):
        rc, out = _run_bin([str(BIN / "roundtable-init.sh"), str(repo_path), task], env, timeout)
        if rc != 0:
            raise RuntimeError(out.strip() or "roundtable-init.sh failed")
        seated = _filter_available_seats([agent], conductor.write_roster(str(repo_path), seats=[agent], seat_models=seat_models or {}))
        conductor.set_participants(str(repo_path), seated)
        refresh_rc, refresh_out = _run_bin([str(BIN / "kb-refresh.sh"), str(repo_path), test_cmd], env, timeout)
        if refresh_rc != 0:
            raise RuntimeError(refresh_out.strip() or "kb-refresh.sh failed")

        script = BIN / f"seat-{agent}.sh"
        proc = process_runner.run_process_group(
            [str(script), str(repo_path), "exec", task],
            cwd=BIN,
            env=env,
            timeout=conductor.resolve_seat_timeout(agent, "exec", default=timeout, env=env),
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
    with _scoped_env(_seat_timeout_env(timeout, config)):
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


def run_audit_lane(repo: str | Path, task: str, test_cmd: str, config: dict, timeout: int) -> dict:
    repo_path = Path(repo).expanduser().resolve()
    audit = config.get("lanes", {}).get("audit", {})
    seats = list(audit.get("seats") or [audit.get("default_reviewer", "codex")])
    required_artifacts = list(audit.get("required_artifact_paths") or [])
    if "allowed_write_paths" in audit:
        allowed_artifacts = list(audit.get("allowed_write_paths") or [])
    else:
        allowed_artifacts = list(audit.get("allowed_report_paths") or [])
    env = _lane_env("audit", task, timeout, config)
    scoped = {key: env[key] for key in ("LOOP_SESSION", "LOOP_ARCHIVE")}
    scoped.update(_seat_timeout_env(timeout, config))

    with _scoped_env(scoped):
        rc, out = _run_bin([str(BIN / "roundtable-init.sh"), str(repo_path), task], env, timeout)
        if rc != 0:
            raise RuntimeError(out.strip() or "roundtable-init.sh failed")
        seated = _filter_available_seats(seats, conductor.write_roster(str(repo_path), seats=seats, seat_models=config.get("seat_models", {})))
        conductor.set_participants(str(repo_path), seated)
        refresh_rc, refresh_out = _run_bin([str(BIN / "kb-refresh.sh"), str(repo_path), test_cmd], env, timeout)
        if refresh_rc != 0:
            raise RuntimeError(refresh_out.strip() or "kb-refresh.sh failed")

        seat_results = []
        for seat in seated:
            model_config = dict(config.get("seat_models", {}).get(seat, {}))
            provider = str(model_config.get("provider", ""))
            model = str(model_config.get("model", ""))
            brief = (
                "Read-only Concilium Audit Lane review. Inspect the target project, do not modify files, "
                "and include concrete findings plus VERDICT: PASS or VERDICT: BLOCK."
            )
            src, sout = conductor.timed_run_seat(str(repo_path), 1, seat, "review", brief=brief, provider=provider, model=model)
            seat_results.append({
                "seat": seat,
                "mode": "review",
                "backend_type": "external_cli",
                "status": "invoked",
                "rc": int(src),
                "verdict": _verdict_for_rc(src),
                "output_tail": capacity_status.redact(str(sout)[-4000:]),
            })

        verify_rc, verify_out = _run_shell(test_cmd, repo_path, timeout)
        report_path = ""
        if required_artifacts:
            strict_empty_allow_list = "allowed_write_paths" in audit and not allowed_artifacts
            pre_gate = concilium_artifacts.evaluate_artifact_gate(
                repo_path,
                required_artifact_paths=required_artifacts,
                allowed_write_paths=allowed_artifacts,
                baseline_delta_paths=concilium_artifacts.collect_delta(repo_path).get("delta_paths", []),
                allow_unlisted_required=not strict_empty_allow_list,
                allow_unlisted_delta=not strict_empty_allow_list,
            )
            if pre_gate.get("invalid") or pre_gate.get("disallowed"):
                return {
                    "status": "artifact_failed",
                    "lane": "audit",
                    "returncode": 2,
                    "seat_results": seat_results,
                    "report_path": "",
                    "artifact_gate": pre_gate,
                    "verify": {"returncode": verify_rc, "output": verify_out[-4000:]},
                }
            report_path = _write_audit_report(repo_path, task, test_cmd, seat_results, verify_rc, verify_out, required_artifacts)
        failing_rcs = [int(result["rc"]) for result in seat_results if int(result["rc"]) != 0]
        if any(rc not in (0, 2) for rc in failing_rcs):
            returncode = 1
        elif any(rc == 2 for rc in failing_rcs):
            returncode = 2
        else:
            returncode = verify_rc
        status = "ran" if returncode == 0 else "blocked" if returncode == 2 else "error"

    return {
        "status": status,
        "lane": "audit",
        "returncode": returncode,
        "seat_results": seat_results,
        "report_path": report_path,
        "verify": {"returncode": verify_rc, "output": verify_out[-4000:]},
    }


def _write_audit_report(
    repo: Path,
    task: str,
    test_cmd: str,
    seat_results: list[dict],
    verify_rc: int,
    verify_out: str,
    required_artifacts: list[str],
) -> str:
    if not required_artifacts:
        return ""
    report = repo / str(required_artifacts[0]).lstrip("/")
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Concilium Audit Report",
        "",
        f"Task: {task}",
        f"Verification command: {test_cmd or '(none)'}",
        f"Verification return code: {verify_rc}",
        "",
        "## Seat Reviews",
        "",
    ]
    for result in seat_results:
        lines += [
            f"### {result.get('seat', '')}",
            "",
            f"- mode: {result.get('mode', '')}",
            f"- returncode: {result.get('rc', '')}",
            "",
            "```text",
            str(result.get("output_tail", "")),
            "```",
            "",
        ]
    lines += [
        "## Verification Output",
        "",
        "```text",
        capacity_status.redact(str(verify_out)[-4000:]),
        "```",
        "",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")
    return str(report.relative_to(repo))


def run_plan_review_lane(repo: str | Path, task: str, test_cmd: str, config: dict, timeout: int) -> dict:
    del test_cmd
    repo_path = Path(repo).expanduser().resolve()
    plan_review = config.get("lanes", {}).get("plan_review", {})
    seats = list(plan_review.get("seats") or config.get("lanes", {}).get("audit", {}).get("seats") or ["codex"])
    plan_path = str(plan_review.get("plan_path") or "")
    raw_plan_path = Path(plan_path)
    if not plan_path or raw_plan_path.is_absolute() or ".." in raw_plan_path.parts:
        return {
            "status": "blocked",
            "lane": "plan_review",
            "returncode": 2,
            "rounds": 0,
            "seat_results": [],
            "unresolved_blockers": [{"severity": "HIGH", "summary": f"plan_path is missing or outside repo: {plan_path}"}],
        }

    plan_file = (repo_path / raw_plan_path).resolve()
    try:
        plan_file.relative_to(repo_path)
    except ValueError:
        return {
            "status": "blocked",
            "lane": "plan_review",
            "returncode": 2,
            "rounds": 0,
            "seat_results": [],
            "unresolved_blockers": [{"severity": "HIGH", "summary": f"plan_path is outside repo: {plan_path}"}],
        }
    if not plan_file.exists():
        return {
            "status": "blocked",
            "lane": "plan_review",
            "returncode": 2,
            "rounds": 0,
            "seat_results": [],
            "unresolved_blockers": [{"severity": "HIGH", "summary": f"plan_path is not found: {plan_path}"}],
        }

    plan_rel = plan_file.relative_to(repo_path).as_posix()
    env = _lane_env("plan-review", task, timeout, config)
    scoped = {key: env[key] for key in ("LOOP_SESSION", "LOOP_ARCHIVE")}
    scoped.update(_seat_timeout_env(timeout, config))
    seat_results = []
    blockers = []
    with _scoped_env(scoped):
        rc, out = _run_bin([str(BIN / "roundtable-init.sh"), str(repo_path), task], env, timeout)
        if rc != 0:
            raise RuntimeError(out.strip() or "roundtable-init.sh failed")
        seated = _filter_available_seats(seats, conductor.write_roster(str(repo_path), seats=seats, seat_models=config.get("seat_models", {})))
        conductor.set_participants(str(repo_path), seated)
        refresh_rc, refresh_out = _run_bin([str(BIN / "kb-refresh.sh"), str(repo_path), ""], env, timeout)
        if refresh_rc != 0:
            raise RuntimeError(refresh_out.strip() or "kb-refresh.sh failed")

        baseline_delta = concilium_artifacts.collect_delta(repo_path).get("delta_paths", [])
        before_hash = hashlib.sha256(plan_file.read_bytes()).hexdigest()
        before_snapshot = concilium_artifacts.hash_delta_snapshot(repo_path, include_paths=[plan_rel])

        for seat in seated:
            model_config = dict(config.get("seat_models", {}).get(seat, {}))
            provider = str(model_config.get("provider", ""))
            model = str(model_config.get("model", ""))
            brief = (
                f"Review execution plan {plan_path}. Do not modify files. "
                "If blocking, provide severity, plan section or file line, blocker reason, and required change. "
                "End with VERDICT: PASS or VERDICT: BLOCK."
            )
            rc, output = conductor.timed_run_seat(str(repo_path), 1, seat, "review", brief=brief, provider=provider, model=model)
            result = {
                "seat": seat,
                "mode": "review",
                "backend_type": "external_cli",
                "status": "invoked",
                "rc": int(rc),
                "verdict": _verdict_for_rc(rc),
                "output_tail": capacity_status.redact(str(output)[-4000:]),
            }
            seat_results.append(result)
            if int(rc) == 2:
                blockers.append({"seat": seat, "severity": "HIGH", "summary": capacity_status.redact(str(output)[-500:])})

        gate = concilium_artifacts.evaluate_artifact_gate(
            repo_path,
            required_artifact_paths=[],
            allowed_write_paths=[],
            baseline_delta_paths=baseline_delta,
            allow_unlisted_required=False,
            allow_unlisted_delta=False,
        )
        fingerprint_changed = hashlib.sha256(plan_file.read_bytes()).hexdigest() != before_hash
        after_snapshot = concilium_artifacts.hash_delta_snapshot(repo_path, include_paths=[plan_rel])
        non_plan_review_paths = concilium_artifacts.changed_snapshot_paths(before_snapshot, after_snapshot, allowed_paths=[plan_rel])
    if gate["status"] != "passed" or fingerprint_changed or non_plan_review_paths:
        artifact_blockers = []
        if fingerprint_changed:
            artifact_blockers.append({"severity": "HIGH", "summary": "plan_fingerprint_changed"})
        for path in gate.get("disallowed_delta", []):
            artifact_blockers.append({"severity": "HIGH", "summary": f"disallowed_delta: {path}"})
        for path in non_plan_review_paths:
            artifact_blockers.append({"severity": "HIGH", "summary": f"non_plan_review_delta: {path}"})
        return {
            "status": "artifact_failed",
            "lane": "plan_review",
            "returncode": 2,
            "rounds": 1,
            "seat_results": seat_results,
            "artifact_gate": gate,
            "unresolved_blockers": artifact_blockers,
        }

    if any(int(result["rc"]) not in (0, 2) for result in seat_results):
        return {
            "status": "retry_required",
            "lane": "plan_review",
            "returncode": 1,
            "rounds": 1,
            "seat_results": seat_results,
            "unresolved_blockers": [{"severity": "MEDIUM", "summary": "reviewer ERR; retry, fallback, or mark unavailable"}],
        }
    if blockers:
        return {
            "status": "blocked",
            "lane": "plan_review",
            "returncode": 2,
            "rounds": 1,
            "seat_results": seat_results,
            "unresolved_blockers": blockers,
        }
    return {
        "status": "passed",
        "lane": "plan_review",
        "returncode": 0,
        "rounds": 1,
        "seat_results": seat_results,
        "unresolved_blockers": [],
    }


def run_roundtable_lane(
    repo: str | Path,
    task: str,
    test_cmd: str,
    config: dict,
    timeout: int,
    reporter=None,
) -> dict:
    roundtable = config.get("lanes", {}).get("roundtable", {})
    with _scoped_env(_seat_timeout_env(timeout, config)):
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
    return {"status": "ran", "lane": "roundtable", "returncode": rc}
