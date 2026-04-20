#!/usr/bin/env bash
# Install Gemini CLI hook and configure OTLP telemetry in user settings (~/.gemini)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GEMINI_HOOK_DEST="${HOME}/.gemini/llm-tracker-hook.sh"

mkdir -p "${HOME}/.gemini"
cp "${ROOT_DIR}/scripts/gemini-hook.sh" "${GEMINI_HOOK_DEST}"
chmod +x "${GEMINI_HOOK_DEST}"

OTLP_PORT="${1:-}"

if [[ -z "${OTLP_PORT}" ]]; then
  CONFIG_PATH="${HOME}/.llm-tracker/config.yaml"
  if [[ -f "${CONFIG_PATH}" ]]; then
    # Try to extract otlp_port from config.yaml using a simple grep/sed to avoid dependency on a specific python/yaml in this script
    # but since we have the venv, maybe we should use it?
    # Actually, let's just use a simple python command if available or default.
    PYTHON_CMD="python3"
    if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
      PYTHON_CMD="${ROOT_DIR}/.venv/bin/python"
    fi
    OTLP_PORT=$("${PYTHON_CMD}" -c "import yaml; from pathlib import Path; p = Path('${CONFIG_PATH}'); c = yaml.safe_load(p.read_text()) or {}; print(c.get('server', {}).get('otlp_port', ''))" 2>/dev/null || echo "")
  fi
fi

python3 "${ROOT_DIR}/scripts/configure-gemini-settings.py" \
  "${HOME}/.gemini/settings.json" \
  "${ROOT_DIR}/.gemini/settings.json" \
  "${GEMINI_HOOK_DEST}" \
  ${OTLP_PORT:+"${OTLP_PORT}"}
