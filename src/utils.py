import time
from typing import Any


def secs_to_micros(secs: int | float) -> int:
    """Convert epoch seconds to integer microseconds."""
    return round(secs * 1_000_000)


def micros_to_secs(micros: int) -> float:
    """Convert integer microseconds to epoch seconds."""
    return micros / 1_000_000


def extract_usage(usage: dict[str, Any]) -> dict[str, int]:
    """Normalize usage fields across chat completions, responses, and Anthropic formats."""
    prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens", 0)
    completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens", 0)

    input_details = (
        usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    )

    # Anthropic cache-write tokens (no OpenAI equivalent).
    cache_creation_tokens = usage.get("cache_creation_input_tokens") or 0

    # OpenAI's cached_tokens is a *subset* of prompt_tokens. Anthropic's
    # cache_read_input_tokens is a *disjoint* bucket -- input_tokens only counts
    # tokens after the last cache breakpoint -- so fold it into prompt_tokens to
    # match the "prompt_tokens >= cached_tokens" contract calculate_costs expects.
    anthropic_cache_read = usage.get("cache_read_input_tokens")
    if anthropic_cache_read is not None:
        cached_tokens = anthropic_cache_read
        prompt_tokens = prompt_tokens + cached_tokens
    else:
        cached_tokens = input_details.get("cached_tokens") or 0

    total_tokens = usage.get("total_tokens") or (
        prompt_tokens + completion_tokens + cache_creation_tokens
    )

    output_details = (
        usage.get("output_tokens_details")
        or usage.get("completion_tokens_details")
        or {}
    )

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": output_details.get("reasoning_tokens", 0),
        "cached_tokens": cached_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "total_tokens": total_tokens,
    }


def find_stream_usage(message: dict[str, Any]) -> dict[str, Any] | None:
    """Return the raw usage dict from a streaming chunk, if present.

    Checks top-level usage (chat/completions deltas, Anthropic message_delta),
    then response.usage (OpenAI responses API) and message.usage (Anthropic
    message_start, which carries input/cache tokens the later message_delta
    doesn't repeat).
    """
    if usage := message.get("usage"):
        return usage

    response_payload = message.get("response") or {}
    if usage := response_payload.get("usage"):
        return usage

    inner_message = message.get("message") or {}
    if usage := inner_message.get("usage"):
        return usage

    return None


def extract_stream_usage(message: dict[str, Any]) -> dict[str, int] | None:
    usage = find_stream_usage(message)
    return extract_usage(usage) if usage is not None else None


def build_usage_record(
    *,
    ts: int | None = None,
    provider_name: str,
    model: str,
    client_source: str | None,
    endpoint: str,
    latency_ms: int,
    ttft_ms: int | None = None,
    status: int,
    usage_fields: dict[str, int],
) -> dict[str, Any]:
    return {
        "ts": ts if ts is not None else time.time_ns() // 1000,
        "provider": provider_name,
        "model": model,
        "client_source": client_source,
        "endpoint": endpoint,
        "latency_ms": latency_ms,
        "ttft_ms": ttft_ms,
        "status": status,
        **usage_fields,
    }
