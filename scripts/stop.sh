#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPERVISORD_CONF="${HOME}/.llm-tracker/supervisord.conf"
SUPERVISORCTL="${ROOT_DIR}/.venv/bin/supervisorctl"

if [[ ! -f "${SUPERVISORD_CONF}" ]]; then
  echo "Not running." >&2
  exit 0
fi

echo "==> Stopping programs..."
"${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" stop all || true
echo "==> Shutting down supervisord..."
"${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" shutdown || true
