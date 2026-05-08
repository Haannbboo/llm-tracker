[English](README.md) | [中文](README_CN.md)

# llm-tracker

Local-first usage tracking for command-line LLM agents.

`llm-tracker` records token usage, cost estimates, latency, TTFT, and session IDs for tools such as Codex, Claude Code, Gemini CLI, and OpenAI/Anthropic-compatible clients. It is designed for teams and side projects that want structured per-session usage data without rebuilding agent-specific tracking logic in every repo.

It can collect data in two ways:

- An OTLP collector receives telemetry emitted by coding agents.
- A transparent proxy forwards provider requests and records usage from responses.

Credentials are not managed by llm-tracker. API keys and authorization headers are forwarded unchanged when using the proxy.

## Features

- Tracks Codex, Claude Code, Gemini CLI, and direct proxy traffic.
- Preserves session IDs for per-run and per-agent summaries.
- Prints command-level summaries with `scripts/llm-tracker`.
- Supports SQLite by default and SQL databases through SQLAlchemy URLs.
- Estimates cost from model pricing in `~/.llm-tracker/config.yaml`.
- Includes a React dashboard for usage, cost, latency, and model trends.
- Keeps agent telemetry config in sync from `scripts/start.sh` and `scripts/restart.sh`.

## Quick Start

Prerequisites:

- macOS or Linux shell environment
- Python 3.13, or `uv` available so the startup script can create it
- Node.js 18+ for the optional dashboard

One-command local startup:

```bash
bash scripts/bootstrap.sh
```

Bootstrap calls `scripts/install.sh` (creates `.venv`, installs dependencies, sets up CLI symlink) then `scripts/start.sh` (creates config if needed, applies schema migrations, configures agent telemetry, starts services with Supervisor). It finishes with a health check on all service ports.

The dashboard still runs separately:

```bash
cd frontend
npm install
npm run dev
```

