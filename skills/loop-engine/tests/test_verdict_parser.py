#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
LIB = ROOT / "skills" / "loop-engine" / "bin" / "_lib.sh"


class VerdictParserTests(unittest.TestCase):
    def run_parser(self, text: str) -> subprocess.CompletedProcess[str]:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
            f.write(text)
            path = pathlib.Path(f.name)
        try:
            return subprocess.run(
                ["bash", "-c", 'source "$1"; loop_verdict_exit "$2"', "_", str(LIB), str(path)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        finally:
            path.unlink(missing_ok=True)

    def test_accepts_plain_verdict_line(self):
        result = self.run_parser("Looks fine\nVERDICT: PASS\n")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_accepts_bold_markdown_verdict_line(self):
        result = self.run_parser("Looks fine\n**VERDICT: PASS**\n")
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
