import json
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import FastAPI, Request

from config.app import CONFIG
from .database import init_db, log_usage
from .provider_parser import parse_provider

GEMINI_EVENT = "gemini_cli.api_response"
CLAUDE_EVENT = "claude_code.api_request"
CODEX_EVENT = "codex.sse_event"
CODEX_API_REQUEST_EVENT = "codex.api_request"
CODEX_DEBUG_FILE = "/tmp/codex-otlp-debug.json"
GEMINI_HOOK_DIR = os.path.join(os.environ.get("TMPDIR", "/tmp"), "llm-tracker-gemini")

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


@dataclass
class _PromptLengthState:
    """Queued prompt-length values waiting for the matching usage event."""

    values: list[int] = field(default_factory=list)
    ts: float = 0.0


class PromptLengthTracker:
    """Tracks prompt-event lengths until the later OTLP usage event is written."""

    def __init__(self, prompt_events: set[str]):
        self._prompt_events = prompt_events
        self._state: dict[str, _PromptLengthState] = {}

    def record_prompt_event(
        self, service_name: str, attrs: list, session_id: str
    ) -> None:
        """Store prompt_length from prompt-only events for later usage rows."""
        prompt_length = _attr(attrs, "prompt_length")
        if prompt_length is None:
            return

        event_name = _attr(attrs, "event.name") or ""
        if event_name not in self._prompt_events:
            return

        key = self._key_for(service_name, attrs, session_id)
        if key is None:
            return

        state = self._state.setdefault(key, _PromptLengthState())
        state.ts = time.time()
        state.values.append(int(prompt_length))

    def consume_for_usage_event(
        self, service_name: str, attrs: list, session_id: str
    ) -> int:
        """Return the prompt length for a usage row, preferring an inline value when present."""
        prompt_length = _attr(attrs, "prompt_length")
        if prompt_length is not None:
            return int(prompt_length)

        key = self._key_for(service_name, attrs, session_id)
        if key is None:
            return 0

        state = self._state.get(key)
        if not state:
            return 0

        if not state.values:
            del self._state[key]
            return 0

        value = state.values.pop(0)
        if not state.values:
            del self._state[key]
        return value

    def evict_stale(self, ttl_seconds: int = 600) -> None:
        """Drop old correlation entries so prompt-only events cannot accumulate forever."""
        now = time.time()
        stale_keys = [
            key for key, state in self._state.items() if now - state.ts > ttl_seconds
        ]
        for key in stale_keys:
            del self._state[key]

    def _key_for(self, service_name: str, attrs: list, session_id: str) -> str | None:
        """Build a stable correlation key from the strongest ID the client exposes."""
        prompt_id = _attr(attrs, "prompt.id") or _attr(attrs, "prompt_id")
        if prompt_id:
            return f"{service_name}:prompt:{prompt_id}"

        conversation_id = _attr(attrs, "conversation.id")
        if conversation_id:
            return f"{service_name}:conversation:{conversation_id}"

        attr_session_id = _attr(attrs, "session.id") or session_id
        if attr_session_id:
            return f"{service_name}:session:{attr_session_id}"

        return None


PROMPT_LENGTH_TRACKER = PromptLengthTracker(
    {"user_prompt", "codex.user_prompt", "gemini_cli.user_prompt"}
)


