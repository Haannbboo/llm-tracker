import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request

from config.app import CONFIG
from .database import init_db, log_usage

GEMINI_EVENT = "gemini_cli.api_response"
CLAUDE_EVENT = "api_request"
CODEX_EVENT = "codex.sse_event"
CODEX_API_REQUEST_EVENT = "codex.api_request"
CODEX_DEBUG_FILE = "/tmp/codex-otlp-debug.json"

# State cache for merging Codex events: conversation_id -> {duration_ms, ttft_ms, timestamp}
codex_state = {}


def _attr(attributes: list, key: str):
    """Extract a value from OTLP attribute list [{key, value: {stringValue|intValue|...}}]."""
    for a in attributes:
        if a.get("key") == key:
            v = a.get("value", {})
            if "intValue" in v:
                return int(v["intValue"])
            if "doubleValue" in v:
                return v["doubleValue"]
            if "stringValue" in v:
                return v["stringValue"]
            if "boolValue" in v:
                return v["boolValue"]
    return None


def _resource_attr(resource: dict, key: str):
    return _attr(resource.get("attributes", []), key)


def _parse_gemini_record(record: dict, attrs: list) -> None:
    time_ns = record.get("timeUnixNano", "0")
    ts = datetime.fromtimestamp(int(time_ns) / 1e9, tz=timezone.utc).isoformat()

    log_usage(
        CONFIG["db"]["path"],
        ts=ts,
        provider="google",
        model=_attr(attrs, "model") or "gemini-unknown",
        endpoint="generate-otlp",
        prompt_tokens=_attr(attrs, "input_token_count"),
        completion_tokens=_attr(attrs, "output_token_count"),
        cached_tokens=_attr(attrs, "cached_content_token_count"),
        reasoning_tokens=_attr(attrs, "thoughts_token_count"),
        tool_tokens=_attr(attrs, "tool_token_count"),
        total_tokens=_attr(attrs, "total_token_count"),
        latency_ms=_attr(attrs, "duration_ms"),
        ttft_ms=None,  # TODO: capture from gemini_cli.api.request.latency metric or BeforeModel hook
        cache_creation_tokens=None,
        status=_attr(attrs, "status_code"),
    )


def _parse_claude_record(record: dict, attrs: list) -> None:
    time_ns = record.get("timeUnixNano", "0")
    ts = datetime.fromtimestamp(int(time_ns) / 1e9, tz=timezone.utc).isoformat()

    input_tokens = _attr(attrs, "input_tokens")
    output_tokens = _attr(attrs, "output_tokens")
    cache_read = _attr(attrs, "cache_read_tokens")
    cache_create = _attr(attrs, "cache_creation_tokens")

    # prompt_tokens = raw input + cache reads (what the model actually processed)
    prompt_tokens = (int(input_tokens or 0)) + (int(cache_read or 0))

    total = prompt_tokens + int(output_tokens or 0) + int(cache_create or 0)

    log_usage(
        CONFIG["db"]["path"],
        ts=ts,
        provider="anthropic",
        model=_attr(attrs, "model") or "claude-unknown",
        endpoint="generate-otlp",
        prompt_tokens=prompt_tokens,
        completion_tokens=int(output_tokens) if output_tokens is not None else None,
        cached_tokens=int(cache_read) if cache_read is not None else None,
        cache_creation_tokens=int(cache_create) if cache_create is not None else None,
        reasoning_tokens=None,
        tool_tokens=None,
        total_tokens=total,
        latency_ms=_attr(attrs, "duration_ms"),
        ttft_ms=None,
        status=None,
    )


def _parse_codex_api_request(record: dict, attrs: list) -> None:
    conv_id = _attr(attrs, "conversation.id")
    duration = _attr(attrs, "duration_ms")
    if conv_id and duration is not None:
        if conv_id not in codex_state:
            codex_state[conv_id] = {"ts": time.time()}
        codex_state[conv_id]["duration_ms"] = int(duration)


