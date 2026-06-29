#!/usr/bin/env python3
"""Summarize Loop Engine Phase 2 benchmark records."""
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


def group_by_task(records: list[dict]) -> dict[str, dict[str, dict]]:
    grouped: dict[str, dict[str, dict]] = defaultdict(dict)
    for record in records:
        grouped[record["task_id"]][record["lane"]] = record
    return dict(grouped)


def build_summary(records: list[dict]) -> str:
    grouped = group_by_task(records)
    counts = defaultdict(int)
    lines = [
        "# Loop Engine Phase 2 Benchmark Summary",
        "",
        "| Task | Kimi | Roundtable | Outcome | Reason |",
        "|---|---|---|---|---|",
    ]
    for task_id in sorted(grouped):
        kimi = grouped[task_id].get("baseline-kimi")
        roundtable = grouped[task_id].get("roundtable")
        outcome, reason = classify_pair(kimi, roundtable)
        counts[outcome] += 1
        lines.append(
            f"| {task_id} | {kimi.get('status', '-') if kimi else '-'} | "
            f"{roundtable.get('status', '-') if roundtable else '-'} | {outcome} | {reason} |"
        )
    lines += [
        "",
        "## Counts",
        "",
    ]
    for key in ("roundtable_better", "kimi_better", "tie", "inconclusive"):
        lines.append(f"- {key}: {counts[key]}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize Loop Engine Phase 2 benchmark records.")
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
