import asyncio
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
import tomllib
import yaml
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, model_validator
from starlette.middleware.base import BaseHTTPMiddleware

from config.app import (
    CONFIG,
    CONFIG_PATH,
    ResolvedCost,
    _apply_patch,
    _config_lock,
    refresh_runtime_config,
    set_evaluation_evaluator,
)
from config.server_config import load_server_config

from ._version import get_version
from .costs import resolve_cost_match
from .database import (
    VALID_OUTCOMES,
    VALID_SOURCES,
    User,
    aggregate_daily_by_dimension,
    aggregate_model_effectiveness,
    aggregate_usage_by_period,
    count_sessions,
    count_usage,
    daily_session_effectiveness_report,
    delete_session_evaluation,
    distinct_client_sources,
    distinct_tool_names,
    fetch_recent_usage,
    fetch_session_selector_rows,
    fetch_sessions,
    fetch_tool_calls,
    get_evaluation_job_progress,
    get_session_evaluation,
    get_usage_high_watermark_ts,
    init_db,
    list_active_evaluation_jobs_with_progress,
    list_session_evaluation_jobs_with_progress,
    resolve_token,
    summarize_session_tool_calls,
    summarize_sessions,
    summarize_tool_calls,
    summarize_usage_by_provider,
    summarize_usage_by_source,
    summarize_usage_daily,
    summarize_usage_window,
    update_queued_evaluation_job_evaluator,
    upsert_session_evaluation,
)
from .evaluation import (
    VALID_EVALUATOR_AGENTS,
    list_evaluator_agents,
    require_available_evaluator_type,
    start_session_evaluation_job,
)
from .evaluation_worker import load_evaluation_worker_config, run_evaluation_worker

logger = logging.getLogger(__name__)
EVALUATION_WORKER_SHUTDOWN_TIMEOUT_SECONDS = 5
USAGE_QUERY_LIMIT_MAX = 1000
LOCAL_CORS_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")


class ConfigUpdate(BaseModel):
    content: str


class ConfigPatch(BaseModel):
    path: list[str]
    op: Literal["set", "delete"]
    value: float | None = None

    @model_validator(mode="before")
    @classmethod
    def require_numeric_value_for_set(cls, data):
        if not isinstance(data, dict):
            return data
        if data.get("op") != "set":
            return data
        value = data.get("value")
        if value is None:
            raise ValueError("set patches require a numeric value")
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("set patches require a numeric value")
        return data


class ConfigPatchUpdate(BaseModel):
    patches: list[ConfigPatch]


def _runtime_config_payload(parsed_config: dict | None) -> dict:
    worker_config = load_evaluation_worker_config(parsed_config or {})
    return {
        "evaluation": {
            "evaluator": worker_config.evaluator,
            "evaluators": list_evaluator_agents(),
        },
    }


def _evaluation_metadata_payload() -> dict:
    worker_config = load_evaluation_worker_config()
    evaluators = list_evaluator_agents()
    default_evaluator = worker_config.evaluator
    default_available = any(
        evaluator["id"] == default_evaluator and evaluator["available"]
        for evaluator in evaluators
    )
    return {
        "evaluators": evaluators,
        "global_evaluator_type": default_evaluator,
        "global_evaluator_available": default_available,
    }


class ConnectivityTest(BaseModel):
    base_url: str
    api_key: str
    format: str  # "openai", "anthropic", "responses"
    model: str | None = None
    message: str | None = None


class SessionEvaluationUpdate(BaseModel):
    outcome: str
    source: str = "manual"
    confidence: float | None = None
    task_title: str | None = None
    task_title_zh: str | None = None
    summary: str | None = None
    evidence: list[str] = []
    failure_reason: str | None = None
    project: str | None = None


class EvaluateSessionWithLlmRequest(BaseModel):
    evaluator_type: str | None = None


class EvaluationJobUpdate(BaseModel):
    evaluator_type: str


class EvaluationConfigUpdate(BaseModel):
    evaluator: str


