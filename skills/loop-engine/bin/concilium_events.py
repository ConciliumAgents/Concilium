#!/usr/bin/env python3
from __future__ import annotations

import queue
import sys
from pathlib import Path
from typing import Any

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import capacity_status  # noqa: E402


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return capacity_status.redact(value)
    return value


class ListEventSink:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.done_emitted = False

    def emit(self, event_type: str, **fields) -> None:
        if event_type == "done" and self.done_emitted:
            return
        if event_type == "done":
            self.done_emitted = True
        event = dict(fields)
        event["type"] = event_type
        self.events.append(_redact(event))


class QueueEventSink:
    def __init__(self, q: "queue.Queue") -> None:
        self.q = q
        self.done_emitted = False

    def emit(self, event_type: str, **fields) -> None:
        if event_type == "done" and self.done_emitted:
            return
        if event_type == "done":
            self.done_emitted = True
        event = dict(fields)
        event["type"] = event_type
        self.q.put(_redact(event))


def emit_done(sink, rc: int) -> None:
    sink.emit("done", rc=rc)
