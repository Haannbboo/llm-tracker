#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPERVISORD_CONF="${HOME}/.llm-tracker/supervisord.conf"
SUPERVISORCTL="${ROOT_DIR}/.venv/bin/supervisorctl"
CONFIG_PATH="${HOME}/.llm-tracker/config.yaml"
PYTHON="${ROOT_DIR}/.venv/bin/python"
PORT_CHECKER="${ROOT_DIR}/scripts/check-service-ports.py"

if [[ ! -f "${SUPERVISORD_CONF}" ]]; then
  echo "Services are not configured or not running (missing supervisord.conf)." >&2
else
  echo "==> Service Status"
  if [[ $# -gt 0 ]]; then
    "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" status "$@"
  else
    "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" status
  fi
fi

if [[ -f "${CONFIG_PATH}" ]]; then
  echo
  echo "==> Port Information"
  # Extract ports using python to handle defaults consistently with the app
  "${PYTHON}" -c "
import yaml
import os
with open(os.path.expanduser('${CONFIG_PATH}')) as f:
    c = yaml.safe_load(f) or {}
s = c.get('server', {})
p = int(s.get('port', 4000))
a = int(s.get('api_port', p + 1))
o = int(s.get('otlp_port', a + 1))
h = s.get('host', '0.0.0.0')
print(f'  Proxy: {h}:{p}')
print(f'  API:   {h}:{a}')
print(f'  OTLP:  {h}:{o}')
"

  "${PYTHON}" "${PORT_CHECKER}" \
    --config "${CONFIG_PATH}" \
    --supervisorctl "${SUPERVISORCTL}" \
    --supervisord-conf "${SUPERVISORD_CONF}"
fi
