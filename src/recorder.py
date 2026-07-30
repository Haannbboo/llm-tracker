"""Unified usage recording pipeline.

Both proxy and OTLP paths converge here for cost calculation, base URL
resolution, Usage construction, and persistence.
"""

from __future__ import annotations

import time

from sqlalchemy.exc import IntegrityError

from .costs import calculate_costs
from .database.base_url import resolve_base_url_id
from .database.models import ToolCall, Usage
from .database.usage import log_usage, merge_duplicate_usage


def record_usage(
    *,
    ts: int | None = None,
    provider: str,
    model: str,
    client_source: str | None = None,
    session_id: str | None = None,
    endpoint: str,
    prompt_tokens: int | None = None,
    prompt_length: int | None = None,
    completion_tokens: int | None = None,
    cached_tokens: int | None = None,
    cache_creation_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    tool_tokens: int | None = None,
    total_tokens: int | None = None,
    latency_ms: int | None = None,
    ttft_ms: int | None = None,
    status: int | None = None,
    client_ip: str | None = None,
    base_url: str | None = None,
    base_url_provider: str | None = None,
    base_url_source: str | None = None,
    db_path: str | None = None,
) -> Usage | None:
    """Record a single LLM usage event. Returns the Usage object, or None if skipped."""
    # Skip if successful and no token counts are available (None or zero).
    if status == 200 and not (
        prompt_tokens or completion_tokens or cached_tokens or total_tokens
    ):
        return None

    usage_ts = ts if ts is not None else time.time_ns() // 1000

    # Proxy and OTLP are independent collection paths for the same agent;
    # either can land first, so check for a same-shaped row already recorded
    # by the other path, enrich it, and return it instead of inserting a
    # duplicate (the caller can still attach tool calls to its id).
    duplicate = merge_duplicate_usage(
        client_source=client_source,
        is_otlp=(endpoint == "otlp"),
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
        total_tokens=total_tokens,
        ts=usage_ts,
        session_id=session_id,
        client_ip=client_ip,
        db_path=db_path,
    )
    if duplicate is not None:
        return duplicate

    costs = calculate_costs(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
        provider=provider,
        model=model,
    )
    base_url_id = resolve_base_url_id(
        base_url=base_url,
        db_path=db_path,
        provider_name=base_url_provider or provider,
        source=base_url_source,
    )

    usage = Usage(
        ts=usage_ts,
        provider=provider,
        model=model,
        client_source=client_source,
        session_id=session_id,
        endpoint=endpoint,
        prompt_tokens=prompt_tokens,
        prompt_length=prompt_length or 0,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
        cache_creation_tokens=cache_creation_tokens,
        reasoning_tokens=reasoning_tokens,
        tool_tokens=tool_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        ttft_ms=ttft_ms,
        status=status,
        client_ip=client_ip,
        base_url_id=base_url_id,
        **costs,
    )
    log_usage(usage, db_path=db_path)
    return usage


def normalize_tool_name(tool_name: str) -> str:
    """Fold tool name casing so e.g. `Bash`/`bash` aggregate as one tool."""
    return tool_name.lower()


def record_tool_call(
    *,
    tool_use_id: str,
    usage_id: str | None = None,
    session_id: str | None = None,
    tool_name: str,
    client_source: str | None = None,
    ts: int,
    db_path: str | None = None,
) -> None:
    """Record a tool call and update session tool_calls_json."""
    from sqlalchemy.orm import Session as SASession

    from .database import get_engine
    from .database.sessions import upsert_session_from_tool_call

    engine = get_engine(db_path)
    tc = ToolCall(
        tool_use_id=tool_use_id,
        usage_id=usage_id,
        session_id=session_id,
        tool_name=normalize_tool_name(tool_name),
        client_source=client_source,
        ts=ts,
    )
    with SASession(engine, expire_on_commit=False) as session:
        if session.get(ToolCall, tool_use_id) is not None:
            return  # already recorded; avoid double-counting on redelivery
        session.add(tc)
        try:
            session.commit()
        except IntegrityError:
            # Concurrent redelivery raced us to the same PK; already recorded.
            session.rollback()
            return
    upsert_session_from_tool_call(tc, db_path=db_path)
