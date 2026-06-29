#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import concilium_config  # noqa: E402
import concilium_events  # noqa: E402
import concilium_lanes  # noqa: E402
import concilium_preflight  # noqa: E402
import lane_router  # noqa: E402

MODES = {"preview", "stub_run", "live_run"}
INTENTS = {"task", "tiny_smoke"}
FINGERPRINT_KEYS = (
    "repo",
    "task",
    "test_cmd",
    "mode",
    "timeout",
    "intent",
    "signals",
    "overlay",
)


def _load_local_module(name: str, filename: str):
    import importlib.util

    module_path = BIN / filename
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


budget_guard = _load_local_module("_concilium_budget_guard_runtime", "budget_guard.py")


def _bool(value: object) -> bool:
    return bool(value) and str(value).strip().lower() not in {"0", "false", "no", "off"}


def _normalize_seat_models(value: object) -> dict:
    seat_models = {}
    for seat, config in dict(value or {}).items():
        if isinstance(config, dict):
            normalized = {}
            for key in ("provider", "model"):
                if key in config:
                    normalized[key] = str(config[key] or "")
            seat_models[str(seat)] = normalized
        else:
            model = str(config or "").strip()
            if model:
                seat_models[str(seat)] = {"model": model}
    return seat_models


def _select_timeout(params: dict) -> int:
    if "timeout" in params and params.get("timeout") is not None:
        timeout_value = params.get("timeout")
    elif "seat_timeout" in params and params.get("seat_timeout") is not None:
        timeout_value = params.get("seat_timeout")
    else:
        timeout_value = 300

    timeout = int(timeout_value)
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    return timeout


def normalize_request(params: dict) -> dict:
    repo = Path(params.get("repo") or ".").expanduser().resolve()
    task = str(params.get("task") or "").strip()
    if not task:
        raise ValueError("task is required")

    mode = str(params.get("mode") or "").strip()
    if not mode:
        mode = "preview" if _bool(params.get("dry_run")) or not _bool(params.get("live")) else "live_run"
    if mode not in MODES:
        raise ValueError(f"unknown execution mode: {mode}")

    intent = str(params.get("intent") or "task").strip()
    if intent not in INTENTS:
        raise ValueError(f"unknown intent: {intent}")

    overlay = {
        "seats": list(params.get("seats") or []),
        "seat_models": _normalize_seat_models(params.get("seat_models")),
        "fast_agent": str(params.get("fast_agent") or "").strip(),
        "review_executor": str(params.get("review_executor") or "").strip(),
        "review_reviewer": str(params.get("review_reviewer") or "").strip(),
        "commander": str(params.get("commander") or "").strip(),
        "reviewer": str(params.get("reviewer") or "").strip(),
        "max_iters": params.get("max_iters"),
    }

    timeout = _select_timeout(params)

    return {
        "repo": str(repo),
        "task": task,
        "test_cmd": str(params.get("test_cmd") or ""),
        "mode": mode,
        "timeout": timeout,
        "intent": intent,
        "signals": dict(params.get("signals") or {}),
        "overlay": overlay,
    }


def apply_request_overlay(config: dict, request: dict) -> dict:
    effective = copy.deepcopy(config)
    lanes = effective.setdefault("lanes", {})
    fast = lanes.setdefault("fast", {})
    review = lanes.setdefault("review", {})
    roundtable = lanes.setdefault("roundtable", {})
    overlay = request.get("overlay") or {}

    if overlay.get("fast_agent"):
        fast["default_single_agent"] = overlay["fast_agent"]
    if overlay.get("review_executor"):
        review["default_review_executor"] = overlay["review_executor"]
    if overlay.get("review_reviewer"):
        review["default_review_reviewer"] = overlay["review_reviewer"]
    if overlay.get("commander"):
        roundtable["commander"] = overlay["commander"]
    if overlay.get("reviewer"):
        roundtable["reviewer"] = overlay["reviewer"]
    if overlay.get("seats"):
        roundtable["seats"] = list(overlay["seats"])
    if overlay.get("max_iters") is not None:
        roundtable["max_iters"] = int(overlay["max_iters"])
    if overlay.get("seat_models"):
        seat_models = effective.setdefault("seat_models", {})
        seat_models.update(dict(overlay["seat_models"]))

    return effective


def request_fingerprint(request: dict) -> str:
    payload = {key: request.get(key) for key in FINGERPRINT_KEYS}
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def attach_guard(preview: dict, confirmation: dict | None = None) -> dict:
    local_budget_guard = _load_local_module("_concilium_budget_guard", "budget_guard.py")
    guard = local_budget_guard.evaluate_budget_guard(preview, mode=preview.get("mode", "preview"), confirmation=confirmation)
    result = dict(preview)
    result["guard"] = guard
    return result


