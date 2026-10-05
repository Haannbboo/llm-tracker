#!/usr/bin/env bash
# scripts/start.sh
# Start tokenage services via supervisord.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${HOME}/.tokenage/run"
CONFIG_DIR="${HOME}/.tokenage"
CONFIG_PATH="${CONFIG_DIR}/config.yaml"
SUPERVISORD_CONF="${CONFIG_DIR}/supervisord.conf"
SUPERVISORD_PID="${RUNTIME_DIR}/supervisord.pid"
SOCKET_PATH="${RUNTIME_DIR}/supervisor.sock"
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON="${VENV_DIR}/bin/python"
SUPERVISORD="${VENV_DIR}/bin/supervisord"
SUPERVISORCTL="${VENV_DIR}/bin/supervisorctl"
PORT_CHECKER="${ROOT_DIR}/scripts/check-service-ports.py"
AUTO_PORT_ASSIGNER="${ROOT_DIR}/scripts/auto-assign-ports.py"

# ── Load terminal helpers ───────────────────────────────────────────
source "${ROOT_DIR}/scripts/lib/terminal.sh"

# Show banner only when run standalone (not from bootstrap.sh)
if [[ -z "${TOKENAGE_SKIP_BANNER:-}" ]]; then
  banner
  step_header "Starting services"
fi

# ── Verification ────────────────────────────────────────────────────
if [[ ! -x "${PYTHON}" ]]; then
  fail "Virtual environment not found — run scripts/bootstrap.sh first"
  exit 1
fi

# ── Dependencies must already be installed ──────────────────────────
# Installing belongs to bootstrap. start only turns services on, so it
# refuses when the recorded requirements hash no longer matches the file.
# shellcheck source=scripts/lib/requirements.sh
source "${ROOT_DIR}/scripts/lib/requirements.sh"
if ! requirements_are_current "${VENV_DIR}" "${ROOT_DIR}/requirements.txt"; then
  fail "Dependencies are out of date (requirements.txt changed)"
  info "run tokenage server bootstrap"
  exit 1
fi
pass "Dependencies up to date"

if [[ ! -x "${HOME}/.local/bin/tokenage" ]]; then
  info "NOTE: tokenage is not on PATH — run scripts/bootstrap.sh to set it up"
fi

mkdir -p "${ROOT_DIR}/logs" "${RUNTIME_DIR}"

# ── Config ──────────────────────────────────────────────────────────
CONFIG_WAS_CREATED=0
if [[ -e "${CONFIG_PATH}" || -L "${CONFIG_PATH}" ]]; then
  pass "Config exists: ${CONFIG_PATH}"
else
  cp "${ROOT_DIR}/config.example.yaml" "${CONFIG_PATH}"
  CONFIG_WAS_CREATED=1
  pass "Config created: ${CONFIG_PATH}"
fi

"${PYTHON}" "${ROOT_DIR}/scripts/sync-config.py" "${CONFIG_PATH}" "${ROOT_DIR}/config.example.yaml"

OTLP_PORT=$("${PYTHON}" -c "import yaml; from pathlib import Path; p = Path('${CONFIG_PATH}'); c = yaml.safe_load(p.read_text()) or {}; print(c.get('server', {}).get('otlp_port', 4002))" 2>/dev/null || echo "4002")

# ── Port check ──────────────────────────────────────────────────────
if ! PORT_CHECK_OUTPUT="$("${PYTHON}" "${PORT_CHECKER}" \
  --strict \
  --config "${CONFIG_PATH}" \
  --supervisorctl "${SUPERVISORCTL}" \
  --supervisord-conf "${SUPERVISORD_CONF}" 2>&1)"; then
  if [[ "${CONFIG_WAS_CREATED}" -eq 1 ]]; then
    "${PYTHON}" "${AUTO_PORT_ASSIGNER}" --config "${CONFIG_PATH}"
    if ! PORT_CHECK_OUTPUT="$("${PYTHON}" "${PORT_CHECKER}" \
      --strict \
      --config "${CONFIG_PATH}" \
      --supervisorctl "${SUPERVISORCTL}" \
      --supervisord-conf "${SUPERVISORD_CONF}" 2>&1)"; then
      fail "Port check failed after auto-assign"
      printf "%s\n" "${PORT_CHECK_OUTPUT}"
      exit 1
    fi
    pass "Ports auto-assigned"
  else
    fail "Port check failed"
    printf "%s\n" "${PORT_CHECK_OUTPUT}"
    exit 1
  fi
