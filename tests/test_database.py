def test_init_db_log_usage_and_fetch_rows(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    database_module.log_usage(
        db_path,
        ts="2026-04-17T00:00:00+00:00",
        provider="test-provider",
        model="test-model",
        endpoint="/v1/responses",
        prompt_tokens=10,
        completion_tokens=5,
        reasoning_tokens=1,
        cached_tokens=2,
        total_tokens=15,
        latency_ms=123,
        ttft_ms=None,
        tool_tokens=None,
        cache_creation_tokens=None,
        status=200,
    )

    rows = database_module.fetch_usage_rows("SELECT * FROM usage")

    assert rows == [
        {
            "id": 1,
            "ts": "2026-04-17T00:00:00+00:00",
            "provider": "test-provider",
            "model": "test-model",
            "endpoint": "/v1/responses",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "reasoning_tokens": 1,
            "cached_tokens": 2,
            "total_tokens": 15,
            "latency_ms": 123,
            "ttft_ms": None,
            "tool_tokens": None,
            "cache_creation_tokens": None,
            "status": 200,
        }
    ]
