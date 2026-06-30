#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills" / "loop-engine" / "bin" / "redact-text.py"


class RedactTextTests(unittest.TestCase):
    def test_redacts_query_tokens_and_assignment_secrets(self):
        raw = "SORFTIME_MCP_URL=https://example.invalid/mcp?key=abc123\nOPENAI_API_KEY=sk-test123\n"
        proc = subprocess.run([str(SCRIPT)], input=raw, text=True, capture_output=True, check=True)

        self.assertNotIn("abc123", proc.stdout)
        self.assertNotIn("sk-test123", proc.stdout)
        self.assertIn("[REDACTED]", proc.stdout)

    def test_loop_publish_minutes_redacts_without_raw_copy_by_default(self):
        with subprocess.Popen(
            ["bash", "-lc", f'''
                set -euo pipefail
                tmp="$(mktemp -d)"
                raw="$tmp/raw.md"
                out="$tmp/out.md"
                printf '%s\n' 'SORFTIME_MCP_URL=https://example.invalid/mcp?key=abc123' > "$raw"
                source "{ROOT / "skills" / "loop-engine" / "bin" / "_lib.sh"}"
                loop_publish_minutes "$raw" "$out"
                test -f "$out"
                ! test -f "$out.raw"
                ! grep -q 'abc123' "$out"
                grep -q '\\[REDACTED\\]' "$out"
            '''],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as proc:
            _stdout, stderr = proc.communicate(timeout=10)

        self.assertEqual(proc.returncode, 0, stderr)

    def test_loop_publish_minutes_keeps_raw_only_when_requested(self):
        with subprocess.Popen(
            ["bash", "-lc", f'''
                set -euo pipefail
                tmp="$(mktemp -d)"
                raw="$tmp/raw.md"
                out="$tmp/out.md"
                printf '%s\n' 'OPENAI_API_KEY=sk-test123' > "$raw"
                source "{ROOT / "skills" / "loop-engine" / "bin" / "_lib.sh"}"
                LOOP_KEEP_RAW_MINUTES=1 loop_publish_minutes "$raw" "$out"
                test -f "$out.raw"
                grep -q 'sk-test123' "$out.raw"
                ! grep -q 'sk-test123' "$out"
            '''],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as proc:
            _stdout, stderr = proc.communicate(timeout=10)

        self.assertEqual(proc.returncode, 0, stderr)


if __name__ == "__main__":
    unittest.main()
