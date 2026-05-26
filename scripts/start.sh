#!/usr/bin/env bash
# scripts/start.sh
# Start llm-tracker services via supervisord.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${HOME}/.llm-tracker/run"
CONFIG_DIR="${HOME}/.llm-tracker"
CONFIG_PATH="${CONFIG_DIR}/config.yaml"
SUPERVISORD_CONF="${CONFIG_DIR}/supervisord.conf"
SUPERVISORD_PID="${RUNTIME_DIR}/supervisord.pid"
SOCKET_PATH="${RUNTIME_DIR}/supervisor.sock"
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON="${VENV_DIR}/bin/python"
SUPERVISORD="${VENV_DIR}/bin/supervisord"
SUPERVISORCTL="${VENV_DIR}/bin/supervisorctl"
REQS_STAMP="${VENV_DIR}/.requirements.sha256"
PORT_CHECKER="${ROOT_DIR}/scripts/check-service-ports.py"
AUTO_PORT_ASSIGNER="${ROOT_DIR}/scripts/auto-assign-ports.py"

# ── Load terminal helpers ───────────────────────────────────────────
source "${ROOT_DIR}/scripts/lib/terminal.sh"

# Show banner only when run standalone (not from bootstrap.sh)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  banner
  step_header "Starting services"
fi

# ── Verification ────────────────────────────────────────────────────
if [[ ! -x "${PYTHON}" ]]; then
  fail "Virtual environment not found — run scripts/bootstrap.sh first"
  exit 1
fi

if [[ ! -L "${HOME}/.local/bin/llm-tracker" ]]; then
  info "NOTE: CLI symlink missing — run scripts/bootstrap.sh to set it up"
fi

# ── Install deps when requirements.txt changes ─────────────────────
if command -v shasum >/dev/null 2>&1; then
  CURRENT_HASH="$(shasum -a 256 "${ROOT_DIR}/requirements.txt" | awk '{print $1}')"
elif command -v sha256sum >/dev/null 2>&1; then
  CURRENT_HASH="$(sha256sum "${ROOT_DIR}/requirements.txt" | awk '{print $1}')"
else
  CURRENT_HASH="$(ls -l "${ROOT_DIR}/requirements.txt" | awk '{print $5 "_" $9}')"
fi
SAVED_HASH="$(cat "${REQS_STAMP}" 2>/dev/null || true)"
if [[ "${CURRENT_HASH}" != "${SAVED_HASH}" ]]; then
  info "Installing dependencies..."
  uv pip install --python "${PYTHON}" -r "${ROOT_DIR}/requirements.txt"
  echo "${CURRENT_HASH}" > "${REQS_STAMP}"
  pass "Dependencies installed"
else
  pass "Dependencies up to date"
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

OTLP_PORT=$("${PYTHON}" -c "import yaml; from pathlib import Path; p = Path('${CONFIG_PATH}'); c = yaml.safe_load(p.read_text()) or {}; print(c.get('server', {}).get('otlp_port', 4002))" 2>/dev/null || echo "4002")

# ── Configure agent OTLP telemetry ──────────────────────────────────
if command -v codex >/dev/null 2>&1; then
  CODEX_CONFIG="${HOME}/.codex/config.toml"
  "${PYTHON}" "${ROOT_DIR}/scripts/configure-codex-settings.py" "${CODEX_CONFIG}" "${OTLP_PORT}"
  pass "Codex configured"
fi

if command -v gemini >/dev/null 2>&1; then
  bash "${ROOT_DIR}/scripts/setup-gemini.sh" "${OTLP_PORT}"
  pass "Gemini configured"
fi

if command -v claude >/dev/null 2>&1; then
  CLAUDE_SETTINGS="${HOME}/.claude/settings.json"
  "${PYTHON}" "${ROOT_DIR}/scripts/configure-claude-settings.py" "${CLAUDE_SETTINGS}" "${OTLP_PORT}"
  pass "Claude configured"
fi

if command -v opencode >/dev/null 2>&1; then
  "${PYTHON}" "${ROOT_DIR}/scripts/configure-opencode-plugin.py" "${ROOT_DIR}" "${OTLP_PORT}"
  pass "OpenCode configured"
fi

if command -v kilo >/dev/null 2>&1; then
  "${PYTHON}" "${ROOT_DIR}/scripts/configure-kilo-plugin.py" "${ROOT_DIR}" "${OTLP_PORT}"
  pass "Kilo Code configured"
fi

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

[program:llm-tracker-proxy]
command=${PYTHON} -m gunicorn -c ${ROOT_DIR}/config/proxy.conf.py src.proxy:app
environment=OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
directory=${ROOT_DIR}
autostart=true
autorestart=true
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile=${ROOT_DIR}/logs/proxy.stdout.log
stderr_logfile=${ROOT_DIR}/logs/proxy.stderr.log

[program:llm-tracker-api]
command=${PYTHON} -m gunicorn -c ${ROOT_DIR}/config/api.conf.py src.api:app
environment=OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
directory=${ROOT_DIR}
autostart=true
autorestart=true
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile=${ROOT_DIR}/logs/api.stdout.log
stderr_logfile=${ROOT_DIR}/logs/api.stderr.log

[program:llm-tracker-otlp]
command=${PYTHON} -m gunicorn -c ${ROOT_DIR}/config/otlp.conf.py src.otlp:app
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
for prog in llm-tracker-proxy llm-tracker-api llm-tracker-otlp; do
  status="$("${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" status "${prog}" 2>/dev/null | awk '{print $2}' || true)"
  case "${status}" in
    RUNNING)  pass "${prog}: running" ;;
    STARTING) pass "${prog}: starting" ;;
    *)        info "Starting ${prog}..."
              "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" start "${prog}"
              pass "${prog}: started" ;;
  esac
done

# ── Restart API if frontend is built ────────────────────────────────
if [[ -d "${ROOT_DIR}/frontend/dist" ]]; then
  "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" restart llm-tracker-api
  pass "llm-tracker-api: restarted (frontend available)"
fi

# ── Final status (only when run standalone) ─────────────────────────
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  API_PORT=$("${PYTHON}" -c "import yaml; from pathlib import Path; p = Path('${CONFIG_PATH}'); c = yaml.safe_load(p.read_text()) or {}; print(c.get('server', {}).get('api_port', c.get('server', {}).get('port', 4000) + 1))" 2>/dev/null || echo "4001")
  final_status_ok "http://127.0.0.1:${API_PORT}"
fi