def _parse_codex_record(record: dict, attrs: list) -> None:
    event_kind = _attr(attrs, "event.kind")
    conv_id = _attr(attrs, "conversation.id")

    if event_kind == "response.created":
        duration = _attr(attrs, "duration_ms")
        if conv_id and duration is not None:
            if conv_id not in codex_state:
                codex_state[conv_id] = {"ts": time.time()}
            codex_state[conv_id]["ttft_ms"] = int(duration)
        return

    if event_kind != "response.completed":
        return

    # Only parse if we have token counts (to avoid the other response.completed event)
    input_tokens = _attr(attrs, "input_token_count")
    if input_tokens is None:
        return

    time_ns = record.get("timeUnixNano", "0")
    if time_ns == "0":
        time_ns = record.get("observedTimeUnixNano", "0")

    ts = datetime.fromtimestamp(int(time_ns) / 1e9, tz=timezone.utc).isoformat()

    output_tokens = _attr(attrs, "output_token_count")
    cached_tokens = _attr(attrs, "cached_token_count")
    reasoning_tokens = _attr(attrs, "reasoning_token_count")
    tool_tokens = _attr(attrs, "tool_token_count")
    latency_ms = _attr(attrs, "duration_ms")
    ttft_ms = None

    # Try to get better latency and ttft from the state cache
    if conv_id in codex_state:
        state = codex_state[conv_id]
        if "duration_ms" in state:
            latency_ms = state["duration_ms"]
        if "ttft_ms" in state:
            ttft_ms = state["ttft_ms"]
        del codex_state[conv_id]

    prompt_tokens = int(input_tokens or 0)
    completion_tokens = int(output_tokens or 0)
    total_tokens = prompt_tokens + completion_tokens

    log_usage(
        CONFIG["db"]["path"],
        ts=ts,
        provider="openai",
        model=_attr(attrs, "model") or "codex-unknown",
        endpoint="generate-otlp",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=int(cached_tokens) if cached_tokens is not None else None,
        reasoning_tokens=int(reasoning_tokens)
        if reasoning_tokens is not None
        else None,
        tool_tokens=int(tool_tokens) if tool_tokens is not None else None,
        total_tokens=total_tokens,
        latency_ms=int(latency_ms) if latency_ms is not None else None,
        ttft_ms=int(ttft_ms) if ttft_ms is not None else None,
        cache_creation_tokens=None,
        status=None,
    )


def _parse_log_record(record: dict, service_name: str) -> None:
    attrs = record.get("attributes", [])
    event_name = _attr(attrs, "event.name") or ""

    if event_name == GEMINI_EVENT:
        _parse_gemini_record(record, attrs)
    elif event_name == CLAUDE_EVENT and service_name == "claude-code":
        _parse_claude_record(record, attrs)
    elif event_name == CODEX_EVENT and service_name == "codex_cli_rs":
        _parse_codex_record(record, attrs)
    elif event_name == CODEX_API_REQUEST_EVENT and service_name == "codex_cli_rs":
        _parse_codex_api_request(record, attrs)
    elif (
        service_name not in ("claude-code", "gemini-cli", "codex_cli_rs")
        and attrs
        and not os.path.exists(CODEX_DEBUG_FILE)
    ):
        # Capture first unknown-service payload with attributes to discover schema
        with open(CODEX_DEBUG_FILE, "w") as f:
            json.dump(
                {"service": service_name, "event": event_name, "record": record},
                f,
                indent=2,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(CONFIG["db"]["path"])
    yield


app = FastAPI(title="llm-tracker-otlp", lifespan=lifespan)


@app.post("/v1/logs")
async def receive_logs(request: Request):
    # Evict stale codex_state entries (older than 10 minutes)
    now = time.time()
    stale_keys = [k for k, v in codex_state.items() if now - v.get("ts", 0) > 600]
    for k in stale_keys:
        del codex_state[k]

    body = await request.json()
    for resource_log in body.get("resourceLogs", []):
        resource = resource_log.get("resource", {})
        service_name = _resource_attr(resource, "service.name") or ""
        # Dump first unrecognised resource block to discover service name
        if service_name not in (
            "claude-code",
            "gemini-cli",
            "codex_cli_rs",
        ) and not os.path.exists(CODEX_DEBUG_FILE + ".resource"):
            with open(CODEX_DEBUG_FILE + ".resource", "w") as f:
                json.dump(
                    {"service_name": service_name, "resource": resource}, f, indent=2
                )
        for scope_log in resource_log.get("scopeLogs", []):
            for record in scope_log.get("logRecords", []):
                _parse_log_record(record, service_name)
    return {}


@app.post("/v1/metrics")
async def receive_metrics():
    return {}


@app.post("/v1/traces")
async def receive_traces():
    return {}
