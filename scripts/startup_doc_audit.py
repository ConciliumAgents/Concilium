#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

SHARED_STARTUP_BEGIN = "<!-- SHARED-STARTUP:BEGIN -->"
SHARED_STARTUP_END = "<!-- SHARED-STARTUP:END -->"
STARTUP_DOCS = ("AGENTS.md", "CLAUDE.md")
MD_PATH_RE = re.compile(
    r"`([^`\n]+\.md)`|(?<![\w/.-])"
    r"((?:docs|decisions|plans|config|scripts|src|tests|\.agents|\.codex)/[^\s`)]+\.md)"
)


@dataclass
class Finding:
    kind: str
    path: str
    detail: str


def marked_region(text: str, begin: str, end: str) -> str | None:
    start = text.find(begin)
    stop = text.find(end)
    if start == -1 or stop == -1 or stop < start:
        return None
    return text[start + len(begin):stop]


def normalize_shared_region(text: str) -> str:
    text = text.replace("`AGENTS.md`", "`STARTUP_DOC.md`")
    text = text.replace("`CLAUDE.md`", "`STARTUP_DOC.md`")
    text = text.replace("AGENTS.md", "STARTUP_DOC.md")
    text = text.replace("CLAUDE.md", "STARTUP_DOC.md")
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def check_startup_parity(project_dir: Path) -> list[Finding]:
    docs: dict[str, str] = {}
    missing: list[str] = []
    for name in STARTUP_DOCS:
        path = project_dir / name
        if not path.is_file():
            missing.append(name)
            continue
        region = marked_region(path.read_text(encoding="utf-8"), SHARED_STARTUP_BEGIN, SHARED_STARTUP_END)
        if region is None:
            missing.append(name)
            continue
        docs[name] = normalize_shared_region(region)
    if missing:
        return [Finding("startup-parity-marker", ", ".join(missing), "missing startup document or SHARED-STARTUP markers")]
    if docs["AGENTS.md"] != docs["CLAUDE.md"]:
        return [Finding("startup-parity", "AGENTS.md / CLAUDE.md", "shared startup blocks differ after self-reference normalization")]
    return []


def startup_markdown_refs(text: str) -> list[str]:
    refs: list[str] = []
    for match in MD_PATH_RE.finditer(text):
        raw = next(group for group in match.groups() if group)
        ref = raw.strip().rstrip(".,;:.")
        if any(ch in ref for ch in "*?[]<>"):
            continue
        refs.append(ref)
    return refs


def check_startup_links(project_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    for name in STARTUP_DOCS:
        path = project_dir / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        region = marked_region(text, SHARED_STARTUP_BEGIN, SHARED_STARTUP_END)
        if region is None:
            continue
        for ref in startup_markdown_refs(region):
            if ref in STARTUP_DOCS:
                continue
            if not (project_dir / ref).exists():
                findings.append(Finding("startup-link", name, f"unresolved markdown reference: {ref}"))
    return findings


def audit_project(project_dir: Path) -> list[Finding]:
    return [
        *check_startup_parity(project_dir),
        *check_startup_links(project_dir),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check AGENTS.md / CLAUDE.md startup contract parity.")
    parser.add_argument("--project-dir", default=".")
    args = parser.parse_args(argv)
    findings = audit_project(Path(args.project_dir).resolve())
    if not findings:
        print("startup-doc-audit: PASS")
        return 0
    print("startup-doc-audit: FAIL")
    for finding in findings:
        print(f"- [{finding.kind}] {finding.path}: {finding.detail}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
