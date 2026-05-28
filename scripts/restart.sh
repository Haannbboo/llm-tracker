#!/usr/bin/env bash
# scripts/restart.sh
# Graceful restart of llm-tracker services.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="${HOME}/.llm-tracker"
CONFIG_PATH="${CONFIG_DIR}/config.yaml"
SUPERVISORD_CONF="${CONFIG_DIR}/supervisord.conf"
SUPERVISORCTL="${ROOT_DIR}/.venv/bin/supervisorctl"
PYTHON="${ROOT_DIR}/.venv/bin/python"
PORT_CHECKER="${ROOT_DIR}/scripts/check-service-ports.py"

# ── Load terminal helpers ───────────────────────────────────────────
source "${ROOT_DIR}/scripts/lib/terminal.sh"

# ── Banner ──────────────────────────────────────────────────────────
banner

# ── Pre-checks ──────────────────────────────────────────────────────
step_header "Pre-flight checks"

if [[ ! -x "${PYTHON}" ]]; then
  fail "Virtual environment not found — run scripts/bootstrap.sh first"
  exit 1
fi
pass "Python: ${PYTHON}"

if [[ ! -L "${HOME}/.local/bin/llm-tracker" ]]; then
  info "NOTE: CLI symlink missing — run scripts/bootstrap.sh to set it up"
fi

if [[ ! -f "${SUPERVISORD_CONF}" ]]; then
  fail "Not running — run scripts/start.sh first"
  exit 1
fi
pass "Supervisord config: ${SUPERVISORD_CONF}"

# ── Sync config ─────────────────────────────────────────────────────
step_header "Syncing config"
"${PYTHON}" "${ROOT_DIR}/scripts/sync-config.py" "${CONFIG_PATH}" "${ROOT_DIR}/config.example.yaml"
pass "Config synced"

# ── Parse args ──────────────────────────────────────────────────────
OTLP_PORT=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --otlp-port)
      if [[ $# -lt 2 ]]; then
        fail "Missing value for --otlp-port"
        exit 1
      fi
      if [[ ! "$2" =~ ^[0-9]+$ ]] || (( $2 < 1 || $2 > 65535 )); then
        fail "Invalid --otlp-port: $2 (expected 1-65535)"
        exit 1
      fi
      OTLP_PORT="$2"
      shift 2
      ;;
    *)
      fail "Unknown argument: $1"
      exit 1
      ;;
  esac
done

PORT_CHANGED=false
if [[ -n "${OTLP_PORT}" ]]; then
  PORT_CHANGED=true
  info "Updating OTLP port to ${OTLP_PORT}..."
  "${PYTHON}" -c "
import yaml
from pathlib import Path
p = Path('${CONFIG_PATH}')
c = yaml.safe_load(p.read_text()) or {}
server = c.setdefault('server', {})
server['otlp_port'] = int('${OTLP_PORT}')
p.write_text(yaml.dump(c, sort_keys=False))
"
  pass "OTLP port updated: ${OTLP_PORT}"
else
  OTLP_PORT=$("${PYTHON}" -c "import yaml; from pathlib import Path; p = Path('${CONFIG_PATH}'); c = yaml.safe_load(p.read_text()) or {}; print(c.get('server', {}).get('otlp_port', 4002))" 2>/dev/null || echo "4002")
  info "OTLP port: ${OTLP_PORT}"
fi

# ── Port check ──────────────────────────────────────────────────────
step_header "Checking ports"
if "${PYTHON}" "${PORT_CHECKER}" \
  --strict \
  --config "${CONFIG_PATH}" \
  --supervisorctl "${SUPERVISORCTL}" \
  --supervisord-conf "${SUPERVISORD_CONF}"; then
  pass "Port check passed"
else
  fail "Port check failed"
  exit 1
fi

# ── Configure agent OTLP telemetry ──────────────────────────────────
step_header "Configuring agent telemetry"

if command -v codex >/dev/null 2>&1; then
  CODEX_CONFIG="${HOME}/.codex/config.toml"
  "${PYTHON}" "${ROOT_DIR}/scripts/configure-codex-settings.py" "${CODEX_CONFIG}" "${OTLP_PORT}"
  pass "Codex configured"
else
  info "Codex: not installed, skipped"
fi

if command -v gemini >/dev/null 2>&1; then
  bash "${ROOT_DIR}/scripts/setup-gemini.sh" "${OTLP_PORT}"
  pass "Gemini configured"
else
  info "Gemini: not installed, skipped"
fi

if command -v claude >/dev/null 2>&1; then
  "${PYTHON}" "${ROOT_DIR}/scripts/configure-claude-settings.py" "${HOME}/.claude/settings.json" "${OTLP_PORT}"
  pass "Claude configured"
else
  info "Claude: not installed, skipped"
fi

if command -v opencode >/dev/null 2>&1; then
  "${PYTHON}" "${ROOT_DIR}/scripts/configure-opencode-plugin.py" "${ROOT_DIR}" "${OTLP_PORT}"
  pass "OpenCode configured"
else
  info "OpenCode: not installed, skipped"
fi

if command -v kilo >/dev/null 2>&1; then
  "${PYTHON}" "${ROOT_DIR}/scripts/configure-kilo-plugin.py" "${ROOT_DIR}" "${OTLP_PORT}"
  pass "Kilo Code configured"
else
  info "Kilo Code: not installed, skipped"
fi

# ── Schema migrations ───────────────────────────────────────────────
step_header "Applying schema migrations"
"${PYTHON}" "${ROOT_DIR}/scripts/migrate_schema.py"
pass "Migrations applied"

# ── Restart services ────────────────────────────────────────────────
step_header "Restarting services"

for prog in llm-tracker-proxy llm-tracker-api llm-tracker-otlp; do
  status="$("${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" status "${prog}" 2>/dev/null | awk '{print $2}' || true)"
  if [[ "${status}" == "RUNNING" ]]; then
    if [[ "${prog}" == "llm-tracker-otlp" && "${PORT_CHANGED}" == "true" ]]; then
      info "Restarting ${prog} (port changed)..."
      "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" restart "${prog}"
      pass "${prog}: restarted"
    else
      info "Sending SIGHUP to ${prog}..."
      "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" signal HUP "${prog}"
      pass "${prog}: reloaded"
    fi
  else
    info "Starting ${prog} (was not running)..."
    "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" start "${prog}"
    pass "${prog}: started"
  fi
done

# ── Read API port for final status ──────────────────────────────────
API_PORT=$("${PYTHON}" -c "import yaml; from pathlib import Path; p = Path('${CONFIG_PATH}'); c = yaml.safe_load(p.read_text()) or {}; print(c.get('server', {}).get('api_port', c.get('server', {}).get('port', 4000) + 1))" 2>/dev/null || echo "4001")

# ── Final status ────────────────────────────────────────────────────
final_status_ok "http://127.0.0.1:${API_PORT}"
