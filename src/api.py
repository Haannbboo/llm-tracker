from typing import Any
from fastapi import FastAPI
from config.app import CONFIG
from .database import fetch_usage_rows, init_db
from contextlib import asynccontextmanager

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

app = FastAPI(title="llm-tracker-api", lifespan=lifespan)

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
    port = CONFIG["server"].get("api_port", CONFIG["server"]["port"] + 1)
    uvicorn.run(app, host=CONFIG["server"]["host"], port=port)
