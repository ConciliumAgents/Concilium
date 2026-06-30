#!/usr/bin/env python3
"""Concilium capacity status records and redaction helpers."""
from __future__ import annotations

import datetime
import re

STATUSES = {"ok", "soft_limited", "hard_exhausted", "unavailable", "unknown"}
BLOCKING_STATUSES = {"hard_exhausted", "unavailable"}
REDACTED = "[REDACTED]"
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
API_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]+\b")
JWT_LIKE_RE = re.compile(r"\b[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]{3,}\b")
QUERY_SECRET_RE = re.compile(
    r"([?&][A-Za-z0-9_.-]*(?:key|token|secret|password|credential)[A-Za-z0-9_.-]*=)[^&\s\"']+",
    re.I,
)
ASSIGNMENT_SECRET_RE = re.compile(
    r"(?<![?&A-Za-z0-9_.-])([A-Z][A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTHORIZATION)[A-Z0-9_]*\s*[:=]\s*)[^\s\"']+",
    re.I,
)
AUTH_HEADER_RE = re.compile(r"\b(Authorization\s*[:=]\s*(?:Bearer|Basic)\s+)[^\s\"']+", re.I)
SORFTIME_URL_RE = re.compile(r"\b(SORFTIME_MCP_URL\s*=\s*)[^\s\"']+", re.I)


def classify_percent(percent_remaining: float | int | None, warn_below: int, block_below: int) -> str:
    if percent_remaining is None:
        return "unknown"
    if percent_remaining < block_below:
        return "hard_exhausted"
    if percent_remaining < warn_below:
        return "soft_limited"
    return "ok"


def redact(text: str) -> str:
    value = API_KEY_RE.sub(REDACTED, text)
    value = EMAIL_RE.sub(REDACTED, value)
    value = JWT_LIKE_RE.sub(REDACTED, value)
    value = QUERY_SECRET_RE.sub(r"\1" + REDACTED, value)
    value = AUTH_HEADER_RE.sub(r"\1" + REDACTED, value)
    value = ASSIGNMENT_SECRET_RE.sub(r"\1" + REDACTED, value)
    value = SORFTIME_URL_RE.sub(r"\1" + REDACTED, value)
    return value


def make_record(
    seat: str,
    provider: str,
    model: str,
    status: str,
    source: str,
    reason: str,
    percent_remaining: float | None = None,
    reset_at: str = "",
    stale_after_seconds: int = 300,
) -> dict:
    if status not in STATUSES:
        raise ValueError(f"unknown capacity status: {status}")
    now = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "seat": seat,
        "provider": provider,
        "model": model,
        "status": status,
        "source": source,
        "percent_remaining": percent_remaining,
        "reset_at": reset_at,
        "checked_at": now,
        "stale_after_seconds": stale_after_seconds,
        "blocking": status in BLOCKING_STATUSES,
        "reason": redact(reason),
    }


def _capacity_thresholds(config: dict) -> tuple[int, int, int]:
    capacity = config.get("capacity", {}) if isinstance(config, dict) else {}
    warn = capacity.get("warn_below_percent", 20)
    block = capacity.get("block_below_percent", 5)
    stale = capacity.get("max_status_age_seconds", 300)
    return int(warn), int(block), int(stale)


def roster_capacity_from_detected_seat(seat: dict, config: dict) -> dict:
    warn, block, stale = _capacity_thresholds(config)
    raw_capacity = seat.get("capacity") if isinstance(seat.get("capacity"), dict) else {}
    percent = raw_capacity.get("percent_remaining")
    provider = seat.get("provider", "")
    model = seat.get("model", "")

    if not seat.get("available", False):
        return make_record(
            seat=str(seat.get("seat", "unknown")),
            provider=str(provider),
            model=str(model),
            status="unavailable",
            source="roster",
            reason=seat.get("reason") or raw_capacity.get("reason") or "seat CLI unavailable",
            percent_remaining=percent,
            stale_after_seconds=stale,
        )

    status = classify_percent(percent, warn_below=warn, block_below=block)
    reason = raw_capacity.get("reason") or "quota source not checked"
    return make_record(
        seat=str(seat.get("seat", "unknown")),
        provider=str(provider),
        model=str(model),
        status=status,
        source=raw_capacity.get("source") or "roster",
        reason=reason,
        percent_remaining=percent,
        reset_at=raw_capacity.get("reset_at", ""),
        stale_after_seconds=stale,
    )


def collect_capacity_from_roster(detected: list[dict], config: dict) -> list[dict]:
    return [roster_capacity_from_detected_seat(seat, config) for seat in detected]


def summarize_blockers(records: list[dict]) -> list[str]:
    blockers = []
    for record in records:
        if record.get("blocking"):
            seat = record.get("seat", "unknown")
            reason = record.get("reason") or record.get("status", "blocked")
            blockers.append(f"{seat}: {reason}")
    return blockers
