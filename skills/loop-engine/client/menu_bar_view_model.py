#!/usr/bin/env python3
from __future__ import annotations


BLOCKING_GUARD_STATUSES = {"blocked", "confirmation_required"}


def _config(effective_config: dict) -> dict:
    if isinstance(effective_config.get("config"), dict):
        return effective_config["config"]
    return effective_config


def _latest_seat_event(events: list[dict]) -> dict:
    for event in reversed(events):
        if event.get("agent") or event.get("seat"):
            return event
    return events[-1] if events else {}


def build_popover_model(status: dict, effective_config: dict, preflight: dict, events: list[dict]) -> dict:
    config = _config(effective_config)
    lanes = config.get("lanes", {})
    routing = config.get("routing", {})
    route = preflight.get("route", {})
    preflight_status = preflight.get("preflight", {})
    guard = preflight.get("guard", {})
    capacity = list(preflight.get("capacity") or [])
    latest_event = _latest_seat_event(list(events or []))
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
            "request_fingerprint": preflight.get("request_fingerprint", ""),
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
                "provider": item.get("provider", ""),
                "model": item.get("model", ""),
                "status": item.get("status", "unknown"),
                "checked_at": item.get("checked_at", ""),
                "reset_at": item.get("reset_at", ""),
            }
            for item in capacity
        ],
        "config_summary": {
            "risk_posture": routing.get("risk_posture", ""),
            "auto_escalation": bool(routing.get("allow_auto_escalation", False)),
            "auto_downgrade": bool(routing.get("allow_auto_downgrade", False)),
            "project_override_active": bool(status.get("project_override_active", False)),
            "fast_agent": lanes.get("fast", {}).get("default_single_agent", ""),
            "review_executor": lanes.get("review", {}).get("default_review_executor", ""),
            "review_reviewer": lanes.get("review", {}).get("default_review_reviewer", ""),
            "roundtable_commander": lanes.get("roundtable", {}).get("commander", ""),
            "roundtable_reviewer": lanes.get("roundtable", {}).get("reviewer", ""),
            "roundtable_seats": list(lanes.get("roundtable", {}).get("seats") or []),
        },
        "execution_snapshot": {
            "lane": route.get("lane", ""),
            "active_seat": latest_event.get("agent") or latest_event.get("seat", ""),
            "latest_event": latest_event.get("type", ""),
            "phase": latest_event.get("phase", ""),
            "elapsed_seconds": latest_event.get("elapsed_seconds", 0),
        },
        "debug_action": {"label": "Open Debug Console", "target": "webui"},
    }
