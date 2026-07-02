#!/usr/bin/env python3
"""Generate a compact human report for one Loop Engine session."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


VERDICT_RE = re.compile(r"^\s*(?:\*\*)?VERDICT:\s*(PASS|BLOCK)(?:\*\*)?\s*$", re.M)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(read(path))
    except json.JSONDecodeError:
        return {}


def summarize_minutes(minutes_dir: Path, timings: list[dict] | None = None) -> list[dict]:
    timing_index = {
        (str(row.get("iter", "")), row.get("seat", ""), row.get("mode", "")): row
        for row in (timings or [])
    }
    rows = []
    for path in sorted(minutes_dir.glob("iter-*-*.md")):
        text = read(path)
        verdict = ",".join(VERDICT_RE.findall(text))
        match = re.match(r"iter-(\d+)-(.+?)-(plan|exec|review)", path.name)
        key = (
            match.group(1) if match else "",
            match.group(2) if match else "",
            match.group(3) if match else "",
        )
        timing = timing_index.get(key, {})
        rows.append({
            "file": path.name,
            "iter": key[0],
            "seat": key[1],
            "mode": key[2],
            "verdict": verdict,
            "duration_seconds": timing.get("duration_seconds", ""),
            "bytes": len(text.encode("utf-8")),
        })
    return rows


def build_report(session: Path) -> str:
    kb = session / "KB"
    conclusion = read(kb / "conclusion.md").strip()
    task = read(kb / "task.md").strip()
    tests = read(kb / "test-results.txt").strip()
    roundtable = load_json(session / "roundtable.json")
    run_summary = load_json(session / "run-summary.json")

    rows = summarize_minutes(session / "minutes", roundtable.get("seat_timings", []))
    lines = [
        f"# Roundtable Session Report: {session.name}",
        "",
        "## Session",
        f"- Participants: {', '.join(roundtable.get('participants', [])) or 'unknown'}",
        f"- Iteration: {roundtable.get('iter', 'unknown')}",
        f"- Final verdict: {run_summary.get('final_verdict', 'unknown') if run_summary else 'unknown'}",
        f"- Budget Guard: {run_summary.get('budget_guard', {}).get('status', 'unknown') if run_summary else 'unknown'}",
        "",
    ]
    if run_summary.get("seats"):
        lines += [
            "## Run Summary Seats",
            "| Seat | Outcome | Backend |",
            "|---|---|---|",
        ]
        for seat in run_summary["seats"]:
            lines.append(f"| {seat.get('seat', '')} | {seat.get('outcome', '')} | {seat.get('backend_type', '')} |")
        lines.append("")
    lines += [
        "## Conclusion",
        conclusion or "No conclusion.md found.",
        "",
        "## Task Snapshot",
        task[:2000] or "No task.md found.",
        "",
        "## Minute Index",
        "| Iter | Seat | Mode | Verdict | Duration(s) | Bytes | File |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['iter']} | {row['seat']} | {row['mode']} | {row['verdict'] or '-'} | "
            f"{row['duration_seconds'] if row['duration_seconds'] != '' else '-'} | {row['bytes']} | `{row['file']}` |"
        )
    lines += [
        "",
        "## Latest Test Output",
        "```text",
        tests[-3000:] if tests else "No test-results.txt found.",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Loop Engine session report.")
    parser.add_argument("session", help=".roundtable/sessions/<id> path")
    parser.add_argument("--out", default="", help="Output markdown path. Defaults to KB/report.md.")
    args = parser.parse_args()

    session = Path(args.session).resolve()
    out = Path(args.out).resolve() if args.out else session / "KB" / "report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_report(session), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
