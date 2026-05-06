import os
import time
import yaml
import httpx
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
    aggregate_daily_by_period,
    aggregate_usage_by_period,
    count_usage,
    distinct_client_sources,
    fetch_recent_usage,
    get_usage_high_watermark,
    init_db,
    log_usage,
    resolve_base_url_id,
    summarize_usage_by_provider,
    summarize_usage_by_source,
    summarize_usage_daily,
    summarize_usage_window,
)
from contextlib import asynccontextmanager
from pydantic import BaseModel


class ConfigUpdate(BaseModel):
    content: str


class ConnectivityTest(BaseModel):
    base_url: str
    api_key: str
    format: str  # "openai", "anthropic", "responses"
    model: str | None = None
    message: str | None = None


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
    return summarize_usage_daily(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
    )


@app.get("/usage/by-source")
async def usage_by_source(
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
):
    return summarize_usage_by_source(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
    )


@app.get("/usage/by-provider")
async def usage_by_provider(
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
):
    return summarize_usage_by_provider(
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
    if granularity == "hour":
        return aggregate_usage_by_period(
            since=since,
            until=until,
            provider=provider,
            model=model,
            client_source=client_source,
            granularity=granularity,
            tz_offset=tz_offset,
        )
    return aggregate_daily_by_period(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
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


@app.post("/test-connectivity")
async def test_connectivity(test: ConnectivityTest):
    url = test.base_url.rstrip("/")
    headers = {}
    payload = {}

    # Normalize: ensure /v1 is in the path
    if "/v1" not in url:
        url = f"{url}/v1"

    if test.format == "openai":
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        headers = {"Authorization": f"Bearer {test.api_key}"}
        payload = {
            "model": test.model or "gpt-5.4",
            "messages": [{"role": "user", "content": test.message or "What is 2 + 3?"}],
            "max_tokens": 10,
        }
    elif test.format == "anthropic":
        if not url.endswith("/messages"):
            url = f"{url}/messages"
        headers = {
            "x-api-key": test.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": test.model or "gpt-5.4",
            "messages": [{"role": "user", "content": test.message or "What is 2 + 3?"}],
            "max_tokens": 10,
        }
    elif test.format == "responses":
        if not url.endswith("/responses"):
            url = f"{url}/responses"
        headers = {"Authorization": f"Bearer {test.api_key}"}
        payload = {
            "model": test.model or "gpt-5.4",
            "messages": [{"role": "user", "content": test.message or "What is 2 + 3?"}],
            "max_tokens": 10,
        }
    else:
        raise HTTPException(
            status_code=400, detail=f"Unsupported format: {test.format}"
        )

    start_time = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            latency_ms = int((time.monotonic() - start_time) * 1000)

            try:
                body = response.json()
            except Exception:
                body = response.text

            return {
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "body": body,
                "url": url,
            }
    except Exception as e:
        return {
            "status_code": 0,
            "latency_ms": int((time.monotonic() - start_time) * 1000),
            "error": str(e),
            "url": url,
        }


if __name__ == "__main__":
    import uvicorn

    port = CONFIG["server"].get("api_port", CONFIG["server"]["port"] + 1)
    uvicorn.run(app, host=CONFIG["server"]["host"], port=port)
