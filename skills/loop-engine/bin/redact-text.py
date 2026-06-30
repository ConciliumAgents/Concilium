#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import capacity_status  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    del argv
    sys.stdout.write(capacity_status.redact(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
