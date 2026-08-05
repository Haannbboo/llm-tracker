def test_extract_usage_supports_responses_format_and_details(utils_module):
    usage = utils_module.extract_usage(
        {
            "input_tokens": 11,
            "output_tokens": 7,
            "input_tokens_details": {"cached_tokens": 3},
            "output_tokens_details": {"reasoning_tokens": 5},
        }
    )

    assert usage == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "reasoning_tokens": 5,
        "cached_tokens": 3,
        "cache_creation_tokens": 0,
        "total_tokens": 18,
    }


def test_extract_usage_supports_chat_completion_format_and_explicit_total(
    utils_module,
):
    usage = utils_module.extract_usage(
        {
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total_tokens": 25,
            "prompt_tokens_details": {"cached_tokens": 4},
            "completion_tokens_details": {"reasoning_tokens": 6},
        }
    )

    assert usage == {
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "reasoning_tokens": 6,
        "cached_tokens": 4,
        "cache_creation_tokens": 0,
        "total_tokens": 25,
    }


def test_extract_usage_supports_anthropic_cache_creation_tokens(utils_module):
    usage = utils_module.extract_usage(
        {
            "input_tokens": 25,
            "output_tokens": 15,
            "cache_creation_input_tokens": 8,
            "cache_read_input_tokens": 3,
        }
    )

    # Anthropic's input_tokens excludes cache_read/cache_creation tokens (they're
    # disjoint buckets), so cache_read folds into prompt_tokens: 25 + 3 = 28.
    assert usage == {
        "prompt_tokens": 28,
        "completion_tokens": 15,
        "reasoning_tokens": 0,
        "cached_tokens": 3,
        "cache_creation_tokens": 8,
        "total_tokens": 51,
    }


def test_extract_usage_defaults_missing_values_to_zero(utils_module):
    assert utils_module.extract_usage({}) == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
        "total_tokens": 0,
    }


def test_extract_stream_usage_reads_top_level_usage(utils_module):
    usage = utils_module.extract_stream_usage(
        {
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 2,
            },
        }
    )

    assert usage == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "reasoning_tokens": 0,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
        "total_tokens": 5,
    }


def test_extract_stream_usage_reads_nested_response_payload(utils_module):
    usage = utils_module.extract_stream_usage(
        {
            "type": "response.completed",
            "response": {
                "usage": {
                    "input_tokens": 9,
                    "output_tokens": 4,
                    "output_tokens_details": {"reasoning_tokens": 2},
                }
            },
        }
    )

    assert usage == {
        "prompt_tokens": 9,
        "completion_tokens": 4,
        "reasoning_tokens": 2,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
        "total_tokens": 13,
    }


def test_extract_stream_usage_reads_anthropic_message_start_payload(utils_module):
    """Anthropic's message_start event nests usage under `message`, not top-level."""
    usage = utils_module.extract_stream_usage(
        {
            "type": "message_start",
            "message": {
                "usage": {
                    "input_tokens": 25,
                    "cache_creation_input_tokens": 8,
                    "cache_read_input_tokens": 3,
                    "output_tokens": 1,
                }
            },
        }
    )

    assert usage == {
        "prompt_tokens": 28,
        "completion_tokens": 1,
        "reasoning_tokens": 0,
        "cached_tokens": 3,
        "cache_creation_tokens": 8,
        "total_tokens": 37,
    }


def test_extract_stream_usage_returns_none_without_usage(utils_module):
    assert (
        utils_module.extract_stream_usage({"type": "response.output_text.delta"})
        is None
    )


def test_find_stream_usage_merges_across_anthropic_events(utils_module):
    """message_start carries input/cache tokens; message_delta carries the
    final output token count. Callers must merge the raw dicts, not treat
    each event's usage as a complete replacement."""
    raw_usage: dict = {}

    start = utils_module.find_stream_usage(
        {
            "type": "message_start",
            "message": {
                "usage": {
                    "input_tokens": 25,
                    "cache_creation_input_tokens": 8,
                    "cache_read_input_tokens": 3,
                    "output_tokens": 1,
                }
            },
        }
    )
    raw_usage.update(start)

    delta = utils_module.find_stream_usage(
        {"type": "message_delta", "usage": {"output_tokens": 15}}
    )
    raw_usage.update(delta)

    merged = utils_module.extract_usage(raw_usage)
    assert merged == {
        "prompt_tokens": 28,
        "completion_tokens": 15,
        "reasoning_tokens": 0,
        "cached_tokens": 3,
        "cache_creation_tokens": 8,
        "total_tokens": 51,
    }


def test_build_usage_record_includes_provider_metadata(utils_module):
    record = utils_module.build_usage_record(
        provider_name="alpha",
        model="alpha-1",
        client_source="opencode",
        endpoint="/v1/responses",
        latency_ms=42,
        ttft_ms=11,
        status=201,
        usage_fields={
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "reasoning_tokens": 1,
            "cached_tokens": 2,
            "total_tokens": 15,
        },
    )

    assert record["provider"] == "alpha"
    assert record["model"] == "alpha-1"
    assert record["client_source"] == "opencode"
    assert record["endpoint"] == "/v1/responses"
    assert record["latency_ms"] == 42
    assert record["ttft_ms"] == 11
    assert record["status"] == 201
    assert record["total_tokens"] == 15
    assert isinstance(record["ts"], int)
    assert record["ts"] > 0


def test_secs_to_micros_integer(utils_module):
    assert utils_module.secs_to_micros(1776384000) == 1776384000000000


def test_secs_to_micros_float(utils_module):
    assert utils_module.secs_to_micros(1776384000.5) == 1776384000500000


def test_secs_to_micros_zero(utils_module):
    assert utils_module.secs_to_micros(0) == 0


def test_micros_to_secs(utils_module):
    assert utils_module.micros_to_secs(1776384000000000) == 1776384000.0


def test_micros_to_secs_zero(utils_module):
    assert utils_module.micros_to_secs(0) == 0.0


def test_secs_to_micros_roundtrip(utils_module):
    original = 1776384000
    assert utils_module.micros_to_secs(utils_module.secs_to_micros(original)) == float(
        original
    )
