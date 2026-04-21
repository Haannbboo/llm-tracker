# llm-tracker

A transparent proxy for LLM providers with usage logging. It does not inspect, modify, or manage credentials: authorization headers such as `ANTHROPIC_AUTH_TOKEN`, `Authorization`, and `x-api-key` are forwarded unchanged. The proxy reads request metadata needed for routing and logging, may normalize provider-prefixed model names before forwarding, and records usage in the configured database.

## How it works

```
Claude Code / Codex
    │  (your real API key in headers, your model in body)
    ▼
llm-tracker proxy  ←── reads `model` field to know which base_url to forward to
    │  (credentials unchanged, body forwarded except provider-prefix normalization)
    ▼
Upstream provider (Anthropic, OpenAI, VectorEngine, MiniMax, ...)
```

The proxy never touches your credentials. `ANTHROPIC_AUTH_TOKEN` / `Authorization` / `x-api-key` pass through exactly as sent by the client.

## Features

- Supports `/v1/chat/completions`, `/v1/responses`, and `/v1/messages` (Anthropic)
- Logs prompt, completion, reasoning, cached, cache creation, tool, latency, and TTFT fields where available
- SQLite storage by default, with PostgreSQL/MySQL support via SQLAlchemy
- Usage API endpoints for recent rows, summaries, counts, daily/hourly aggregation, and config editing

## Setup

```bash
bash scripts/start.sh
```

This bootstraps `uv` if needed, creates `.venv`, installs `requirements.txt`, ensures `~/.llm-tracker/config.yaml` exists, and starts the proxy, API, and OTLP services under Supervisor.
It also configures Codex OTLP telemetry when `~/.codex/config.toml` exists, installs the Gemini hook at `~/.gemini/llm-tracker-hook.sh`, and writes Gemini telemetry plus `BeforeModel`/`AfterModel` hooks to `~/.gemini/settings.json`. Project-local Gemini llm-tracker hooks are removed to avoid duplicate telemetry.

## Configuration

Copy the example config to `~/.llm-tracker/config.yaml`:

```bash
mkdir -p ~/.llm-tracker
cp config.example.yaml ~/.llm-tracker/config.yaml
```

```yaml
providers:
  my-provider:
    base_url: https://api.example.com/v1
    models:
      - model-name-a
      - model-name-b
```

`base_url` is the only required field per provider — no `api_key` needed. The proxy routes by matching the `model` field in the request body to a provider, then forwards to that provider's `base_url`.

## Backend Database

By default, usage is stored in local SQLite:

```yaml
db:
  path: ~/.llm-tracker/usage.db
```

To switch to PostgreSQL or MySQL, replace `db.path` with `db.url` in `~/.llm-tracker/config.yaml`:

```yaml
db:
  url: postgresql+psycopg://user:password@db-host:5432/llm_tracker?sslmode=require
```

```yaml
db:
  url: mysql+pymysql://user:password@db-host:3306/llm_tracker
```

Then restart the services:

```bash
bash scripts/restart.sh
```

The app creates the `usage` table automatically if it does not exist.

### Migrating Existing SQLite Data

If you already have local SQLite history, migrate it once after setting `db.url`:

```bash
uv run python scripts/migrate_usage.py --source-url sqlite:///$HOME/.llm-tracker/usage.db
```

The migration target defaults to `db.url` from `~/.llm-tracker/config.yaml`. The script refuses to write into a non-empty target by default. To safely re-run a migration and skip rows that already exist by `id`, use:

```bash
uv run python scripts/migrate_usage.py \
  --source-url sqlite:///$HOME/.llm-tracker/usage.db \
  --allow-nonempty-target \
  --skip-existing
```

Passwords in database URLs must be URL-encoded if they contain reserved characters such as `@`, `:`, `/`, `#`, or `?`.

## Running

The project is split into three managed services:

- **Proxy**: routes provider requests and logs direct proxy usage on port `4000` by default.
- **API**: serves usage stats and config editing endpoints on port `4001` by default.
- **OTLP**: receives telemetry logs from Codex, Gemini CLI, and Claude Code on port `4002` by default.