def _consume_hook_ttft(hook_dir: str, session_id: str) -> tuple[int | None, int | None]:
    if not session_id:
        return None, None

    queue_path = os.path.join(hook_dir, f"queue-{session_id}.jsonl")
    try:
        with open(queue_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return None, None

    if not lines:
        return None, None

    entry_line = lines[0]
    remaining = lines[1:]
    if remaining:
        with open(queue_path, "w", encoding="utf-8") as f:
            f.writelines(remaining)
    else:
        try:
            os.unlink(queue_path)
        except OSError:
            pass

    try:
        entry = json.loads(entry_line)
    except json.JSONDecodeError:
        return None, None

    ttft_ms = entry.get("ttft_ms")
    latency_ms = entry.get("latency_ms")
    return (
        int(ttft_ms) if ttft_ms is not None else None,
        int(latency_ms) if latency_ms is not None else None,
    )


def _parse_gemini_record(record: dict, attrs: list, session_id: str) -> None:
    time_ns = record.get("timeUnixNano", "0")
    ts = datetime.fromtimestamp(int(time_ns) / 1e9, tz=timezone.utc).isoformat()

    input_tokens = _attr(attrs, "input_token_count")
    visible_tokens = _attr(attrs, "output_token_count")
    thoughts_tokens = _attr(attrs, "thoughts_token_count")
    tool_tokens = _attr(attrs, "tool_token_count")

    completion_total = (
        int(visible_tokens or 0) + int(thoughts_tokens or 0) + int(tool_tokens or 0)
    )
    model = _attr(attrs, "model") or "gemini-unknown"
    role = _attr(attrs, "role") or ""
    sid = _attr(attrs, "session.id") or session_id
    ttft_ms, hook_latency_ms = (
        _consume_hook_ttft(GEMINI_HOOK_DIR, sid) if role == "main" else (None, None)
    )
    latency_ms = _attr(attrs, "duration_ms")
    prompt_tokens = int(input_tokens) if input_tokens is not None else None
    prompt_length = PROMPT_LENGTH_TRACKER.consume_for_usage_event(
        "gemini-cli", attrs, sid
    )

    log_usage(
        CONFIG["db"]["url"],
        ts=ts,
        provider=parse_provider("gemini"),
        model=model,
        endpoint="generate-otlp",
        prompt_tokens=prompt_tokens,
        prompt_length=prompt_length,
        completion_tokens=completion_total,
        cached_tokens=_attr(attrs, "cached_content_token_count"),
        reasoning_tokens=thoughts_tokens,
        tool_tokens=tool_tokens,
        total_tokens=_attr(attrs, "total_token_count"),
        latency_ms=latency_ms if latency_ms is not None else hook_latency_ms,
        ttft_ms=ttft_ms,
        cache_creation_tokens=None,
        status=_attr(attrs, "status_code"),
    )


def _parse_claude_record(record: dict, attrs: list, session_id: str) -> None:
    time_ns = record.get("timeUnixNano", "0")
    ts = datetime.fromtimestamp(int(time_ns) / 1e9, tz=timezone.utc).isoformat()

    input_tokens = _attr(attrs, "input_tokens")
    output_tokens = _attr(attrs, "output_tokens")
    cache_read = _attr(attrs, "cache_read_tokens")
    cache_create = _attr(attrs, "cache_creation_tokens")

    # prompt_tokens = raw input + cache reads (what the model actually processed)
    prompt_tokens = (int(input_tokens or 0)) + (int(cache_read or 0))
    prompt_length = PROMPT_LENGTH_TRACKER.consume_for_usage_event(
        "claude-code", attrs, session_id
    )

    total = prompt_tokens + int(output_tokens or 0) + int(cache_create or 0)
    log_usage(
        CONFIG["db"]["url"],
        ts=ts,
        provider=parse_provider("claude"),
        model=_attr(attrs, "model") or "claude-unknown",
        endpoint="generate-otlp",
        prompt_tokens=prompt_tokens,
        prompt_length=prompt_length,
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
    prompt_length = PROMPT_LENGTH_TRACKER.consume_for_usage_event(
        "codex_cli_rs", attrs, ""
    )

    log_usage(
        CONFIG["db"]["url"],
        ts=ts,
        provider=parse_provider("codex"),
        model=_attr(attrs, "model") or "codex-unknown",
        endpoint="generate-otlp",
        prompt_tokens=prompt_tokens,
        prompt_length=prompt_length,
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


def _parse_log_record(record: dict, service_name: str, session_id: str) -> None:
    attrs = record.get("attributes", [])
    PROMPT_LENGTH_TRACKER.record_prompt_event(service_name, attrs, session_id)
    event_name = _attr(attrs, "event.name") or ""

    if event_name == GEMINI_EVENT:
        _parse_gemini_record(record, attrs, session_id)
    elif (
        event_name == CLAUDE_EVENT or event_name == "api_request"
    ) and service_name == "claude-code":
        _parse_claude_record(record, attrs, session_id)
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
    init_db(CONFIG["db"]["url"])
    yield


app = FastAPI(title="llm-tracker-otlp", lifespan=lifespan)


@app.post("/v1/logs")
async def receive_logs(request: Request):
    # Evict stale codex_state entries (older than 10 minutes)
    now = time.time()
    stale_keys = [k for k, v in codex_state.items() if now - v.get("ts", 0) > 600]
    for k in stale_keys:
        del codex_state[k]
    PROMPT_LENGTH_TRACKER.evict_stale()

    body = await request.json()
    for resource_log in body.get("resourceLogs", []):
        resource = resource_log.get("resource", {})
        service_name = _resource_attr(resource, "service.name") or ""
        session_id = _resource_attr(resource, "session.id") or ""
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
                _parse_log_record(record, service_name, session_id)
    return {}


@app.post("/v1/metrics")
async def receive_metrics(request: Request):
    return {}


@app.post("/v1/traces")
async def receive_traces(request: Request):
    return {}
