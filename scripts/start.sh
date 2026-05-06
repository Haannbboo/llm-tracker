#!/usr/bin/env bash
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

# Verification: Check if environment is ready
if [[ ! -x "${PYTHON}" ]]; then
  echo "ERROR: Virtual environment not found. Please run 'scripts/install.sh' first."
  exit 1
fi

if [[ ! -L "${HOME}/.local/bin/llm-tracker" ]]; then
  echo "NOTE: 'llm-tracker' CLI symlink is missing. Run 'scripts/install.sh' to set it up."
fi

# Install deps when requirements.txt changes
CURRENT_HASH="$(shasum -a 256 "${ROOT_DIR}/requirements.txt" | awk '{print $1}')"
SAVED_HASH="$(cat "${REQS_STAMP}" 2>/dev/null || true)"
if [[ "${CURRENT_HASH}" != "${SAVED_HASH}" ]]; then
  echo "==> Installing dependencies..."
  uv pip install --python "${PYTHON}" -r "${ROOT_DIR}/requirements.txt"
  echo "${CURRENT_HASH}" > "${REQS_STAMP}"
else
  echo "==> Dependencies up to date"
fi

mkdir -p "${ROOT_DIR}/logs" "${RUNTIME_DIR}"

# Seed config without overwriting an existing user config.
if [[ -e "${CONFIG_PATH}" || -L "${CONFIG_PATH}" ]]; then
  echo "==> Config already exists at ${CONFIG_PATH}"
else
  cp "${ROOT_DIR}/config.example.yaml" "${CONFIG_PATH}"
  echo "==> Config created at ${CONFIG_PATH}"
fi

"${PYTHON}" "${ROOT_DIR}/scripts/sync-config.py" "${CONFIG_PATH}" "${ROOT_DIR}/config.example.yaml"

if ! "${PYTHON}" "${PORT_CHECKER}" \
  --strict \
  --config "${CONFIG_PATH}" \
  --supervisorctl "${SUPERVISORCTL}" \
  --supervisord-conf "${SUPERVISORD_CONF}"; then
  exit 1
fi

# Configure Codex OTLP telemetry if Codex is installed
OTLP_PORT=$("${PYTHON}" -c "import yaml; from pathlib import Path; p = Path('${CONFIG_PATH}'); c = yaml.safe_load(p.read_text()) or {}; print(c.get('server', {}).get('otlp_port', 4002))" 2>/dev/null || echo "4002")

CODEX_CONFIG="${HOME}/.codex/config.toml"
if [[ -f "${CODEX_CONFIG}" ]]; then
  "${PYTHON}" "${ROOT_DIR}/scripts/configure-codex-settings.py" "${CODEX_CONFIG}" "${OTLP_PORT}"
fi

# Install Gemini CLI hook and configure OTLP telemetry
bash "${ROOT_DIR}/scripts/setup-gemini.sh" "${OTLP_PORT}"

# Configure Claude Code telemetry if Claude is installed
CLAUDE_SETTINGS="${HOME}/.claude/settings.json"
if [[ -d "${HOME}/.claude" ]]; then
  "${PYTHON}" "${ROOT_DIR}/scripts/configure-claude-settings.py" "${CLAUDE_SETTINGS}" "${OTLP_PORT}"
fi

echo "==> Applying schema migrations..."
"${PYTHON}" "${ROOT_DIR}/scripts/migrate_schema.py"

# Generate supervisord.conf (references project gunicorn configs)
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

# Reuse existing supervisord if alive, otherwise start fresh
EXISTING_PID="$(cat "${SUPERVISORD_PID}" 2>/dev/null || true)"
if [[ -n "${EXISTING_PID}" ]] && kill -0 "${EXISTING_PID}" 2>/dev/null; then
  echo "==> Reloading existing supervisord (pid ${EXISTING_PID})..."
  "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" reread
  "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" update
  # update already starts/restarts programs with autostart=true; wait briefly then
  # start any that are still stopped (e.g. manually stopped before this run)
  sleep 1
else
  rm -f "${SOCKET_PATH}" "${SUPERVISORD_PID}"
  echo "==> Starting supervisord..."
  "${SUPERVISORD}" -c "${SUPERVISORD_CONF}"
  for _ in $(seq 10); do [[ -S "${SOCKET_PATH}" ]] && break; sleep 0.3; done
fi

# Start any programs not yet running (autostart handles most cases; this catches manually-stopped ones)
for prog in llm-tracker-proxy llm-tracker-api llm-tracker-otlp; do
  status="$("${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" status "${prog}" 2>/dev/null | awk '{print $2}' || true)"
  case "${status}" in
    RUNNING)  echo "==> ${prog}: running" ;;
    STARTING) echo "==> ${prog}: starting" ;;
    *)        echo "==> Starting ${prog}..."
              "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" start "${prog}" ;;
  esac
done