async def _stop_evaluation_worker(
    worker_task: asyncio.Task,
    *,
    timeout_seconds: float | None = None,
) -> None:
    timeout = (
        EVALUATION_WORKER_SHUTDOWN_TIMEOUT_SECONDS
        if timeout_seconds is None
        else timeout_seconds
    )
    done, _pending = await asyncio.wait({worker_task}, timeout=timeout)
    if done:
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        return

    worker_task.cancel()
    logger.warning("Evaluation worker shutdown timed out; cancelling worker task")
    done, _pending = await asyncio.wait({worker_task}, timeout=timeout)
    if done:
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        return
    logger.warning("Evaluation worker task did not finish after cancellation")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    stop_event = asyncio.Event()
    worker_task = asyncio.create_task(run_evaluation_worker(stop_event=stop_event))
    try:
        yield
    finally:
        stop_event.set()
        await _stop_evaluation_worker(worker_task)


app = FastAPI(title="llm-tracker-api", lifespan=lifespan)


def get_current_user(request: Request) -> User | None:
    """Resolve the request's bearer token to a user.

    Returns None when auth is disabled. When enabled, raises 401 for
    missing/malformed/unknown/revoked tokens (one message for all cases —
    callers must not learn which). DB errors propagate as 500: fail closed.
    """
    if not CONFIG.get("auth", {}).get("enabled"):
        return None
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="invalid token")
    resolved = resolve_token(token)
    if resolved is None:
        raise HTTPException(status_code=401, detail="invalid token")
    user, auth_token = resolved
    request.state.auth_token = auth_token
    return user


@app.get("/auth/me")
def auth_me(request: Request, user: User | None = Depends(get_current_user)):
    if user is None:
        return {"auth_enabled": False, "user": None}
    auth_token = request.state.auth_token
    return {
        "auth_enabled": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "created_at": user.created_at,
        },
        "token": (
            {"kind": auth_token.kind, "device_name": auth_token.device_name}
            if auth_token
            else None
        ),
    }


def _is_usage_read_path(path: str) -> bool:
    return path == "/usage" or path.startswith("/usage/")


def _add_usage_cors_headers(response: Response, origin: str) -> Response:
    response.headers["Access-Control-Allow-Origin"] = origin
    vary = response.headers.get("Vary")
    if vary:
        vary_tokens = [token.strip() for token in vary.split(",") if token.strip()]
        if "Origin" not in vary_tokens:
            vary_tokens.append("Origin")
        response.headers["Vary"] = ", ".join(vary_tokens)
    else:
        response.headers["Vary"] = "Origin"
    return response


@app.middleware("http")
async def usage_read_cors(request: Request, call_next):
    origin = request.headers.get("origin")
    allow_origin = origin is not None and LOCAL_CORS_ORIGIN_RE.fullmatch(origin)
    if not allow_origin or not _is_usage_read_path(request.url.path):
        return await call_next(request)

    if request.method == "OPTIONS":
        requested_method = request.headers.get("access-control-request-method", "")
        if requested_method.upper() == "GET":
            response = Response(status_code=204)
            _add_usage_cors_headers(response, origin)  # type: ignore[arg-type]
            response.headers["Access-Control-Allow-Methods"] = "GET"
            response.headers["Access-Control-Allow-Headers"] = request.headers.get(
                "access-control-request-headers",
                "",
            )
            return response
        return await call_next(request)

    response = await call_next(request)
    if request.method == "GET":
        _add_usage_cors_headers(response, origin)  # type: ignore[arg-type]
    return response


@app.get("/usage")
async def get_usage(
    limit: int = Query(100, ge=0, le=USAGE_QUERY_LIMIT_MAX),
    offset: int = Query(0, ge=0),
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    session_id: str | None = None,
    tool_name: str | None = None,
    since: str | None = None,
    until: str | None = None,
    only_failed: bool = False,
    status_429: bool = False,
    status_4xx: bool = False,
    status_5xx: bool = False,
):
    return fetch_recent_usage(
        limit=limit,
        offset=offset,
        provider=provider,
        model=model,
        client_source=client_source,
        session_id=session_id,
        tool_name=tool_name,
        since=since,
        until=until,
        only_failed=only_failed,
        status_429=status_429,
        status_4xx=status_4xx,
        status_5xx=status_5xx,
    )


