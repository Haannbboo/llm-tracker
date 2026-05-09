[English](README.md) | [中文](README_CN.md)

# llm-tracker

**Local-first observability for command-line LLM agents.**

`llm-tracker` shows what your coding agents are doing: requests, token usage, cost estimates, latency, TTFT, models, sources, and session IDs across **Claude Code**, **Codex**, **Gemini CLI**, and OpenAI/Anthropic-compatible traffic.

It is built for people who run multiple LLM agents locally and want one place to answer:

- Which agent/model is spending the most?
- Did my last command actually get tracked?
- How much did this coding session cost?
- Which requests were slow, streamed, cached, or reasoning-heavy?

The default setup is local: config in `~/.llm-tracker/config.yaml`, usage data in SQLite at `~/.llm-tracker/usage.db`, and services bound to loopback ports.

## What it does

- **Tracks popular coding agents**: Claude Code, Codex, and Gemini CLI through local OTLP telemetry.
- **Tracks OpenAI/Anthropic-compatible clients**: route clients through the optional local proxy.
- **Shows a dashboard**: usage, cost, latency, models, sources, request logs, setup health, and first-event onboarding.
- **Prints command summaries**: run an agent through `llm-tracker` and get usage for that run.
- **Keeps setup inspectable**: plain YAML config, SQLite by default, logs in `logs/`, no hosted backend required.
- **Supports SQL databases**: keep SQLite locally or point `db.url` at PostgreSQL/MySQL through SQLAlchemy.

## How collection works

`llm-tracker` collects usage in two complementary ways:

```text
Claude Code / Codex / Gemini CLI
        │
        │ OTLP telemetry
        ▼
llm-tracker OTLP collector ──► database ──► dashboard / API / summaries
```

```text
OpenAI-compatible or Anthropic-compatible client
        │
        │ HTTP
        ▼
llm-tracker proxy ──► upstream provider
        │
        ▼
     database
```

Agent telemetry is best for agent-specific fields such as sessions and tool/reasoning metadata. The proxy is useful for clients that support custom base URLs.

## Quick start

### Prerequisites

- macOS or Linux shell environment
- Python 3.13, or `uv` so the installer can create it
- Node.js 18+ if you want the dashboard built and served
- Optional: `claude`, `codex`, or `gemini` installed locally

### 1. Bootstrap everything

```bash
bash scripts/bootstrap.sh
```

Bootstrap does the boring crap for you:

1. installs Python dependencies into `.venv`
2. builds the dashboard when Node/npm are available
3. creates `~/.llm-tracker/config.yaml` if needed
4. configures detected agents for local OTLP tracking
5. starts proxy, API, and OTLP services with Supervisor
6. verifies service ports and agent setup health
7. creates a CLI symlink at `~/.local/bin/llm-tracker`

If `~/.local/bin` is not on your `PATH`, the installer prints the shell command to add it.

### 2. Open the dashboard

```bash
open http://localhost:4001
```

If you prefer the Vite dev server while developing the frontend:

```bash
cd frontend
npm install
npm run dev
```

