#!/usr/bin/env bash
set -e

CONFIG="${LLM_TRACKER_CONFIG:-/root/.llm-tracker/config.yaml}"

# Copy default config if none is mounted
if [ ! -f "$CONFIG" ]; then
    cp /app/config.example.yaml "$CONFIG"
    echo "Created default config at $CONFIG"
fi

# Ensure host is 0.0.0.0 for Docker networking
python3 -c "
import sys, yaml
path = sys.argv[1]
with open(path) as f:
    cfg = yaml.safe_load(f) or {}
server = cfg.setdefault('server', {})
changed = False
if server.get('host') == '127.0.0.1':
    server['host'] = '0.0.0.0'
    changed = True
if server.get('otlp_host') == '127.0.0.1':
    server['otlp_host'] = '0.0.0.0'
    changed = True
if changed:
    with open(path, 'w') as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)
    print('Patched server host to 0.0.0.0 for Docker networking')
" "$CONFIG"

# Run schema migrations
python scripts/migrate_schema.py || echo "Migration skipped or failed (non-fatal)"

# Sync config defaults
python scripts/sync-config.py "$CONFIG" config.example.yaml || true

exec supervisord -n -c /etc/supervisor/supervisord.conf
