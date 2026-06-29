#!/usr/bin/env python3
"""Summarize Loop Engine benchmark records."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def read_records(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def passed(record: dict | None) -> bool:
    return bool(record and record.get("status") == "PASS" and record.get("verify_passed") is not False)


def classify_pair(kimi: dict | None, roundtable: dict | None) -> tuple[str, str]:
    kimi_passed = passed(kimi)
    roundtable_passed = passed(roundtable)
    if roundtable_passed and not kimi_passed:
        return "roundtable_better", "roundtable passed while kimi did not"
    if kimi_passed and not roundtable_passed:
        return "kimi_better", "kimi passed while roundtable did not"
    if kimi_passed and roundtable_passed:
        return "tie", "both passed quality checks"
    return "inconclusive", "neither lane passed quality checks"


def classify_task(kimi: dict | None, review: dict | None, roundtable: dict | None) -> tuple[str, str]:
    lanes = [
        ("kimi", kimi),
        ("review", review),
        ("roundtable", roundtable),
    ]
    passed_lanes = [name for name, item in lanes if passed(item)]
    if len(passed_lanes) == 3:
        return "tie", "all lanes passed quality checks"
    if len(passed_lanes) == 1:
        lane = passed_lanes[0]
        return f"{lane}_better", f"{lane} passed while other lanes did not"
    if len(passed_lanes) > 1:
        return "partial_tie", ", ".join(passed_lanes) + " passed quality checks"
    return "inconclusive", "no lane passed quality checks"


def group_by_task(records: list[dict]) -> dict[str, dict[str, dict]]:
    grouped: dict[str, dict[str, dict]] = defaultdict(dict)
    for record in records:
        grouped[record["task_id"]][record["lane"]] = record
    return dict(grouped)


def format_lane_cell(record: dict | None) -> str:
    if not record:
        return "-"
    status = record.get("status", "-")
    if record.get("lane") == "router":
        selected = record.get("selected_lane", "")
        preflight = record.get("preflight_status", "")
        if status == "PASS":
            return f"PASS(selected={selected or '-'})"
        if preflight:
            return f"{status}({preflight})"
    return status


def build_summary(records: list[dict]) -> str:
    grouped = group_by_task(records)
    counts = defaultdict(int)
    lines = [
        "# Loop Engine Benchmark Summary",
        "",
        "| Task | Kimi | Review | Roundtable | Router | Outcome | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for task_id in sorted(grouped):
        kimi = grouped[task_id].get("baseline-kimi")
        review = grouped[task_id].get("review")
        roundtable = grouped[task_id].get("roundtable")
        router = grouped[task_id].get("router")
        outcome, reason = classify_task(kimi, review, roundtable)
        counts[outcome] += 1
        lines.append(
            f"| {task_id} | {format_lane_cell(kimi)} | "
            f"{format_lane_cell(review)} | "
            f"{format_lane_cell(roundtable)} | "
            f"{format_lane_cell(router)} | {outcome} | {reason} |"
        )
    lines += [
        "",
        "## Counts",
        "",
    ]
    for key in ("roundtable_better", "review_better", "kimi_better", "tie", "partial_tie", "inconclusive"):
        lines.append(f"- {key}: {counts[key]}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize Loop Engine benchmark records.")
    parser.add_argument("--records", required=True)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    records_path = Path(args.records).resolve()
    out = Path(args.out).resolve() if args.out else records_path.parent / "summary.md"
    out.write_text(build_summary(read_records(records_path)), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
