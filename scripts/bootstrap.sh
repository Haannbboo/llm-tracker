#!/usr/bin/env bash
# scripts/bootstrap.sh
# One-command local startup: install, start, and verify llm-tracker services.
set -euo pipefail

# ── Resolve repo root ───────────────────────────────────────────────
BOOTSTRAP_SOURCE="${BASH_SOURCE[0]}"
while [[ -L "${BOOTSTRAP_SOURCE}" ]]; do
  BOOTSTRAP_SOURCE="$(readlink "${BOOTSTRAP_SOURCE}")"
done
ROOT_DIR="$(cd "$(dirname "${BOOTSTRAP_SOURCE}")/.." && pwd)"

SCRIPTS_DIR="${ROOT_DIR}/scripts"
CONFIG_PATH="${HOME}/.llm-tracker/config.yaml"
CLI_WRAPPER="${SCRIPTS_DIR}/llm-tracker"
CLI_SYMLINK="${HOME}/.local/bin/llm-tracker"

# ── Helpers ─────────────────────────────────────────────────────────
_pass() { printf "  ✅ %s\n" "$*"; }
_fail() { printf "  ❌ %s\n" "$*"; }

_python_cmd() {
  if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    echo "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    return 1
  fi
}

_port_listening() {
  # Test if a TCP port is reachable (short timeout).
  # Returns 0 if something is listening, 1 otherwise.
  local host="$1" port="$2"
  if command -v curl >/dev/null 2>&1; then
    curl --connect-timeout 3 -sf "http://${host}:${port}/" >/dev/null 2>&1 && return 0
    # curl exits non-200 on 404/405 etc., but connection succeeded → port is open.
    # Retry without -f to catch services that return error codes but are alive.
    curl --connect-timeout 3 -s -o /dev/null -w '%{http_code}' "http://${host}:${port}/" 2>/dev/null | grep -qE '^[2-5]' && return 0
    return 1
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect(('${host}', ${port}))
    s.close()
except Exception:
    sys.exit(1)
" && return 0
    return 1
  else
    # Fallback: /dev/tcp (bash built-in)
    (echo >/dev/tcp/"${host}"/"${port}") 2>/dev/null && return 0
    return 1
  fi
}

_fetch_setup_health() {
  local url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl --connect-timeout 3 -sS "${url}"
    return
  fi

  local python
  python="$(_python_cmd)" || return 1
  "${python}" -c '
import sys
import urllib.request

url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=3) as response:
        sys.stdout.write(response.read().decode("utf-8"))
except Exception:
    sys.exit(1)
' "${url}"
}

_verify_agent_setup_health() {
  local url="http://${HOST}:${API_PORT}/local/setup-health"
  local health_json
  local python
  local claude_detected=0
  local codex_detected=0
  local gemini_detected=0

  echo ""
  echo "==> Agent tracking verification (/local/setup-health)..."

  python="$(_python_cmd)" || {
    _fail "Agent tracking: Python not available for setup-health verification"
    CHECKS_FAIL=$((CHECKS_FAIL + 1))
    return
  }

  if ! health_json="$(_fetch_setup_health "${url}" 2>/dev/null)"; then
    _fail "Agent tracking: could not read ${url}"
    CHECKS_FAIL=$((CHECKS_FAIL + 1))
    return
  fi

  command -v claude >/dev/null 2>&1 && claude_detected=1
  command -v codex >/dev/null 2>&1 && codex_detected=1
  command -v gemini >/dev/null 2>&1 && gemini_detected=1

  if printf "%s" "${health_json}" \
      | LLM_TRACKER_CLAUDE_DETECTED="${claude_detected}" \
        LLM_TRACKER_CODEX_DETECTED="${codex_detected}" \
        LLM_TRACKER_GEMINI_DETECTED="${gemini_detected}" \
        "${python}" -c '
import json
import os
import sys

try:
    data = json.loads(sys.stdin.read())
except Exception:
    print("  ❌ Agent tracking: invalid setup-health response")
    sys.exit(1)

agents = data.get("agents")
if not isinstance(agents, dict):
    print("  ❌ Agent tracking: setup-health response is missing agents")
    sys.exit(1)

ready = 0
skipped = 0
failed = 0
for key, label in (("claude", "Claude"), ("codex", "Codex"), ("gemini", "Gemini")):
    agent = agents.get(key)
    if not isinstance(agent, dict):
        failed += 1
        print(f"  ❌ {label}: setup health unavailable")
        continue

    status = agent.get("status")
    configured = agent.get("configured") is True
    endpoint_matches = agent.get("endpoint_matches") is True
    detected = os.environ.get(f"LLM_TRACKER_{key.upper()}_DETECTED") == "1"

    if not detected:
        skipped += 1
        print(f"  ✅ {label}: skipped")
    elif status == "ready" and endpoint_matches:
        ready += 1
        print(f"  ✅ {label}: ready")
    elif status == "wrong_endpoint" or (configured and not endpoint_matches):
        failed += 1
        print(f"  ❌ {label}: configured endpoint mismatch with current llm-tracker OTLP endpoint")
    elif status == "missing_config":
        failed += 1
        print(f"  ❌ {label}: OTLP not configured")
    else:
        failed += 1
        print(f"  ❌ {label}: setup health unavailable")

icon = "✅" if failed == 0 else "❌"
print(f"  {icon} Agent tracking: {ready} ready, {skipped} skipped, {failed} failed")
sys.exit(1 if failed else 0)
'
  then
    CHECKS_PASS=$((CHECKS_PASS + 1))
  else
    CHECKS_FAIL=$((CHECKS_FAIL + 1))
  fi
}

