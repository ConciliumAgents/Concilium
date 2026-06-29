#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

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
