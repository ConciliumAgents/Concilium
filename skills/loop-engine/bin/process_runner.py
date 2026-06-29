#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path


def run_process_group(
    args: list[str] | str,
    cwd: Path,
    env: dict,
    timeout: int,
    shell: bool = False,
) -> dict:
    started = time.monotonic()
    proc = subprocess.Popen(
        args,
        cwd=str(cwd),
        env=env or None,
        shell=shell,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        output, _ = proc.communicate(timeout=timeout)
        return {
            "returncode": proc.returncode,
            "output": output or "",
            "timed_out": False,
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            output, _ = proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            output, _ = proc.communicate()
        text = output or ""
        return {
            "returncode": 124,
            "output": text + f"\n(timeout after {timeout}s)",
            "timed_out": True,
            "duration_seconds": round(time.monotonic() - started, 3),
        }
