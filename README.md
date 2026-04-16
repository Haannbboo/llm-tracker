# llm-tracker

A lightweight pass-through proxy for OpenAI-compatible LLM providers with usage logging. No translation, no overhead — just forwarding and tracking.

## Features

- Supports `/v1/chat/completions` and `/v1/responses` (OpenAI Responses API)
- Logs prompt, completion, reasoning, and cached tokens per request
- SQLite storage, no external dependencies
- `/usage` and `/usage/summary` endpoints for querying logs

## Setup

```bash
uv venv --python 3.14
uv pip install fastapi uvicorn httpx pyyaml
```

## Configuration

Copy the example config to `~/.llm-tracker/config.yaml` and fill in your providers:

```bash
mkdir -p ~/.llm-tracker
cp config.example.yaml ~/.llm-tracker/config.yaml
```

```yaml
providers:
  my-provider:
    base_url: https://api.example.com/v1
    api_key: sk-...
    models:
      - model-name
```

## Running

```bash
.venv/bin/python src/proxy.py
```

Proxy starts on `http://localhost:4000` by default.

## Pointing agents at the proxy

Change only the `base_url` in your agent's config — no other changes needed.

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
| `endpoint` | `/v1/chat/completions` or `/v1/responses` |
| `prompt_tokens` | Input tokens |
| `completion_tokens` | Output tokens |
| `reasoning_tokens` | Reasoning tokens (from output details) |
| `cached_tokens` | Cache hits (from input details) |
| `total_tokens` | Total tokens |
| `latency_ms` | End-to-end proxy latency |
| `status` | HTTP status code |
