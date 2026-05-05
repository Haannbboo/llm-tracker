#!/usr/bin/env bash
# Stop an isolated dev environment started by dev-start.sh.
# Usage: ./scripts/dev-stop.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_FILE="${ROOT_DIR}/.dev-env.json"

if [[ ! -f "${STATE_FILE}" ]]; then
  echo "==> No dev environment running (no .dev-env.json found)."
  exit 0
fi

api_pid=$(python3 -c "import json; print(json.load(open('${STATE_FILE}'))['api_pid'])" 2>/dev/null || echo "")
vite_pid=$(python3 -c "import json; print(json.load(open('${STATE_FILE}'))['vite_pid'])" 2>/dev/null || echo "")
work_dir=$(python3 -c "import json; print(json.load(open('${STATE_FILE}'))['work_dir'])" 2>/dev/null || echo "")

kill_pid() {
  local pid=$1
  local name=$2
  if [[ -z "${pid}" ]]; then return; fi
  if kill -0 "${pid}" 2>/dev/null; then
    echo "==> Stopping ${name} (pid ${pid})..."
    kill "${pid}" 2>/dev/null || true
    # Wait up to 5 seconds for graceful shutdown
    for _ in $(seq 10); do
      kill -0 "${pid}" 2>/dev/null || return 0
      sleep 0.5
    done
    kill -9 "${pid}" 2>/dev/null || true
  fi
}

kill_pid "${vite_pid}" "frontend"
kill_pid "${api_pid}" "API server"

if [[ -n "${work_dir}" && -d "${work_dir}" ]]; then
  rm -rf "${work_dir}"
  echo "==> Removed ${work_dir}"
fi

rm -f "${STATE_FILE}"
echo "==> Dev environment stopped."
