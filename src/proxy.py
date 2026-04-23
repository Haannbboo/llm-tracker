#!/usr/bin/env python3
"""
llm-tracker: pass-through proxy for OpenAI-compatible providers with usage logging.
Supports both /v1/chat/completions and /v1/responses endpoints.
"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from config.app import CONFIG, MODEL_MAP, PROVIDER_MAP, ProviderConfig
from .database import init_db, log_usage, resolve_base_url_id
from .utils import extract_usage, extract_stream_usage, build_usage_record

REQUEST_TIMEOUT_SECONDS = 300


def resolve_provider(model: str) -> tuple[ProviderConfig, str]:
    """Returns (provider, upstream_model). Strips provider prefix if present."""
    for sep in ("/", "."):
        if sep in model:
            provider_name, upstream_model = model.split(sep, 1)
            if provider_name in PROVIDER_MAP:
                return PROVIDER_MAP[provider_name], upstream_model

    if model in MODEL_MAP:
        return MODEL_MAP[model], model

    raise HTTPException(
        status_code=404,
        detail=f"No provider configured for model '{model}'",
    )


def build_upstream_url(base_url: str, path: str) -> str:
    stripped_path = path.lstrip("/")
    if stripped_path.startswith("v1/"):
        stripped_path = stripped_path[3:]
    return f"{base_url.rstrip('/')}/{stripped_path}"


def build_forward_headers(request: Request) -> dict[str, str]:
    return {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length"}
    }


def parse_json_body(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    return json.loads(body)


def resolve_provider_base_url_id(provider: ProviderConfig) -> int | None:
    return resolve_base_url_id(
        db_path=CONFIG["db"]["url"],
        base_url=provider.base_url,
        provider_name=provider.name,
        source="proxy_config",
    )


async def stream_upstream_response(
    *,
    url: str,
    headers: dict[str, str],
    body: bytes,
    provider: ProviderConfig,
    model: str,
    path: str,
    started_at: float,
):
    usage_fields = extract_usage({})
    status = 200

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            async with client.stream(
                "POST", url, headers=headers, content=body
            ) as response:
                status = response.status_code
                buffer = ""

                async for chunk in response.aiter_bytes():
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
        log_usage(
            CONFIG["db"]["url"],
            **build_usage_record(
                provider_name=provider.name,
                model=model,
                endpoint=path,
                latency_ms=latency_ms,
                status=status,
                usage_fields=usage_fields,
            )
            | {"base_url_id": resolve_provider_base_url_id(provider)},
        )


async def forward(request: Request, path: str):
    body = await request.body()
    body_json = parse_json_body(body)
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
                path=path,
                started_at=started_at,
            ),
            media_type="text/event-stream",
        )

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(url, headers=headers, content=body)

    latency_ms = int((time.monotonic() - started_at) * 1000)
    response_json = response.json()
    log_usage(
        CONFIG["db"]["url"],
        **build_usage_record(
            provider_name=provider.name,
            model=model,
            endpoint=path,
            latency_ms=latency_ms,
            status=response.status_code,
            usage_fields=extract_usage(response_json.get("usage", {})),
        )
        | {"base_url_id": resolve_provider_base_url_id(provider)},
    )

    return JSONResponse(content=response_json, status_code=response.status_code)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(CONFIG["db"]["url"])
    yield


app = FastAPI(title="llm-tracker-proxy", lifespan=lifespan)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    return await forward(request, "/v1/chat/completions")


@app.post("/v1/responses")
async def responses(request: Request):
    return await forward(request, "/v1/responses")


@app.post("/v1/messages")
async def messages(request: Request):
    return await forward(request, "/v1/messages")


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {"id": model, "object": "model", "owned_by": provider.name}
            for model, provider in MODEL_MAP.items()
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=CONFIG["server"]["host"], port=CONFIG["server"]["port"])
