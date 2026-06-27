#!/usr/bin/env bash
# Install Gemini CLI hook and configure OTLP telemetry in user settings (~/.gemini)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GEMINI_HOOK_DEST="${HOME}/.gemini/llm-tracker-hook.sh"

mkdir -p "${HOME}/.gemini"
cp "${ROOT_DIR}/scripts/gemini-hook.sh" "${GEMINI_HOOK_DEST}"
chmod +x "${GEMINI_HOOK_DEST}"

OTLP_PORT="${1:-}"
OTLP_HOST="${2:-}"

if [[ -z "${OTLP_PORT}" ]]; then
  CONFIG_PATH="${HOME}/.llm-tracker/config.yaml"
  if [[ -f "${CONFIG_PATH}" ]]; then
    PYTHON_CMD="python3"
    if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
      PYTHON_CMD="${ROOT_DIR}/.venv/bin/python"
    fi
    OTLP_PORT=$("${PYTHON_CMD}" -c "import yaml; from pathlib import Path; p = Path('${CONFIG_PATH}'); c = yaml.safe_load(p.read_text()) or {}; print(c.get('server', {}).get('otlp_port', ''))" 2>/dev/null || echo "")
  fi
fi

if [[ -z "${OTLP_HOST}" ]]; then
  CONFIG_PATH="${HOME}/.llm-tracker/config.yaml"
  if [[ -f "${CONFIG_PATH}" ]]; then
    PYTHON_CMD="python3"
    if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
      PYTHON_CMD="${ROOT_DIR}/.venv/bin/python"
    fi
    OTLP_HOST=$("${PYTHON_CMD}" -c "
import yaml
from pathlib import Path
from urllib.parse import urlparse
c = yaml.safe_load(Path('${CONFIG_PATH}').read_text()) or {}
base = c.get('server', {}).get('base_url')
if base:
    parsed = urlparse(base)
    print(parsed.hostname or 'localhost')
else:
    print('localhost')
" 2>/dev/null || echo "localhost")
  fi
fi

python3 "${ROOT_DIR}/scripts/configure-gemini-settings.py" \
  "${HOME}/.gemini/settings.json" \
  "${ROOT_DIR}/.gemini/settings.json" \
  "${GEMINI_HOOK_DEST}" \
  ${OTLP_PORT:+"${OTLP_PORT}"} \
  ${OTLP_HOST:+"${OTLP_HOST}"}
