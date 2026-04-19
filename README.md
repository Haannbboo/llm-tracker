# llm-tracker

A **pure pass-through proxy** for LLM providers with usage logging. It does not inspect, modify, or manage credentials — every request is forwarded byte-for-byte with all original headers intact. The only thing it adds is a statistics record in SQLite.

## How it works

```
Claude Code / Codex
    │  (your real API key in headers, your model in body)
    ▼
llm-tracker proxy  ←── reads `model` field to know which base_url to forward to
    │  (headers unchanged, body unchanged)
    ▼
Upstream provider (Anthropic, OpenAI, VectorEngine, MiniMax, ...)
```

The proxy never touches your credentials. `ANTHROPIC_AUTH_TOKEN` / `Authorization` / `x-api-key` pass through exactly as sent by the client.

## Features

- Supports `/v1/chat/completions`, `/v1/responses`, and `/v1/messages` (Anthropic)
- Logs prompt, completion, reasoning, and cached tokens per request
- SQLite storage, no external dependencies
- `/usage` and `/usage/summary` endpoints for querying logs

## Setup

```bash
bash scripts/start.sh
```

This bootstraps `uv` if needed, creates `.venv`, installs `requirements.txt`, ensures `~/.llm-tracker/config.yaml` exists, and starts the proxy/API services under Supervisor.
It also configures project-local Gemini telemetry and `BeforeModel`/`AfterModel` hooks in [.gemini/settings.json](/Users/hanbo/Documents/llm-tracker/.gemini/settings.json) so Gemini TTFT is captured without hand-editing the settings file.

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

## Running

The project is split into two servers: the **Proxy** (routing and logging) and the **API** (usage stats and frontend connection).

**Start both services under Supervisor:**
```bash
bash scripts/start.sh
```

**Reload both services:**
```bash
bash scripts/restart.sh
```
This sends `SIGHUP` to the managed proxy and API processes through Supervisor.

**Stop both services:**
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

## Usage API

The Usage API now runs on its own port (default `4001`):

```bash
# Recent requests
curl http://localhost:4001/usage

# Totals grouped by provider/model
curl http://localhost:4001/usage/summary
```

## Logged fields

| Field | Description |
|---|---|
| `ts` | UTC timestamp |
| `provider` | Provider name from config |
| `model` | Model name |
| `endpoint` | `/v1/chat/completions`, `/v1/responses`, or `/v1/messages` |
| `prompt_tokens` | Input tokens |
| `completion_tokens` | Output tokens |
| `reasoning_tokens` | Reasoning tokens (from output details) |
| `cached_tokens` | Cache hits (from input details) |
| `total_tokens` | Total tokens |
| `latency_ms` | End-to-end proxy latency |
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
