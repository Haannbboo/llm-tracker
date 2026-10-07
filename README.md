[English](README.md) | [中文](README_CN.md)

# tokenage

**Local-first observability for command-line LLM agents.**

`tokenage` shows what your coding agents are doing: requests, token usage, cost estimates, latency, TTFT, models, sources, and session IDs across **Claude Code**, **Codex**, **OpenCode**, **Kilo Code**, and OpenAI/Anthropic-compatible traffic.

It is built for people who run multiple LLM agents locally and want one place to answer:

- Which agent/model is spending the most?
- Did my last command actually get tracked?
- How much did this coding session cost?
- Which requests were slow, streamed, cached, or reasoning-heavy?

The default setup is local: config in `~/.tokenage/config.yaml`, usage data in SQLite at `~/.tokenage/usage.db`, and services bound to loopback ports.

## What it does

- **Tracks popular coding agents**: Claude Code, Codex, OpenCode, and Kilo Code through local OTLP telemetry.
- **Tracks OpenAI/Anthropic-compatible clients**: route clients through the optional local proxy.
- **Shows a dashboard**: usage, cost, latency, models, sources, request logs, setup health, and first-event onboarding.
- **Prints command summaries**: run an agent through `tokenage` and get usage for that run.
- **Keeps setup inspectable**: plain YAML config, SQLite by default, logs in `logs/`, no hosted backend required.
- **Supports SQL databases**: keep SQLite locally or point `db.url` at PostgreSQL/MySQL through SQLAlchemy.

## How collection works

`tokenage` collects usage in two complementary ways:

```text
Claude Code / Codex / OpenCode / Kilo Code
        │
        │ OTLP telemetry
        ▼
tokenage OTLP collector ──► database ──► dashboard / API / summaries
```

```text
OpenAI-compatible or Anthropic-compatible client
        │
        │ HTTP
        ▼
tokenage proxy ──► upstream provider
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
- Optional: `claude`, `codex`, `opencode`, or `kilo` installed locally

### 1. Bootstrap everything

```bash
bash scripts/bootstrap.sh
```

Bootstrap does the boring crap for you:

1. installs Python dependencies into `.venv`
2. builds the dashboard when Node/npm are available
3. creates a CLI symlink at `~/.local/bin/tokenage`
4. creates `~/.tokenage/config.yaml` if needed
5. starts proxy, API, and OTLP services with Supervisor
6. verifies service ports, the dashboard, and agent setup health
7. restarts the API so the freshly built dashboard is served

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

### 3. Point your agents at the collector

Bootstrap reports agent setup health but does not configure agents any more. That
is the client's job:

```bash
tokenage setup
```

It points the agents installed on this machine at the local OTLP collector, and
leaves every setting it does not own alone. `tokenage setup --disable` takes
them back off again. `tokenage status` shows what is installed, whether it
runs, and where the agents point.

### 4. Generate your first tracked event

After bootstrap, run one of the commands shown by the dashboard, or use one of these directly:

```bash
tokenage codex exec "hello"
tokenage claude
```

Repo-local fallback, useful before the symlink is on your `PATH`:

```bash
./scripts/tokenage codex exec "hello"
./scripts/tokenage claude
```

The empty dashboard automatically checks for your first event. No fake demo data, no manual seeding.

## Docker deployment

Run all three servers in a single container for NAS or remote server deployment. See [docker/README.md](docker/README.md).

## CLI examples

The wrapper runs a child command, captures usage while it runs, then prints a summary. It reports to the collector that is already running: it never starts a service, never spins up a temporary database or collector, and never merges anything afterwards. If the collector is not reachable the child still runs, untracked, and the exit code is still the child's.

```bash
# Interactive agents
tokenage codex
tokenage claude

# One-shot commands
tokenage codex exec "say hello in one sentence"

# Installed CLI
tokenage codex exec "say hello in one sentence"
```

The same command also covers everything that is not a tracked run:

```bash
# Components, services, agents
tokenage status
tokenage setup
tokenage update --check

# The local server needs no Google account: its dashboard and `tokenage login`
# work from the server machine; for a browser on another machine, run
# `tokenage server login-link` on the server and open the URL it prints.
# A remote server instead of a local one
tokenage login --server https://app.example.com
tokenage logout
```

Use `--` when passing flags to `tokenage` itself:

```bash
tokenage --json -- codex
tokenage --usage-only -- codex exec "say hello in one sentence"
tokenage --wait-ms 5000 -- codex exec "say hello in one sentence"
tokenage --summary-dest file --summary-file /tmp/llm-summary.json -- claude
tokenage --proxy-env -- some-openai-compatible-cli
tokenage --no-summary -- codex exec "say hello"
```

See [docs/cli-reference.md](docs/cli-reference.md) for all flags, the tracking model, exit codes, service commands, API endpoints, and environment variables. Per-command behavior is in [docs/cli-refactor.md](docs/cli-refactor.md).

## Dashboard

The dashboard gives you:

- first-event onboarding when no data exists yet
- usage and cost overview
- model/source breakdowns
- latency and TTFT trends
- request logs
- detected agents and setup health

By default, the backend API serves the built dashboard at `http://localhost:4001`. The frontend dev server resolves the API URL in this order:

