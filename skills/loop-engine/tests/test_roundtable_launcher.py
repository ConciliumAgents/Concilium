#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
LAUNCHER = ROOT / "roundtable"


class RoundtableLauncherTests(unittest.TestCase):
    def test_version_prints_resolved_launcher_identity(self):
        proc = subprocess.run([str(LAUNCHER), "--version"], text=True, capture_output=True, check=True)

        self.assertIn("Concilium roundtable", proc.stdout)
        self.assertIn(f"entrypoint: {LAUNCHER}", proc.stdout)
        self.assertIn(f"repo_root: {ROOT}", proc.stdout)
        self.assertIn("branch:", proc.stdout)
        self.assertIn("commit:", proc.stdout)

    def test_doctor_preserves_roster_probe_and_adds_launcher_diagnostics(self):
        with tempfile.TemporaryDirectory() as td:
            bin_dir = pathlib.Path(td)
            stub = bin_dir / "python3"
            stub.write_text("#!/usr/bin/env bash\nprintf 'stub-python %s\\n' \"$*\"\n", encoding="utf-8")
            stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
            env = dict(os.environ)
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

            proc = subprocess.run([str(LAUNCHER), "--doctor"], text=True, capture_output=True, env=env, check=True)

        self.assertIn("roster-detect.py", proc.stdout)
        self.assertIn("Concilium roundtable", proc.stderr)
        self.assertIn(f"repo_root: {ROOT}", proc.stderr)

    def test_default_task_invocation_execs_concilium_run_live(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td) / "repo"
            repo.mkdir()
            stub = pathlib.Path(td) / "python-stub"
            capture = pathlib.Path(td) / "argv.json"
            stub.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "open(os.environ['CAPTURE_ARGV'], 'w', encoding='utf-8').write(json.dumps(sys.argv))\n",
                encoding="utf-8",
            )
            stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
            env = dict(os.environ)
            env["CONCILIUM_LAUNCHER_PYTHON"] = str(stub)
            env["CAPTURE_ARGV"] = str(capture)

            subprocess.run(
                [str(LAUNCHER), "--repo", str(repo), "--task", "方案评审，只评不改。"],
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )

            argv = json.loads(capture.read_text(encoding="utf-8"))
            self.assertIn("concilium-run.py", " ".join(argv))
            self.assertIn("--live", argv)
            self.assertIn("--repo", argv)
            self.assertIn(str(repo), argv)
            self.assertNotIn("conductor.py", " ".join(argv))
            self.assertNotIn("tui.py", " ".join(argv))


if __name__ == "__main__":
    unittest.main()