The dashboard is usually available at [http://localhost:5173](http://localhost:5173).

Default backend ports:

| Service | Default URL |
| --- | --- |
| Proxy | `http://127.0.0.1:4000` |
| API | `http://127.0.0.1:4001` |
| OTLP | `http://127.0.0.1:4002` |

Check service status:

```bash
bash scripts/status.sh
```

## Command Summaries

See [docs/cli-reference.md](docs/cli-reference.md) for the full CLI reference, including all flags, exit codes, tracking modes, and service management commands.

Use the repo-local wrapper to run an agent or command and print usage captured while it was running:

```bash
scripts/llm-tracker -- codex
scripts/llm-tracker -- claude
scripts/llm-tracker -- gemini
scripts/llm-tracker -- codex exec "say hello in one sentence"
```

Common options:

```bash
scripts/llm-tracker --json -- codex
scripts/llm-tracker --usage-only -- codex exec "say hello in one sentence"
scripts/llm-tracker --wait-ms 5000 -- codex exec "say hello in one sentence"
scripts/llm-tracker --summary-dest file --summary-file /tmp/llm-summary.json -- claude
scripts/llm-tracker --proxy-env -- some-openai-compatible-cli
scripts/llm-tracker --no-summary -- gemini -p "say hello"
```

With `--proxy-env`, the command is pointed at a temporary local proxy for the run, so proxy-recorded usage is isolated before it is merged into the main database.

By default, summaries are written to stderr so the child command's stdout stays usable. Use `--usage-only` when another program needs stdout to contain only the llm-tracker summary, and combine it with `--json` when that summary should be machine-readable JSON. The wrapper starts a temporary local OTLP collector for each command, records usage in a per-run SQLite database, then merges those rows back into the main configured database after the command exits.

## Configuration

Main config lives at:

```text
~/.llm-tracker/config.yaml
```

Minimal provider config:

```yaml
models:
  gpt-5.4:
    cost:
      input: 2.5
      output: 15.0
      cacheRead: 0.25

providers:
  my-provider:
    base_url: https://api.example.com/v1
    models:
      gpt-5.4: {}

server:
  host: 127.0.0.1
  port: 4000
  api_port: 4001

db:
  path: ~/.llm-tracker/usage.db
```

The proxy routes requests by matching the request `model` to a configured provider model, then forwards the request to that provider's `base_url`.

To use PostgreSQL or MySQL instead of SQLite, set `db.url`:

```yaml
db:
  url: postgresql+psycopg://user:password@db-host:5432/llm_tracker?sslmode=require
```

Running `bash scripts/start.sh` or `bash scripts/restart.sh` merges missing defaults from `config.example.yaml` into your user config without overwriting existing values.

## How Collection Works

### OTLP Collector

Codex, Claude Code, and Gemini CLI can emit OpenTelemetry logs. llm-tracker receives those logs locally and parses agent-specific fields that are not visible at the HTTP proxy layer.

```text
Agent telemetry
      |
      v
llm-tracker OTLP collector
      |
      v
SQLite/Postgres/MySQL
```

The startup scripts configure:

- `~/.codex/config.toml` for Codex OTLP logs
- `~/.claude/settings.json` for Claude Code OTLP logs
- `~/.gemini/settings.json` plus a shell hook for Gemini CLI timing data

### Transparent Proxy

For tools that support custom base URLs, llm-tracker can sit between the client and upstream provider:

```text
LLM client
      |
      v
llm-tracker proxy
      |
      v
Upstream provider
```

Supported proxy paths include:

- `/v1/chat/completions`
- `/v1/responses`
- `/v1/messages`

For streamed responses, the proxy records TTFT as the time until the first upstream chunk arrives.

## Pointing Clients At The Proxy

For OpenAI-compatible clients:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:4000/v1
```

For Anthropic-compatible clients:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:4000
```

The command wrapper can set these for a child process:

```bash
scripts/llm-tracker --proxy-env -- some-openai-compatible-cli
```

## Dashboard

The dashboard lives in `frontend/` and talks to the API service. It resolves the backend API URL in this order:

1. `LLM_TRACKER_API_URL`
2. `LLM_TRACKER_BACKEND_URL`
3. `~/.llm-tracker/config.yaml` using `server.host` and `server.api_port`
4. `http://localhost:4001`

See [frontend/README.md](frontend/README.md) for frontend-specific setup.

## Tracking Coverage

| Metric | Gemini CLI | Claude Code | Codex | Direct Proxy |
| --- | --- | --- | --- | --- |
| Input tokens | OTLP | OTLP | OTLP | Response usage |
| Output tokens | OTLP | OTLP | OTLP | Response usage |
| Cached tokens read | OTLP | OTLP | OTLP | Response usage |
| Cached tokens write | Not available | OTLP | Not available | Not available |
| Reasoning tokens | OTLP | Not available | OTLP | Response usage |
| Tool tokens | OTLP | Not available | OTLP | Not available |
| Prompt length | OTLP | OTLP | OTLP | Not available |
| Latency | Hook/OTLP | OTLP | OTLP | Proxy timing |
| TTFT | Hook | Not available | OTLP | Streaming only |
| Session ID | OTLP | OTLP | OTLP | Not available |

TTFT should be treated as an operational hint, not a billing-grade metric. Each agent exposes different timing data.

## API

Useful local endpoints:

```bash
curl http://127.0.0.1:4001/usage?limit=20
curl http://127.0.0.1:4001/usage/summary
curl http://127.0.0.1:4001/usage/daily
curl http://127.0.0.1:4001/usage/high-watermark
```

The dashboard uses the same API.

## Development

Install and start backend services:

```bash
bash scripts/start.sh
```

Run tests:

```bash
./.venv/bin/python -m pytest -q
```

Maintainer-only bootstrap smoke:

```bash
bash scripts/dev/smoke-bootstrap-container.sh
```

This opt-in check runs `scripts/bootstrap.sh` in a fresh Docker or Apple
`container` environment. It is not part of normal user setup.

Manage services:

```bash
bash scripts/restart.sh
bash scripts/stop.sh
bash scripts/status.sh
```

Logs are written to `logs/`. Supervisor runtime files live under `~/.llm-tracker/run/`.

## Privacy Notes

llm-tracker is intended to run locally. By default, usage is stored in `~/.llm-tracker/usage.db`. If you configure `db.url`, usage data is written to that database instead.

The proxy forwards auth headers unchanged. OTLP payloads are emitted by the agents themselves; review your agent telemetry settings if you need strict control over what metadata is collected.

## License

MIT. See [LICENSE](LICENSE).
