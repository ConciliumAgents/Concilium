#!/usr/bin/env python3
"""Generate a compact human report for one Loop Engine session."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


VERDICT_RE = re.compile(r"^\s*VERDICT:\s*(PASS|BLOCK)\s*$", re.M)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def summarize_minutes(minutes_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(minutes_dir.glob("iter-*-*.md")):
        text = read(path)
        verdict = ",".join(VERDICT_RE.findall(text))
        match = re.match(r"iter-(\d+)-(.+?)-(plan|exec|review)", path.name)
        rows.append({
            "file": path.name,
            "iter": match.group(1) if match else "",
            "seat": match.group(2) if match else "",
            "mode": match.group(3) if match else "",
            "verdict": verdict,
            "bytes": len(text.encode("utf-8")),
        })
    return rows


def build_report(session: Path) -> str:
    kb = session / "KB"
    conclusion = read(kb / "conclusion.md").strip()
    task = read(kb / "task.md").strip()
    tests = read(kb / "test-results.txt").strip()
    roundtable = {}
    if (session / "roundtable.json").exists():
        try:
            roundtable = json.loads(read(session / "roundtable.json"))
        except json.JSONDecodeError:
            roundtable = {}

    rows = summarize_minutes(session / "minutes")
    lines = [
        f"# Roundtable Session Report: {session.name}",
        "",
        "## Session",
        f"- Participants: {', '.join(roundtable.get('participants', [])) or 'unknown'}",
        f"- Iteration: {roundtable.get('iter', 'unknown')}",
        "",
        "## Conclusion",
        conclusion or "No conclusion.md found.",
        "",
        "## Task Snapshot",
        task[:2000] or "No task.md found.",
        "",
        "## Minute Index",
        "| Iter | Seat | Mode | Verdict | Bytes | File |",
        "|---|---|---|---|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['iter']} | {row['seat']} | {row['mode']} | {row['verdict'] or '-'} | {row['bytes']} | `{row['file']}` |"
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
