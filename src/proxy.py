#!/usr/bin/env python3
"""
llm-tracker: pass-through proxy for OpenAI-compatible providers with usage logging.
Supports both /v1/chat/completions and /v1/responses endpoints.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse


REQUEST_TIMEOUT_SECONDS = 300
CONFIG_PATH = "~/.llm-tracker/config.yaml"


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str


def load_config(path: str = CONFIG_PATH) -> dict[str, Any]:
    with open(os.path.expanduser(path), encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    config["db"]["path"] = os.path.expanduser(config["db"]["path"])
    return config


def build_maps(config: dict[str, Any]) -> tuple[dict[str, ProviderConfig], dict[str, ProviderConfig]]:
    provider_map: dict[str, ProviderConfig] = {}
    model_map: dict[str, ProviderConfig] = {}

    for provider_name, provider in config["providers"].items():
        provider_config = ProviderConfig(name=provider_name, base_url=provider["base_url"])
        provider_map[provider_name] = provider_config
        for model in provider.get("models", []):
            model_map[model] = provider_config

    return provider_map, model_map


CONFIG = load_config()
PROVIDER_MAP, MODEL_MAP = build_maps(CONFIG)


def connect_db(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect_db(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS usage (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                ts                TEXT NOT NULL,
                provider          TEXT NOT NULL,
                model             TEXT NOT NULL,
                endpoint          TEXT NOT NULL,
                prompt_tokens     INTEGER,
                completion_tokens INTEGER,
                reasoning_tokens  INTEGER,
                cached_tokens     INTEGER,
                total_tokens      INTEGER,
                latency_ms        INTEGER,
                status            INTEGER
            )
            """
        )


def log_usage(db_path: str, **fields: Any) -> None:
    with connect_db(db_path) as connection:
        connection.execute(
            """
            INSERT INTO usage (
                ts, provider, model, endpoint, prompt_tokens, completion_tokens,
                reasoning_tokens, cached_tokens, total_tokens, latency_ms, status
            ) VALUES (
                :ts, :provider, :model, :endpoint, :prompt_tokens, :completion_tokens,
                :reasoning_tokens, :cached_tokens, :total_tokens, :latency_ms, :status
            )
            """,
            fields,
        )


def extract_usage(usage: dict[str, Any]) -> dict[str, int]:
    """Normalize usage fields across chat completions and responses API formats."""
    prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens", 0)
    completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens", 0)
    total_tokens = usage.get("total_tokens") or (prompt_tokens + completion_tokens)

    input_details = (
        usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    )
    output_details = (
        usage.get("output_tokens_details") or usage.get("completion_tokens_details") or {}
    )

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": output_details.get("reasoning_tokens", 0),
        "cached_tokens": input_details.get("cached_tokens", 0),
        "total_tokens": total_tokens,
    }


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
    return {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}


def build_usage_record(
    *,
    provider: ProviderConfig,
    model: str,
    endpoint: str,
    latency_ms: int,
    status: int,
    usage_fields: dict[str, int],
) -> dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "provider": provider.name,
        "model": model,
        "endpoint": endpoint,
        "latency_ms": latency_ms,
        "status": status,
        **usage_fields,
    }


def parse_json_body(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    return json.loads(body)


def extract_stream_usage(message: dict[str, Any]) -> dict[str, int] | None:
    if usage := message.get("usage"):
        return extract_usage(usage)

    response_payload = message.get("response") or {}
    if usage := response_payload.get("usage"):
        return extract_usage(usage)

    return None


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
            async with client.stream("POST", url, headers=headers, content=body) as response:
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
            CONFIG["db"]["path"],
            **build_usage_record(
                provider=provider,
                model=model,
                endpoint=path,
                latency_ms=latency_ms,
                status=status,
                usage_fields=usage_fields,
            ),
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
        CONFIG["db"]["path"],
        **build_usage_record(
            provider=provider,
            model=model,
            endpoint=path,
            latency_ms=latency_ms,
            status=response.status_code,
            usage_fields=extract_usage(response_json.get("usage", {})),
        ),
    )

    return JSONResponse(content=response_json, status_code=response.status_code)


def fetch_usage_rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connect_db(CONFIG["db"]["path"]) as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def build_usage_query(
    *,
    limit: int,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[str, tuple[Any, ...]]:
    query = "SELECT * FROM usage"
    clauses: list[str] = []
    params: list[Any] = []

    if provider:
        clauses.append("provider = ?")
        params.append(provider)

    if model:
        clauses.append("model = ?")
        params.append(model)

    if clauses:
        query = f"{query} WHERE {' AND '.join(clauses)}"

    query = f"{query} ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return query, tuple(params)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(CONFIG["db"]["path"])
    yield


app = FastAPI(title="llm-tracker", lifespan=lifespan)


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


@app.get("/usage")
async def get_usage(
    limit: int = 100,
    provider: str | None = None,
    model: str | None = None,
):
    query, params = build_usage_query(limit=limit, provider=provider, model=model)
    return fetch_usage_rows(query, params)


@app.get("/usage/summary")
async def usage_summary():
    return fetch_usage_rows(
        """
        SELECT provider, model,
               COUNT(*)               AS requests,
               SUM(prompt_tokens)     AS prompt_tokens,
               SUM(completion_tokens) AS completion_tokens,
               SUM(reasoning_tokens)  AS reasoning_tokens,
               SUM(cached_tokens)     AS cached_tokens,
               SUM(total_tokens)      AS total_tokens,
               AVG(latency_ms)        AS avg_latency_ms
        FROM usage
        GROUP BY provider, model
        ORDER BY total_tokens DESC
        """
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=CONFIG["server"]["host"], port=CONFIG["server"]["port"])
