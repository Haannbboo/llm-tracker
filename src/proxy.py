#!/usr/bin/env python3
"""
llm-tracker: pass-through proxy for OpenAI-compatible providers with usage logging.
Supports both /v1/chat/completions and /v1/responses endpoints.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from config.app import (
    CONFIG,
    MODEL_MAP,
    PROVIDER_MAP,
    ProviderConfig,
    refresh_runtime_config,
)

from .database import init_db
from .recorder import record_usage
from .utils import extract_stream_usage, extract_usage

REQUEST_TIMEOUT_SECONDS = 300
PROXY_USER_AGENT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs",
    "proxy-user-agent",
)
RECORDED_PROXY_USER_AGENTS: set[str] = set()


def parse_client_source(user_agent: str) -> str | None:
    """Infer a normalized client source label from a proxy User-Agent string."""
    normalized = user_agent.strip().lower()
    if not normalized:
        return None

    # Prefer stable agent/provider markers anywhere in the UA over the leading token.
    if "gemini" in normalized:
        return "gemini"
    if "codex" in normalized:
        return "codex"
    if "claude" in normalized:
        return "claude"
    if "opencode" in normalized:
        return "opencode"

    # Fall back to the leading product/version token for unknown clients.
    first_token = normalized.split()[0]
    if "/" in first_token:
        product = first_token.split("/", 1)[0]
        if product:
            return product

    return None


def record_proxy_user_agent(path: str, user_agent: str) -> None:
    """Append first-seen proxy user agents to the local discovery log."""
    try:
        os.makedirs(PROXY_USER_AGENT_DIR, exist_ok=True)
        log_path = os.path.join(PROXY_USER_AGENT_DIR, "requests.log")

        # Reload prior discoveries after worker restart so the log stays deduplicated.
        if not RECORDED_PROXY_USER_AGENTS and os.path.exists(log_path):
            with open(log_path, encoding="utf-8") as log_file:
                for line in log_file:
                    marker = " user_agent="
                    if marker in line:
                        RECORDED_PROXY_USER_AGENTS.add(
                            line.rstrip("\n").split(marker, 1)[1]
                        )

        if user_agent in RECORDED_PROXY_USER_AGENTS:
            return

        with open(log_path, "a", encoding="utf-8") as log_file:
            client_source = parse_client_source(user_agent)
            client_source_field = (
                f"client_source={client_source}"
                if client_source is not None
                else "client_source="
            )
            log_file.write(
                f"path={path} {client_source_field} user_agent={user_agent}\n"
            )
        RECORDED_PROXY_USER_AGENTS.add(user_agent)
    except OSError:
        return


def resolve_provider(model: str) -> tuple[ProviderConfig, str]:
    """Returns (provider, upstream_model). Strips provider prefix if present and not explicitly mapped."""
    if model in MODEL_MAP:
        return MODEL_MAP[model], model

    for sep in ("/", "."):
        if sep in model:
            provider_name, upstream_model = model.split(sep, 1)
            if provider_name in PROVIDER_MAP:
                return PROVIDER_MAP[provider_name], upstream_model

    raise HTTPException(
        status_code=404,
        detail=f"No provider configured for model '{model}'",
    )


def build_upstream_url(base_url: str, path: str) -> str:
    """Normalize and combine base URL and request path for upstream request."""
    stripped_path = path.lstrip("/")
    if stripped_path.startswith("v1/"):
        stripped_path = stripped_path[3:]
    return urljoin(base_url.rstrip("/") + "/", stripped_path)


def build_forward_headers(
    request: Request, provider: ProviderConfig | None = None
) -> dict[str, str]:
    """Filter and prepare headers for forwarding to upstream provider."""
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length", "authorization"}
    }
    if provider and provider.api_key:
        headers["authorization"] = f"Bearer {provider.api_key}"
    return headers


def parse_json_body(body: bytes) -> dict[str, Any]:
    """Safely parse JSON request body, returning empty dict if empty."""
    if not body:
        return {}
    return json.loads(body)


def _content_text_length(content: Any) -> int:
    """Return character count of a message content value."""
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                total += len(part["text"])
        return total
    return 0


def compute_prompt_length(body_json: dict[str, Any]) -> int:
    """Compute new user prompt character count from a request body.

    Only counts ``role=user`` messages that appear *after* the last
    ``role=assistant`` message, so that tool-call continuation turns
    (which replay the full history but add no new human input) report 0.
    Supports chat/completions (``messages``) and responses (``input``) formats.
    """
    items = body_json.get("messages", []) or body_json.get("input", []) or []
    # Find index of last assistant message; only count user messages after it.
    last_assistant = -1
    for i, item in enumerate(items):
        if isinstance(item, dict) and item.get("role") == "assistant":
            last_assistant = i

    total = 0
    for item in items[last_assistant + 1 :]:
        if isinstance(item, dict) and item.get("role") == "user":
            total += _content_text_length(item.get("content"))
    return total


async def _forward_stream_or_error(
    *,
    url: str,
    headers: dict[str, str],
    body: bytes,
    provider: ProviderConfig,
    model: str,
    client_source: str | None,
    client_ip: str | None,
    path: str,
    started_at: float,
    prompt_length: int = 0,
) -> StreamingResponse | JSONResponse:
    """Open an upstream streaming connection, check status, and relay or error."""
    client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        req = client.build_request("POST", url, headers=headers, content=body)
        upstream = await client.send(req, stream=True)
    except Exception:
        try:
            await client.aclose()
        except Exception:
            pass
        raise

    if upstream.status_code >= 400:
        try:
            error_body = await upstream.aread()
        except Exception:
            try:
                await client.aclose()
            except Exception:
                pass
            raise
        await client.aclose()
        try:
            error_content = (
                json.loads(error_body) if error_body else {"error": "upstream error"}
            )
        except json.JSONDecodeError:
            error_content = {"error": error_body.decode(errors="ignore")}
        return JSONResponse(content=error_content, status_code=upstream.status_code)

    async def _relay():
        usage_fields = extract_usage({})
        ttft_ms: int | None = None
        buffer = ""

        try:
            async for chunk in upstream.aiter_bytes():
                if ttft_ms is None:
                    ttft_ms = int((time.monotonic() - started_at) * 1000)
                yield chunk

                try:
                    buffer += chunk.decode(errors="ignore")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line.startswith("data:") or "[DONE]" in line:
                            continue

                        payload = json.loads(line[5:].strip())
                        stream_usage = extract_stream_usage(payload)
                        if stream_usage is not None:
                            usage_fields = stream_usage
                except Exception:
                    continue
        finally:
            await client.aclose()
            latency_ms = int((time.monotonic() - started_at) * 1000)
            record_usage(
                provider=provider.name,
                model=model,
                client_source=client_source,
                session_id=None,
                endpoint=path,
                prompt_tokens=usage_fields.get("prompt_tokens"),
                prompt_length=prompt_length,
                completion_tokens=usage_fields.get("completion_tokens"),
                cached_tokens=usage_fields.get("cached_tokens"),
                reasoning_tokens=usage_fields.get("reasoning_tokens"),
                total_tokens=usage_fields.get("total_tokens"),
                latency_ms=latency_ms,
                ttft_ms=ttft_ms,
                status=upstream.status_code,
                client_ip=client_ip,
                base_url=provider.base_url,
                base_url_provider=provider.name,
                base_url_source="proxy_config",
            )

    return StreamingResponse(_relay(), media_type="text/event-stream")


async def forward(request: Request, path: str):
    """Core proxy logic: resolve provider, forward request, and record usage."""
    body = await request.body()
    body_json = parse_json_body(body)
    user_agent = request.headers.get("user-agent", "")
    client_source = parse_client_source(user_agent)
    client_ip = request.client.host if request.client else None
    record_proxy_user_agent(path, user_agent)
    model = body_json.get("model", "")
    provider, upstream_model = resolve_provider(model)
    prompt_length = compute_prompt_length(body_json)

    if upstream_model != model:
        body_json["model"] = upstream_model
        body = json.dumps(body_json).encode()

    url = build_upstream_url(provider.base_url, path)
    headers = build_forward_headers(request, provider)
    started_at = time.monotonic()

    if body_json.get("stream", False):
        # Ensure usage is included in the stream if not explicitly disabled
        if "stream_options" not in body_json:
            body_json["stream_options"] = {"include_usage": True}
            body = json.dumps(body_json).encode()

        return await _forward_stream_or_error(
            url=url,
            headers=headers,
            body=body,
            provider=provider,
            model=model,
            client_source=client_source,
            client_ip=client_ip,
            path=path,
            started_at=started_at,
            prompt_length=prompt_length,
        )

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(url, headers=headers, content=body)

    latency_ms = int((time.monotonic() - started_at) * 1000)
    response_json = response.json()

    usage_fields = extract_usage(response_json.get("usage", {}))
    record_usage(
        provider=provider.name,
        model=model,
        client_source=client_source,
        session_id=None,
        endpoint=path,
        prompt_tokens=usage_fields.get("prompt_tokens"),
        prompt_length=prompt_length,
        completion_tokens=usage_fields.get("completion_tokens"),
        cached_tokens=usage_fields.get("cached_tokens"),
        reasoning_tokens=usage_fields.get("reasoning_tokens"),
        total_tokens=usage_fields.get("total_tokens"),
        latency_ms=latency_ms,
        ttft_ms=None,
        status=response.status_code,
        client_ip=client_ip,
        base_url=provider.base_url,
        base_url_provider=provider.name,
        base_url_source="proxy_config",
    )

    return JSONResponse(content=response_json, status_code=response.status_code)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    init_db()
    yield


app = FastAPI(title="llm-tracker-proxy", lifespan=lifespan)


def proxy_metadata() -> dict[str, Any]:
    """Return metadata about the proxy and its supported endpoints."""
    return {
        "name": app.title,
        "supported_endpoints": [
            "/chat/completions",
            "/v1/chat/completions",
            "/responses",
            "/v1/responses",
            "/messages",
            "/v1/messages",
            "/models",
            "/v1/models",
            "/api/v1/models",
            "/props",
            "/v1/props",
        ],
    }


@app.post("/chat/completions")
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """OpenAI-compatible chat completions endpoint."""
    return await forward(request, "/v1/chat/completions")


@app.post("/responses")
@app.post("/v1/responses")
async def responses(request: Request):
    """Proxy for /responses endpoint."""
    return await forward(request, "/v1/responses")


@app.post("/messages")
@app.post("/v1/messages")
async def messages(request: Request):
    """Proxy for /messages endpoint."""
    return await forward(request, "/v1/messages")


@app.get("/api/v1/models")
@app.get("/v1/models")
@app.get("/models")
async def list_models():
    """List available models supported by the proxy."""
    return {
        "object": "list",
        "data": [
            {"id": model, "object": "model", "owned_by": provider.name}
            for model, provider in MODEL_MAP.items()
        ],
    }


@app.post("/config/refresh")
async def refresh_config():
    """Reload config from disk so the proxy picks up provider/model changes."""
    await asyncio.to_thread(refresh_runtime_config)
    return {"status": "success"}


@app.get("/models/{model_id:path}")
@app.get("/v1/models/{model_id:path}")
async def get_model(model_id: str):
    """Get information about a specific model."""
    provider = MODEL_MAP.get(model_id)
    if provider is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found",
        )

    return {
        "id": model_id,
        "object": "model",
        "owned_by": provider.name,
    }


@app.get("/v1/props")
@app.get("/props")
async def props():
    """Return proxy metadata."""
    return proxy_metadata()


@app.get("/version")
async def version():
    """Return proxy version information."""
    from ._version import get_version

    return {
        "name": app.title,
        "version": get_version(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=CONFIG["server"]["host"], port=CONFIG["server"]["port"])
