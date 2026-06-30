#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
REPO="${1:-$ROOT}"

echo "[phase4] unit suite"
python3 -m unittest discover -s "$ROOT/skills/loop-engine/tests"

echo "[phase4] CLI preview"
python3 "$ROOT/skills/loop-engine/bin/concilium-run.py" \
  --repo "$REPO" \
  --task "Fix one typo in docs/example.md." \
  --test-cmd "true" \
  --mode preview \
  --signals-json '{"risk":"low","file_count":1,"security_sensitive":false,"ambiguous":false}' \
  >/tmp/concilium-phase4-preview.json

python3 - <<'PY'
import json
from pathlib import Path
preview = json.loads(Path("/tmp/concilium-phase4-preview.json").read_text(encoding="utf-8"))
assert preview["status"] == "preview"
assert preview["route"]["lane"] in {"fast", "review", "roundtable"}
assert preview["request_fingerprint"]
PY

echo "[phase4] CLI stub run"
python3 "$ROOT/skills/loop-engine/bin/concilium-run.py" \
  --repo "$REPO" \
  --task "Fix one typo in docs/example.md." \
  --test-cmd "true" \
  --mode stub_run \
  --signals-json '{"risk":"low","file_count":1,"security_sensitive":false,"ambiguous":false}' \
  >/tmp/concilium-phase4-stub.json

python3 - <<'PY'
import json
from pathlib import Path
stub = json.loads(Path("/tmp/concilium-phase4-stub.json").read_text(encoding="utf-8"))
assert stub["status"] == "stubbed"
assert stub["returncode"] == 0
events = stub.get("events", [])
assert events
assert events[-1]["type"] == "done"
PY

echo "[phase4] diff check"
git -C "$ROOT" diff --check