Then open [http://localhost:5173](http://localhost:5173).

### 3. Generate your first tracked event

After bootstrap, run one of the commands shown by the dashboard, or use one of these directly:

```bash
llm-tracker codex exec "hello"
llm-tracker claude
llm-tracker gemini -p "hello"
```

Repo-local fallback, useful before the symlink is on your `PATH`:

```bash
llm-tracker codex exec "hello"
llm-tracker claude
llm-tracker gemini -p "hello"
```

The empty dashboard automatically checks for your first event. No fake demo data, no manual seeding.

## CLI examples

The wrapper runs a child command, captures usage while it runs, then prints a summary.

```bash
# Interactive agents
llm-tracker codex
llm-tracker claude
llm-tracker gemini

# One-shot commands
llm-tracker codex exec "say hello in one sentence"
llm-tracker gemini -p "say hello in one sentence"

# Installed CLI
llm-tracker codex exec "say hello in one sentence"
```

Use `--` when passing flags to `llm-tracker` itself:

```bash
llm-tracker --json -- codex
llm-tracker --usage-only -- codex exec "say hello in one sentence"
llm-tracker --wait-ms 5000 -- codex exec "say hello in one sentence"
llm-tracker --summary-dest file --summary-file /tmp/llm-summary.json -- claude
llm-tracker --proxy-env -- some-openai-compatible-cli
llm-tracker --no-summary -- gemini -p "say hello"
```

See [docs/cli-reference.md](docs/cli-reference.md) for all flags, tracking modes, exit codes, service commands, API endpoints, and environment variables.

## Dashboard

The dashboard gives you:

- first-event onboarding when no data exists yet
- usage and cost overview
- model/source breakdowns
- latency and TTFT trends
- request logs
- detected agents and setup health
- connectivity testing

By default, the backend API serves the built dashboard at `http://localhost:4001`. The frontend dev server resolves the API URL in this order:

1. `LLM_TRACKER_API_URL`
2. `LLM_TRACKER_BACKEND_URL`
3. `~/.llm-tracker/config.yaml` using `server.host` and `server.api_port`
4. `http://localhost:4001`

Frontend-specific notes live in [frontend/README.md](frontend/README.md).

## Default local services

| Service | Default URL | Purpose |
| --- | --- | --- |
| Proxy | `http://127.0.0.1:4000` | OpenAI/Anthropic-compatible forwarding and usage capture |
| API + dashboard | `http://127.0.0.1:4001` | REST API and built dashboard |
| OTLP collector | `http://127.0.0.1:4002` | Local agent telemetry ingestion |

Service commands:

```bash
bash scripts/status.sh
bash scripts/restart.sh
bash scripts/stop.sh
```

Runtime files live under `~/.llm-tracker/run/`. Logs are written to `logs/`.

## Configuration

Main config:

```text
~/.llm-tracker/config.yaml
```

Minimal provider and database config:

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
  otlp_port: 4002

db:
  path: ~/.llm-tracker/usage.db
```

To use PostgreSQL or MySQL instead of SQLite, set `db.url`:

```yaml
db:
  url: postgresql+psycopg://user:password@db-host:5432/llm_tracker?sslmode=require
```

`bash scripts/start.sh` and `bash scripts/restart.sh` merge missing defaults from `config.example.yaml` into your user config without overwriting existing values.

## Point clients at the proxy

For OpenAI-compatible clients:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:4000/v1
```

For Anthropic-compatible clients:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:4000
```

Or let the wrapper set both for one child process:

```bash
llm-tracker --proxy-env -- some-openai-compatible-cli
```

Supported proxy paths include:

- `/v1/chat/completions`
- `/v1/responses`
- `/v1/messages`

For streamed responses, the proxy records TTFT as time until the first upstream chunk arrives.

## Tracking coverage

| Metric | Gemini CLI | Claude Code | Codex | Direct proxy |
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

TTFT is an operational signal, not a billing-grade metric. Each agent exposes different timing data.

## API

Useful local endpoints:

```bash
curl http://127.0.0.1:4001/usage?limit=20
curl http://127.0.0.1:4001/usage/summary
curl http://127.0.0.1:4001/usage/daily
curl http://127.0.0.1:4001/usage/high-watermark
curl http://127.0.0.1:4001/config
curl http://127.0.0.1:4001/local/setup-health
```

Query params for `/usage`: `limit`, `offset`, `provider`, `model`, `since`, `until`.

Query params for `/usage/daily`: `since`, `until`, `provider`, `model`, `granularity`, `tz_offset`.

## Development

Install/start backend services:

```bash
bash scripts/start.sh
```

Run backend tests:

```bash
./.venv/bin/python -m pytest -q
```

Run frontend tests and build:

```bash
cd frontend
npm test
npm run build
```

Maintainer-only bootstrap smoke test:

```bash
bash scripts/dev/smoke-bootstrap-container.sh
```

That check runs `scripts/bootstrap.sh` in a fresh Docker or Apple `container` environment. It is not part of normal user setup.

## Privacy and security notes

- `llm-tracker` is intended to run locally.
- Usage is stored in `~/.llm-tracker/usage.db` by default.
- If you configure `db.url`, usage data is written to that database instead.
- The proxy forwards auth headers unchanged.
- API keys are not managed by `llm-tracker`.
- OTLP payloads are emitted by the agents themselves; review agent telemetry settings if you need strict metadata control.

## Contributing

Issues and PRs are welcome. Good contributions usually include:

- a clear bug report or product problem
- a small, testable change
- backend tests with `pytest` when changing Python behavior
- frontend tests under `frontend/tests/` when changing dashboard behavior
- updated docs when commands, setup, or behavior changes

Please keep examples consistent: plain agent invocations should use `llm-tracker codex`, `llm-tracker claude`, or `llm-tracker gemini`; reserve `--` for cases where `llm-tracker` flags are present.

## License

MIT. See [LICENSE](LICENSE).
