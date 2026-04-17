#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPERVISORD_CONF="${HOME}/.llm-tracker/supervisord.conf"
SUPERVISORCTL="${ROOT_DIR}/.venv/bin/supervisorctl"

if [[ ! -f "${SUPERVISORD_CONF}" ]]; then
  echo "Not running. Run scripts/start.sh first." >&2
  exit 1
fi

for prog in llm-tracker-proxy llm-tracker-api; do
  status="$("${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" status "${prog}" 2>/dev/null | awk '{print $2}' || true)"
  if [[ "${status}" == "RUNNING" ]]; then
    echo "==> Sending SIGHUP to ${prog} (graceful reload)..."
    "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" signal HUP "${prog}"
  else
    echo "==> Starting ${prog} (was not running)..."
    "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" start "${prog}"
  fi
done