@app.get("/usage/count")
async def get_usage_count(
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    session_id: str | None = None,
    tool_name: str | None = None,
    since: str | None = None,
    until: str | None = None,
):
    return {
        "total": count_usage(
            provider=provider,
            model=model,
            client_source=client_source,
            session_id=session_id,
            tool_name=tool_name,
            since=since,
            until=until,
        )
    }


@app.get("/usage/high-watermark")
async def usage_high_watermark():
    return {"ts": get_usage_high_watermark_ts()}


@app.get("/usage/sources")
async def usage_sources(
    since: str | None = None,
    until: str | None = None,
):
    return distinct_client_sources(since=since, until=until)


@app.get("/usage/tools")
async def usage_tools(
    since: str | None = None,
    until: str | None = None,
):
    return distinct_tool_names(since=since, until=until)


@app.get("/usage/run-summary")
async def usage_run_summary(
    after_ts: int = 0,
    until_ts: int | None = None,
    since: str | None = None,
    until: str | None = None,
    client_source: str | None = None,
    session_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    include_rows: bool = False,
):
    return summarize_usage_window(
        after_ts=after_ts,
        until_ts=until_ts,
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


@app.get("/usage/by-tool")
async def usage_by_tool(
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    only_failed: bool = False,
    status_429: bool = False,
    status_4xx: bool = False,
    status_5xx: bool = False,
):
    return summarize_tool_calls(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
        only_failed=only_failed,
        status_429=status_429,
        status_4xx=status_4xx,
        status_5xx=status_5xx,
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
    return aggregate_usage_by_period(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
        granularity=granularity,
        tz_offset=tz_offset,
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
    view: str = "summary",
    sort_by: str = "ended",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    hide_noop: bool = False,
):
    if view not in {"summary", "selector"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid view. Must be one of ['summary', 'selector']",
        )

    if view == "selector":
        return {
            "sessions": fetch_session_selector_rows(
                client_source=client_source,
                since=since,
                until=until,
                sort_by=sort_by,
                sort_order=sort_order,
                limit=limit,
                offset=offset,
                hide_noop=hide_noop,
            ),
            "total": None,
        }

    sessions = fetch_sessions(
        client_source=client_source,
        since=since,
        until=until,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
        hide_noop=hide_noop,
    )
    total = count_sessions(
        client_source=client_source,
        since=since,
        until=until,
        hide_noop=hide_noop,
    )
    return {"sessions": sessions, "total": total}


@app.get("/sessions/summary")
async def get_sessions_summary(
    client_source: str | None = None,
    since: str | None = None,
    until: str | None = None,
    hide_noop: bool = False,
):
    return summarize_sessions(
        client_source=client_source,
        since=since,
        until=until,
        hide_noop=hide_noop,
    )


@app.get("/model-effectiveness")
async def model_effectiveness(
    since: str | None = None,
    until: str | None = None,
    client_source: str | None = None,
    group_by: str = "model",
    hide_noop: bool = False,
):
    if group_by not in {"model", "source", "provider"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid group_by. Must be one of ['model', 'provider', 'source']",
        )
    return aggregate_model_effectiveness(
        group_by=group_by,
        since=since,
        until=until,
        client_source=client_source,
        hide_noop=hide_noop,
    )


@app.get("/sessions/daily-effectiveness")
async def sessions_daily_effectiveness(date: str):
    try:
        return daily_session_effectiveness_report(date=date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/sessions/{session_id}/evaluation")
async def put_session_evaluation(session_id: str, update: SessionEvaluationUpdate):
    if update.outcome not in VALID_OUTCOMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid outcome: {update.outcome}. Must be one of {sorted(VALID_OUTCOMES)}",
        )
    if update.source not in VALID_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source: {update.source}. Must be one of {sorted(VALID_SOURCES)}",
        )
    if update.source != "manual":
        raise HTTPException(
            status_code=400,
            detail="Manual evaluation endpoint only accepts source 'manual'. Use the LLM evaluation endpoint for LLM-sourced results.",
        )
    try:
        upsert_session_evaluation(
            session_id=session_id,
            outcome=update.outcome,
            source=update.source,
            confidence=update.confidence,
            task_title=update.task_title,
            task_title_zh=update.task_title_zh,
            summary=update.summary,
            evidence=update.evidence,
            failure_reason=update.failure_reason,
            project=update.project,
        )
    except ValueError as e:
        if "Session not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise
    return {"status": "success"}


@app.get("/sessions/{session_id}/evaluation")
async def get_evaluation(session_id: str):
    evaluation = get_session_evaluation(session_id)
    return {"evaluation": evaluation}


@app.delete("/sessions/{session_id}/evaluation")
async def delete_evaluation(session_id: str):
    deleted = delete_session_evaluation(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}


@app.post("/sessions/{session_id}/evaluate-with-llm", status_code=202)
async def evaluate_session_with_llm(
    session_id: str,
    request: EvaluateSessionWithLlmRequest | None = None,
):
    configured_evaluator = load_evaluation_worker_config().evaluator
    evaluator_type = (
        request.evaluator_type if request else None
    ) or configured_evaluator
    try:
        evaluator_type = require_available_evaluator_type(evaluator_type)
        return start_session_evaluation_job(
            session_id,
            trigger="manual",
            evaluator_type=evaluator_type,
        )
    except ValueError as e:
        message = str(e)
        if "Session not found" in message:
            raise HTTPException(status_code=404, detail=message)
        if "Unsupported session source" in message:
            raise HTTPException(status_code=400, detail=message)
        if (
            "Unsupported evaluator agent" in message
            or "Evaluator not available" in message
        ):
            raise HTTPException(status_code=400, detail=message)
        if "Manual evaluation exists" in message:
            raise HTTPException(status_code=409, detail=message)
        raise


@app.get("/poll/{job_id}")
async def poll_job(job_id: str):
    job = get_evaluation_job_progress(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/evaluation-jobs/active")
async def active_evaluation_jobs(session_ids: str | None = None):
    parsed_session_ids = [
        item for item in (session_ids or "").split(",") if item
    ] or None
    jobs = list_active_evaluation_jobs_with_progress(
        session_ids=parsed_session_ids,
    )
    return {
        "jobs": {job["session_id"]: job for job in jobs},
        **_evaluation_metadata_payload(),
    }


@app.get("/sessions/{session_id}/evaluation-jobs")
async def session_evaluation_jobs(session_id: str):
    return {
        "jobs": list_session_evaluation_jobs_with_progress(session_id),
        **_evaluation_metadata_payload(),
    }


@app.patch("/evaluation-jobs/{job_id}")
async def update_evaluation_job(job_id: str, update: EvaluationJobUpdate):
    current = get_evaluation_job_progress(job_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if current["status"] != "queued":
        raise HTTPException(
            status_code=409,
            detail="Only queued evaluation jobs can change evaluator",
        )

    try:
        evaluator_type = require_available_evaluator_type(update.evaluator_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    updated = update_queued_evaluation_job_evaluator(
        job_id,
        evaluator_type=evaluator_type,
    )
    if updated is None:
        raise HTTPException(
            status_code=409,
            detail="Only queued evaluation jobs can change evaluator",
        )
    refreshed = get_evaluation_job_progress(job_id)
    return refreshed or updated


@app.get("/usage/{usage_id}/tool-calls")
async def get_usage_tool_calls(usage_id: str):
    return fetch_tool_calls(usage_id=usage_id)


@app.get("/sessions/{session_id}/tool-calls")
async def get_session_tool_calls(session_id: str):
    return fetch_tool_calls(session_id=session_id)


@app.get("/sessions/{session_id}/tool-calls/summary")
async def get_session_tool_calls_summary(session_id: str):
    summary = summarize_session_tool_calls(session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return summary


@app.get("/config")
async def get_config():
    path = os.path.expanduser(CONFIG_PATH)
    if not os.path.exists(path):
        parsed: dict = {}
        return {
            "content": "",
            "parsed": parsed,
            "runtime": _runtime_config_payload(parsed),
        }
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        try:
            parsed = yaml.safe_load(content) or {}
        except yaml.YAMLError:
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        return {
            "content": content,
            "parsed": parsed,
            "runtime": _runtime_config_payload(parsed),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _notify_proxy_refresh() -> None:
    """Ask the proxy process to reload its runtime config.

    Fire-and-forget: failures are logged but never surfaced to the caller.
    """
    try:
        server = load_server_config()
        proxy_url = f"http://{server.host}:{server.port}/config/refresh"
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(proxy_url)
    except Exception:
        logging.getLogger(__name__).warning(
            "Failed to notify proxy to refresh config", exc_info=True
        )


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
        asyncio.create_task(_notify_proxy_refresh())
        return {"status": "success"}
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/config")
async def patch_config(update: ConfigPatchUpdate):
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError as RuamelYAMLError

    path = os.path.expanduser(CONFIG_PATH)
    yaml_parser = YAML()
    yaml_parser.preserve_quotes = True

    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                config = yaml_parser.load(f) or {}
        else:
            config = {}

        if not isinstance(config, dict):
            raise HTTPException(
                status_code=400,
                detail="Config root must be a YAML mapping",
            )

        for patch in update.patches:
            _apply_patch(config, patch.path, patch.op, patch.value)

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml_parser.dump(config, f)

        refresh_runtime_config(path)
        asyncio.create_task(_notify_proxy_refresh())
        return {"status": "success"}
    except RuamelYAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/config/evaluation")
async def update_evaluation_config(update: EvaluationConfigUpdate):
    """Update the global evaluator type in config.yaml."""
    if update.evaluator not in VALID_EVALUATOR_AGENTS:
        raise HTTPException(
            status_code=400, detail=f"Invalid evaluator: {update.evaluator}"
        )
    try:
        set_evaluation_evaluator(update.evaluator)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"global_evaluator_type": update.evaluator}


def _pricing_entry(resolved_cost, scope: str, multiplier: float) -> dict:
    cost = resolved_cost.cost
    return {
        "input": cost.input,
        "output": cost.output,
        "cache_read": cost.cache_read,
        "cache_write": cost.cache_write,
        "tiers": [
            {
                "min_tokens": tier.min_tokens,
                "max_tokens": tier.max_tokens,
                "input": tier.input,
                "output": tier.output,
                "cache_read": tier.cache_read,
            }
            for tier in cost.tiers
        ],
        "source": resolved_cost.source,
        "scope": scope,
        "effective_input": cost.input * multiplier,
        "effective_output": cost.output * multiplier,
        "effective_cache_read": cost.cache_read * multiplier,
        "effective_cache_write": (
            cost.cache_write * multiplier if cost.cache_write is not None else None
        ),
        "multiplier": multiplier,
    }


def _resolve_provider_multiplier(config_snapshot: dict, provider: str | None) -> float:
    if provider is None:
        return 1.0
    provider_config = config_snapshot.get("providers", {}).get(provider, {})
    if not isinstance(provider_config, dict):
        return 1.0
    return float(provider_config.get("price_multiplier", 1.0))


@app.get("/pricing")
async def get_pricing(provider: str | None = None):
    """Return all models with resolved pricing and source metadata."""
    from config.app import resolve_all_costs
    from config.pricing import get_remote_pricing

    with _config_lock:
        config_snapshot = dict(CONFIG)

    resolved = resolve_all_costs(config_snapshot, get_remote_pricing())
    result: dict[str, dict] = {}

    if provider is not None:
        multiplier = _resolve_provider_multiplier(config_snapshot, provider)

        for key, resolved_cost in resolved.global_costs.items():
            result[key] = _pricing_entry(resolved_cost, "global", multiplier)

        for key, resolved_cost in resolved.provider_costs.get(provider, {}).items():
            result[key] = _pricing_entry(resolved_cost, provider, multiplier)

        return result

    for key, resolved_cost in resolved.global_costs.items():
        result[key] = _pricing_entry(resolved_cost, "global", 1.0)

    for provider_name, costs in resolved.provider_costs.items():
        for key, resolved_cost in costs.items():
            result[key] = _pricing_entry(resolved_cost, provider_name, 1.0)

    return result


@app.get("/pricing/{model:path}")
async def get_model_pricing(model: str, provider: str | None = None):
    """Return resolved pricing for a single model.

    Follows the same resolution used at record time: config overrides first,
    then LiteLLM, with a containing-name fallback when no exact match exists.
    """
    from config.app import resolve_all_costs
    from config.pricing import get_remote_pricing

    if not model:
        raise HTTPException(status_code=422, detail="model must not be empty")

    with _config_lock:
        config_snapshot = dict(CONFIG)

    resolved = resolve_all_costs(config_snapshot, get_remote_pricing())
    model_costs = {key: rc.cost for key, rc in resolved.global_costs.items()}
    provider_model_costs = {
        provider_name: {key: rc.cost for key, rc in costs.items()}
        for provider_name, costs in resolved.provider_costs.items()
    }

    multiplier = _resolve_provider_multiplier(config_snapshot, provider)

    match = resolve_cost_match(provider, model, model_costs, provider_model_costs)
    if match is None:
        return {
            "model": model,
            "provider": provider,
            "resolved": False,
            "scope": None,
            "source": None,
            "input": 0.0,
            "output": 0.0,
            "cache_read": 0.0,
            "cache_write": None,
            "tiers": [],
            "effective_input": 0.0,
            "effective_output": 0.0,
            "effective_cache_read": 0.0,
            "effective_cache_write": None,
            "multiplier": multiplier,
        }

    if match.scope == "provider" and provider is not None:
        source = resolved.provider_costs[provider][match.key].source
        scope = provider
    else:
        source = resolved.global_costs[match.key].source
        scope = "global"

    return {
        "model": match.key,
        "provider": provider,
        "resolved": True,
        **_pricing_entry(
            ResolvedCost(cost=match.cost, source=source), scope, multiplier
        ),
    }


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
    from pathlib import Path

    # Kilo's install script adds ~/.kilo/bin to PATH via ~/.zshrc, but
    # the supervisor service runs without sourcing .zshrc so it lacks this
    # directory. Other agents (claude, codex, gemini, opencode) are found via
    # ~/superset/bin which IS on the supervisor PATH, so only Kilo needs
    # a fallback path check.
    kilo_fallback = str(Path.home() / ".kilo" / "bin" / "kilo")

    agents = {}
    for name in ("claude", "codex", "gemini", "opencode", "kilo"):
        path = shutil.which(name)
        if path is None and name == "kilo":
            path = kilo_fallback if Path(kilo_fallback).exists() else None
        agents[name] = {"found": path is not None, "path": path}
    return agents


def _local_setup_expected_endpoints() -> dict[str, str]:
    from config.server_config import resolve_server_urls

    urls = resolve_server_urls(CONFIG)
    base = urls["otlp_url"]
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

    opencode_config_path = home / ".config" / "opencode" / "opencode.json"
    opencode_config = _read_json_file(opencode_config_path)
    opencode_plugins = opencode_config.get("plugin", [])
    opencode_endpoint = None
    opencode_plugin_registered = False
    opencode_plugin_suffixes = ("plugins/opencode/dist/index.js",)
    _otlp_host = (
        CONFIG["server"]
        .get("base_url", "")
        .rstrip("/")
        .replace("http://", "")
        .replace("https://", "")
        if CONFIG["server"].get("base_url")
        else "localhost"
    )
    opencode_default_endpoint = f"http://{_otlp_host}:4005/v1/logs"
    if isinstance(opencode_plugins, list):
        for entry in opencode_plugins:
            entry_path = (
                str(entry)
                if isinstance(entry, str)
                else str(entry[0])
                if isinstance(entry, list) and len(entry) >= 1
                else ""
            )
            matched_suffix = next(
                (s for s in opencode_plugin_suffixes if entry_path.endswith(s)),
                None,
            )
            if matched_suffix is None:
                continue
            opencode_plugin_registered = True
            if isinstance(entry, str):
                opencode_endpoint = opencode_default_endpoint
            elif (
                isinstance(entry, list)
                and len(entry) >= 2
                and isinstance(entry[1], dict)
            ):
                opencode_endpoint = (
                    entry[1].get("endpoint") or opencode_default_endpoint
                )
            else:
                opencode_endpoint = opencode_default_endpoint
            break

    kilo_config_path = home / ".config" / "kilo" / "opencode.json"
    kilo_config = _read_json_file(kilo_config_path)
    kilo_plugins = kilo_config.get("plugin", [])
    kilo_endpoint = None
    kilo_plugin_registered = False
    kilo_plugin_suffix = "plugins/kilo/dist/index.js"
    kilo_default_endpoint = f"http://{_otlp_host}:4005/v1/logs"
    if isinstance(kilo_plugins, list):
        for entry in kilo_plugins:
            entry_path = (
                str(entry)
                if isinstance(entry, str)
                else str(entry[0])
                if isinstance(entry, list) and len(entry) >= 1
                else ""
            )
            if not entry_path.endswith(kilo_plugin_suffix):
                continue
            kilo_plugin_registered = True
            if isinstance(entry, str):
                kilo_endpoint = kilo_default_endpoint
            elif (
                isinstance(entry, list)
                and len(entry) >= 2
                and isinstance(entry[1], dict)
            ):
                kilo_endpoint = entry[1].get("endpoint") or kilo_default_endpoint
            else:
                kilo_endpoint = kilo_default_endpoint
            break

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
        "opencode": _agent_health(
            opencode_plugin_registered,
            opencode_endpoint,
            expected["otlp_logs_endpoint"],
        ),
        "kilo": _agent_health(
            kilo_plugin_registered,
            kilo_endpoint,
            expected["otlp_logs_endpoint"],
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


@app.get("/version")
async def version():
    """Return API version information."""
    return {
        "name": app.title,
        "version": get_version(),
    }


# Serve built frontend if available (must come after all API routes)
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    _index_html = _frontend_dist / "index.html"

    _SPA_API_PREFIXES = (
        "/auth/",
        "/usage",
        "/sessions",
        "/model-effectiveness",
        "/poll/",
        "/evaluation-jobs",
        "/config",
        "/pricing",
        "/local/",
        "/test-connectivity",
        "/version",
    )

    class SPACatchAllMiddleware(BaseHTTPMiddleware):
        """Rewrite non-API, non-file requests to /index.html for SPA routing."""

        async def dispatch(self, request: Request, call_next):
            path = request.url.path
            requested = path.lstrip("/")
            if (
                request.method in ("GET", "HEAD")
                and _index_html.is_file()
                and not any(path.startswith(p) for p in _SPA_API_PREFIXES)
                and not Path(requested).suffix
                and not (_frontend_dist / requested).is_file()
            ):
                request.scope["path"] = "/index.html"
            return await call_next(request)

    app.add_middleware(SPACatchAllMiddleware)
    app.mount(
        "/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend"
    )


if __name__ == "__main__":
    import uvicorn

    port = CONFIG["server"].get("api_port", CONFIG["server"]["port"] + 1)
    uvicorn.run(app, host=CONFIG["server"]["host"], port=port)
