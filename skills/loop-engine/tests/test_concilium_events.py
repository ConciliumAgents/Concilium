#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
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

    def test_done_is_emitted_once(self):
        sink = concilium_events.ListEventSink()
        concilium_events.emit_done(sink, rc=0)
        concilium_events.emit_done(sink, rc=1)

        done = [event for event in sink.events if event["type"] == "done"]
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["rc"], 0)


if __name__ == "__main__":
    unittest.main()
