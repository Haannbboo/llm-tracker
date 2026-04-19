#!/usr/bin/env bash
# Install Gemini CLI hook and configure OTLP telemetry in user settings (~/.gemini)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GEMINI_HOOK_DEST="${HOME}/.gemini/llm-tracker-hook.sh"

mkdir -p "${HOME}/.gemini"
cp "${ROOT_DIR}/scripts/gemini-hook.sh" "${GEMINI_HOOK_DEST}"
chmod +x "${GEMINI_HOOK_DEST}"
python3 "${ROOT_DIR}/scripts/configure-gemini-settings.py" \
  "${HOME}/.gemini/settings.json" \
  "${ROOT_DIR}/.gemini/settings.json" \
  "${GEMINI_HOOK_DEST}"
