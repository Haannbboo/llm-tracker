from typing import Any
from datetime import datetime, timezone


def extract_usage(usage: dict[str, Any]) -> dict[str, int]:
    """Normalize usage fields across chat completions and responses API formats."""
    prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens", 0)
    completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens", 0)
    total_tokens = usage.get("total_tokens") or (prompt_tokens + completion_tokens)

    input_details = (
        usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    )

    # Support OpenAI (cached_tokens) and Anthropic (cache_read_input_tokens)
    cached_tokens = (
        input_details.get("cached_tokens") or usage.get("cache_read_input_tokens") or 0
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
        "total_tokens": total_tokens,
    }


def extract_stream_usage(message: dict[str, Any]) -> dict[str, int] | None:
    if usage := message.get("usage"):
        return extract_usage(usage)

    response_payload = message.get("response") or {}
    if usage := response_payload.get("usage"):
        return extract_usage(usage)

    return None


def build_usage_record(
    *,
    provider_name: str,
    model: str,
    endpoint: str,
    latency_ms: int,
    status: int,
    usage_fields: dict[str, int],
) -> dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "provider": provider_name,
        "model": model,
        "endpoint": endpoint,
        "latency_ms": latency_ms,
        "status": status,
        **usage_fields,
    }
