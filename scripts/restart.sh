#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPERVISORD_CONF="${HOME}/.llm-tracker/supervisord.conf"
SUPERVISORCTL="${ROOT_DIR}/.venv/bin/supervisorctl"

if [[ ! -f "${SUPERVISORD_CONF}" ]]; then
  echo "Not running. Run scripts/start.sh first." >&2
  exit 1
fi

# Configure Gemini CLI OTLP telemetry if Gemini is installed
GEMINI_CONFIG="${HOME}/.gemini/settings.json"
if [[ -f "${GEMINI_CONFIG}" ]]; then
  python3 - "${GEMINI_CONFIG}" << 'PY_EOF'
import json, sys
path = sys.argv[1]
with open(path) as f:
    s = json.load(f)
desired = {"enabled": True, "target": "local", "otlpEndpoint": "http://localhost:4002", "otlpProtocol": "http"}
if s.get("telemetry") != desired:
    s["telemetry"] = desired
    with open(path, "w") as f:
        json.dump(s, f, indent=2)
    print("==> Gemini OTLP telemetry configured")
PY_EOF
fi

for prog in llm-tracker-proxy llm-tracker-api llm-tracker-otlp; do
  status="$("${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" status "${prog}" 2>/dev/null | awk '{print $2}' || true)"
  if [[ "${status}" == "RUNNING" ]]; then
    echo "==> Sending SIGHUP to ${prog} (graceful reload)..."
    "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" signal HUP "${prog}"
  else
    echo "==> Starting ${prog} (was not running)..."
    "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" start "${prog}"
  fi
done
