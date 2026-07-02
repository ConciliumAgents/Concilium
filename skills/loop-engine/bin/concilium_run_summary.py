#!/usr/bin/env python3
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "concilium.run_summary.v1"
QUOTA_PATTERNS = (
    re.compile(r"\b429\b", re.I),
    re.compile(r"\brate[_ -]?limit\b", re.I),
    re.compile(r"\busage limit\b", re.I),
    re.compile(r"\bquota\b", re.I),
    re.compile(r"\brefreshed? in\b", re.I),
)


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _capacity_index(capacity: list[dict]) -> dict[str, dict]:
    return {str(item.get("seat", "")): item for item in capacity if isinstance(item, dict) and item.get("seat")}


def is_quota_error(row: dict) -> bool:
    rc = int(row.get("rc", 0) or 0)
    verdict = str(row.get("verdict", "")).upper()
    if rc != 1 and verdict != "ERR":
        return False
    text = " ".join(str(row.get(key, "")) for key in ("output_tail", "error", "reason"))
    return any(pattern.search(text) for pattern in QUOTA_PATTERNS)


def seat_outcome(row: dict) -> str:
    rc = int(row.get("rc", 0) or 0)
    verdict = str(row.get("verdict", "")).upper()
    if rc == 0 and verdict in {"", "PASS"}:
        return "pass"
    if rc == 2 or verdict == "BLOCK":
        return "block"
    if is_quota_error(row):
        return "quota_exhausted"
    if rc == 124:
        return "timeout"
    return "error"


def _roundtable_seat_rows(result: dict) -> list[dict]:
    state = _as_dict(result.get("roundtable_state"))
    if not state:
        return []
    timings = {
        (str(row.get("iter", "")), str(row.get("seat", "")), str(row.get("mode", ""))): row
        for row in _as_list(state.get("seat_timings"))
        if isinstance(row, dict)
    }
    latest = {}
    for row in _as_list(state.get("seat_verdicts")):
        if not isinstance(row, dict):
            continue
        seat = str(row.get("seat", ""))
        mode = str(row.get("mode", ""))
        try:
            iter_no = int(row.get("iter", 0) or 0)
        except (TypeError, ValueError):
            iter_no = 0
        key = (seat, mode)
        if key not in latest or iter_no >= latest[key][0]:
            latest[key] = (iter_no, row)
    rows = []
    for (seat, mode), (_iter_no, row) in latest.items():
        key = (str(row.get("iter", "")), str(row.get("seat", "")), str(row.get("mode", "")))
        timing = timings.get(key, {})
        rows.append(
            {
                "seat": seat,
                "mode": mode,
                "backend_type": "external_cli",
                "status": "invoked",
                "rc": int(row.get("rc", 0) or 0),
                "verdict": str(row.get("verdict", "")),
                "duration_seconds": timing.get("duration_seconds", ""),
            }
        )
    return rows


def _seat_rows(result: dict) -> list[dict]:
    capacity = _capacity_index(_as_list(result.get("capacity")))
    source_rows = _as_list(result.get("seat_results")) or _roundtable_seat_rows(result)
    rows = []
    for item in source_rows:
        if not isinstance(item, dict):
            continue
        seat = str(item.get("seat", ""))
        cap = capacity.get(seat, {})
        rows.append(
            {
                "seat": seat,
                "mode": str(item.get("mode", "")),
                "backend_type": str(item.get("backend_type", "")),
                "status": str(item.get("status", "")),
                "rc": int(item.get("rc", 0) or 0),
                "verdict": str(item.get("verdict", "")),
                "outcome": seat_outcome(item),
                "provider": str(cap.get("provider", "")),
                "model": str(cap.get("model", "")),
                "capacity_status": str(cap.get("status", "unknown")),
                "capacity_source": str(cap.get("source", "")),
                "duration_seconds": item.get("duration_seconds", ""),
            }
        )
    return rows


def final_verdict(result: dict, seats: list[dict]) -> tuple[str, list[str], list[str]]:
    blocking = [row["seat"] for row in seats if row.get("outcome") == "block"]
    retry = [row["seat"] for row in seats if row.get("outcome") in {"quota_exhausted", "timeout", "error"}]
    if _as_dict(result.get("artifact_gate")).get("status") == "failed":
        return "artifact_failed", blocking, retry
    if blocking:
        return "block", blocking, retry
    if retry:
        return "retry_required", blocking, retry
    if int(result.get("returncode", 0) or 0) == 0 and str(result.get("status", "")) not in {"blocked", "error", "artifact_failed"}:
        return "pass", blocking, retry
    return "error", blocking, retry


def build_run_summary(result: dict, launcher: dict | None = None) -> dict:
    launcher = dict(launcher or {})
    seats = _seat_rows(result)
    verdict, blocking, retry = final_verdict(result, seats)
    request = _as_dict(result.get("request"))
    route = _as_dict(result.get("route"))
    preflight = _as_dict(result.get("preflight"))
    guard = _as_dict(result.get("guard"))
    artifact_gate = _as_dict(result.get("artifact_gate"))
    verify = _as_dict(result.get("verify"))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "launcher": launcher,
        "request_fingerprint": str(result.get("request_fingerprint", "")),
        "request": {
            "repo": str(request.get("repo", "")),
            "task": str(request.get("task", "")),
            "mode": str(request.get("mode", result.get("mode", ""))),
        },
        "route": {
            "lane": str(route.get("lane", result.get("lane", ""))),
            "required_seats": list(route.get("required_seats") or []),
            "reason": str(route.get("reason", "")),
        },
        "preflight": preflight,
        "budget_guard": guard,
        "capacity": _as_list(result.get("capacity")),
        "seats": seats,
        "final_verdict": verdict,
        "blocking_seats": blocking,
        "retry_required_seats": retry,
        "returncode": int(result.get("returncode", 0) or 0),
        "status": str(result.get("status", "")),
        "verify": verify,
        "artifact_gate": artifact_gate,
        "session_path": str(result.get("session_path", "")),
    }


def write_run_summary(path: str | Path, result: dict, launcher: dict | None = None) -> dict:
    summary = build_run_summary(result, launcher=launcher)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
