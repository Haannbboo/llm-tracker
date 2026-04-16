#!/usr/bin/env python3
"""
llm-tracker: pass-through proxy for OpenAI-compatible providers with usage logging.
Supports both /v1/chat/completions and /v1/responses endpoints.
"""

import json
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(path: str = "~/.llm-tracker/config.yaml") -> dict:
    with open(os.path.expanduser(path)) as f:
        cfg = yaml.safe_load(f)
    cfg["db"]["path"] = os.path.expanduser(cfg["db"]["path"])
    return cfg


CONFIG = load_config()

# model name → provider config
MODEL_MAP: dict[str, dict] = {}
for name, provider in CONFIG["providers"].items():
    for model in provider.get("models", []):
        MODEL_MAP[model] = {"name": name, **provider}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.execute("""
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
    """)
    con.commit()
    con.close()


def log_usage(db_path: str, **kwargs):
    con = sqlite3.connect(db_path)
    con.execute(
        """INSERT INTO usage
           (ts, provider, model, endpoint, prompt_tokens, completion_tokens,
            reasoning_tokens, cached_tokens, total_tokens, latency_ms, status)
           VALUES (:ts, :provider, :model, :endpoint, :prompt_tokens, :completion_tokens,
                   :reasoning_tokens, :cached_tokens, :total_tokens, :latency_ms, :status)""",
        kwargs,
    )
    con.commit()
    con.close()


def extract_usage(usage: dict) -> dict:
    """Normalize usage fields across chat completions and responses API formats."""
    prompt     = usage.get("prompt_tokens") or usage.get("input_tokens", 0)
    completion = usage.get("completion_tokens") or usage.get("output_tokens", 0)
    total      = usage.get("total_tokens") or (prompt + completion)

    input_details  = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or usage.get("completion_tokens_details") or {}

    cached    = input_details.get("cached_tokens", 0)
    reasoning = output_details.get("reasoning_tokens", 0)

    return {
        "prompt_tokens":     prompt,
        "completion_tokens": completion,
        "reasoning_tokens":  reasoning,
        "cached_tokens":     cached,
        "total_tokens":      total,
    }


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(CONFIG["db"]["path"])
    yield


app = FastAPI(title="llm-tracker", lifespan=lifespan)


def resolve_provider(model: str) -> dict:
    if model in MODEL_MAP:
        return MODEL_MAP[model]
    for key, provider in MODEL_MAP.items():
        if model.startswith(key) or key.startswith(model):
            return provider
    raise HTTPException(status_code=404, detail=f"No provider configured for model '{model}'")


async def forward(request: Request, path: str):
    body = await request.body()
    body_json = json.loads(body) if body else {}
    model = body_json.get("model", "")
    provider = resolve_provider(model)

    # base_url already includes /v1, so strip it from path to avoid /v1/v1
    stripped = path.lstrip("/")
    if stripped.startswith("v1/"):
        stripped = stripped[3:]
    url = provider["base_url"].rstrip("/") + "/" + stripped
    headers = {
        "Authorization": f"Bearer {provider['api_key']}",
        "Content-Type": "application/json",
    }
    for k, v in request.headers.items():
        if k.lower() not in ("host", "authorization", "content-length"):
            headers[k] = v

    is_stream = body_json.get("stream", False)
    start = time.monotonic()

    if is_stream:
        async def stream_gen():
            usage_fields = {"prompt_tokens": 0, "completion_tokens": 0,
                            "reasoning_tokens": 0, "cached_tokens": 0, "total_tokens": 0}
            status = 200
            try:
                async with httpx.AsyncClient(timeout=300) as client:
                    async with client.stream("POST", url, headers=headers, content=body) as resp:
                        status = resp.status_code
                        buf = ""
                        async for chunk in resp.aiter_bytes():
                            yield chunk
                            try:
                                buf += chunk.decode(errors="ignore")
                                while "\n" in buf:
                                    line, buf = buf.split("\n", 1)
                                    line = line.strip()
                                    if not line.startswith("data:") or "[DONE]" in line:
                                        continue
                                    data = json.loads(line[5:].strip())
                                    # chat completions format
                                    if u := data.get("usage"):
                                        usage_fields = extract_usage(u)
                                    # responses API: response.completed
                                    if resp_obj := data.get("response"):
                                        if u := resp_obj.get("usage"):
                                            usage_fields = extract_usage(u)
                            except Exception:
                                pass
            finally:
                latency = int((time.monotonic() - start) * 1000)
                log_usage(
                    CONFIG["db"]["path"],
                    ts=datetime.now(timezone.utc).isoformat(),
                    provider=provider["name"],
                    model=model,
                    endpoint=path,
                    latency_ms=latency,
                    status=status,
                    **usage_fields,
                )

        return StreamingResponse(stream_gen(), media_type="text/event-stream")

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(url, headers=headers, content=body)
        latency = int((time.monotonic() - start) * 1000)
        resp_json = resp.json()
        usage_fields = extract_usage(resp_json.get("usage", {}))
        log_usage(
            CONFIG["db"]["path"],
            ts=datetime.now(timezone.utc).isoformat(),
            provider=provider["name"],
            model=model,
            endpoint=path,
            latency_ms=latency,
            status=resp.status_code,
            **usage_fields,
        )
        return resp_json


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    return await forward(request, "/v1/chat/completions")


@app.post("/v1/responses")
async def responses(request: Request):
    return await forward(request, "/v1/responses")


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {"id": m, "object": "model", "owned_by": p["name"]}
            for m, p in MODEL_MAP.items()
        ],
    }


@app.get("/usage")
async def get_usage(limit: int = 100):
    con = sqlite3.connect(CONFIG["db"]["path"])
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM usage ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


@app.get("/usage/summary")
async def usage_summary():
    con = sqlite3.connect(CONFIG["db"]["path"])
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT provider, model,
               COUNT(*)                   AS requests,
               SUM(prompt_tokens)         AS prompt_tokens,
               SUM(completion_tokens)     AS completion_tokens,
               SUM(reasoning_tokens)      AS reasoning_tokens,
               SUM(cached_tokens)         AS cached_tokens,
               SUM(total_tokens)          AS total_tokens,
               AVG(latency_ms)            AS avg_latency_ms
        FROM usage
        GROUP BY provider, model
        ORDER BY total_tokens DESC
    """).fetchall()
    con.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=CONFIG["server"]["host"], port=CONFIG["server"]["port"])
