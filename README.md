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
uv venv --python 3.14
uv pip install fastapi uvicorn httpx pyyaml
```

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

```bash
.venv/bin/python src/proxy.py
```

Proxy starts on `http://localhost:4000` by default.

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

## Usage API

```bash
# Recent requests
curl http://localhost:4000/usage

# Totals grouped by provider/model
curl http://localhost:4000/usage/summary
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
