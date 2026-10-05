#!/usr/bin/env bash
# scripts/restart.sh
# Reload the running tokenage services so new backend code takes effect.
#
# Deliberately narrow: no dependency install, no frontend build, no config sync,
# no port check, and it never starts a service that is already down. Use
# scripts/start.sh to turn services on and scripts/bootstrap.sh to install or
# build. Migrations do run here, because `git pull && restart` against an old
# schema would serve broken code.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="${HOME}/.tokenage"
CONFIG_PATH="${CONFIG_DIR}/config.yaml"
SUPERVISORD_CONF="${CONFIG_DIR}/supervisord.conf"
SUPERVISORCTL="${ROOT_DIR}/.venv/bin/supervisorctl"
PYTHON="${ROOT_DIR}/.venv/bin/python"

# ── Load terminal helpers ───────────────────────────────────────────
source "${ROOT_DIR}/scripts/lib/terminal.sh"

# ── Banner ──────────────────────────────────────────────────────────
banner

# ── Pre-checks ──────────────────────────────────────────────────────
step_header "Pre-flight checks"

if [[ ! -x "${PYTHON}" ]]; then
  fail "Virtual environment not found — run tokenage server bootstrap"
  exit 1
fi

if [[ ! -f "${SUPERVISORD_CONF}" ]]; then
  fail "Not running — run tokenage server start"
  exit 1
fi

# ── Parse args ──────────────────────────────────────────────────────
OTLP_PORT=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --otlp-port)
      if [[ $# -lt 2 ]]; then
        fail "Missing value for --otlp-port"
        exit 1
      fi
      if ! [[ "$2" =~ ^[0-9]+$ ]] || (( $2 < 1 || $2 > 65535 )); then
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

# An OTEL endpoint override wins over server.otlp_port at bind time
# (resolve_otlp_host_port), so --otlp-port would be saved but never take effect.
if [[ -n "${OTLP_PORT}" && -n "${OTEL_EXPORTER_OTLP_LOGS_ENDPOINT:-}" ]]; then
  if "${PYTHON}" - "${OTEL_EXPORTER_OTLP_LOGS_ENDPOINT}" <<'PY'
import sys
from urllib.parse import urlparse

parsed = urlparse(sys.argv[1])
raise SystemExit(0 if parsed.hostname and parsed.port else 1)
PY
  then
    fail "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT is set, so the collector keeps binding to it and --otlp-port would not take effect. Unset the endpoint (and restart supervisord) or bake the port into the endpoint."
    exit 1
  fi
fi

# ── Schema migrations ───────────────────────────────────────────────
# The one thing a reload must not skip: new code against an old schema.
step_header "Applying schema migrations"
"${PYTHON}" "${ROOT_DIR}/scripts/migrate_schema.py"
pass "Migrations applied"

# Keep the configured collector endpoint in sync with the port baked into the
# OTLP process. Pass paths and values as argv instead of interpolating them into
# Python source.
if [[ -n "$OTLP_PORT" ]]; then
  step_header "Persisting OTLP port"
  "${PYTHON}" - "${CONFIG_PATH}" "${OTLP_PORT}" <<'PY'
import sys
from pathlib import Path

import yaml

config_path = Path(sys.argv[1]).expanduser()
port = int(sys.argv[2])
config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
if not isinstance(config, dict):
    raise SystemExit("config.yaml must contain a mapping")
server = config.setdefault("server", {})
if not isinstance(server, dict):
    raise SystemExit("config.yaml server section must be a mapping")
server["otlp_port"] = port
config_path.write_text(
    yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8"
)
PY
  pass "OTLP port saved as ${OTLP_PORT}"
fi

# ── Reload services ─────────────────────────────────────────────────
step_header "Reloading services"

STOPPED=()
for prog in tokenage-proxy tokenage-api tokenage-otlp; do
  status="$("${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" status "${prog}" 2>/dev/null | awk '{print $2}' || true)"
  if [[ "$status" != "RUNNING" ]]; then
    STOPPED+=("$prog")
    continue
  fi
  if [[ "$prog" == "tokenage-otlp" && -n "$OTLP_PORT" ]]; then
    # The port is baked into the process, so a port change is a restart.
    info "Restarting ${prog} (port changed to ${OTLP_PORT})..."
    "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" restart "${prog}"
    pass "${prog}: restarted"
  else
    info "Sending SIGHUP to ${prog}..."
    "${SUPERVISORCTL}" -c "${SUPERVISORD_CONF}" signal HUP "${prog}"
    pass "${prog}: reloaded"
  fi
done

if [[ ${#STOPPED[@]} -gt 0 ]]; then
  # Restart does not turn services on. Say which ones, and how.
  for prog in "${STOPPED[@]}"; do
    info "${prog}: not running, left stopped"
  done
  info "run tokenage server start to bring them up"
fi

# ── Final status ────────────────────────────────────────────────────
_otlp_line="$("${PYTHON}" "${ROOT_DIR}/scripts/read-otlp-config.py" "${CONFIG_PATH}" 2>/dev/null || echo "4002 localhost")"
OTLP_HOST="${_otlp_line#* }"
API_PORT="$("${PYTHON}" -c 'import sys, yaml; from pathlib import Path; p = Path(sys.argv[1]); c = yaml.safe_load(p.read_text()) or {}; s = c.get("server", {}); print(s.get("api_port", s.get("port", 4000) + 1))' "${CONFIG_PATH}" 2>/dev/null || echo "4001")"

final_status_ok "http://${OTLP_HOST}:${API_PORT}"
