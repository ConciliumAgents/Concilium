#!/usr/bin/env python3
"""Evaluate Concilium lane preflight facts."""
from __future__ import annotations

import json

BLOCKING_STATUSES = {"hard_exhausted", "unavailable"}
WARNING_STATUSES = {"unknown", "soft_limited"}


def evaluate_preflight(required_seats: list[str], capacity: list[dict], allow_auto_escalation: bool) -> dict:
    del allow_auto_escalation
    by_seat = {str(record.get("seat", "")): record for record in capacity}
    blocking_seats: list[str] = []
    warnings: list[str] = []

    for seat in required_seats:
        record = by_seat.get(seat)
        if record is None:
            blocking_seats.append(seat)
            continue

        status = str(record.get("status", "unknown"))
        reason = str(record.get("reason", "") or status)
        if record.get("blocking") or status in BLOCKING_STATUSES:
            blocking_seats.append(seat)
            continue
        if status in WARNING_STATUSES:
            warnings.append(f"{seat} capacity {status}: {reason}")

    if blocking_seats:
        status = "blocked"
    elif warnings:
        status = "warn"
    else:
        status = "ok"

    return {
        "status": status,
        "blocking_seats": blocking_seats,
        "warnings": warnings,
        "required_seats": list(required_seats),
    }


def render_preflight(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
