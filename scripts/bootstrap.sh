#!/usr/bin/env bash
# scripts/bootstrap.sh
# One-command local startup: install, start, and verify tokenage services.
set -euo pipefail

# ── Resolve repo root ───────────────────────────────────────────────
BOOTSTRAP_SOURCE="${BASH_SOURCE[0]}"
while [[ -L "${BOOTSTRAP_SOURCE}" ]]; do
  BOOTSTRAP_SOURCE="$(readlink "${BOOTSTRAP_SOURCE}")"
done
ROOT_DIR="$(cd "$(dirname "${BOOTSTRAP_SOURCE}")/.." && pwd)"

SCRIPTS_DIR="${ROOT_DIR}/scripts"
CONFIG_PATH="${HOME}/.tokenage/config.yaml"
CLI_WRAPPER="${SCRIPTS_DIR}/tokenage"
CLI_SYMLINK="${HOME}/.local/bin/tokenage"

# ── Load terminal helpers ───────────────────────────────────────────
source "${SCRIPTS_DIR}/lib/terminal.sh"

# ── Helpers ─────────────────────────────────────────────────────────
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

# `server start` compares requirements.txt against this stamp and refuses to run
# when they differ, so installing deps and recording them happen together.
# shellcheck source=scripts/lib/requirements.sh
source "${SCRIPTS_DIR}/lib/requirements.sh"

# The launcher is shared with the client install: whichever component installs
# first places it, and the client install later replaces it with its own copy.
# An existing launcher is left alone so this never repoints a client's command.
_link_launcher() {
  chmod +x "${CLI_WRAPPER}"
  if [[ ! -e "${CLI_SYMLINK}" && ! -L "${CLI_SYMLINK}" ]]; then
    ln -s "${CLI_WRAPPER}" "${CLI_SYMLINK}"
  fi
}

_install_deps() {
  if [[ "${TOKENAGE_SKIP_INSTALL:-0}" == "1" ]]; then
    mkdir -p "${HOME}/.local/bin" "${HOME}/.tokenage"
    _link_launcher
    # `server start` refuses when this stamp is missing or stale, so record it
    # even on the skip path — the flag asserts deps are current by fiat.
    record_requirements_stamp "${ROOT_DIR}/.venv" "${ROOT_DIR}/requirements.txt"
    info "Installation skipped (TOKENAGE_SKIP_INSTALL=1)"
    return 0
  fi

  local python_version="${TOKENAGE_PYTHON_VERSION:-3.13}"
  local venv_dir="${ROOT_DIR}/.venv"
  local bin_dir="${HOME}/.local/bin"
  local frontend_dir="${ROOT_DIR}/frontend"

  info "Setting up tokenage environment..."

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
  record_requirements_stamp "${ROOT_DIR}/.venv" "${ROOT_DIR}/requirements.txt"

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
  _link_launcher

  # 6. PATH Check & Notification
  if [[ ":$PATH:" != *":${bin_dir}:"* ]]; then
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "WARNING: ${bin_dir} is not in your PATH."
    echo "To use 'tokenage' from anywhere, add this to your shell profile:"
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

  info "Installation complete! You can now use 'tokenage' (if in PATH) or 'scripts/start.sh'."
}

# ── Banner ──────────────────────────────────────────────────────────
if [[ -z "${TOKENAGE_SKIP_BANNER:-}" ]]; then
  banner
fi

# ── Step 1: Install ─────────────────────────────────────────────────
step_header "Installing dependencies & CLI"
_install_deps

# ── Step 2: Start services ──────────────────────────────────────────
step_header "Starting services"
TOKENAGE_SKIP_BANNER=1 bash "${SCRIPTS_DIR}/start.sh"

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

# Read base_url for display URLs (external address)
BASE_URL=""
if [[ -f "${CONFIG_PATH}" ]]; then
  BASE_URL="$(grep -E "^\s+base_url:" "${CONFIG_PATH}" 2>/dev/null | head -1 | sed 's/.*base_url:\s*//' | tr -d '"' || true)"
