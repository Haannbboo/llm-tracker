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

# ── Load terminal helpers ───────────────────────────────────────────
source "${SCRIPTS_DIR}/lib/terminal.sh"

# ── Helpers ─────────────────────────────────────────────────────────
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
  local host="$1" port="$2"
  if command -v curl >/dev/null 2>&1; then
    curl --connect-timeout 3 -sf "http://${host}:${port}/" >/dev/null 2>&1 && return 0
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

_install_deps() {
  if [[ "${LLM_TRACKER_SKIP_INSTALL:-0}" == "1" ]]; then
    mkdir -p "${HOME}/.local/bin" "${HOME}/.llm-tracker"
    ln -sf "${SCRIPTS_DIR}/llm-tracker" "${HOME}/.local/bin/llm-tracker"
    chmod +x "${SCRIPTS_DIR}/llm-tracker"
    info "Installation skipped (LLM_TRACKER_SKIP_INSTALL=1)"
    return 0
  fi

  local python_version="${LLM_TRACKER_PYTHON_VERSION:-3.13}"
  local venv_dir="${ROOT_DIR}/.venv"
  local bin_dir="${HOME}/.local/bin"
  local cli_link="${bin_dir}/llm-tracker"
  local cli_source="${SCRIPTS_DIR}/llm-tracker"
  local frontend_dir="${ROOT_DIR}/frontend"

  info "Setting up llm-tracker environment..."

  # 1. Bootstrap uv
  if ! command -v uv >/dev/null 2>&1; then
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
  fi

  # 2. Create venv
  if [[ ! -x "${venv_dir}/bin/python" ]]; then
    info "Creating venv..."
    uv venv --python "${python_version}" "${venv_dir}"
  fi

  # 3. Install initial dependencies
  info "Installing dependencies..."
  uv pip install --python "${venv_dir}/bin/python" -r "${ROOT_DIR}/requirements.txt"

  # 4. Build frontend
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    local node_version node_major
    node_version=$(node -v | cut -d'v' -f2)
    node_major=$(echo "$node_version" | cut -d'.' -f1)

    if [[ "$node_major" -lt 18 ]]; then
      echo ""
      echo "⚠️  Node.js version $node_version is too old (minimum v18 required)."
      echo "   Skipping frontend build. Dashboard will not be available."
      echo ""
    elif [[ -d "${frontend_dir}" ]]; then
      info "Building frontend (Node $node_version)..."
      if ! (cd "${frontend_dir}" && npm install --ignore-scripts && npm run build); then
        echo ""
        echo "❌ Frontend build failed."
        echo "   If you see 'Cannot find native binding', try cleaning the frontend directory and retrying:"
        echo "     rm -rf frontend/node_modules frontend/package-lock.json && bash scripts/bootstrap.sh"
        echo ""
        exit 1
      fi
      info "Frontend built: ${frontend_dir}/dist"
    fi
  else
    echo ""
    echo "⚠️  Node.js not found — skipping frontend build."
    echo "   The dashboard will not be available until you install Node.js and run:"
    echo "     cd frontend && npm install && npm run build"
    echo ""
  fi

  # 5. CLI Setup
  info "Setting up CLI symlink..."
  mkdir -p "${bin_dir}"
  ln -sf "${cli_source}" "${cli_link}"
  chmod +x "${cli_source}"

  # 6. PATH Check & Notification
  if [[ ":$PATH:" != *":${bin_dir}:"* ]]; then
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "WARNING: ${bin_dir} is not in your PATH."
    echo "To use 'llm-tracker' from anywhere, add this to your shell profile:"
    echo ""
    if [[ "${SHELL}" == *"/zsh" ]]; then
      echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
      echo "  source ~/.zshrc"
    else
      echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
      echo "  source ~/.bashrc"
    fi
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo ""
  fi

  info "Installation complete! You can now use 'llm-tracker' (if in PATH) or 'scripts/start.sh'."
}

