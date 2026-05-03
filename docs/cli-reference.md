# llm-tracker CLI Reference

## Overview

The `llm-tracker` CLI wrapper runs an LLM agent (or any command), captures token usage while it runs, prints a summary, and merges the data into the main database. It works by starting a temporary OTLP collector per run, so usage is tracked even when the main services are down.

## Usage

```bash
scripts/llm-tracker [options] -- <command> [args...]
```

The `--` separator is optional when the first non-option argument is not a recognized flag.

## Examples

```bash
# Track an interactive Codex session
scripts/llm-tracker -- codex

# Track Claude Code
scripts/llm-tracker -- claude

# Track a single-shot Codex command
scripts/llm-tracker -- codex exec "say hello in one sentence"

# JSON summary
scripts/llm-tracker --json -- codex

# Machine-readable summary only (suppress child stdout/stderr)
scripts/llm-tracker --usage-only --json -- codex exec "hello"

# Write summary to a file
scripts/llm-tracker --summary-dest file --summary-file /tmp/llm-summary.json -- claude

# Route through a temporary local proxy
scripts/llm-tracker --proxy-env -- some-openai-compatible-cli

# Longer wait for late-arriving telemetry
scripts/llm-tracker --wait-ms 5000 -- codex exec "hello"

# No summary at all
scripts/llm-tracker --no-summary -- gemini -p "say hello"
```

## Flags

| Flag | Default | Description |
|---|---|---|
| `--json` | off | Output summary as a single-line JSON object. |
| `--usage-only` | off | Write only the summary to stdout; suppress child stdout/stderr. Cannot combine with `--no-summary`. |
| `--summary-dest` | `stderr` | Where to write the summary: `stdout`, `stderr`, or `file`. |
| `--summary-file` | (none) | Path for `--summary-dest file`. Required when using that mode. |
| `--wait-ms` | `3000` | Milliseconds to poll for usage data after the child exits. |
| `--poll-ms` | `250` | Milliseconds between poll attempts. |
| `--proxy-env` | off | Set `OPENAI_BASE_URL` and `ANTHROPIC_BASE_URL` for the child, pointing at a temporary local proxy. |
| `--no-summary` | off | Skip the summary; just run the command and return its exit code. |

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Child command succeeded. |
| 1 | General error (e.g., isolated service startup failure). |
| 2 | Argument validation error. |
| 126 | Child command is not executable. |
| 127 | Child command not found. |
| 128+N | Child killed by signal N. |
| Other | The child command's own exit code. |

## Tracking Modes

**Isolated mode** (default when the main API is not running, or when `--proxy-env` is set):

1. Creates a temporary SQLite database.
2. Starts a temporary OTLP collector (and optionally a temporary proxy) on random loopback ports.
3. Sets `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` for the child process.
4. Runs the child command.
5. Polls for usage data, stops temporary services, prints the summary.
6. Merges rows into the main database at `~/.llm-tracker/usage.db`.

**Watermark mode** (when the main API is already running):

1. Records the high-watermark usage ID.
2. Runs the child command.
3. Queries the API for usage records added since the watermark.
4. Prints the summary.

## Service Management

```bash
bash scripts/start.sh              # Full setup and start (venv, deps, config, migrations, supervisor)
bash scripts/restart.sh            # Graceful restart (config sync, migrations, SIGHUP reload)
bash scripts/restart.sh --otlp-port 5002  # Change OTLP port and restart
bash scripts/stop.sh               # Stop all services
bash scripts/stop.sh llm-tracker-proxy    # Stop a specific service
bash scripts/status.sh             # Show service status and port info
bash scripts/status.sh llm-tracker-api    # Status for a specific service
```

## Configuration

Located at `~/.llm-tracker/config.yaml`. A template is provided at `config.example.yaml`.

```yaml
models:
  gpt-5.4:
    cost:
      input: 2.5        # USD per million input tokens
      output: 15.0       # USD per million output tokens
      cacheRead: 0.25    # USD per million cached input tokens

providers:
  my-provider:
    base_url: https://api.example.com/v1
    models:
      gpt-5.4: {}

server:
  host: 127.0.0.1
  port: 4000        # Proxy port
  api_port: 4001    # API port
  otlp_port: 4002   # OTLP collector port

db:
  path: ~/.llm-tracker/usage.db   # SQLite (default)
  # url: postgresql+psycopg://user:pass@host:5432/db
```

Running `start.sh` or `restart.sh` automatically merges missing defaults from `config.example.yaml` into your config without overwriting existing values.

## Environment Variables

| Variable | Description |
|---|---|
| `LLM_TRACKER_HOME` | Override the tracker home directory (default `~/.llm-tracker`). |
| `LLM_TRACKER_CONFIG` | Override the config file path. |
| `LLM_TRACKER_DB_URL` | Override the database URL at runtime. |
| `LLM_TRACKER_API_URL` | Override the API base URL for the dashboard. |
| `OPENAI_BASE_URL` | Set by `--proxy-env` to route OpenAI-compatible clients through the proxy. |
| `ANTHROPIC_BASE_URL` | Set by `--proxy-env` to route Anthropic-compatible clients through the proxy. |
| `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` | Override the OTLP endpoint URL. |

## API Endpoints

The API service runs at `http://127.0.0.1:4001` by default.

```bash
curl http://127.0.0.1:4001/usage?limit=20
curl http://127.0.0.1:4001/usage/summary
curl http://127.0.0.1:4001/usage/daily
curl http://127.0.0.1:4001/usage/high-watermark
curl http://127.0.0.1:4001/config
```

Query params for `/usage`: `limit`, `offset`, `provider`, `model`, `since`, `until`.

Query params for `/usage/daily`: `since`, `until`, `provider`, `model`, `granularity`, `tz_offset`.

## Helper Scripts

| Script | Purpose |
|---|---|
| `scripts/sync-config.py` | Merge missing defaults into user config. |
| `scripts/migrate_schema.py` | Apply database schema migrations. |
| `scripts/check-service-ports.py` | Detect port conflicts before starting services. |
| `scripts/configure-claude-settings.py` | Configure Claude Code OTLP telemetry. |
| `scripts/configure-codex-settings.py` | Configure Codex OTLP telemetry. |
| `scripts/configure-gemini-settings.py` | Configure Gemini CLI OTLP telemetry and hooks. |
| `scripts/setup-gemini.sh` | Install Gemini CLI hook and configure telemetry. |
