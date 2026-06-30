#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import queue
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium_events.py"
spec = importlib.util.spec_from_file_location("concilium_events", MODULE)
concilium_events = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(concilium_events)


class ConciliumEventsTests(unittest.TestCase):
    def test_list_sink_redacts_secret_text(self):
        sink = concilium_events.ListEventSink()
        sink.emit("seat", agent="kimi", text="token sk-secret123")

        self.assertEqual(sink.events[0]["type"], "seat")
        self.assertNotIn("sk-secret123", str(sink.events[0]))

    def test_list_sink_redacts_url_key_and_secret_assignments(self):
        sink = concilium_events.ListEventSink()
        sink.emit("seat", text="SORFTIME_MCP_URL=https://example.test/mcp?key=abc123")

        payload = str(sink.events[0])
        self.assertNotIn("abc123", payload)
        self.assertIn("[REDACTED]", payload)

    def test_done_is_emitted_once(self):
        sink = concilium_events.ListEventSink()
        concilium_events.emit_done(sink, rc=0)
        concilium_events.emit_done(sink, rc=1)

        done = [event for event in sink.events if event["type"] == "done"]
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["rc"], 0)

    def test_event_type_cannot_be_overwritten_by_fields(self):
        sink = concilium_events.ListEventSink()
        sink.emit("done", **{"type": "progress", "rc": 0})
        sink.emit("done", rc=1)

        self.assertEqual(sink.events[0]["type"], "done")
        done = [event for event in sink.events if event["type"] == "done"]
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["rc"], 0)

    def test_queue_sink_redacts_and_emits_done_once(self):
        q: queue.Queue = queue.Queue()
        sink = concilium_events.QueueEventSink(q)
        sink.emit("done", text="token sk-secret123", rc=0)
        sink.emit("done", rc=1)

        self.assertEqual(q.qsize(), 1)
        event = q.get_nowait()
        self.assertEqual(event["type"], "done")
        self.assertEqual(event["rc"], 0)
        self.assertNotIn("sk-secret123", str(event))


if __name__ == "__main__":
    unittest.main()
