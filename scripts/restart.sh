#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="${HOME}/.llm-tracker"
CONFIG_PATH="${CONFIG_DIR}/config.yaml"
SUPERVISORD_CONF="${CONFIG_DIR}/supervisord.conf"
SUPERVISORCTL="${ROOT_DIR}/.venv/bin/supervisorctl"
PYTHON="${ROOT_DIR}/.venv/bin/python"
PORT_CHECKER="${ROOT_DIR}/scripts/check-service-ports.py"

# Verification: Check if environment is ready
if [[ ! -x "${PYTHON}" ]]; then
  echo "ERROR: Virtual environment not found. Please run 'scripts/install.sh' first."
  exit 1
fi

if [[ ! -L "${HOME}/.local/bin/llm-tracker" ]]; then
  echo "NOTE: 'llm-tracker' CLI symlink is missing. Run 'scripts/install.sh' to set it up."
fi

if [[ ! -f "${SUPERVISORD_CONF}" ]]; then
  echo "Not running. Run scripts/start.sh first." >&2
  exit 1
fi

"${PYTHON}" "${ROOT_DIR}/scripts/sync-config.py" "${CONFIG_PATH}" "${ROOT_DIR}/config.example.yaml"

OTLP_PORT=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --otlp-port)
      OTLP_PORT="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

PORT_CHANGED=false
if [[ -n "${OTLP_PORT}" ]]; then
  PORT_CHANGED=true
  echo "==> Updating OTLP port to ${OTLP_PORT} in ${CONFIG_PATH}..."
  "${PYTHON}" -c "
import yaml
from pathlib import Path
p = Path('${CONFIG_PATH}')
c = yaml.safe_load(p.read_text()) or {}
server = c.setdefault('server', {})
server['otlp_port'] = int('${OTLP_PORT}')
p.write_text(yaml.dump(c, sort_keys=False))
"
else
  # Read current port from config
  OTLP_PORT=$("${PYTHON}" -c "import yaml; from pathlib import Path; p = Path('${CONFIG_PATH}'); c = yaml.safe_load(p.read_text()) or {}; print(c.get('server', {}).get('otlp_port', 4002))" 2>/dev/null || echo "4002")
fi

if ! "${PYTHON}" "${PORT_CHECKER}" \
  --strict \
  --config "${CONFIG_PATH}" \
  --supervisorctl "${SUPERVISORCTL}" \
  --supervisord-conf "${SUPERVISORD_CONF}"; then
  exit 1
fi

# Update Codex OTLP telemetry if Codex is installed
CODEX_CONFIG="${HOME}/.codex/config.toml"
if [[ -f "${CODEX_CONFIG}" ]]; then
  "${PYTHON}" "${ROOT_DIR}/scripts/configure-codex-settings.py" "${CODEX_CONFIG}" "${OTLP_PORT}"
fi

# Refresh Gemini CLI hook and configure OTLP telemetry
bash "${ROOT_DIR}/scripts/setup-gemini.sh" "${OTLP_PORT}"

# Configure Claude Code telemetry if Claude is installed
if [[ -d "${HOME}/.claude" ]]; then
  "${PYTHON}" "${ROOT_DIR}/scripts/configure-claude-settings.py" "${HOME}/.claude/settings.json" "${OTLP_PORT}"
fi

echo "==> Applying schema migrations..."
"${PYTHON}" "${ROOT_DIR}/scripts/migrate_schema.py"

for prog in llm-tracker-proxy llm-tracker-api llm-tracker-otlp; do
  status="$("${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" status "${prog}" 2>/dev/null | awk '{print $2}' || true)"
  if [[ "${status}" == "RUNNING" ]]; then
    if [[ "${prog}" == "llm-tracker-otlp" && "${PORT_CHANGED}" == "true" ]]; then
      echo "==> Restarting ${prog} (port changed)..."
      "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" restart "${prog}"
    else
      echo "==> Sending SIGHUP to ${prog} (graceful reload)..."
      "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" signal HUP "${prog}"
    fi
  else
    echo "==> Starting ${prog} (was not running)..."
    "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" start "${prog}"
  fi
done
