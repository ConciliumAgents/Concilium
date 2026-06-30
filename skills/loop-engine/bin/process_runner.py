#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def _timeout_output(error: subprocess.TimeoutExpired) -> str:
    if error.output is not None:
        return _text(error.output)
    return _text(error.stdout)


def _kill_process_group(proc: subprocess.Popen, sig: signal.Signals) -> None:
    try:
        pgid = os.getpgid(proc.pid)
    except OSError:
        return
    try:
        os.killpg(pgid, sig)
    except OSError:
        pass


def run_process_group(
    args: list[str] | str,
    cwd: Path,
    env: dict | None,
    timeout: int,
    shell: bool = False,
) -> dict:
    started = time.monotonic()
    proc = subprocess.Popen(
        args,
        cwd=str(cwd),
        env=env,
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
    except subprocess.TimeoutExpired as error:
        output = _timeout_output(error)
        _kill_process_group(proc, signal.SIGTERM)
        try:
            collected, _ = proc.communicate(timeout=2)
            output = collected or output
        except subprocess.TimeoutExpired as term_error:
            output = _timeout_output(term_error) or output
            _kill_process_group(proc, signal.SIGKILL)
            try:
                collected, _ = proc.communicate(timeout=2)
                output = collected or output
            except subprocess.TimeoutExpired as kill_error:
                output = _timeout_output(kill_error) or output
        text = output or ""
        return {
            "returncode": 124,
            "output": text + f"\n(timeout after {timeout}s)",
            "timed_out": True,
            "duration_seconds": round(time.monotonic() - started, 3),
        }
