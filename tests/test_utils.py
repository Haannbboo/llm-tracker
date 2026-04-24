from datetime import datetime


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
        "total_tokens": 25,
    }


def test_extract_usage_defaults_missing_values_to_zero(utils_module):
    assert utils_module.extract_usage({}) == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "cached_tokens": 0,
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
        "total_tokens": 13,
    }


def test_extract_stream_usage_returns_none_without_usage(utils_module):
    assert (
        utils_module.extract_stream_usage({"type": "response.output_text.delta"})
        is None
    )


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
    datetime.fromisoformat(record["ts"])