**Start all services under Supervisor:**
```bash
bash scripts/start.sh
```

**Reload all services:**
```bash
bash scripts/restart.sh
```
This refreshes Gemini telemetry setup and sends `SIGHUP` to the managed proxy, API, and OTLP processes through Supervisor.

**Stop all services:**
```bash
bash scripts/stop.sh
```

**Inspect process status:**
```bash
uv run --with supervisor supervisorctl -c ~/.llm-tracker/supervisord.conf status
```

Supervisor runtime files live under `~/.llm-tracker/run/`, and `scripts/start.sh` regenerates the Supervisor config at `~/.llm-tracker/supervisord.conf`. Logs remain in the repo `logs/` directory.

## Pointing agents at the proxy

Set the base URL to the proxy. Your real API key stays in the client — the proxy forwards it unchanged.

**Claude Code:**
```bash
export ANTHROPIC_BASE_URL=http://localhost:4000
export ANTHROPIC_MODEL=claude-sonnet-4-5  # must match a model name in config
# ANTHROPIC_API_KEY stays as-is — forwarded transparently
```

**Codex** (`~/.codex/config.toml`):
```toml
[model_providers.my-provider]
base_url = "http://localhost:4000/v1"
```

## Frontend dev server

The Vite frontend proxies `/usage` requests to the API server, not the proxy server.

```bash
cd frontend
LLM_TRACKER_API_URL=http://localhost:4001 npm run dev
```

If `LLM_TRACKER_API_URL` is unset, the frontend defaults to `http://localhost:4001`.

## Testing

Run tests through Python so the repository root is on the import path:

```bash
uv run python -m pytest
```

## Usage API

The Usage API now runs on its own port (default `4001`):

```bash
# Recent requests
curl http://localhost:4001/usage

# Totals grouped by provider/model
curl http://localhost:4001/usage/summary

# Total row count, with optional filters
curl http://localhost:4001/usage/count

# Daily or hourly aggregate data
curl "http://localhost:4001/usage/daily?granularity=day"

# Read the active config
curl http://localhost:4001/config
```

## Logged fields

| Field | Description |
|---|---|
| `ts` | UTC timestamp |
| `provider` | Provider name from config |
| `model` | Model name |
| `endpoint` | Proxy endpoint such as `/v1/chat/completions`, `/v1/responses`, `/v1/messages`, or OTLP endpoint marker `generate-otlp` |
| `prompt_tokens` | Input tokens |
| `completion_tokens` | Output tokens |
| `reasoning_tokens` | Reasoning tokens (from output details) |
| `cached_tokens` | Cache hits (from input details) |
| `total_tokens` | Total tokens |
| `latency_ms` | End-to-end latency when available |
| `ttft_ms` | Time to first token when available |
| `tool_tokens` | Tool-use tokens when reported by the integration |
| `cache_creation_tokens` | Cache write tokens when reported by the integration |
| `status` | HTTP status code |

## Tracking Status

The following table shows which metrics are currently captured for each integration:

| Metric | Gemini CLI | Claude Code | Codex | Direct Proxy |
| :--- | :---: | :---: | :---: | :---: |
| Input Tokens | ✅ | ✅ | ✅ | ✅ |
| Output Tokens | ✅ | ✅ | ✅ | ✅ |
| Cached Tokens (Read) | ✅ | ✅ | ✅ | ✅ |
| Cached Tokens (Write) | ❌ | ✅ | ❌ | ❌ |
| Reasoning Tokens | ✅ | ❌ | ✅ | ✅ |
| Tool Tokens | ✅ | ❌ | ✅ | ❌ |
| Latency | ✅ | ✅ | ✅ | ✅ |
| TTFT (time to first token) | ✅ (Hook) | ❌ | ✅ (OTLP) | ❌ |


*Note: Gemini CLI captures TTFT via a shell hook (time from request sent to first streaming chunk) because its OTLP payload lacks a first-chunk timestamp. Codex captures true TTFT natively via OTLP. Claude Code has no BeforeModel/AfterModel hook equivalents, so TTFT is unavailable.*
