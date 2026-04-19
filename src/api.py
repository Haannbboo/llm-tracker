import os
import yaml
from typing import Any
from fastapi import FastAPI, HTTPException
from config.app import CONFIG, CONFIG_PATH
from .database import fetch_usage_rows, init_db, log_usage
from contextlib import asynccontextmanager
from pydantic import BaseModel


class ConfigUpdate(BaseModel):
    content: str


class UsageEntry(BaseModel):
    ts: str
    provider: str
    model: str
    endpoint: str = "generate"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None
    ttft_ms: int | None = None
    tool_tokens: int | None = None
    cache_creation_tokens: int | None = None
    status: int | None = None


def build_usage_query(
    *,
    limit: int,
    offset: int = 0,
    provider: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
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

    if since:
        clauses.append("ts >= ?")
        params.append(since)

    if until:
        clauses.append("ts <= ?")
        params.append(until)

    if clauses:
        query = f"{query} WHERE {' AND '.join(clauses)}"

    query = f"{query} ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return query, tuple(params)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(CONFIG["db"]["path"])
    yield


app = FastAPI(title="llm-tracker-api", lifespan=lifespan)


@app.get("/usage")
async def get_usage(
    limit: int = 100,
    offset: int = 0,
    provider: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
):
    query, params = build_usage_query(
        limit=limit,
        offset=offset,
        provider=provider,
        model=model,
        since=since,
        until=until,
    )
    return fetch_usage_rows(query, params)


@app.get("/usage/count")
async def get_usage_count(
    provider: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
):
    query = "SELECT COUNT(*) AS total FROM usage"
    clauses: list[str] = []
    params: list[Any] = []

    if provider:
        clauses.append("provider = ?")
        params.append(provider)
    if model:
        clauses.append("model = ?")
        params.append(model)
    if since:
        clauses.append("ts >= ?")
        params.append(since)
    if until:
        clauses.append("ts <= ?")
        params.append(until)

    if clauses:
        query = f"{query} WHERE {' AND '.join(clauses)}"

    rows = fetch_usage_rows(query, tuple(params))
    return {"total": rows[0]["total"] if rows else 0}


@app.get("/usage/summary")
async def usage_summary(
    since: str | None = None,
    until: str | None = None,
):
    clauses: list[str] = []
    params: list[Any] = []

    if since:
        clauses.append("ts >= ?")
        params.append(since)
    if until:
        clauses.append("ts <= ?")
        params.append(until)

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    return fetch_usage_rows(
        f"""
        SELECT provider, model,
               COUNT(*)               AS requests,
               SUM(prompt_tokens)     AS prompt_tokens,
               SUM(completion_tokens) AS completion_tokens,
               SUM(reasoning_tokens)  AS reasoning_tokens,
               SUM(cached_tokens)     AS cached_tokens,
               SUM(total_tokens)      AS total_tokens,
               AVG(latency_ms)        AS avg_latency_ms
        FROM usage
        {where_clause}
        GROUP BY provider, model
        ORDER BY total_tokens DESC
        """,
        tuple(params),
    )


@app.post("/usage")
async def post_usage(entry: UsageEntry):
    log_usage(CONFIG["db"]["path"], **entry.model_dump())
    return {"status": "ok"}


@app.get("/config")
async def get_config():
    path = os.path.expanduser(CONFIG_PATH)
    if not os.path.exists(path):
        return {"content": ""}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/config")
async def update_config(update: ConfigUpdate):
    path = os.path.expanduser(CONFIG_PATH)
    try:
        # Validate YAML
        yaml.safe_load(update.content)

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(update.content)
        return {"status": "success"}
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = CONFIG["server"].get("api_port", CONFIG["server"]["port"] + 1)
    uvicorn.run(app, host=CONFIG["server"]["host"], port=port)
