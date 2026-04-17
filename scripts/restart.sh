#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${HOME}/.llm-tracker/config.yaml"
DEFAULT_PORT=4000

if [[ ! -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  echo "Missing virtualenv Python at ${ROOT_DIR}/.venv/bin/python" >&2
  exit 1
fi

read_port() {
  if [[ ! -f "${CONFIG_PATH}" ]]; then
    echo "${DEFAULT_PORT}"
    return
  fi

  "${ROOT_DIR}/.venv/bin/python" - <<'PY' "${CONFIG_PATH}" "${DEFAULT_PORT}"
import pathlib
import sys

import yaml

config_path = pathlib.Path(sys.argv[1]).expanduser()
default_port = sys.argv[2]

try:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
except Exception:
    print(default_port)
    raise SystemExit(0)

server = config.get("server") or {}
print(server.get("port", default_port))
PY
}

PORT="$(read_port)"

if pids="$(lsof -ti tcp:"${PORT}")" && [[ -n "${pids}" ]]; then
  echo "Stopping process on port ${PORT}: ${pids}"
  kill ${pids}
  sleep 1
fi

echo "Starting proxy on port ${PORT}"
cd "${ROOT_DIR}"
exec .venv/bin/python src/proxy.py
