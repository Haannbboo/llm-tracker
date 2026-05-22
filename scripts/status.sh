#!/usr/bin/env bash
# scripts/status.sh
# Show llm-tracker service status.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPERVISORD_CONF="${HOME}/.llm-tracker/supervisord.conf"
SUPERVISORCTL="${ROOT_DIR}/.venv/bin/supervisorctl"
CONFIG_PATH="${HOME}/.llm-tracker/config.yaml"
PYTHON="${ROOT_DIR}/.venv/bin/python"
PORT_CHECKER="${ROOT_DIR}/scripts/check-service-ports.py"

# ── Load terminal helpers ───────────────────────────────────────────
source "${ROOT_DIR}/scripts/lib/terminal.sh"

banner

if [[ ! -f "${SUPERVISORD_CONF}" ]]; then
  fail "Services not configured (missing supervisord.conf)"
  exit 1
fi

step_header "Service Status"
if [[ $# -gt 0 ]]; then
  "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" status "$@"
else
  "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" status
fi

if [[ -f "${CONFIG_PATH}" ]]; then
  step_header "Port Information"
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

  step_header "Port Check"
  "${PYTHON}" "${PORT_CHECKER}" \
    --config "${CONFIG_PATH}" \
    --supervisorctl "${SUPERVISORCTL}" \
    --supervisord-conf "${SUPERVISORD_CONF}"
fi