_verify_agent_setup_health() {
  local url="http://${HOST}:${API_PORT}/local/setup-health"
  local health_json
  local python
  local claude_detected=0
  local codex_detected=0
  local gemini_detected=0
  local opencode_detected=0
  local kilo_detected=0

  step_header "Verifying agent tracking"

  python="$(_python_cmd)" || {
    fail "Agent tracking: Python not available"
    CHECKS_FAIL=$((CHECKS_FAIL + 1))
    return
  }

  if ! health_json="$(_fetch_setup_health "${url}" 2>/dev/null)"; then
    fail "Agent tracking: could not read ${url}"
    CHECKS_FAIL=$((CHECKS_FAIL + 1))
    return
  fi

  command -v claude >/dev/null 2>&1 && claude_detected=1
  command -v codex >/dev/null 2>&1 && codex_detected=1
  command -v gemini >/dev/null 2>&1 && gemini_detected=1
  command -v opencode >/dev/null 2>&1 && opencode_detected=1
  command -v kilo >/dev/null 2>&1 && kilo_detected=1

  if printf "%s" "${health_json}" \
      | LLM_TRACKER_CLAUDE_DETECTED="${claude_detected}" \
        LLM_TRACKER_CODEX_DETECTED="${codex_detected}" \
        LLM_TRACKER_GEMINI_DETECTED="${gemini_detected}" \
        LLM_TRACKER_OPENCODE_DETECTED="${opencode_detected}" \
        LLM_TRACKER_KILO_DETECTED="${kilo_detected}" \
        LLM_TRACKER_GREEN="${_T_GREEN}" \
        LLM_TRACKER_RED="${_T_RED}" \
        LLM_TRACKER_RESET="${_T_RESET}" \
        "${python}" -c '
import json
import os
import sys

GREEN = os.environ.get("LLM_TRACKER_GREEN", "")
RED = os.environ.get("LLM_TRACKER_RED", "")
RESET = os.environ.get("LLM_TRACKER_RESET", "")

try:
    data = json.loads(sys.stdin.read())
except Exception:
    print(f"  {RED}✗{RESET} Agent tracking: invalid setup-health response")
    sys.exit(1)

agents = data.get("agents")
if not isinstance(agents, dict):
    print(f"  {RED}✗{RESET} Agent tracking: setup-health response is missing agents")
    sys.exit(1)

ready = 0
skipped = 0
failed = 0
for key, label in (
    ("claude", "Claude"),
    ("codex", "Codex"),
    ("gemini", "Gemini"),
    ("opencode", "OpenCode"),
    ("kilo", "Kilo"),
):
    agent = agents.get(key)
    if not isinstance(agent, dict):
        failed += 1
        print(f"  {RED}✗{RESET} {label}: setup health unavailable")
        continue

    status = agent.get("status")
    configured = agent.get("configured") is True
    endpoint_matches = agent.get("endpoint_matches") is True
    detected = os.environ.get(f"LLM_TRACKER_{key.upper()}_DETECTED") == "1"

    if not detected:
        skipped += 1
        print(f"  {GREEN}✓{RESET} {label}: skipped")
    elif status == "ready" and endpoint_matches:
        ready += 1
        print(f"  {GREEN}✓{RESET} {label}: ready")
    elif status == "wrong_endpoint" or (configured and not endpoint_matches):
        failed += 1
        print(f"  {RED}✗{RESET} {label}: endpoint mismatch")
    elif status == "missing_config":
        failed += 1
        print(f"  {RED}✗{RESET} {label}: OTLP not configured")
    else:
        failed += 1
        print(f"  {RED}✗{RESET} {label}: setup health unavailable")

if failed == 0:
    print(f"  {GREEN}✓{RESET} Agents: {ready} ready, {skipped} skipped, {failed} failed")
else:
    print(f"  {RED}✗{RESET} Agents: {ready} ready, {skipped} skipped, {failed} failed")
sys.exit(1 if failed else 0)
'
  then
    CHECKS_PASS=$((CHECKS_PASS + 1))
  else
    CHECKS_FAIL=$((CHECKS_FAIL + 1))
  fi
}

# ── Banner ──────────────────────────────────────────────────────────
if [[ -z "${LLM_TRACKER_SKIP_BANNER:-}" ]]; then
  banner
fi

# ── Step 1: Install ─────────────────────────────────────────────────
step_header "Installing dependencies & CLI"
_install_deps

# ── Step 2: Start services ──────────────────────────────────────────
step_header "Starting services"
LLM_TRACKER_SKIP_BANNER=1 bash "${SCRIPTS_DIR}/start.sh"

# ── Step 3: Post-start checks ──────────────────────────────────────
step_header "Running post-start checks"

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

# Wait for a port to become reachable (gunicorn may still be starting)
_wait_for_port() {
  local host="$1" port="$2" label="$3"
  local retries=10
  for ((i = 1; i <= retries; i++)); do
    if _port_listening "${host}" "${port}"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# Config file
if [[ -f "${CONFIG_PATH}" ]]; then
  pass "Config: ${CONFIG_PATH}"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  fail "Config: ${CONFIG_PATH} (not found)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# CLI wrapper
if [[ -x "${CLI_WRAPPER}" ]]; then
  pass "CLI wrapper: scripts/llm-tracker"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  fail "CLI wrapper: scripts/llm-tracker (not executable)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# CLI symlink
if [[ -L "${CLI_SYMLINK}" ]]; then
  pass "CLI symlink: ${CLI_SYMLINK}"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  fail "CLI symlink: ${CLI_SYMLINK} (not found)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# API reachable (wait for gunicorn to finish starting)
if _wait_for_port "${HOST}" "${API_PORT}" "API"; then
  pass "API running: http://${HOST}:${API_PORT}"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  fail "API reachable: http://${HOST}:${API_PORT} (not responding)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# Proxy listening
if _wait_for_port "${HOST}" "${PROXY_PORT}" "Proxy"; then
  pass "Proxy listening: http://${HOST}:${PROXY_PORT}"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  fail "Proxy listening: http://${HOST}:${PROXY_PORT} (not responding)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# OTLP listening
if _wait_for_port "${HOST}" "${OTLP_PORT}" "OTLP"; then
  pass "OTLP listening: http://${HOST}:${OTLP_PORT}"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  fail "OTLP listening: http://${HOST}:${OTLP_PORT} (not responding)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# Dashboard reachable (API serves frontend)
if command -v curl >/dev/null 2>&1; then
  _dash_ct="$(curl --connect-timeout 3 -s -o /dev/null -w '%{content_type}' "http://${HOST}:${API_PORT}/" 2>/dev/null || true)"
  if [[ "${_dash_ct}" == text/html* ]]; then
    pass "Dashboard: http://${HOST}:${API_PORT}"
    CHECKS_PASS=$((CHECKS_PASS + 1))
  else
    fail "Dashboard: http://${HOST}:${API_PORT} (frontend not served)"
    CHECKS_FAIL=$((CHECKS_FAIL + 1))
  fi
else
  pass "Dashboard: http://${HOST}:${API_PORT} (curl not available, skipped)"
  CHECKS_PASS=$((CHECKS_PASS + 1))
fi

_verify_agent_setup_health

# ── Final report ────────────────────────────────────────────────────
if [[ "${CHECKS_FAIL}" -eq 0 ]]; then
  final_status_ok "http://${HOST}:${API_PORT}"
  exit 0
else
  final_status_warn "http://${HOST}:${API_PORT}" "${CHECKS_FAIL}"
  exit 1
fi
