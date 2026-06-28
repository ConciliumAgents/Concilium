#!/usr/bin/env python3
"""Offline validator for Loop Engine seat minute files."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


AGENTS = {"claude", "codex", "hermes", "kimi"}
VERDICT_RE = re.compile(r"^\s*(?:\*\*)?VERDICT:\s*(PASS|BLOCK)(?:\*\*)?\s*$", re.M)
BLOCKING_SEVERITY_RE = re.compile(r"\[(CRITICAL|HIGH)\]", re.I)


def extract_h2_section(text: str, header: str) -> str:
    out = []
    in_section = False
    for line in text.splitlines():
        if line.strip() == header:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            out.append(line)
    return "\n".join(out)


def extract_plan(text: str) -> list[dict]:
    match = re.search(r"```json\s*(.+?)```", text, re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent", "")).strip().lower()
        subtask = str(item.get("subtask", "")).strip()
        if agent in AGENTS and subtask:
            out.append({"agent": agent, "subtask": subtask})
    return out


def validate_plan(text: str) -> list[str]:
    errors = []
    if not extract_plan(text):
        errors.append("plan output must contain a fenced json list with valid agent/subtask entries")
    return errors


def validate_exec(text: str) -> list[str]:
    errors = []
    lessons = extract_h2_section(text, "## 教训")
    if not lessons:
        errors.append("exec output must include ## 教训")
    if "### 通用" not in lessons:
        errors.append("exec output must include ### 通用")
    subsections = [m.group(1).strip() for m in re.finditer(r"^###\s+(.+?)\s*$", lessons, re.M)]
    if not any(section != "通用" for section in subsections):
        errors.append("exec output must include a project lesson subsection")
    return errors


def validate_review(text: str) -> list[str]:
    errors = []
    verdicts = VERDICT_RE.findall(text)
    if len(verdicts) != 1:
        errors.append("review output must contain exactly one VERDICT line")
    elif verdicts[0] == "PASS" and BLOCKING_SEVERITY_RE.search(text):
        errors.append("review output with HIGH or CRITICAL findings must use VERDICT: BLOCK")
    return errors


def infer_mode(path: Path) -> str:
    name = path.name
    if "-plan" in name:
        return "plan"
    if "-exec" in name:
        return "exec"
    if "-review" in name:
        return "review"
    return ""


def validate_file(path: Path, mode: str = "") -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    selected = mode or infer_mode(path)
    if selected == "plan":
        return validate_plan(text)
    if selected == "exec":
        return validate_exec(text)
    if selected == "review":
        return validate_review(text)
    return [f"cannot infer mode for {path.name}; pass --mode plan|exec|review"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Loop Engine seat minute files.")
    parser.add_argument("paths", nargs="+", help="Minute files to validate.")
    parser.add_argument("--mode", choices=["plan", "exec", "review"], default="")
    args = parser.parse_args()

    failed = 0
    for raw in args.paths:
        path = Path(raw)
        errors = validate_file(path, args.mode)
        if errors:
            failed += 1
            print(f"FAIL {path}", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
        else:
            print(f"PASS {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
