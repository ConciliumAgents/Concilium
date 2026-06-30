#!/usr/bin/env python3
"""Pure Concilium lane routing rules."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CONFIG_TERMS = {"config", "configuration", "routing", "router", "evaluation", "benchmark", "preflight"}
ROUNDTABLE_TERMS = {
    "architecture",
    "architectural",
    "auth",
    "security",
    "migration",
    "migrate",
    "high-impact",
    "business decision",
}
AUDIT_TERMS = {"audit", "review", "审查", "审计"}
READ_ONLY_TERMS = {"read-only", "readonly", "只读", "不要修改", "不得修改", "only write", "只允许新增"}
PLAN_REVIEW_TERMS = {"execution plan", "implementation plan", "执行方案", "实施方案", "计划审查", "审核方案"}
DOC_ONLY_RE = re.compile(r"\b(?:docs?|markdown|readme|typo)\b", re.I)


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def infer_task_signals(task: str, repo: str | Path | None = None) -> dict:
    del repo
    text = task.lower()
    file_count = 4 if any(term in text for term in ("multiple modules", "cross-file", "across")) else 1
    security_sensitive = any(term in text for term in ("auth", "security", "token", "credential", "permission"))
    ambiguous = any(term in text for term in ("design", "redesign", "unclear", "ambiguous", "decide"))
    risk = "high" if security_sensitive or ambiguous else "medium" if any(term in text for term in CONFIG_TERMS) else "low"
    return {
        "file_count": file_count,
        "risk": risk,
        "security_sensitive": security_sensitive,
        "ambiguous": ambiguous,
    }


def required_seats_for_lane(lane: str, config: dict) -> list[str]:
    lanes = config.get("lanes", {})
    if lane == "fast":
        return [lanes.get("fast", {}).get("default_single_agent", "kimi")]
    if lane == "review":
        review = lanes.get("review", {})
        return _unique([
            review.get("default_review_executor", "kimi"),
            review.get("default_review_reviewer", "hermes"),
        ])
    if lane == "audit":
        audit = lanes.get("audit", {})
        seats = list(audit.get("seats") or [])
        if not seats:
            seats = [audit.get("default_reviewer", "codex")]
        return _unique(seats)
    if lane == "plan_review":
        plan_review = lanes.get("plan_review", {})
        return _unique(list(plan_review.get("seats") or lanes.get("audit", {}).get("seats") or ["codex"]))
    if lane == "roundtable":
        roundtable = lanes.get("roundtable", {})
        seats = [roundtable.get("commander", "claude")]
        seats.extend(roundtable.get("seats", []))
        seats.append(roundtable.get("reviewer", ""))
        return _unique(seats)
    raise ValueError(f"unknown lane: {lane}")


def _route(lane: str, reason: str, config: dict) -> dict:
    return {
        "lane": lane,
        "required_seats": required_seats_for_lane(lane, config),
        "status": "selected",
        "reason": reason,
    }


def route_task(task: str, signals: dict, config: dict) -> dict:
    merged = infer_task_signals(task)
    merged.update({k: v for k, v in (signals or {}).items() if v is not None})
    text = task.lower()
    risk = str(merged.get("risk", "medium"))
    file_count = int(merged.get("file_count", 1) or 1)
    ambiguous = bool(merged.get("ambiguous", False))
    security_sensitive = bool(merged.get("security_sensitive", False))
    read_only = bool(merged.get("read_only", False))
    risk_posture = config.get("routing", {}).get("risk_posture", "balanced")

    plan_review = bool(merged.get("plan_review", False)) or any(term in text for term in PLAN_REVIEW_TERMS)
    if plan_review:
        return _route("plan_review", "execution-plan review uses bounded reviewer loop before implementation", config)

    if (
        read_only
        or any(term in text for term in READ_ONLY_TERMS)
    ) and any(term in text for term in AUDIT_TERMS):
        return _route("audit", "read-only audit uses reviewer-only lane with artifact gate", config)

    if ambiguous or security_sensitive or risk == "high" or file_count >= 4 or any(term in text for term in ROUNDTABLE_TERMS):
        return _route("roundtable", "ambiguous or high-risk task needs full roundtable", config)

    docs_only = bool(DOC_ONLY_RE.search(text)) and file_count <= 1
    if risk_posture == "review-first" and risk in {"low", "medium"} and not docs_only:
        return _route("review", "review-first posture routes low-medium task to independent review", config)

    if risk_posture == "speed-first" and risk in {"low", "medium"} and not ambiguous and not security_sensitive:
        return _route("fast", "speed-first posture allows bounded low-medium task", config)

    if risk == "low" and file_count <= 1 and not ambiguous and not security_sensitive:
        return _route("fast", "clear low-risk task fits single-agent lane", config)

    if risk == "medium" or any(term in text for term in CONFIG_TERMS):
        return _route("review", "bounded medium-risk task benefits from independent review", config)

    return _route("roundtable", "defaulting unclear task to roundtable", config)


def apply_preflight(route: dict, preflight: dict, config: dict) -> dict:
    del config
    result = dict(route)
    status = preflight.get("status", "ok")
    result["preflight"] = preflight
    if status == "blocked":
        result["status"] = "blocked"
        result["reason"] = f"{route.get('reason', '')}; preflight blocked, no silent downgrade"
        return result
    if status == "warn":
        result["status"] = "warn"
        result["reason"] = f"{route.get('reason', '')}; preflight warning"
        return result
    result["status"] = "selected"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview Concilium lane routing.")
    parser.add_argument("--task", required=True)
    parser.add_argument("--signals", default="{}")
    parser.add_argument("--config-json", required=True)
    args = parser.parse_args(argv)

    signals = json.loads(args.signals)
    config = json.loads(Path(args.config_json).read_text(encoding="utf-8"))
    route = route_task(args.task, signals, config)
    print(json.dumps(route, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