fi
# Derive display host from base_url, fall back to 127.0.0.1
if [[ -n "${BASE_URL}" ]]; then
  DISPLAY_HOST="${BASE_URL#http://}"
  DISPLAY_HOST="${DISPLAY_HOST#https://}"
  DISPLAY_HOST="${DISPLAY_HOST%%:*}"  # strip port if any
  DISPLAY_SCHEME="${BASE_URL%%://*}"
else
  DISPLAY_HOST="127.0.0.1"
  DISPLAY_SCHEME="http"
fi

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
  pass "CLI wrapper: scripts/tokenage"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  fail "CLI wrapper: scripts/tokenage (not executable)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# Launcher (a symlink here, or the client install's copy)
if [[ -e "${CLI_SYMLINK}" ]]; then
  pass "Launcher: ${CLI_SYMLINK}"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  fail "Launcher: ${CLI_SYMLINK} (not found)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# API reachable (wait for gunicorn to finish starting)
if _wait_for_port "${HOST}" "${API_PORT}" "API"; then
  pass "API running: ${DISPLAY_SCHEME}://${DISPLAY_HOST}:${API_PORT}"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  fail "API reachable: ${DISPLAY_SCHEME}://${DISPLAY_HOST}:${API_PORT} (not responding)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# Proxy listening
if _wait_for_port "${HOST}" "${PROXY_PORT}" "Proxy"; then
  pass "Proxy listening: ${DISPLAY_SCHEME}://${DISPLAY_HOST}:${PROXY_PORT}"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  fail "Proxy listening: ${DISPLAY_SCHEME}://${DISPLAY_HOST}:${PROXY_PORT} (not responding)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# OTLP listening
if _wait_for_port "${HOST}" "${OTLP_PORT}" "OTLP"; then
  pass "OTLP listening: ${DISPLAY_SCHEME}://${DISPLAY_HOST}:${OTLP_PORT}"
  CHECKS_PASS=$((CHECKS_PASS + 1))
else
  fail "OTLP listening: ${DISPLAY_SCHEME}://${DISPLAY_HOST}:${OTLP_PORT} (not responding)"
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
fi

# A freshly built frontend/dist is not served by a process that started before
# it existed: src/api.py mounts it at import time, under `if dist.is_dir()`.
# So the only command that builds is also the one that restarts the API.
if [[ -d "${ROOT_DIR}/frontend/dist" ]]; then
  info "Restarting the API to serve the new dashboard..."
  "${ROOT_DIR}/.venv/bin/supervisorctl" -c "${HOME}/.tokenage/supervisord.conf" restart tokenage-api || true
fi

# Dashboard reachable (API serves frontend)
if command -v curl >/dev/null 2>&1; then
  _dash_ct="$(curl --connect-timeout 3 -s -o /dev/null -w '%{content_type}' "http://${HOST}:${API_PORT}/" 2>/dev/null || true)"
  if [[ "${_dash_ct}" == text/html* ]]; then
    pass "Dashboard: ${DISPLAY_SCHEME}://${DISPLAY_HOST}:${API_PORT}"
    CHECKS_PASS=$((CHECKS_PASS + 1))
  else
    fail "Dashboard: ${DISPLAY_SCHEME}://${DISPLAY_HOST}:${API_PORT} (frontend not served)"
    CHECKS_FAIL=$((CHECKS_FAIL + 1))
  fi
else
  pass "Dashboard: ${DISPLAY_SCHEME}://${DISPLAY_HOST}:${API_PORT} (curl not available, skipped)"
  CHECKS_PASS=$((CHECKS_PASS + 1))
fi

# ── Final report ────────────────────────────────────────────────────
if [[ "${CHECKS_FAIL}" -eq 0 ]]; then
  final_status_ok "http://${HOST}:${API_PORT}"
  exit 0
else
  final_status_warn "http://${HOST}:${API_PORT}" "${CHECKS_FAIL}"
  exit 1
fi
