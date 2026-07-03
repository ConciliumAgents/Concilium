#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
AUDIT = ROOT / "scripts" / "startup_doc_audit.py"


def load_audit_module():
    spec = importlib.util.spec_from_file_location("startup_doc_audit", AUDIT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = load_audit_module()


def shared_block(extra: str = "") -> str:
    return textwrap.dedent(f"""
    <!-- SHARED-STARTUP:BEGIN -->
    ## Concilium Startup Contract
    - Keep AGENTS.md and CLAUDE.md shared startup blocks in parity.
    - Check active runtime with `roundtable --version`.
    {extra}
    <!-- SHARED-STARTUP:END -->
    """).strip()


class StartupDocAuditTests(unittest.TestCase):
    def test_matching_shared_blocks_pass(self):
        with tempfile.TemporaryDirectory() as td:
            project = pathlib.Path(td)
            (project / "AGENTS.md").write_text("# Agents\n\n" + shared_block() + "\n", encoding="utf-8")
            (project / "CLAUDE.md").write_text("# Claude\n\n" + shared_block() + "\n", encoding="utf-8")

            findings = audit.audit_project(project)

        self.assertEqual(findings, [])

    def test_mismatched_shared_blocks_fail(self):
        with tempfile.TemporaryDirectory() as td:
            project = pathlib.Path(td)
            (project / "AGENTS.md").write_text("# Agents\n\n" + shared_block() + "\n", encoding="utf-8")
            (project / "CLAUDE.md").write_text("# Claude\n\n" + shared_block("- Claude-only shared line.") + "\n", encoding="utf-8")

            findings = audit.audit_project(project)

        self.assertEqual(findings[0].kind, "startup-parity")

    def test_startup_markdown_links_must_resolve_inside_shared_block(self):
        with tempfile.TemporaryDirectory() as td:
            project = pathlib.Path(td)
            block = shared_block("- Release gates live in `docs/RELEASE.md`.")
            (project / "AGENTS.md").write_text("# Agents\n\n" + block + "\n", encoding="utf-8")
            (project / "CLAUDE.md").write_text("# Claude\n\n" + block + "\n", encoding="utf-8")

            findings = audit.audit_project(project)

        self.assertTrue(any(f.kind == "startup-link" for f in findings))

    def test_markdown_links_outside_shared_block_are_tool_specific(self):
        with tempfile.TemporaryDirectory() as td:
            project = pathlib.Path(td)
            outside = "\n\n## Tool Specific\n\nRelease gates live in `docs/RELEASE.md`.\n"
            (project / "AGENTS.md").write_text("# Agents\n\n" + shared_block() + outside, encoding="utf-8")
            (project / "CLAUDE.md").write_text("# Claude\n\n" + shared_block() + outside, encoding="utf-8")

            findings = audit.audit_project(project)

        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
