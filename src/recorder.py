"""Unified usage recording pipeline.

Both proxy and OTLP paths converge here for cost calculation, base URL
resolution, Usage construction, and persistence.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .database.base_url import resolve_base_url_id
from .database.models import ToolCall, Usage
from .database.usage import log_usage, merge_duplicate_usage
from .pricing.costs import ResolvedPricing, calculate_costs, resolve_pricing
from .pricing.models import normalize_model_cost_key
from .pricing.snapshots import ensure_price_snapshot
from .utils import micros_to_secs

log = logging.getLogger(__name__)


def record_usage(
    *,
    ts: int | None = None,
    provider: str,
    model: str,
    user_id: str | None = None,
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
        cache_creation_tokens=cache_creation_tokens,
        ts=usage_ts,
        session_id=session_id,
        client_ip=client_ip,
        user_id=user_id,
        db_path=db_path,
    )
    if duplicate is not None:
        return duplicate

    resolved = resolve_pricing(provider, model, usage_ts)
    costs = calculate_costs(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
        cache_creation_tokens=cache_creation_tokens,
        provider=provider,
        model=model,
        model_cost=resolved.cost,
        multiplier=resolved.multiplier,
    )
    base_url_id = resolve_base_url_id(
        base_url=base_url,
        db_path=db_path,
        provider_name=base_url_provider or provider,
        source=base_url_source,
    )

    # Snapshot the pricing that was in effect so the row's cost split can be
    # recomputed exactly later. Best-effort: a snapshot failure must never turn
    # a persisted usage row into a failed request.
    snapshot_id = _record_price_snapshot(resolved, provider, model, usage_ts, db_path)

    usage = Usage(
        ts=usage_ts,
        provider=provider,
        model=model,
        user_id=user_id,
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
        price_snapshot_id=snapshot_id,
        **costs,
    )
    log_usage(usage, db_path=db_path)
    return usage


def _record_price_snapshot(
    resolved: ResolvedPricing,
    provider: str,
    model: str,
    usage_ts: int,
    db_path: str | None,
) -> int | None:
    """Persist the exact rates used for this row, returning the snapshot id."""
    if resolved.match is None:
        return None
    date = datetime.fromtimestamp(micros_to_secs(usage_ts), tz=timezone.utc).strftime(
        "%Y-%m-%d"
    )
    try:
        return ensure_price_snapshot(
            date=date,
            provider=provider,
            model=normalize_model_cost_key(model),
            source=resolved.source or "unknown",
            cost=resolved.cost,
            multiplier=resolved.multiplier,
            db_path=db_path,
        )
    except Exception:
        log.warning("Failed to record price snapshot for %s/%s", provider, model)
        return None


def normalize_tool_name(tool_name: str) -> str:
    """Fold tool name casing so e.g. `Bash`/`bash` aggregate as one tool."""
    return tool_name.lower()


def record_tool_call(
    *,
    tool_use_id: str,
    usage_id: str | None = None,
    session_id: str | None = None,
    tool_name: str,
    user_id: str | None = None,
    client_source: str | None = None,
    duration_ms: int | None = None,
    ts: int,
    db_path: str | None = None,
) -> None:
    """Record a tool call and update session tool_calls_json."""
    from sqlalchemy.orm import Session as SASession

    from .database import get_engine
    from .database.sessions import upsert_session_from_tool_call

    engine = get_engine(db_path)
    normalized_tool_name = normalize_tool_name(tool_name)
    tc = ToolCall(
        tool_use_id=tool_use_id,
        user_id=user_id,
        usage_id=usage_id,
        session_id=session_id,
        tool_name=normalized_tool_name,
        client_source=client_source,
        duration_ms=duration_ms,
        ts=ts,
    )
    with SASession(engine, expire_on_commit=False) as session:
        if session.get(ToolCall, tool_use_id) is not None:
            return  # already recorded; avoid double-counting on redelivery
        if user_id is not None:
            prefix = f"{user_id}:"
            if (
                session_id
                and tool_use_id.startswith(prefix)
                and session_id.startswith(prefix)
            ):
                # ponytail: only match a legacy row with the same session and
                # source; raw input has no tenant identity, so never guess a
                # scoped owner.
                legacy_tool_use_id = tool_use_id[len(prefix) :]
                legacy_session_id = session_id[len(prefix) :]
                legacy = session.scalar(
                    select(ToolCall).where(
                        ToolCall.tool_use_id == legacy_tool_use_id,
                        ToolCall.user_id.is_(None),
                        ToolCall.session_id == legacy_session_id,
                        ToolCall.tool_name == normalized_tool_name,
                        ToolCall.client_source == client_source,
                    )
                )
                if legacy is not None:
                    return  # match a pre-auth raw provider ID on redelivery
        session.add(tc)
        try:
            session.commit()
        except IntegrityError:
            # Concurrent redelivery raced us to the same PK; already recorded.
            session.rollback()
            return
    upsert_session_from_tool_call(tc, db_path=db_path)
