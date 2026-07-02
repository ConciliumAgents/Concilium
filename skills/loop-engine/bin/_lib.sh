#!/usr/bin/env bash
# _lib.sh - Shared loop-engine shell library. Source it from scripts; do not run it directly.
# Responsibilities: argument validation, repository resolution, .roundtable paths, logging, verdict parsing, and defaults.

set -euo pipefail

# Force a UTF-8 locale for portable text handling.
# All scripts source this library before doing string work.
# The export is active before later script lines run.
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="en_US.UTF-8"

# ---- Default configuration values; environment variables may override them----
: "${LOOP_MAX_ITERS:=5}"
: "${LOOP_STUCK_LIMIT:=2}"
: "${LOOP_REVIEW_PROVIDER:=deepseek}"
: "${LOOP_REVIEW_MODEL:=deepseek-reasoner}"
: "${LOOP_TEST_CMD:=}"

# Roundtable directory name
LOOP_TABLE_DIRNAME=".roundtable"

# Current loop-engine/bin directory; compute inside the library because callers differ.
LOOP_BIN_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---- Logs go to stderr; stdout is reserved for raw agent output ----
loop_log()  { printf '\033[2m[loop-engine] %s\033[0m\n' "$*" >&2; }
loop_warn() { printf '\033[33m[loop-engine] %s\033[0m\n' "$*" >&2; }
loop_die()  { printf '\033[31m[loop-engine] error: %s\033[0m\n' "$*" >&2; exit 1; }

# ---- Resolve target repository: first argument, must be a git repository ----
loop_resolve_repo() {
  local repo="${1:-}"
  [ -n "$repo" ] || loop_die "missing target repository path (first argument)"
  [ -d "$repo" ] || loop_die "target repository does not exist: $repo"
  repo="$(cd "$repo" && pwd)"
  git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || loop_die "target is not a git repository: ${repo} (roundtable requires git history as memory)"
  printf '%s' "$repo"
}

# ---- Roundtable root directory: <repo>/.roundtable/ ----
loop_root() { printf '%s' "$1/$LOOP_TABLE_DIRNAME"; }

# ---- Session directory: <repo>/.roundtable/sessions/<session id>/, including KB and minutes ----
# The conductor passes LOOP_SESSION; standalone calls fall back to default.
# Memory is isolated by project repository and session.
loop_table_dir() {
  local repo="$1" sid="${LOOP_SESSION:-default}"
  local dir="$repo/$LOOP_TABLE_DIRNAME/sessions/$sid"
  mkdir -p "$dir/KB" "$dir/minutes"
  printf '%s' "$dir"
}

# ---- Current iteration: read from session roundtable.json, default 1 ----
loop_iter() {
  local sf; sf="$(loop_table_dir "$1")/roundtable.json"
  if [ -f "$sf" ] && command -v python3 >/dev/null 2>&1; then
    python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('iter',1))" "$sf" 2>/dev/null || echo 1
  else
    echo 1
  fi
}

# ---- Safely update one roundtable.json key with python3----
# Usage: loop_state_set <repo> <key> <value-as-python-literal>
loop_state_set() {
  local repo="$1" key="$2" val="$3" sf; sf="$(loop_table_dir "$repo")/roundtable.json"
  command -v python3 >/dev/null 2>&1 || { loop_warn "python3 unavailable; skipping state update"; return 0; }
  python3 - "$sf" "$key" "$val" <<'PY'
import json,sys,os
sf,key,val=sys.argv[1],sys.argv[2],sys.argv[3]
d={}
if os.path.exists(sf):
    try: d=json.load(open(sf))
    except Exception: d={}
try: v=json.loads(val)        # Try to parse as JSON
except Exception: v=val       # Otherwise treat as string
d[key]=v
json.dump(d,open(sf,'w'),ensure_ascii=False,indent=2)
PY
}

