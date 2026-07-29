#!/usr/bin/env bash
# claude-hook.sh — PreToolUse / PostToolUse hook for Claude Code.
# No-op: tool-call detail logging removed (was writing unredacted tool_input/cwd
# to an unbounded file that nothing reads).
# ponytail: no-op until a future PR records tool calls to the ToolCall DB table.
set -euo pipefail

PAYLOAD="$(cat)"

# Required stdout: PreToolUse → approve, PostToolUse → continue.
if grep -q '"hook_event_name"[[:space:]]*:[[:space:]]*"PreToolUse"' <<<"${PAYLOAD}"; then
  echo '{"decision":"approve"}'
else
  echo '{"continue":true}'
fi
