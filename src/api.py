import os
import yaml
from decimal import Decimal
from fastapi import FastAPI, HTTPException
from config.app import (
    CONFIG,
    CONFIG_PATH,
    refresh_runtime_config,
)
from .costs import calculate_costs
from .database import (
    Usage,
    aggregate_usage_by_period,
    count_usage,
    distinct_client_sources,
    fetch_recent_usage,
    get_usage_high_watermark,
    init_db,
    log_usage,
    resolve_base_url_id,
    summarize_usage,
    summarize_usage_window,
)
from contextlib import asynccontextmanager
from pydantic import BaseModel


class ConfigUpdate(BaseModel):
    content: str


class UsageIngest(BaseModel):
    ts: str
    provider: str
    model: str
    client_source: str | None = None
    session_id: str | None = None
    endpoint: str
    prompt_tokens: int | None = None
    prompt_length: int = 0
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None
    ttft_ms: int | None = None
    tool_tokens: int | None = None
    cache_creation_tokens: int | None = None
    status: int | None = None
    input_cost_usd: Decimal | None = None
    output_cost_usd: Decimal | None = None
    total_cost_usd: Decimal | None = None
    base_url: str | None = None
    base_url_provider_name: str | None = None
    base_url_source: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="llm-tracker-api", lifespan=lifespan)


@app.get("/usage")
async def get_usage(
    limit: int = 100,
    offset: int = 0,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    since: str | None = None,
    until: str | None = None,
):
    return fetch_recent_usage(
        limit=limit,
        offset=offset,
        provider=provider,
        model=model,
        client_source=client_source,
        since=since,
        until=until,
    )


@app.post("/usage", status_code=201)
async def ingest_usage(usage: UsageIngest):
    calculated_costs = calculate_costs(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        cached_tokens=usage.cached_tokens,
        provider=usage.provider,
        model=usage.model,
    )
    base_url_id = resolve_base_url_id(
        base_url=usage.base_url,
        provider_name=usage.base_url_provider_name or usage.provider,
        source=usage.base_url_source,
    )

    log_usage(
        Usage(
            ts=usage.ts,
            provider=usage.provider,
            model=usage.model,
            client_source=usage.client_source,
            session_id=usage.session_id,
            endpoint=usage.endpoint,
            prompt_tokens=usage.prompt_tokens,
            prompt_length=usage.prompt_length,
            completion_tokens=usage.completion_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            cached_tokens=usage.cached_tokens,
            total_tokens=usage.total_tokens,
            latency_ms=usage.latency_ms,
            ttft_ms=usage.ttft_ms,
            tool_tokens=usage.tool_tokens,
            cache_creation_tokens=usage.cache_creation_tokens,
            input_cost_usd=usage.input_cost_usd
            if usage.input_cost_usd is not None
            else calculated_costs["input_cost_usd"],
            output_cost_usd=usage.output_cost_usd
            if usage.output_cost_usd is not None
            else calculated_costs["output_cost_usd"],
            total_cost_usd=usage.total_cost_usd
            if usage.total_cost_usd is not None
            else calculated_costs["total_cost_usd"],
            status=usage.status,
            base_url_id=base_url_id,
        )
    )
    return {"status": "success"}


@app.get("/usage/count")
async def get_usage_count(
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    since: str | None = None,
    until: str | None = None,
):
    return {
        "total": count_usage(
            provider=provider,
            model=model,
            client_source=client_source,
            since=since,
            until=until,
        )
    }


@app.get("/usage/high-watermark")
async def usage_high_watermark():
    return {"id": get_usage_high_watermark()}


@app.get("/usage/sources")
async def usage_sources(
    since: str | None = None,
    until: str | None = None,
):
    return distinct_client_sources(since=since, until=until)


@app.get("/usage/run-summary")
async def usage_run_summary(
    after_id: int = 0,
    until_id: int | None = None,
    since: str | None = None,
    until: str | None = None,
    client_source: str | None = None,
    session_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    include_rows: bool = False,
):
    return summarize_usage_window(
        after_id=after_id,
        until_id=until_id,
        since=since,
        until=until,
        client_source=client_source,
        session_id=session_id,
        provider=provider,
        model=model,
        include_rows=include_rows,
    )


@app.get("/usage/summary")
async def usage_summary(
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
):
    return summarize_usage(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
    )


@app.get("/usage/daily")
async def usage_daily(
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    granularity: str = "day",
    tz_offset: str = "+00:00",
):
    return aggregate_usage_by_period(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
        granularity=granularity,
        tz_offset=tz_offset,
    )


@app.get("/config")
async def get_config():
    path = os.path.expanduser(CONFIG_PATH)
    if not os.path.exists(path):
        return {"content": "", "parsed": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            parsed = yaml.safe_load(content) or {}
        except yaml.YAMLError:
            parsed = {}
        return {"content": content, "parsed": parsed}
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
        refresh_runtime_config(path)
        return {"status": "success"}
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = CONFIG["server"].get("api_port", CONFIG["server"]["port"] + 1)
    uvicorn.run(app, host=CONFIG["server"]["host"], port=port)