def expected_max_agent_calls(route: dict, config: dict) -> int:
    lane = route.get("lane")
    if lane == "fast":
        return 1
    if lane == "review":
        review = config.get("lanes", {}).get("review", {})
        return 2 + int(review.get("review_repair_limit", 1))
    if lane == "roundtable":
        roundtable = config.get("lanes", {}).get("roundtable", {})
        seats = list(route.get("required_seats") or roundtable.get("seats") or [])
        return len(seats) * int(roundtable.get("max_iters", 5))
    return 0


def _build_preflight_with_effective(params: dict, config: dict | None = None, capacity: list[dict] | None = None):
    request = normalize_request(params)
    base_config = copy.deepcopy(config) if config is not None else concilium_config.load_config(request["repo"])
    effective = apply_request_overlay(base_config, request)
    collected_capacity = capacity if capacity is not None else concilium_lanes.collect_capacity(request["repo"], effective)
    signals = dict(request.get("signals") or lane_router.infer_task_signals(request["task"], request["repo"]))
    request["signals"] = signals
    route = lane_router.route_task(request["task"], signals, effective)
    preflight = concilium_preflight.evaluate_preflight(
        route["required_seats"],
        collected_capacity,
        allow_auto_escalation=bool(effective.get("routing", {}).get("allow_auto_escalation", True)),
    )
    decision = lane_router.apply_preflight(route, preflight, effective)
    preview = {
        "status": "preview",
        "mode": request["mode"],
        "request": request,
        "request_fingerprint": request_fingerprint(request),
        "route": route,
        "decision": decision,
        "preflight": preflight,
        "capacity": collected_capacity,
        "signals": signals,
        "expected_max_agent_calls": expected_max_agent_calls(route, effective),
    }
    return preview, effective


def build_preflight(params: dict, config: dict | None = None, capacity: list[dict] | None = None) -> dict:
    preview, _effective = _build_preflight_with_effective(params, config=config, capacity=capacity)
    return preview


def _events_from_sink(sink) -> list[dict]:
    return list(getattr(sink, "events", []))


def _emit_start_preflight_guard(sink, preview: dict) -> None:
    sink.emit("start", mode=preview["mode"], lane=preview["route"].get("lane"))
    sink.emit("preflight", preflight=preview["preflight"])
    sink.emit("guard", guard=preview["guard"])


def _finish(sink, rc: int) -> None:
    sink.emit("finish", rc=rc)
    concilium_events.emit_done(sink, rc)


def _default_lane_executor(preview: dict, effective: dict) -> dict:
    request = preview["request"]
    route = preview["route"]
    repo = request["repo"]
    task = request["task"]
    test_cmd = request["test_cmd"]
    timeout = int(request["timeout"])
    lane = route["lane"]
    if lane == "fast":
        return concilium_lanes.run_fast_lane(
            repo,
            task,
            test_cmd,
            route["required_seats"][0],
            timeout,
            seat_models=effective.get("seat_models", {}),
        )
    if lane == "review":
        return concilium_lanes.run_review_lane(repo, task, test_cmd, effective, timeout)
    if lane == "roundtable":
        return concilium_lanes.run_roundtable_lane(repo, task, test_cmd, effective, timeout)
    raise ValueError(f"unknown lane: {lane}")


def run_concilium_adapter(
    params: dict,
    confirmation: dict | None = None,
    event_sink=None,
    config: dict | None = None,
    capacity: list[dict] | None = None,
    lane_executor=None,
) -> dict:
    sink = event_sink or concilium_events.ListEventSink()
    preview, effective = _build_preflight_with_effective(params, config=config, capacity=capacity)
    guard = budget_guard.evaluate_budget_guard(preview, mode=preview["request"]["mode"], confirmation=confirmation)
    preview["guard"] = guard

    if preview["request"]["mode"] == "preview":
        result = dict(preview)
        result["events"] = _events_from_sink(sink)
        return result

    _emit_start_preflight_guard(sink, preview)

    if guard.get("status") != "allowed":
        _finish(sink, 3)
        result = dict(preview)
        result["status"] = guard.get("status")
        result["returncode"] = 3
        result["events"] = _events_from_sink(sink)
        return result

    if preview["request"]["mode"] == "stub_run":
        for seat in preview["route"].get("required_seats") or []:
            sink.emit("seat", seat=seat, lane=preview["route"].get("lane"), status="stubbed")
        _finish(sink, 0)
        result = dict(preview)
        result["status"] = "stubbed"
        result["returncode"] = 0
        result["events"] = _events_from_sink(sink)
        return result

    executor = lane_executor or _default_lane_executor
    execution_result = dict(executor(preview, effective) or {})
    if "verify" in execution_result:
        sink.emit("verify", verify=execution_result["verify"])
    if "review_verdict" in execution_result:
        sink.emit("verdict", verdict=execution_result["review_verdict"])
    elif "verdict" in execution_result:
        sink.emit("verdict", verdict=execution_result["verdict"])
    rc = int(execution_result.get("returncode", 0))
    _finish(sink, rc)

    result = dict(preview)
    result.update(execution_result)
    result["guard"] = guard
    result["events"] = _events_from_sink(sink)
    return result
