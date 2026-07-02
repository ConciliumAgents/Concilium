#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

SENSITIVE_PATTERNS = {
    ".codex/config.toml": re.compile(r"\.codex/config\.toml", re.I),
    ".env": re.compile(r"(^|[/\\])\.env(\.|$|[/\\])", re.I),
    "aws_env": re.compile(r"\bAWS_(ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN)\b"),
    "ssh_private_key": re.compile(r"-----BEGIN (OPENSSH|RSA|EC|DSA) PRIVATE KEY-----"),
    "api_key": re.compile(r"\b(api[_-]?key|token|secret|credential)\b\s*[:=]", re.I),
    "sk_token": re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
}


def _session_root(repo: str | Path) -> Path:
    return Path(repo).expanduser().resolve() / ".roundtable" / "sessions"


def _read_sample(session: Path) -> str:
    chunks = []
    for path in sorted(session.rglob("*")):
        if path.is_file() and path.suffix in {".md", ".txt", ".json", ".patch"}:
            try:
                chunks.append(path.read_text(encoding="utf-8", errors="replace")[:2000])
            except OSError:
                continue
    return "\n".join(chunks)[:20000]


def _indicators(text: str) -> list[str]:
    return [name for name, pattern in SENSITIVE_PATTERNS.items() if pattern.search(text)]


def scan_repo(repo: str | Path) -> dict:
    root = _session_root(repo)
    sessions = []
    if not root.is_dir():
        return {"repo": str(Path(repo).expanduser().resolve()), "sessions": []}
    for session in sorted(path for path in root.iterdir() if path.is_dir()):
        indicators = _indicators(_read_sample(session))
        sessions.append(
            {
                "session": session.name,
                "path": str(session),
                "sensitivity": "sensitive_possible" if indicators else "normal",
                "indicators": indicators,
            }
        )
    return {"repo": str(Path(repo).expanduser().resolve()), "sessions": sessions}


def prune_repo(repo: str | Path, *, yes: bool, sensitive_only: bool = False) -> list[str]:
    report = scan_repo(repo)
    removed = []
    for item in report["sessions"]:
        if sensitive_only and item["sensitivity"] != "sensitive_possible":
            continue
        path = Path(item["path"])
        if yes:
            shutil.rmtree(path)
            removed.append(str(path))
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan or prune Concilium .roundtable sessions.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--repo", default=".")
    prune = sub.add_parser("prune")
    prune.add_argument("--repo", default=".")
    prune.add_argument("--sensitive-only", action="store_true")
    prune.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "scan":
        print(json.dumps(scan_repo(args.repo), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    removed = prune_repo(args.repo, yes=bool(args.yes), sensitive_only=bool(args.sensitive_only))
    print(json.dumps({"removed": removed, "requires_yes": not bool(args.yes)}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
