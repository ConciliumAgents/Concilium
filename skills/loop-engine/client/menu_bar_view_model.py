#!/usr/bin/env python3
from __future__ import annotations


BLOCKING_GUARD_STATUSES = {"blocked", "confirmation_required"}


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _dict_items(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _config(effective_config: dict) -> dict:
    effective_config = _dict(effective_config)
    if isinstance(effective_config.get("config"), dict):
        return effective_config["config"]
    return effective_config


def _latest_seat_event(events: list[dict]) -> dict:
    for event in reversed(_dict_items(events)):
        if event.get("agent") or event.get("seat"):
            return event
    return {}


def _latest_event_of_type(events: list[dict], event_type: str) -> dict:
    for event in reversed(_dict_items(events)):
        if event.get("type") == event_type:
            return event
    return {}


def _seat_event_by_name(events: list[dict]) -> dict[str, dict]:
    result = {}
    for event in _dict_items(events):
        if event.get("type") != "seat":
            continue
        seat = str(event.get("seat") or event.get("agent") or "")
        if seat:
            result[seat] = event
    return result


def build_popover_model(status: dict, effective_config: dict, preflight: dict, events: list[dict]) -> dict:
    status = _dict(status)
    effective_config = _dict(effective_config)
    preflight = _dict(preflight)
    config = _config(effective_config)
    lanes = _dict(config.get("lanes"))
    routing = _dict(config.get("routing"))
    route = _dict(preflight.get("route"))
    preflight_status = _dict(preflight.get("preflight"))
    guard = _dict(preflight.get("run_guard") or preflight.get("guard"))
    capacity = _dict_items(preflight.get("capacity"))
    latest_event = _latest_seat_event(events)
    latest_artifact_gate = _latest_event_of_type(events, "artifact_gate")
    seat_events = _seat_event_by_name(events)
    guard_status = str(guard.get("status") or "")
    blocked = guard_status in BLOCKING_GUARD_STATUSES or preflight_status.get("status") == "blocked"

    return {
        "header": {
            "product": "Concilium",
            "service": status.get("service", "unknown"),
            "repo": status.get("repo") or effective_config.get("repo", ""),
        },
        "active_decision": {
            "lane": route.get("lane", ""),
            "reason": route.get("reason", ""),
            "preflight_status": preflight_status.get("status", ""),
            "guard_status": guard_status,
            "required_seats": list(route.get("required_seats") or []),
            "request_fingerprint": preflight.get("run_request_fingerprint") or preflight.get("request_fingerprint", ""),
        },
        "verdict": {
            "kind": "blocked" if blocked else "ready",
            "text": guard.get("reason") or preflight_status.get("status", ""),
            "blocking_seats": list(preflight_status.get("blocking_seats") or []),
        },
        "primary_action": {
            "label": "Run",
            "enabled": not blocked,
            "requires_confirmation": guard_status == "confirmation_required",
        },
        "seat_capacity": [
            {
                "seat": item.get("seat", ""),
                "backend_type": _dict(seat_events.get(str(item.get("seat", "")))).get("backend_type", ""),
                "provider": item.get("provider", ""),
                "model": item.get("model", ""),
                "status": item.get("status", "unknown"),
                "capacity_source": item.get("source", ""),
                "checked_at": item.get("checked_at", ""),
                "reset_at": item.get("reset_at", ""),
                "event_status": _dict(seat_events.get(str(item.get("seat", "")))).get("status", ""),
                "event_reason": _dict(seat_events.get(str(item.get("seat", "")))).get("reason", ""),
            }
            for item in capacity
        ],
        "config_summary": {
            "risk_posture": routing.get("risk_posture", ""),
            "auto_escalation": bool(routing.get("allow_auto_escalation", False)),
            "auto_downgrade": bool(routing.get("allow_auto_downgrade", False)),
            "project_override_active": bool(status.get("project_override_active", False)),
            "fast_agent": _dict(lanes.get("fast")).get("default_single_agent", ""),
            "review_executor": _dict(lanes.get("review")).get("default_review_executor", ""),
            "review_reviewer": _dict(lanes.get("review")).get("default_review_reviewer", ""),
            "roundtable_commander": _dict(lanes.get("roundtable")).get("commander", ""),
            "roundtable_reviewer": _dict(lanes.get("roundtable")).get("reviewer", ""),
            "roundtable_seats": list(_dict(lanes.get("roundtable")).get("seats") or []),
        },
        "execution_snapshot": {
            "lane": route.get("lane", ""),
            "active_seat": latest_event.get("agent") or latest_event.get("seat", ""),
            "latest_event": latest_event.get("type", ""),
            "phase": latest_event.get("phase", ""),
            "artifact_gate": latest_artifact_gate.get("artifact_gate", {}),
            "elapsed_seconds": latest_event.get("elapsed_seconds", 0),
        },
        "debug_action": {"label": "Open Debug Console", "target": "webui"},
    }
