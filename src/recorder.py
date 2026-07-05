"""Unified usage recording pipeline.

Both proxy and OTLP paths converge here for cost calculation, base URL
resolution, Usage construction, and persistence.
"""

from __future__ import annotations

import time

from .costs import calculate_costs
from .database.base_url import resolve_base_url_id
from .database.models import Usage
from .database.usage import log_usage


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
) -> None:
    """Record a single LLM usage event."""
    # Skip if successful and no token counts are available (None or zero).
    if status == 200 and not (
        prompt_tokens or completion_tokens or cached_tokens or total_tokens
    ):
        return

    usage_ts = ts if ts is not None else time.time_ns() // 1000
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

    log_usage(
        Usage(
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
        ),
        db_path=db_path,
    )
