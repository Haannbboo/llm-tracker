# llm-tracker

A dual-purpose usage tracker for LLM agent users. It functions as both a **transparent forwarding proxy** and a **lightweight OTLP (OpenTelemetry) collector** designed specifically for coding agents like Claude Code, Gemini CLI, and Codex.

The proxy does not inspect, modify, or manage credentials: authorization headers such as `ANTHROPIC_AUTH_TOKEN`, `Authorization`, and `x-api-key` are forwarded unchanged. It captures usage metrics (tokens, latency, TTFT) either from the proxy response stream or from telemetry logs emitted by the agents themselves.

## How it works

llm-tracker captures usage data through two primary paths:

### 1. OTLP Collector Path
For agents that emit OpenTelemetry logs (Gemini CLI, Claude Code, Codex), llm-tracker acts as a local OTLP backend, parsing rich telemetry to capture metrics that a proxy alone cannot see (e.g., internal tool tokens or client-side latency).

```
Agent (Gemini CLI / Codex / Claude Code)
    │  (internal telemetry events)
    ▼
llm-tracker OTLP    ←── parses provider-specific schemas
    │
    ▼
Configured Database (SQLite/Postgres)
```

### 2. Transparent Proxy Path
For other tools that support custom base URLs (like OpenClaw), the proxy routes requests and logs usage from the response. For streamed requests, it also records `ttft_ms` as the time until the first upstream chunk arrives.

```
Client (e.g. Claude Code)
    │  (API key in headers, model in body)
    ▼
llm-tracker proxy   ←── resolves upstream provider from `model`
    │  (credentials unchanged, body forwarded)
    ▼
Upstream Provider (Anthropic, OpenAI, etc.)
```



## Features

- **Multi-Service Architecture**: Separate high-performance services for Proxying, OTLP collection, and Usage API.
- **Deep Agent Integration**:
    - **Gemini CLI**: Captures TTFT via a custom shell hook and merges it with OTLP usage data.
    - **Claude Code**: Tracks prompt length, cache reads/writes, and completion tokens via OTLP.
    - **Codex**: Correlates SSE events to calculate TTFT and tracks reasoning/tool tokens.
- **Transparent Proxying**: Supports `/v1/chat/completions`, `/v1/responses`, and `/v1/messages`.
- **Flexible Storage**: SQLite by default; supports PostgreSQL and MySQL via SQLAlchemy.
- **Usage Dashboard**: Built-in Vite frontend for visualizing hourly/daily usage and cost trends. See [frontend/README.md](frontend/README.md) for build instructions.

## Setup

```bash
bash scripts/start.sh
```

This bootstraps the environment using `uv`, installs dependencies, and starts the services under Supervisor. It also **automatically configures your local agents**:
- Patches `~/.claude/settings.json` for OTLP telemetry.
- Patches `~/.codex/config.toml` for OTLP telemetry.
- Installs the Gemini CLI hook in `~/.gemini/` and enables OTLP in `~/.gemini/settings.json`.
- Applies explicit database schema migrations before the services start.

## Configuration

Proxy service is configured in `~/.llm-tracker/config.yaml`:

```yaml
models:
  model-name-a:
    cost:
      input: 2.5
      output: 15.0
      cacheRead: 0.25

providers:
  my-provider:
    base_url: https://api.example.com/v1
    models:
      model-name-a: {}
      # model-name-a:
      #   cost:
      #     input: 3.0
      #     output: 18.0
      #     cacheRead: 0.3
```

`base_url` is the only required field per provider. The proxy routes by matching the `model` field in the request body to a provider, then forwards to that provider's `base_url`.

## Backend Database

By default, usage is stored in local SQLite:

```yaml
db:
  path: ~/.llm-tracker/usage.db
```

To enable cross-device data sharing, switch to a cloud SQL database, replace `db.path` with `db.url` in `~/.llm-tracker/config.yaml`:

```yaml
db:
  url: postgresql+psycopg://user:password@db-host:5432/llm_tracker?sslmode=require
```

## Running

The project is split into three managed backend services and a separate frontend dashboard:

### Backend Services
Managed via Supervisor:
- **Proxy (Port 4000)**: Routes provider requests and logs usage.
- **API (Port 4001)**: Serves usage stats and config editing endpoints.
- **OTLP (Port 4002)**: Receives telemetry logs from Codex, Gemini CLI, and Claude Code.

**Manage services with Supervisor:**
```bash
bash scripts/start.sh    # Start all
bash scripts/restart.sh  # Reload config and restart
bash scripts/stop.sh     # Stop all
bash scripts/status.sh   # Check status of servers
```

Logs are stored in the `logs/` directory. Supervisor runtime files live in `~/.llm-tracker/run/`.

### Frontend Dashboard
The dashboard is a Vite/React application that must be started separately:

```bash
cd frontend
npm install
npm run dev
```
By default, the dashboard is available at [http://localhost:5173](http://localhost:5173). See [frontend/README.md](frontend/README.md) for more details.

## Pointing agents at the proxy

While OTLP captures telemetry automatically, you can still point agents at the proxy to ensure all traffic is captured.

**Claude Code:**
```bash
export ANTHROPIC_BASE_URL=http://localhost:4000
```

**Codex** (`~/.codex/config.toml`):
```toml
[model_providers.my-provider]
base_url = "http://localhost:4000/v1"
```

That's it, configure and use the agent normally afterwards.


## Tracking Status

| Metric | Gemini CLI | Claude Code | Codex | Direct Proxy |
| :--- | :---: | :---: | :---: | :---: |
| Input Tokens | ✅ (OTLP) | ✅ (OTLP) | ✅ (OTLP) | ✅ |
| Output Tokens | ✅ (OTLP) | ✅ (OTLP) | ✅ (OTLP) | ✅ |
| Cached Tokens (Read) | ✅ (OTLP) | ✅ (OTLP) | ✅ (OTLP) | ✅ |
| Cached Tokens (Write) | ❌ | ✅ (OTLP) | ❌ | ❌ |
| Reasoning Tokens | ✅ (OTLP) | ❌ | ✅ (OTLP) | ✅ |
| Tool Tokens | ✅ (OTLP) | ❌ | ✅ (OTLP) | ❌ |
| Prompt Length (in chars) | ✅ (OTLP) | ✅ (OTLP) | ✅ (OTLP) | ❌ |
| Latency | ✅ (Hook) | ✅ (OTLP) | ✅ (OTLP) | ✅ |
| TTFT (Time to First Token) | ✅ (Hook) | ❌ | ✅ (OTLP) | ✅ (Streaming only) |

*Note: Gemini CLI captures TTFT via a shell hook because its OTLP payload lacks a first-chunk timestamp. Claude Code has no BeforeModel/AfterModel hook equivalents, so TTFT is currently unavailable. Direct proxy TTFT is captured from the first streamed upstream chunk, so it is only available when `stream=true`. In general TTFT is **not** reliable and only only for fun.*
