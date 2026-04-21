#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPERVISORD_CONF="${HOME}/.llm-tracker/supervisord.conf"
SUPERVISORCTL="${ROOT_DIR}/.venv/bin/supervisorctl"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Usage: scripts/stop.sh [program_name...]"
  echo
  echo "Arguments:"
  echo "  program_name    Optional. Specific supervisor program(s) to stop (e.g., llm-tracker-proxy)."
  echo "                  If omitted, stops all programs and shuts down supervisord."
  echo
  echo "Available programs:"
  echo "  llm-tracker-proxy, llm-tracker-api, llm-tracker-otlp"
  exit 0
fi

if [[ ! -f "${SUPERVISORD_CONF}" ]]; then
  echo "Not running." >&2
  exit 0
fi

if [[ $# -gt 0 ]]; then
  for prog in "$@"; do
    echo "==> Stopping ${prog}..."
    "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" stop "${prog}" || true
  done
else
  echo "==> Stopping all programs..."
  "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" stop all || true
  echo "==> Shutting down supervisord..."
  "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" shutdown || true
fi