1. `TOKENAGE_API_URL`
2. `TOKENAGE_BACKEND_URL`
3. `~/.tokenage/config.yaml` using `server.host` and `server.api_port`
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
tokenage server status
tokenage server restart
tokenage server stop
```

`tokenage server start` turns the services on, and `tokenage server
bootstrap` reinstalls, rebuilds the dashboard and restarts the API so the new
bundle is served. `tokenage status` is a different command: it reports the
installed components and whether they run.

Runtime files live under `~/.tokenage/run/`. Logs are written to `logs/`.

## Configuration

Main config:

```text
~/.tokenage/config.yaml
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
  path: ~/.tokenage/usage.db
```

To use PostgreSQL or MySQL instead of SQLite, set `db.url`:

```yaml
db:
  url: postgresql+psycopg://user:password@db-host:5432/tokenage?sslmode=require
```

`tokenage server start` merges missing defaults from `config.example.yaml` into your user config without overwriting existing values.

## Point clients at the proxy

For OpenAI-compatible clients:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:4000/v1
```

For Anthropic-compatible clients:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:4000
```

By default, if a provider sets `api_key`, the proxy injects it upstream as `Authorization: Bearer <key>`. For providers using Anthropic's native auth scheme (e.g. `api.anthropic.com`), set `auth_scheme: x-api-key` on that provider so the proxy sends `x-api-key: <key>` instead. The client must still send its own `anthropic-version` header (real Anthropic clients like Claude Code always do; the proxy passes it through unchanged and does not set a default):

```yaml
providers:
  anthropic:
    base_url: https://api.anthropic.com/v1
    api_key: sk-ant-...
    auth_scheme: x-api-key
    models:
      claude-sonnet-4-6: {}
```

Or let the wrapper set both for one child process:

```bash
tokenage --proxy-env -- some-openai-compatible-cli
```

Supported proxy paths include:

- `/v1/chat/completions`
- `/v1/responses`
- `/v1/messages`

For streamed responses, the proxy records TTFT as time until the first upstream chunk arrives.

## Tracking coverage

| Metric | Claude Code | Codex | OpenCode / Kilo Code | Direct proxy |
| --- | --- | --- | --- | --- |
| Input tokens | OTLP | OTLP | Plugin OTLP | Response usage |
| Output tokens | OTLP | OTLP | Plugin OTLP | Response usage |
| Cached tokens read | OTLP | OTLP | Plugin OTLP | Response usage |
| Cached tokens write | OTLP | Not available | Plugin OTLP | Not available |
| Reasoning tokens | Not available | OTLP | Plugin OTLP | Response usage |
| Tool tokens | Not available | OTLP | Not available | Not available |
| Prompt length | OTLP | OTLP | Plugin OTLP | Not available |
| Latency | OTLP | OTLP | Plugin OTLP | Proxy timing |
| TTFT | Not available | OTLP | Plugin OTLP | Streaming only |
| Session ID | OTLP | OTLP | Plugin OTLP | Not available |

TTFT is an operational signal, not a billing-grade metric. Each agent exposes different timing data.

OpenCode and Kilo Code tracking is provided by local plugins (`plugins/opencode` and `plugins/kilo`) that emit one OTLP log record for each completed assistant message. `tokenage setup` registers each built plugin (when `opencode` or `kilo` is installed) with the local OTLP logs endpoint, using `client/agents/`.

## API

Useful local endpoints:

```bash
curl http://127.0.0.1:4001/usage?limit=20
curl http://127.0.0.1:4001/usage/summary
curl http://127.0.0.1:4001/usage/daily
curl http://127.0.0.1:4001/usage/high-watermark
curl http://127.0.0.1:4001/config
```

Device status and agent wiring live on the client, not the API:

```bash
tokenage client health --json
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
uv run python -m pytest -q
```

If `uv` is unavailable but the bootstrap-created virtualenv exists, use `./.venv/bin/python -m pytest -q` as a fallback.

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

- `tokenage` is intended to run locally.
- Usage is stored in `~/.tokenage/usage.db` by default.
- If you configure `db.url`, usage data is written to that database instead.
- The proxy forwards auth headers unchanged.
- API keys are not managed by `tokenage`.
- OTLP payloads are emitted by the agents themselves; review agent telemetry settings if you need strict metadata control.

## Contributing

Issues and PRs are welcome. Good contributions usually include:

- a clear bug report or product problem
- a small, testable change
- backend tests with `pytest` when changing Python behavior
- frontend tests under `frontend/tests/` when changing dashboard behavior
- updated docs when commands, setup, or behavior changes

Please keep examples consistent: plain agent invocations should use `tokenage codex` or `tokenage claude`; reserve `--` for cases where `tokenage` flags are present.

## License

MIT. See [LICENSE](LICENSE).