# ── Step 1: Install ─────────────────────────────────────────────────
echo ""
echo "==> [1/3] Installing dependencies and CLI..."
bash "${SCRIPTS_DIR}/install.sh"

# ── Step 2: Start services ──────────────────────────────────────────
echo ""
echo "==> [2/3] Starting services..."
bash "${SCRIPTS_DIR}/start.sh"

# ── Step 3: Post-start checks ──────────────────────────────────────
echo ""
echo "==> [3/3] Running post-start checks..."

# Read configured ports (fallback to defaults)
PROXY_PORT=4000
API_PORT=4001
OTLP_PORT=4002
if [[ -f "${CONFIG_PATH}" ]]; then
  _read_port() {
    local key="$1" default="$2"
    local val
    val="$(grep -E "^\s+${key}:" "${CONFIG_PATH}" 2>/dev/null | head -1 | awk '{print $2}')"
    if [[ -n "${val}" && "${val}" =~ ^[0-9]+$ ]]; then
      echo "${val}"
    else
      echo "${default}"
    fi
  }
  PROXY_PORT="$(_read_port port 4000)"
  API_PORT="$(_read_port api_port 4001)"
  OTLP_PORT="$(_read_port otlp_port 4002)"
fi

HOST="127.0.0.1"
CHECKS_PASS=0
CHECKS_FAIL=0
# Config file
if [[ -f "${CONFIG_PATH}" ]]; then
  _pass "Config: ${CONFIG_PATH}"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  _fail "Config: ${CONFIG_PATH} (not found)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# CLI wrapper
if [[ -x "${CLI_WRAPPER}" ]]; then
  _pass "CLI wrapper: scripts/llm-tracker"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  _fail "CLI wrapper: scripts/llm-tracker (not executable)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# CLI symlink
if [[ -L "${CLI_SYMLINK}" ]]; then
  _pass "CLI symlink: ${CLI_SYMLINK}"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  _fail "CLI symlink: ${CLI_SYMLINK} (not found)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# API reachable
if _port_listening "${HOST}" "${API_PORT}"; then
  _pass "API running: http://${HOST}:${API_PORT}"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  _fail "API reachable: http://${HOST}:${API_PORT} (not responding)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# Proxy listening
if _port_listening "${HOST}" "${PROXY_PORT}"; then
  _pass "Proxy listening: http://${HOST}:${PROXY_PORT}"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  _fail "Proxy listening: http://${HOST}:${PROXY_PORT} (not responding)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# OTLP listening
if _port_listening "${HOST}" "${OTLP_PORT}"; then
  _pass "OTLP listening: http://${HOST}:${OTLP_PORT}"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  _fail "OTLP listening: http://${HOST}:${OTLP_PORT} (not responding)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# Dashboard reachable (API serves frontend)
if command -v curl >/dev/null 2>&1; then
  _dash_ct="$(curl --connect-timeout 3 -s -o /dev/null -w '%{content_type}' "http://${HOST}:${API_PORT}/" 2>/dev/null || true)"
  if [[ "${_dash_ct}" == text/html* ]]; then
    _pass "Dashboard: http://${HOST}:${API_PORT}"
    CHECKS_PASS=$((CHECKS_PASS + 1))
  else
    _fail "Dashboard: http://${HOST}:${API_PORT} (frontend not served — run: cd frontend && npm run build)"
    CHECKS_FAIL=$((CHECKS_FAIL + 1))
  fi
else
  _pass "Dashboard: http://${HOST}:${API_PORT} (curl not available, skipped check)"
  CHECKS_PASS=$((CHECKS_PASS + 1))
fi

_verify_agent_setup_health

# ── Final report ────────────────────────────────────────────────────
echo ""
if [[ "${CHECKS_FAIL}" -eq 0 ]]; then
  echo "✅ llm-tracker bootstrap complete"
else
  echo "⚠️  llm-tracker bootstrap finished with ${CHECKS_FAIL} issue(s)"
fi

exit_code=0
if [[ "${CHECKS_FAIL}" -ne 0 ]]; then
  exit_code=1
fi

echo ""
echo "Dashboard: http://${HOST}:${API_PORT}"

exit "${exit_code}"
