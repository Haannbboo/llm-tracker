#!/usr/bin/env python3
"""
llm-tracker: pass-through proxy for OpenAI-compatible providers with usage logging.
Supports both /v1/chat/completions and /v1/responses endpoints.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from config.app import CONFIG, MODEL_MAP, PROVIDER_MAP, ProviderConfig
from .database import init_db
from .recorder import record_usage
from .utils import extract_usage, extract_stream_usage

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


def build_forward_headers(request: Request) -> dict[str, str]:
    """Filter and prepare headers for forwarding to upstream provider."""
    return {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length"}
    }


def parse_json_body(body: bytes) -> dict[str, Any]:
    """Safely parse JSON request body, returning empty dict if empty."""
    if not body:
        return {}
    return json.loads(body)


async def stream_upstream_response(
    *,
    url: str,
    headers: dict[str, str],
    body: bytes,
    provider: ProviderConfig,
    model: str,
    client_source: str | None,
    path: str,
    started_at: float,
):
    """Forward a streaming request to upstream and record usage on completion."""
    status = 200

    usage_fields = extract_usage({})
    status = 200
    ttft_ms: int | None = None

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            async with client.stream(
                "POST", url, headers=headers, content=body
            ) as response:
                status = response.status_code
                buffer = ""

                async for chunk in response.aiter_bytes():
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
                        # Ignore malformed SSE chunks and keep forwarding the stream.
                        continue
    finally:
        latency_ms = int((time.monotonic() - started_at) * 1000)
        record_usage(
            provider=provider.name,
            model=model,
            client_source=client_source,
            session_id=None,
            endpoint=path,
            prompt_tokens=usage_fields.get("prompt_tokens"),
            completion_tokens=usage_fields.get("completion_tokens"),
            cached_tokens=usage_fields.get("cached_tokens"),
            reasoning_tokens=usage_fields.get("reasoning_tokens"),
            total_tokens=usage_fields.get("total_tokens"),
            latency_ms=latency_ms,
            ttft_ms=ttft_ms,
            status=status,
            base_url=provider.base_url,
            base_url_provider=provider.name,
            base_url_source="proxy_config",
        )


async def forward(request: Request, path: str):
    """Core proxy logic: resolve provider, forward request, and record usage."""
    body = await request.body()
    body_json = parse_json_body(body)
    user_agent = request.headers.get("user-agent", "")
    client_source = parse_client_source(user_agent)
    record_proxy_user_agent(path, user_agent)
    model = body_json.get("model", "")
    provider, upstream_model = resolve_provider(model)

    if upstream_model != model:
        body_json["model"] = upstream_model
        body = json.dumps(body_json).encode()

    url = build_upstream_url(provider.base_url, path)
    headers = build_forward_headers(request)
    started_at = time.monotonic()

    if body_json.get("stream", False):
        # Ensure usage is included in the stream if not explicitly disabled
        if "stream_options" not in body_json:
            body_json["stream_options"] = {"include_usage": True}
            body = json.dumps(body_json).encode()

        return StreamingResponse(
            stream_upstream_response(
                url=url,
                headers=headers,
                body=body,
                provider=provider,
                model=model,
                client_source=client_source,
                path=path,
                started_at=started_at,
            ),
            media_type="text/event-stream",
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
        completion_tokens=usage_fields.get("completion_tokens"),
        cached_tokens=usage_fields.get("cached_tokens"),
        reasoning_tokens=usage_fields.get("reasoning_tokens"),
        total_tokens=usage_fields.get("total_tokens"),
        latency_ms=latency_ms,
        ttft_ms=None,
        status=response.status_code,
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
    return {
        "name": app.title,
        "version": "dev",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=CONFIG["server"]["host"], port=CONFIG["server"]["port"])
