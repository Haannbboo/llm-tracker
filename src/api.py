import os
import yaml
from fastapi import FastAPI, HTTPException, Request
from config.app import (
    CONFIG,
    CONFIG_PATH,
)
from .database import (
    aggregate_usage_by_period,
    count_usage,
    fetch_recent_usage,
    init_db,
    log_usage,
    summarize_usage,
)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(CONFIG["db"]["url"])
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
    return fetch_recent_usage(
        limit=limit,
        offset=offset,
        provider=provider,
        model=model,
        since=since,
        until=until,
    )


@app.get("/usage/count")
async def get_usage_count(
    provider: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
):
    return {
        "total": count_usage(
            provider=provider,
            model=model,
            since=since,
            until=until,
        )
    }


@app.get("/usage/summary")
async def usage_summary(
    since: str | None = None,
    until: str | None = None,
):
    return summarize_usage(since=since, until=until)


@app.get("/usage/daily")
async def usage_daily(
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    granularity: str = "day",
    tz_offset: str = "+00:00",
):
    return aggregate_usage_by_period(
        since=since,
        until=until,
        provider=provider,
        model=model,
        granularity=granularity,
        tz_offset=tz_offset,
    )


@app.post("/usage")
async def post_usage(entry: UsageEntry):
    log_usage(CONFIG["db"]["url"], **entry.model_dump())
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
