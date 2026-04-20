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

# Bootstrap uv
if ! command -v uv >/dev/null 2>&1; then
  echo "==> Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi

# Create venv
if [[ ! -x "${PYTHON}" ]]; then
  echo "==> Creating venv..."
  uv venv --python 3.13 "${VENV_DIR}"
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

# Configure Codex OTLP telemetry if Codex is installed
CODEX_CONFIG="${HOME}/.codex/config.toml"
if [[ -f "${CODEX_CONFIG}" ]] && ! grep -q "\[otel\]" "${CODEX_CONFIG}"; then
  cat >> "${CODEX_CONFIG}" << 'CODEX_EOF'

[otel]
environment = "dev"
exporter = { otlp-http = { endpoint = "http://localhost:4002/v1/logs", protocol = "json" } }
CODEX_EOF
  echo "==> Codex OTLP telemetry configured"
fi

# Install Gemini CLI hook and configure OTLP telemetry
bash "${ROOT_DIR}/scripts/setup-gemini.sh"

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
