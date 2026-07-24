#!/usr/bin/env bash
# claude-hook.sh — PreToolUse / PostToolUse hook for Claude Code.
# Captures tool name, arguments, and result to logs/tool-calls-detail.jsonl.
# Non-blocking: never slows the agent. Stdout is only the required JSON response.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/../logs"
LOG_FILE="${LOG_DIR}/tool-calls-detail.jsonl"

mkdir -p "${LOG_DIR}"

# Read stdin (the hook payload from Claude Code).
PAYLOAD="$(cat)"

# Parse with Python, append to log, and print the required stdout response.
python3 - "${PAYLOAD}" "${LOG_FILE}" "${LOG_DIR}" <<'PY'
import json
import os
import sys
import time

payload_str = sys.argv[1]
log_file = sys.argv[2]
log_dir = sys.argv[3]

try:
    data = json.loads(payload_str)
except Exception:
    data = {}

hook_event = data.get("hook_event_name") or ""
tool_name = data.get("tool_name") or ""
tool_input = data.get("tool_input") or {}
tool_use_id = data.get("tool_use_id") or ""
session_id = data.get("session_id") or ""
cwd = data.get("cwd") or ""

tool_response = data.get("tool_response") or {}
response_size = len(json.dumps(tool_response)) if tool_response else None

entry = {
    "ts": int(time.time() * 1000),
    "event": hook_event,
    "tool_name": tool_name,
    "tool_use_id": tool_use_id,
    "session_id": session_id,
    "cwd": cwd,
    "tool_input": tool_input,
}
if response_size is not None:
    entry["response_size"] = response_size

try:
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
except OSError:
    pass

# Required stdout: PreToolUse → approve, PostToolUse → continue.
if hook_event == "PreToolUse":
    print('{"decision":"approve"}')
else:
    print('{"continue":true}')
PY
