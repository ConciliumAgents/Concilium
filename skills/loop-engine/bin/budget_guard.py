#!/usr/bin/env python3
"""Evaluate Concilium budget guard decisions before model calls."""
from __future__ import annotations

import datetime

BLOCKING_STATUSES = {"hard_exhausted", "unavailable"}
WARNING_STATUSES = {"unknown", "soft_limited"}


def _parse_time(value):
    if isinstance(value, datetime.datetime):
        parsed = value
    elif value:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.UTC)
    return parsed.astimezone(datetime.UTC)


def is_stale(record, now=None):
    checked_at = _parse_time(record.get("checked_at"))
    if checked_at is None:
        return True

    if now is None:
        now = datetime.datetime.now(datetime.UTC)
    else:
        now = _parse_time(now)
        if now is None:
            now = datetime.datetime.now(datetime.UTC)

    try:
        stale_after = int(record.get("stale_after_seconds") or 0)
    except (TypeError, ValueError):
        stale_after = 0
    if stale_after <= 0:
        return False

    return checked_at + datetime.timedelta(seconds=stale_after) < now


def _required_seats(preview):
    preflight = preview.get("preflight") or {}
    route = preview.get("route") or {}
    required = preflight.get("required_seats") or route.get("required_seats") or []
    return [str(seat) for seat in required]


def _required_records(preview):
    by_seat = {str(record.get("seat", "")): record for record in preview.get("capacity") or []}
    records = []
    unresolved = []
    for seat in _required_seats(preview):
        record = by_seat.get(seat)
        if record is None:
            unresolved.append(seat)
        else:
            records.append(record)
    return records, unresolved


def confirmation_payload(preview):
    route = preview.get("route") or {}
    request = preview.get("request") or {}
    records, unresolved = _required_records(preview)

    seats = []
    for record in records:
        seats.append({
            "seat": str(record.get("seat", "")),
            "provider": str(record.get("provider", "")),
            "model": str(record.get("model", "")),
            "capacity_status": str(record.get("status", "unknown")),
            "capacity_source": str(record.get("source", "")),
            "capacity_reason": str(record.get("reason", "")),
            "checked_at": str(record.get("checked_at", "")),
            "reset_at": str(record.get("reset_at", "")),
        })
    for seat in unresolved:
        seats.append({
            "seat": seat,
            "provider": "",
            "model": "",
            "capacity_status": "missing",
            "capacity_source": "",
            "capacity_reason": "missing required seat record",
            "checked_at": "",
            "reset_at": "",
        })

    return {
        "request_fingerprint": str(preview.get("request_fingerprint", "")),
        "selected_lane": str(route.get("lane", "")),
        "routing_reason": str(route.get("reason", "")),
        "required_seats": _required_seats(preview),
        "seats": seats,
        "expected_max_agent_calls": preview.get(
            "expected_max_agent_calls",
            request.get("expected_max_agent_calls", route.get("expected_max_agent_calls")),
        ),
        "files_may_be_modified": bool(preview.get("files_may_be_modified", request.get("files_may_be_modified", False))),
        "global_config_may_be_touched": False,
    }


def _confirmation_matches(preview, confirmation):
    if not confirmation or not confirmation.get("accepted"):
        return False
    expected = confirmation_payload(preview)
    return str(confirmation.get("request_fingerprint", "")) == expected["request_fingerprint"]


def evaluate_budget_guard(preview, mode, confirmation=None, now=None):
    records, unresolved = _required_records(preview)
    request = preview.get("request") or {}
    intent = str(request.get("intent", "task"))
    warnings = list((preview.get("preflight") or {}).get("warnings") or [])
    blocking_seats = []
    confirmation_seats = []
    stale_hard_seats = []

    for record in records:
        seat = str(record.get("seat", ""))
        status = str(record.get("status", "unknown"))
        reason = str(record.get("reason", "") or status)

        if status == "unavailable":
            blocking_seats.append(seat)
            continue
        if status == "hard_exhausted":
            if is_stale(record, now=now) and intent == "tiny_smoke":
                stale_hard_seats.append(seat)
                confirmation_seats.append(seat)
                warnings.append(f"{seat} stale hard_exhausted: {reason}")
                continue
            blocking_seats.append(seat)
            continue
        if status in WARNING_STATUSES:
            confirmation_seats.append(seat)
            warnings.append(f"{seat} capacity {status}: {reason}")

    result = {
        "status": "allowed",
        "requires_confirmation": False,
        "reason": "",
        "warnings": warnings,
        "blocking_seats": blocking_seats,
        "unresolved_seats": unresolved,
    }

    if unresolved:
        result["status"] = "blocked"
        result["reason"] = "required seat records unresolved"
        return result
    if blocking_seats:
        result["status"] = "blocked"
        result["reason"] = "required seats blocked by capacity"
        return result

    if mode != "live_run" or not confirmation_seats:
        return result

    if confirmation is not None and not _confirmation_matches(preview, confirmation):
        result["status"] = "blocked"
        result["reason"] = "confirmation does not match current preflight"
        return result

    if confirmation is not None:
        return result

    result["status"] = "confirmation_required"
    result["requires_confirmation"] = True
    if stale_hard_seats:
        result["reason"] = "stale hard_exhausted capacity requires confirmation"
    else:
        result["reason"] = "live run requires confirmation for limited capacity"
    result["confirmation_payload"] = confirmation_payload(preview)
    return result