else
  pass "Port check passed"
fi

# Agent telemetry is the client's job now. `tokenage setup` points detected
# agents at this collector, and `tokenage server bootstrap` reports when one is
# installed but not wired. The server never edits user agent settings.

# ── Schema migrations ───────────────────────────────────────────────
info "Applying schema migrations..."
"${PYTHON}" "${ROOT_DIR}/scripts/migrate_schema.py"
pass "Migrations applied"

# ── Supervisord ─────────────────────────────────────────────────────
cat > "${SUPERVISORD_CONF}" <<EOF
[unix_http_server]
file=${SOCKET_PATH}

[supervisord]
logfile=${ROOT_DIR}/logs/supervisord.log
pidfile=${SUPERVISORD_PID}
childlogdir=${ROOT_DIR}/logs

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix://${SOCKET_PATH}

[program:tokenage-proxy]
command=${PYTHON} -m gunicorn -c ${ROOT_DIR}/src/config/proxy.conf.py src.proxy:app
environment=OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
directory=${ROOT_DIR}
autostart=true
autorestart=true
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile=${ROOT_DIR}/logs/proxy.stdout.log
stderr_logfile=${ROOT_DIR}/logs/proxy.stderr.log

[program:tokenage-api]
command=${PYTHON} -m gunicorn -c ${ROOT_DIR}/src/config/api.conf.py src.api:app
environment=OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
directory=${ROOT_DIR}
autostart=true
autorestart=true
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile=${ROOT_DIR}/logs/api.stdout.log
stderr_logfile=${ROOT_DIR}/logs/api.stderr.log

[program:tokenage-otlp]
command=${PYTHON} -m gunicorn -c ${ROOT_DIR}/src/config/otlp.conf.py src.otlp:app
environment=OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
directory=${ROOT_DIR}
autostart=true
autorestart=true
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile=${ROOT_DIR}/logs/otlp.stdout.log
stderr_logfile=${ROOT_DIR}/logs/otlp.stderr.log
EOF

# ── Start/reload supervisord ────────────────────────────────────────
EXISTING_PID="$(cat "${SUPERVISORD_PID}" 2>/dev/null || true)"
if [[ -n "${EXISTING_PID}" ]] && kill -0 "${EXISTING_PID}" 2>/dev/null; then
  info "Reloading supervisord (pid ${EXISTING_PID})..."
  "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" reread
  "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" update
  sleep 1
  pass "Supervisord reloaded"
else
  rm -f "${SOCKET_PATH}" "${SUPERVISORD_PID}"
  info "Starting supervisord..."
  "${SUPERVISORD}" -c "${SUPERVISORD_CONF}"
  for _ in $(seq 10); do [[ -S "${SOCKET_PATH}" ]] && break; sleep 0.3; done
  if [[ -S "${SOCKET_PATH}" ]]; then
    pass "Supervisord started"
  else
    info "Supervisord socket not ready at ${SOCKET_PATH} (may still be starting)"
    pass "Supervisord started"
  fi
fi

# ── Start any programs not yet running ──────────────────────────────
for prog in tokenage-proxy tokenage-api tokenage-otlp; do
  status="$("${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" status "${prog}" 2>/dev/null | awk '{print $2}' || true)"
  case "${status}" in
    RUNNING)  pass "${prog}: running" ;;
    STARTING) pass "${prog}: starting" ;;
    *)        info "Starting ${prog}..."
              "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" start "${prog}"
              pass "${prog}: started" ;;
  esac
done

# ── Final status (only when run standalone) ─────────────────────────
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  API_PORT=$("${PYTHON}" -c "import yaml; from pathlib import Path; p = Path('${CONFIG_PATH}'); c = yaml.safe_load(p.read_text()) or {}; print(c.get('server', {}).get('api_port', c.get('server', {}).get('port', 4000) + 1))" 2>/dev/null || echo "4001")
  DISPLAY_HOST="$("${PYTHON}" "${ROOT_DIR}/scripts/read-otlp-config.py" "${CONFIG_PATH}" 2>/dev/null | awk '{print $2}' || true)"
  final_status_ok "http://${DISPLAY_HOST:-127.0.0.1}:${API_PORT}"
fi