# ---- Extract the VERDICT line from an agent output file and map exit codes (0=PASS 2=BLOCK 1=ERR) ----
# Allow leading whitespace, Markdown headings, and bold VERDICT lines.
LOOP_VERDICT_LINE_RE='^[[:space:]]*(#{1,6}[[:space:]]*)?(\*\*)?VERDICT:[[:space:]]*(PASS|BLOCK)(\*\*)?[[:space:]]*$'
LOOP_VERDICT_PASS_RE='^[[:space:]]*(#{1,6}[[:space:]]*)?(\*\*)?VERDICT:[[:space:]]*PASS(\*\*)?[[:space:]]*$'
LOOP_VERDICT_BLOCK_RE='^[[:space:]]*(#{1,6}[[:space:]]*)?(\*\*)?VERDICT:[[:space:]]*BLOCK(\*\*)?[[:space:]]*$'

loop_verdict_exit() {
  local f="$1" line
  line="$(grep -aiE "$LOOP_VERDICT_LINE_RE" "$f" | tail -1 || true)"
  if   printf '%s' "$line" | grep -qiE 'PASS';  then loop_log "verdict: PASS";  return 0
  elif printf '%s' "$line" | grep -qiE 'BLOCK'; then loop_warn "verdict: BLOCK"; return 2
  else loop_warn "No VERDICT line found; treating as ERR. Read full minutes manually."; return 1
  fi
}

# ---- Codex review verdict: prefer explicit verdict, then native P0/P1 markers ----
# Exit codes: 0=PASS, 2=BLOCK, 1=ERR. Call only after codex exits rc=0.
loop_codex_verdict() {
  local f="$1"
  # 1) Prefer an explicit VERDICT line when Codex provides one.
  if grep -aiqE "$LOOP_VERDICT_BLOCK_RE" "$f"; then loop_warn "verdict: BLOCK (explicit VERDICT)"; return 2; fi
  if grep -aiqE "$LOOP_VERDICT_PASS_RE"  "$f"; then loop_log  "verdict: PASS (explicit VERDICT)"; return 0; fi
  # 2) Fallback to native Codex [P0]/[P1] critical/high markers -> BLOCK
  if grep -aqE '\[P[01]\]' "$f"; then loop_warn "verdict: BLOCK (Codex reported P0/P1 findings)"; return 2; fi
  # 3) No high-severity marker -> PASS
  loop_log "verdict: PASS (Codex reported no P0/P1 findings)"; return 0
}

# ---- Require a command to exist ----
loop_need() { command -v "$1" >/dev/null 2>&1 || loop_die "missing dependency command: $1"; }

# ---- Publish seat minutes: write redacted output by default; keep .raw only with LOOP_KEEP_RAW_MINUTES=1 ----
loop_publish_minutes() {
  local raw="$1" out="$2" tmp
  [ -f "$raw" ] || loop_die "minutes file to publish does not exist: $raw"
  if [ "${LOOP_KEEP_RAW_MINUTES:-0}" = "1" ]; then
    cp "$raw" "${out}.raw"
  fi
  tmp="${out}.redacted.$$"
  if command -v python3 >/dev/null 2>&1 && python3 "${LOOP_BIN_DIR}/redact-text.py" <"$raw" >"$tmp" 2>/dev/null; then
    mv "$tmp" "$out"
  else
    rm -f "$tmp"
    {
      printf '%s\n' "[loop-engine] minutes redaction failed; raw transcript withheld."
      printf '%s\n' "[loop-engine] Re-run with LOOP_KEEP_RAW_MINUTES=1 only for local debugging."
    } >"$out"
  fi
}

# ---- Shared seat prompt preamble: tells seats where the blackboard is and what rules apply----
# Usage: loop_seat_preamble <repo>
loop_seat_preamble() {
  local repo="$1" rel=".roundtable/sessions/${LOOP_SESSION:-default}"
  cat <<EOF
You are invited to a Loop Engineering roundtable. This is a one-shot seat response, not a chat.
The shared knowledge base (blackboard) is inside the repository at \`${rel}/KB/\`:
  - project.md          project context, architecture, conventions
  - task.md             current task and acceptance criteria
  - state.md            current progress, decisions, open questions
  - roster.md           active seat strengths
  - imported-memory.md  imported project memory from repository-external sources
  - diff.patch          current diff
  - test-results.txt    latest test output
Read these files and the repository source yourself. Do not assume this prompt contains all context.
EOF
}
