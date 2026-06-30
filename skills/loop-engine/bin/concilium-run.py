#!/usr/bin/env python3
"""Thin CLI for Concilium runtime routing and execution."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import concilium_runtime  # noqa: E402


def _split_seats(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def run_concilium(
    repo: str | Path,
    task: str,
    test_cmd: str = "",
    dry_run: bool = False,
    print_route: bool = False,
    signals: dict | None = None,
    timeout: int = 300,
    mode: str | None = None,
    confirmation: dict | None = None,
    seats: list[str] | None = None,
) -> dict:
    selected_mode = "preview" if dry_run or print_route else mode or "live_run"
    params = {
        "repo": str(repo),
        "task": task,
        "test_cmd": test_cmd,
        "mode": selected_mode,
        "dry_run": dry_run,
        "print_route": print_route,
        "live": selected_mode == "live_run",
        "signals": signals or {},
        "timeout": timeout,
        "seats": list(seats or []),
    }
    return concilium_runtime.run_concilium_adapter(params, confirmation=confirmation)


def _exit_code(result: dict) -> int:
    if result.get("status") in {"blocked", "confirmation_required"}:
        return 3
    if result.get("status") == "preview":
        return 0
    rc = int(result.get("returncode", 0))
    if rc == 0:
        return 0
    if rc == 2:
        return 2
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Concilium lane routing and execution.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--test-cmd", default="")
    parser.add_argument("--mode", choices=sorted(concilium_runtime.MODES), default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-route", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--signals-json", default="")
    parser.add_argument("--confirmation-json", default="")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--seats", default="", help="Comma-separated native seats, for example claude,hermes,kimi.")
    args = parser.parse_args(argv)

    if args.live and args.dry_run:
        print("ValueError: --live and --dry-run cannot be combined", file=sys.stderr)
        return 4

    try:
        signals = json.loads(args.signals_json) if args.signals_json else None
        confirmation = json.loads(args.confirmation_json) if args.confirmation_json else None
        mode = args.mode or ("live_run" if args.live else "preview")
        if args.dry_run or args.print_route:
            mode = "preview"
        params = {
            "repo": args.repo,
            "task": args.task,
            "test_cmd": args.test_cmd,
            "mode": mode,
            "dry_run": args.dry_run,
            "print_route": args.print_route,
            "live": args.live,
            "signals": signals or {},
            "timeout": args.timeout,
            "seats": _split_seats(args.seats),
        }
        result = concilium_runtime.run_concilium_adapter(params, confirmation=confirmation)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 4
    except Exception as e:
        print(json.dumps({"status": "error", "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return _exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
