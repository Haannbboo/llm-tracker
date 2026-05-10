import json
import os
import time
import tomllib
import yaml
import httpx
from decimal import Decimal
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from config.app import (
    CONFIG,
    CONFIG_PATH,
    refresh_runtime_config,
)
from .costs import calculate_costs
from .database import (
    Usage,
    aggregate_daily_by_dimension,
    aggregate_daily_by_period,
    aggregate_usage_by_period,
    count_sessions,
    count_usage,
    distinct_client_sources,
    fetch_recent_usage,
    fetch_sessions,
    get_usage_high_watermark,
    init_db,
    log_usage,
    resolve_base_url_id,
    summarize_sessions,
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
    session_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
):
    return fetch_recent_usage(
        limit=limit,
        offset=offset,
        provider=provider,
        model=model,
        client_source=client_source,
        session_id=session_id,
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
    session_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
):
    return {
        "total": count_usage(
            provider=provider,
            model=model,
            client_source=client_source,
            session_id=session_id,
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


@app.get("/usage/daily-by-dimension")
async def usage_daily_by_dimension(
    dimension: str = "model",
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
):
    return aggregate_daily_by_dimension(
        dimension=dimension,
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
    )


@app.get("/sessions")
async def get_sessions(
    client_source: str | None = None,
    since: str | None = None,
    until: str | None = None,
    sort_by: str = "ended",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
):
    sessions = fetch_sessions(
        client_source=client_source,
        since=since,
        until=until,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    total = count_sessions(
        client_source=client_source,
        since=since,
        until=until,
    )
    return {"sessions": sessions, "total": total}


@app.get("/sessions/summary")
async def get_sessions_summary(
    client_source: str | None = None,
    since: str | None = None,
    until: str | None = None,
):
    return summarize_sessions(
        client_source=client_source,
        since=since,
        until=until,
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


@app.get("/local/agents")
async def detect_local_agents():
    """Detect locally installed CLI agents. Only works when API has host access."""
    import shutil

    agents = {}
    for name in ("claude", "codex", "gemini"):
        path = shutil.which(name)
        agents[name] = {"found": path is not None, "path": path}
    return agents


def _local_setup_expected_endpoints() -> dict[str, str]:
    otlp_port = CONFIG["server"].get(
        "otlp_port", CONFIG["server"].get("port", 4000) + 2
    )
    base = f"http://localhost:{otlp_port}"
    return {"otlp_endpoint": base, "otlp_logs_endpoint": f"{base}/v1/logs"}


def _read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_toml_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _agent_health(
    configured: bool, configured_endpoint: str | None, expected_endpoint: str
) -> dict:
    endpoint_matches = configured and configured_endpoint == expected_endpoint
    if not configured:
        status = "missing_config"
    elif endpoint_matches:
        status = "ready"
    else:
        status = "wrong_endpoint"
    return {
        "configured": configured,
        "endpoint_matches": endpoint_matches,
        "configured_endpoint": configured_endpoint,
        "expected_endpoint": expected_endpoint,
        "status": status,
    }


@app.get("/local/setup-health")
async def get_local_setup_health():
    """Report local AI-agent OTLP config without returning secrets."""
    home = Path.home()
    expected = _local_setup_expected_endpoints()

    claude_settings = _read_json_file(home / ".claude" / "settings.json")
    claude_env = (
        claude_settings.get("env")
        if isinstance(claude_settings.get("env"), dict)
        else {}
    )
    claude_endpoint = claude_env.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")
    claude_configured = (
        claude_env.get("CLAUDE_CODE_ENABLE_TELEMETRY") in ("1", "true", "True", True)
        and claude_env.get("OTEL_LOGS_EXPORTER") == "otlp"
        and isinstance(claude_endpoint, str)
    )

    codex_config = _read_toml_file(home / ".codex" / "config.toml")
    codex_otel = (
        codex_config.get("otel") if isinstance(codex_config.get("otel"), dict) else {}
    )
    codex_exporter = (
        codex_otel.get("exporter", {})
        if isinstance(codex_otel.get("exporter"), dict)
        else {}
    )
    codex_otlp_http = (
        codex_exporter.get("otlp-http", {})
        if isinstance(codex_exporter.get("otlp-http"), dict)
        else {}
    )
    codex_endpoint = codex_otlp_http.get("endpoint")
    codex_disabled = (
        codex_otel.get("enabled") is False or codex_otlp_http.get("enabled") is False
    )
    codex_configured = not codex_disabled and isinstance(codex_endpoint, str)

    gemini_settings = _read_json_file(home / ".gemini" / "settings.json")
    gemini_telemetry = (
        gemini_settings.get("telemetry")
        if isinstance(gemini_settings.get("telemetry"), dict)
        else {}
    )
    gemini_endpoint = gemini_telemetry.get("otlpEndpoint")
    gemini_configured = gemini_telemetry.get("enabled") is True and isinstance(
        gemini_endpoint, str
    )

    agents = {
        "claude": _agent_health(
            claude_configured,
            claude_endpoint if isinstance(claude_endpoint, str) else None,
            expected["otlp_logs_endpoint"],
        ),
        "codex": _agent_health(
            codex_configured,
            codex_endpoint if isinstance(codex_endpoint, str) else None,
            expected["otlp_logs_endpoint"],
        ),
        "gemini": _agent_health(
            gemini_configured,
            gemini_endpoint if isinstance(gemini_endpoint, str) else None,
            expected["otlp_endpoint"],
        ),
    }
    return {
        "expected": expected,
        "summary": {
            "total_agents": len(agents),
            "configured_agents": sum(
                1 for agent in agents.values() if agent["configured"]
            ),
            "matching_agents": sum(
                1 for agent in agents.values() if agent["endpoint_matches"]
            ),
        },
        "agents": agents,
    }


# Serve built frontend if available (must come after all API routes)
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount(
        "/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend"
    )


if __name__ == "__main__":
    import uvicorn

    port = CONFIG["server"].get("api_port", CONFIG["server"]["port"] + 1)
    uvicorn.run(app, host=CONFIG["server"]["host"], port=port)
