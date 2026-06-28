#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills" / "loop-engine" / "bin" / "smoke-roundtable-memory.sh"


def write_roundtable_memory(repo: pathlib.Path) -> None:
    root = repo / "roundtable-memory"
    root.mkdir()
    (root / "INDEX.md").write_text("# INDEX\n\n## temp\n- [示例](temp/example.md)\n", encoding="utf-8")
    (root / "LESSONS.md").write_text(
        "# LESSONS\n\n## 通用铁律\n- 临时通用教训\n\n## 分项目教训\n### temp\n",
        encoding="utf-8",
    )


class MemorySmokeTests(unittest.TestCase):
    def test_memory_smoke_passes_when_no_legacy_sources_exist(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            write_roundtable_memory(repo)

            result = subprocess.run(
                ["bash", str(SCRIPT), str(repo)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("旧源不存在", result.stdout)


if __name__ == "__main__":
    unittest.main()
