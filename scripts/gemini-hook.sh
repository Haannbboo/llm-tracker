#!/usr/bin/env bash
# gemini-hook.sh - Gemini CLI hook for TTFT calculation
set -euo pipefail

TMPDIR="${TMPDIR:-/tmp}"
STATE_DIR="${TMPDIR}/llm-tracker-gemini"
PAYLOAD="$(cat)"

mkdir -p "${STATE_DIR}"

_meta="$(printf '%s' "${PAYLOAD}" | python3 -c '
import json
import os
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

usage = (data.get("llm_response") or {}).get("usageMetadata") or {}
event   = data.get("hook_event_name") or os.environ.get("GEMINI_EVENT") or ""
session = data.get("session_id") or (data.get("session") or {}).get("id") or "unknown"
model   = (data.get("llm_request") or {}).get("model") or "gemini-unknown"
total   = "" if usage.get("totalTokenCount") is None else str(usage.get("totalTokenCount"))
print("|".join([event, session, model, total]))
' 2>/dev/null || echo "|||")"

IFS='|' read -r EVENT SESSION_ID MODEL TOTAL <<EOF
${_meta}
EOF

STATE_FILE="${STATE_DIR}/state-${SESSION_ID}.json"

case "${EVENT}" in
  BeforeModel)
    python3 - "${STATE_FILE}" "${MODEL}" <<'PY'
import json
import sys
import time

path, model = sys.argv[1:3]
with open(path, "w", encoding="utf-8") as f:
    json.dump({"start_ms": int(time.time() * 1000)}, f)
PY
    ;;
  AfterModel)
    python3 - "${STATE_FILE}" "${STATE_DIR}" "${SESSION_ID}" "${MODEL}" "${TOTAL}" <<'PY'
import json
import os
import sys
import time
from pathlib import Path

state_path = Path(sys.argv[1])
state_dir = Path(sys.argv[2])
session_id, model, total = sys.argv[3:6]
now_ms = int(time.time() * 1000)

state = {}
if state_path.exists():
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {}

start_ms = state.get("start_ms")
if start_ms is None:
    start_ms = now_ms

state.setdefault("ttft_ms", max(0, now_ms - int(start_ms)))

if total:
    entry = {
        "session_id": session_id,
        "ttft_ms": int(state["ttft_ms"]),
        "latency_ms": max(0, now_ms - int(start_ms)),
    }
    queue_path = state_dir / f"queue-{session_id}.jsonl"
    with open(queue_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    try:
        state_path.unlink()
    except FileNotFoundError:
        pass
else:
    state_path.write_text(json.dumps(state), encoding="utf-8")
PY
    ;;
esac

echo '{"continue":true}'
