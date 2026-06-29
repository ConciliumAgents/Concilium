#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "skills" / "loop-engine" / "bin" / "concilium_lanes.py"
spec = importlib.util.spec_from_file_location("concilium_lanes", MODULE)
concilium_lanes = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(concilium_lanes)


class ConciliumLanesTests(unittest.TestCase):
    def test_roundtable_lane_passes_seat_models_to_conductor(self):
        config = {
            "seat_models": {
                "claude": {"provider": "anthropic", "model": "claude-opus"},
                "kimi": {"model": "kimi-k2"},
            },
            "lanes": {
                "roundtable": {
                    "commander": "claude",
                    "reviewer": "hermes",
                    "seats": ["claude", "kimi"],
                    "max_iters": 2,
                }
            },
        }
        with tempfile.TemporaryDirectory() as td, mock.patch.object(concilium_lanes.conductor, "run", return_value=0) as run:
            result = concilium_lanes.run_roundtable_lane(td, "Design the adapter.", "true", config, timeout=12)

        self.assertEqual(result, {"status": "ran", "lane": "roundtable", "returncode": 0})
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["seat_models"], config["seat_models"])


if __name__ == "__main__":
    unittest.main()
