import pytest


def test_init_db_log_usage_and_fetch_rows(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    base_url_id = database_module.get_or_create_base_url(
        "https://api.example.com/v1",
        db_path=db_path,
        provider_name="test-provider",
        source="proxy_config",
    )

    database_module.log_usage(
        database_module.Usage(
            ts="2026-04-17T00:00:00+00:00",
            provider="test-provider",
            model="test-model",
            client_source="proxy-client",
            session_id="session-1",
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
            input_cost_usd=0.00002,
            output_cost_usd=0.00003,
            total_cost_usd=0.00005,
            status=200,
            base_url_id=base_url_id,
        ),
        db_path=db_path,
    )

    rows = database_module.fetch_recent_usage(limit=10)

    assert rows == [
        {
            "id": 1,
            "ts": "2026-04-17T00:00:00+00:00",
            "provider": "test-provider",
            "model": "test-model",
            "client_source": "proxy-client",
            "session_id": "session-1",
            "endpoint": "/v1/responses",
            "prompt_tokens": 10,
            "prompt_length": 0,
            "completion_tokens": 5,
            "reasoning_tokens": 1,
            "cached_tokens": 2,
            "total_tokens": 15,
            "latency_ms": 123,
            "ttft_ms": None,
            "tool_tokens": None,
            "cache_creation_tokens": None,
            "input_cost_usd": 2e-05,
            "output_cost_usd": 3e-05,
            "total_cost_usd": 5e-05,
            "status": 200,
            "base_url_id": base_url_id,
            "base_url": "https://api.example.com/v1",
        }
    ]


def test_fetch_recent_usage_returns_expected_row_shape(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    database_module.log_usage(
        database_module.Usage(
            ts="2026-04-17T00:00:00+00:00",
            provider="test-provider",
            model="test-model",
            client_source="proxy-client",
            session_id="session-shape",
            endpoint="/v1/responses",
            prompt_tokens=10,
            prompt_length=123,
            completion_tokens=5,
            reasoning_tokens=1,
            cached_tokens=2,
            total_tokens=15,
            latency_ms=123,
            ttft_ms=45,
            tool_tokens=3,
            cache_creation_tokens=4,
            input_cost_usd=0.00002,
            output_cost_usd=0.00003,
            total_cost_usd=0.00005,
            status=200,
            base_url_id=None,
        ),
        db_path=db_path,
    )

    row = database_module.fetch_recent_usage(limit=1)[0]

    assert set(row) == {
        "id",
        "ts",
        "provider",
        "model",
        "client_source",
        "session_id",
        "endpoint",
        "prompt_tokens",
        "prompt_length",
        "completion_tokens",
        "reasoning_tokens",
        "cached_tokens",
        "total_tokens",
        "latency_ms",
        "ttft_ms",
        "tool_tokens",
        "cache_creation_tokens",
        "input_cost_usd",
        "output_cost_usd",
        "total_cost_usd",
        "status",
        "base_url_id",
        "base_url",
    }


def test_usage_filters_includes_client_source(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for source in ["claude-code", "codex"]:
        database_module.log_usage(
            database_module.Usage(
                ts="2026-04-17T00:00:00+00:00",
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                client_source=source,
                session_id=None,
                endpoint="/v1/messages",
                prompt_tokens=10,
                completion_tokens=5,
                reasoning_tokens=None,
                cached_tokens=None,
                total_tokens=15,
                latency_ms=100,
                ttft_ms=None,
                tool_tokens=None,
                cache_creation_tokens=None,
                input_cost_usd=0.00002,
                output_cost_usd=0.00003,
                total_cost_usd=0.00005,
                status=200,
                base_url_id=None,
            ),
            db_path=db_path,
        )

    rows = database_module.fetch_recent_usage(
        limit=10, client_source="claude-code", db_path=db_path
    )
    assert len(rows) == 1
    assert rows[0]["client_source"] == "claude-code"

    rows = database_module.fetch_recent_usage(
        limit=10, client_source="codex", db_path=db_path
    )
    assert len(rows) == 1
    assert rows[0]["client_source"] == "codex"

    rows = database_module.fetch_recent_usage(limit=10, db_path=db_path)
    assert len(rows) == 2


def test_count_usage_filters_by_client_source(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for source in ["claude-code", "claude-code", "codex"]:
        database_module.log_usage(
            database_module.Usage(
                ts="2026-04-17T00:00:00+00:00",
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                client_source=source,
                session_id=None,
                endpoint="/v1/messages",
                prompt_tokens=10,
                completion_tokens=5,
                reasoning_tokens=None,
                cached_tokens=None,
                total_tokens=15,
                latency_ms=100,
                ttft_ms=None,
                tool_tokens=None,
                cache_creation_tokens=None,
                input_cost_usd=0.00002,
                output_cost_usd=0.00003,
                total_cost_usd=0.00005,
                status=200,
                base_url_id=None,
            ),
            db_path=db_path,
        )

    assert database_module.count_usage(client_source="claude-code") == 2
    assert database_module.count_usage(client_source="codex") == 1
    assert database_module.count_usage() == 3


def test_aggregate_usage_by_period_filters_by_client_source(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for ts, source, tokens in [
        ("2026-04-17T00:00:00+00:00", "claude-code", 150),
        ("2026-04-18T00:00:00+00:00", "codex", 300),
    ]:
        database_module.log_usage(
            database_module.Usage(
                ts=ts,
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                client_source=source,
                session_id=None,
                endpoint="/v1/messages",
                prompt_tokens=100,
                completion_tokens=50,
                reasoning_tokens=None,
                cached_tokens=None,
                total_tokens=tokens,
                latency_ms=100,
                ttft_ms=None,
                tool_tokens=None,
                cache_creation_tokens=None,
                input_cost_usd=0.002,
                output_cost_usd=0.003,
                total_cost_usd=0.005,
                status=200,
                base_url_id=None,
            ),
            db_path=db_path,
        )

    result = database_module.aggregate_usage_by_period(client_source="claude-code")
    assert len(result) == 1
    assert result[0]["total_tokens"] == 150

    result = database_module.aggregate_usage_by_period()
    assert len(result) == 2


def test_summarize_usage_daily_includes_avg_effective_price(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    database_module.log_usage(
        database_module.Usage(
            ts="2026-04-17T00:00:00+00:00",
            provider="test-provider",
            model="test-model",
            client_source="proxy-client",
            session_id=None,
            endpoint="/v1/responses",
            prompt_tokens=100,
            completion_tokens=50,
            reasoning_tokens=None,
            cached_tokens=0,
            total_tokens=150,
            latency_ms=100,
            ttft_ms=None,
            tool_tokens=None,
            cache_creation_tokens=None,
            input_cost_usd=0.0002,
            output_cost_usd=0.0003,
            total_cost_usd=0.0005,
            status=200,
            base_url_id=None,
        ),
        db_path=db_path,
    )
    database_module.log_usage(
        database_module.Usage(
            ts="2026-04-17T01:00:00+00:00",
            provider="test-provider",
            model="test-model",
            client_source="proxy-client",
            session_id=None,
            endpoint="/v1/responses",
            prompt_tokens=200,
            completion_tokens=100,
            reasoning_tokens=None,
            cached_tokens=0,
            total_tokens=300,
            latency_ms=100,
            ttft_ms=None,
            tool_tokens=None,
            cache_creation_tokens=None,
            input_cost_usd=0.0004,
            output_cost_usd=0.0006,
            total_cost_usd=0.001,
            status=200,
            base_url_id=None,
        ),
        db_path=db_path,
    )

    rows = database_module.summarize_usage_daily()
    assert rows[0]["avg_effective_price_usd"] == pytest.approx(0.0015 / 450, abs=1e-8)


def test_summarize_usage_by_provider_includes_avg_effective_price(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for model, total_tokens, total_cost in [
        ("test-model", 150, 0.0005),
        ("gpt-4.1", 300, 0.0010),
    ]:
        database_module.log_usage(
            database_module.Usage(
                ts="2026-04-17T00:00:00+00:00",
                provider="test-provider",
                model=model,
                client_source="proxy-client",
                session_id=None,
                endpoint="/v1/responses",
                prompt_tokens=100,
                completion_tokens=50,
                reasoning_tokens=None,
                cached_tokens=0,
                total_tokens=total_tokens,
                latency_ms=100,
                ttft_ms=None,
                tool_tokens=None,
                cache_creation_tokens=None,
                input_cost_usd=total_cost / 2,
                output_cost_usd=total_cost / 2,
                total_cost_usd=total_cost,
                status=200,
                base_url_id=None,
            ),
            db_path=db_path,
        )

    rows = database_module.summarize_usage_by_provider()
    assert rows[0]["avg_effective_price_usd"] == pytest.approx(0.0015 / 450, abs=1e-8)


def test_init_db_does_not_mutate_existing_usage_table(database_module, isolated_home):
    import sqlite3

    db_file = isolated_home / "usage.db"
    connection = sqlite3.connect(db_file)
    connection.execute(
        """
        CREATE TABLE usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            reasoning_tokens INTEGER,
            cached_tokens INTEGER,
            total_tokens INTEGER,
            latency_ms INTEGER,
            ttft_ms INTEGER,
            tool_tokens INTEGER,
            cache_creation_tokens INTEGER,
            input_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
            output_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
            total_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
            status INTEGER
        )
        """
    )
    connection.execute(
        """
        INSERT INTO usage (
            ts,
            provider,
            model,
            endpoint,
            prompt_tokens,
            completion_tokens,
            reasoning_tokens,
            cached_tokens,
            total_tokens,
            latency_ms,
            ttft_ms,
            tool_tokens,
            cache_creation_tokens,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-04-17T00:00:00+00:00",
            "test-provider",
            "test-model",
            "/v1/responses",
            10,
            5,
            1,
            2,
            15,
            123,
            None,
            None,
            None,
            200,
        ),
    )
    connection.commit()
    connection.close()

    database_module.init_db(str(db_file))

    connection = sqlite3.connect(db_file)
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(usage)").fetchall()
    }
    connection.close()

    assert "prompt_length" not in columns
    assert "base_url_id" not in columns
    assert "client_source" not in columns
    assert "session_id" not in columns


def test_migrate_database_adds_usage_columns(
    database_module, schema_migrations_module, isolated_home
):
    import sqlite3

    db_file = isolated_home / "usage.db"
    connection = sqlite3.connect(db_file)
    connection.execute(
        """
        CREATE TABLE usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            reasoning_tokens INTEGER,
            cached_tokens INTEGER,
            total_tokens INTEGER,
            latency_ms INTEGER,
            ttft_ms INTEGER,
            tool_tokens INTEGER,
            cache_creation_tokens INTEGER,
            status INTEGER
        )
        """
    )
    connection.commit()
    connection.close()

    changes = schema_migrations_module.migrate_database(str(db_file))

    column_names = schema_migrations_module._table_column_names(
        database_module.get_engine(str(db_file)), "usage"
    )
    assert "prompt_length" in column_names
    assert "base_url_id" in column_names
    assert "input_cost_usd" in column_names
    assert "output_cost_usd" in column_names
    assert "total_cost_usd" in column_names
    assert "client_source" in column_names
    assert "session_id" in column_names
    assert "usage.prompt_length" in changes
    assert "usage.base_url_id" in changes
    assert "usage.input_cost_usd" in changes
    assert "usage.output_cost_usd" in changes
    assert "usage.total_cost_usd" in changes
    assert "usage.client_source" in changes
    assert "usage.session_id" in changes

    import sqlite3

    connection = sqlite3.connect(db_file)
    table_info = connection.execute("PRAGMA table_info(usage)").fetchall()
    connection.close()

    defaults = {row[1]: row[4] for row in table_info}
    assert defaults["input_cost_usd"] == "0"
    assert defaults["output_cost_usd"] == "0"
    assert defaults["total_cost_usd"] == "0"


def test_get_usage_high_watermark_returns_latest_id(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    assert database_module.get_usage_high_watermark(db_path=db_path) == 0

    database_module.log_usage(
        database_module.Usage(
            ts="2026-04-17T00:00:00+00:00",
            provider="test-provider",
            model="test-model",
            client_source="codex",
            session_id="session-1",
            endpoint="generate-otlp",
            prompt_tokens=10,
            prompt_length=0,
            completion_tokens=5,
            reasoning_tokens=1,
            cached_tokens=2,
            total_tokens=15,
            latency_ms=100,
            ttft_ms=20,
            tool_tokens=3,
            cache_creation_tokens=4,
            input_cost_usd=0.1,
            output_cost_usd=0.2,
            total_cost_usd=0.3,
            status=200,
            base_url_id=None,
        ),
        db_path=db_path,
    )

    assert database_module.get_usage_high_watermark(db_path=db_path) == 1


def test_get_db_url_prefers_env_override_without_explicit_db(
    database_module, isolated_home, monkeypatch
):
    override = f"sqlite:///{isolated_home / 'run.db'}"
    monkeypatch.setenv("LLM_TRACKER_DB_URL", override)

    assert database_module.get_db_url() == override


def test_get_db_url_explicit_path_wins_over_env_override(
    database_module, isolated_home, monkeypatch
):
    override = f"sqlite:///{isolated_home / 'run.db'}"
    explicit = isolated_home / "main.db"
    monkeypatch.setenv("LLM_TRACKER_DB_URL", override)

    assert database_module.get_db_url(str(explicit)) == f"sqlite:///{explicit}"


def test_get_db_url_explicit_url_wins_over_env_override(
    database_module, isolated_home, monkeypatch
):
    override = f"sqlite:///{isolated_home / 'run.db'}"
    explicit = f"sqlite:///{isolated_home / 'main.db'}"
    monkeypatch.setenv("LLM_TRACKER_DB_URL", override)

    assert database_module.get_db_url(explicit) == explicit


def test_merge_usage_database_copies_usage_and_base_url_metadata(
    database_module, isolated_home
):
    run_db = str(isolated_home / "run.db")
    main_db = str(isolated_home / "main.db")
    database_module.init_db(run_db)
    database_module.init_db(main_db)

    run_base_url_id = database_module.get_or_create_base_url(
        "https://api.example.com/v1",
        db_path=run_db,
        provider_name="test-provider",
        source="proxy_config",
    )
    database_module.log_usage(
        database_module.Usage(
            ts="2026-05-03T18:00:00+00:00",
            provider="test-provider",
            model="test-model",
            client_source="codex",
            session_id="session-run-1",
            endpoint="generate-otlp",
            prompt_tokens=10,
            prompt_length=123,
            completion_tokens=5,
            reasoning_tokens=1,
            cached_tokens=2,
            total_tokens=15,
            latency_ms=100,
            ttft_ms=20,
            tool_tokens=3,
            cache_creation_tokens=4,
            input_cost_usd=0.1,
            output_cost_usd=0.2,
            total_cost_usd=0.3,
            status=200,
            base_url_id=run_base_url_id,
        ),
        db_path=run_db,
    )

    inserted = database_module.merge_usage_database(
        source_db_path=run_db,
        target_db_path=main_db,
    )

    assert inserted == 1
    rows = database_module.fetch_recent_usage(limit=10, db_path=main_db)
    assert len(rows) == 1
    assert rows[0]["session_id"] == "session-run-1"
    assert rows[0]["prompt_length"] == 123
    assert rows[0]["base_url"] == "https://api.example.com/v1"

    with database_module.get_engine(main_db).connect() as connection:
        base_urls = connection.execute(
            database_module.select(database_module.BaseUrl)
        ).all()
    assert len(base_urls) == 1
    assert base_urls[0].provider_name == "test-provider"
    assert base_urls[0].source == "proxy_config"


def test_summarize_usage_window_groups_by_session_source_and_model(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    rows = [
        database_module.Usage(
            ts="2026-04-17T00:00:00+00:00",
            provider="openai",
            model="gpt-test",
            client_source="codex",
            session_id="conv-1",
            endpoint="generate-otlp",
            prompt_tokens=100,
            prompt_length=0,
            completion_tokens=20,
            reasoning_tokens=5,
            cached_tokens=40,
            total_tokens=120,
            latency_ms=1000,
            ttft_ms=100,
            tool_tokens=3,
            cache_creation_tokens=0,
            input_cost_usd=0.10,
            output_cost_usd=0.20,
            total_cost_usd=0.30,
            status=200,
            base_url_id=None,
        ),
        database_module.Usage(
            ts="2026-04-17T00:01:00+00:00",
            provider="openai",
            model="gpt-test",
            client_source="codex",
            session_id="conv-1",
            endpoint="generate-otlp",
            prompt_tokens=50,
            prompt_length=0,
            completion_tokens=10,
            reasoning_tokens=2,
            cached_tokens=10,
            total_tokens=60,
            latency_ms=3000,
            ttft_ms=None,
            tool_tokens=1,
            cache_creation_tokens=0,
            input_cost_usd=0.05,
            output_cost_usd=0.10,
            total_cost_usd=0.15,
            status=500,
            base_url_id=None,
        ),
        database_module.Usage(
            ts="2026-04-17T00:02:00+00:00",
            provider="anthropic",
            model="claude-test",
            client_source="claude-code",
            session_id="claude-session",
            endpoint="generate-otlp",
            prompt_tokens=200,
            prompt_length=0,
            completion_tokens=50,
            reasoning_tokens=None,
            cached_tokens=100,
            total_tokens=250,
            latency_ms=None,
            ttft_ms=None,
            tool_tokens=None,
            cache_creation_tokens=30,
            input_cost_usd=0.20,
            output_cost_usd=0.50,
            total_cost_usd=0.70,
            status=None,
            base_url_id=None,
        ),
    ]

    for row in rows:
        database_module.log_usage(row, db_path=db_path)

    summary = database_module.summarize_usage_window(after_id=0, db_path=db_path)

    assert summary["window"] == {
        "after_id": 0,
        "until_id": 3,
        "row_count": 3,
    }
    assert summary["summary"]["requests"] == 3
    assert summary["summary"]["successful_requests"] == 2
    assert summary["summary"]["failed_requests"] == 1
    assert summary["summary"]["prompt_tokens"] == 350
    assert summary["summary"]["completion_tokens"] == 80
    assert summary["summary"]["reasoning_tokens"] == 7
    assert summary["summary"]["cached_tokens"] == 150
    assert summary["summary"]["tool_tokens"] == 4
    assert summary["summary"]["cache_creation_tokens"] == 30
    assert summary["summary"]["total_tokens"] == 430
    assert summary["summary"]["cache_hit_rate"] == 150 / 350
    assert summary["summary"]["avg_latency_ms"] == 2000
    assert summary["summary"]["avg_ttft_ms"] == 100
    assert summary["summary"]["total_cost_usd"] == 1.15

    assert summary["sessions"][0]["session_id"] == "claude-session"
    assert summary["sessions"][1]["session_id"] == "conv-1"
    assert summary["client_sources"][0]["client_source"] == "claude-code"
    assert summary["client_sources"][1]["client_source"] == "codex"
    assert summary["models"][0]["provider"] == "anthropic"
    assert summary["models"][0]["model"] == "claude-test"
    assert summary["models"][1]["provider"] == "openai"
    assert summary["models"][1]["model"] == "gpt-test"


def test_summarize_usage_window_filters_after_and_until_ids(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for index in range(3):
        database_module.log_usage(
            database_module.Usage(
                ts=f"2026-04-17T00:0{index}:00+00:00",
                provider="test-provider",
                model="test-model",
                client_source="codex",
                session_id=f"session-{index}",
                endpoint="generate-otlp",
                prompt_tokens=10,
                prompt_length=0,
                completion_tokens=5,
                reasoning_tokens=0,
                cached_tokens=1,
                total_tokens=15,
                latency_ms=100,
                ttft_ms=10,
                tool_tokens=0,
                cache_creation_tokens=0,
                input_cost_usd=0,
                output_cost_usd=0,
                total_cost_usd=0,
                status=200,
                base_url_id=None,
            ),
            db_path=db_path,
        )

    summary = database_module.summarize_usage_window(
        after_id=1,
        until_id=2,
        db_path=db_path,
    )

    assert summary["window"]["row_count"] == 1
    assert summary["summary"]["requests"] == 1
    assert summary["sessions"][0]["session_id"] == "session-1"


def test_summarize_usage_window_filters_metadata_and_includes_rows(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    rows = [
        database_module.Usage(
            ts="2026-04-17T00:00:00+00:00",
            provider="openai",
            model="gpt-test",
            client_source="codex",
            session_id="conv-1",
            endpoint="generate-otlp",
            prompt_tokens=10,
            prompt_length=0,
            completion_tokens=5,
            reasoning_tokens=0,
            cached_tokens=1,
            total_tokens=15,
            latency_ms=100,
            ttft_ms=10,
            tool_tokens=0,
            cache_creation_tokens=0,
            input_cost_usd=0,
            output_cost_usd=0,
            total_cost_usd=0,
            status=200,
            base_url_id=None,
        ),
        database_module.Usage(
            ts="2026-04-18T00:00:00+00:00",
            provider="openai",
            model="gpt-other",
            client_source="codex",
            session_id="conv-2",
            endpoint="generate-otlp",
            prompt_tokens=20,
            prompt_length=0,
            completion_tokens=10,
            reasoning_tokens=0,
            cached_tokens=2,
            total_tokens=30,
            latency_ms=200,
            ttft_ms=20,
            tool_tokens=0,
            cache_creation_tokens=0,
            input_cost_usd=0,
            output_cost_usd=0,
            total_cost_usd=0,
            status=200,
            base_url_id=None,
        ),
    ]

    for row in rows:
        database_module.log_usage(row, db_path=db_path)

    summary = database_module.summarize_usage_window(
        after_id=0,
        since="2026-04-17T00:00:00+00:00",
        until="2026-04-17T23:59:59+00:00",
        client_source="codex",
        session_id="conv-1",
        provider="openai",
        model="gpt-test",
        include_rows=True,
        db_path=db_path,
    )

    assert summary["window"]["row_count"] == 1
    assert summary["summary"]["total_tokens"] == 15
    assert summary["rows"][0]["session_id"] == "conv-1"
    assert summary["rows"][0]["model"] == "gpt-test"


def test_summarize_usage_window_empty_window(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    summary = database_module.summarize_usage_window(after_id=12, db_path=db_path)

    assert summary["window"] == {
        "after_id": 12,
        "until_id": 12,
        "row_count": 0,
    }
    assert summary["summary"]["requests"] == 0
    assert summary["summary"]["cache_hit_rate"] == 0.0
    assert summary["sessions"] == []
    assert summary["client_sources"] == []
    assert summary["models"] == []


def test_aggregate_usage_by_period_includes_cost_totals(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    database_module.log_usage(
        database_module.Usage(
            ts="2026-04-17T00:10:00+00:00",
            provider="test-provider",
            model="test-model",
            endpoint="/v1/responses",
            prompt_tokens=10,
            completion_tokens=5,
            reasoning_tokens=None,
            cached_tokens=2,
            total_tokens=15,
            latency_ms=100,
            ttft_ms=None,
            tool_tokens=None,
            cache_creation_tokens=None,
            input_cost_usd=0.00002,
            output_cost_usd=0.00003,
            total_cost_usd=0.00005,
            status=200,
            base_url_id=None,
        ),
        db_path=db_path,
    )
    database_module.log_usage(
        database_module.Usage(
            ts="2026-04-17T00:20:00+00:00",
            provider="test-provider",
            model="test-model",
            endpoint="/v1/responses",
            prompt_tokens=20,
            completion_tokens=10,
            reasoning_tokens=None,
            cached_tokens=4,
            total_tokens=30,
            latency_ms=200,
            ttft_ms=None,
            tool_tokens=None,
            cache_creation_tokens=None,
            input_cost_usd=0.00004,
            output_cost_usd=0.00006,
            total_cost_usd=0.0001,
            status=200,
            base_url_id=None,
        ),
        db_path=db_path,
    )

    daily = database_module.aggregate_usage_by_period(granularity="day")

    assert daily == [
        {
            "period": "2026-04-17",
            "requests": 2,
            "prompt_tokens": 30,
            "completion_tokens": 15,
            "avg_throughput": 50.0,
            "cached_tokens": 6,
            "total_tokens": 45,
            "input_cost_usd": 6e-05,
            "output_cost_usd": 9e-05,
            "total_cost_usd": 0.00015,
            "successful_requests": 2,
            "failed_requests": 0,
            "avg_latency_ms": 150.0,
        }
    ]


def test_get_or_create_base_url_reuses_exact_url_and_updates_metadata(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    base_url_id = database_module.get_or_create_base_url(
        "https://gateway.example/v1",
        db_path=db_path,
    )
    same_id = database_module.get_or_create_base_url(
        "https://gateway.example/v1",
        db_path=db_path,
        provider_name="OpenAI",
        source="codex_config",
    )

    assert same_id == base_url_id

    with database_module.get_engine(db_path).connect() as connection:
        rows = connection.execute(database_module.select(database_module.BaseUrl)).all()

    assert len(rows) == 1
    row = rows[0]
    assert row.base_url == "https://gateway.example/v1"
    assert row.provider_name == "OpenAI"
    assert row.source == "codex_config"


def test_get_or_create_base_url_retries_in_fresh_transaction_after_duplicate_insert(
    database_module, monkeypatch
):
    import src.database.base_url as base_url_mod
    from sqlalchemy.exc import IntegrityError

    class FakeRow:
        id = 7
        provider_name = None
        source = None

    state = {"attempt": -1, "updated": False, "rolled_back": False}

    class FakeSession:
        def __init__(self, engine):
            state["attempt"] += 1
            self.attempt = state["attempt"]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def scalar(self, statement):
            if self.attempt == 0:
                return None
            return FakeRow()

        def add(self, row):
            self.row = row

        def commit(self):
            if self.attempt == 0:
                raise IntegrityError("INSERT", None, Exception("dup"))
            state["updated"] = True

        def rollback(self):
            state["rolled_back"] = True

    monkeypatch.setattr(base_url_mod, "get_engine", lambda db_path=None: object())
    monkeypatch.setattr(base_url_mod, "Session", FakeSession)

    base_url_id = database_module.get_or_create_base_url(
        "https://race.example/v1",
        provider_name="OpenAI",
        source="proxy_config",
    )

    assert base_url_id == 7
    assert state["updated"] is True
    assert state["rolled_back"] is True


def test_migrate_database_drops_removed_base_url_columns(
    database_module, schema_migrations_module, isolated_home
):
    import sqlite3

    db_file = isolated_home / "usage.db"
    connection = sqlite3.connect(db_file)
    connection.execute(
        """
        CREATE TABLE base_urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            base_url TEXT NOT NULL UNIQUE,
            provider_name TEXT,
            source TEXT,
            validation_status TEXT,
            last_error TEXT
        )
        """
    )
    connection.commit()
    connection.close()

    changes = schema_migrations_module.migrate_database(str(db_file))

    column_names = schema_migrations_module._table_column_names(
        database_module.get_engine(str(db_file)), "base_urls"
    )
    assert "validation_status" not in column_names
    assert "last_error" not in column_names
    assert "base_urls.validation_status" in changes
    assert "base_urls.last_error" in changes


def test_ensure_column_ignores_duplicate_column_from_concurrent_migration(
    schema_migrations_module, monkeypatch
):
    state = {"column_exists": set()}

    class FakeInspector:
        def get_table_names(self):
            return ["usage"]

        def get_columns(self, table_name):
            columns = [{"name": "id"}, {"name": "prompt_tokens"}]
            for name in state["column_exists"]:
                columns.append({"name": name})
            if "prompt_length" not in state["column_exists"]:
                return columns
            if "base_url_id" not in state["column_exists"]:
                columns.append({"name": "prompt_length"})
            return columns

    class FakeConnection:
        def execute(self, statement):
            sql = str(statement)
            if "prompt_length" in sql:
                state["column_exists"].add("prompt_length")
                raise schema_migrations_module.SQLAlchemyError(
                    "duplicate column name: prompt_length"
                )
            if "base_url_id" in sql:
                state["column_exists"].add("base_url_id")
                raise schema_migrations_module.SQLAlchemyError(
                    "duplicate column name: base_url_id"
                )
            raise schema_migrations_module.SQLAlchemyError("duplicate column")

    class FakeBegin:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeDialect:
        name = "sqlite"

    class FakeEngine:
        dialect = FakeDialect()

        def begin(self):
            return FakeBegin()

    monkeypatch.setattr(
        schema_migrations_module, "inspect", lambda engine: FakeInspector()
    )

    assert (
        schema_migrations_module._ensure_column(
            FakeEngine(),
            "usage",
            "prompt_length",
            sqlite_definition="INTEGER NOT NULL DEFAULT 0",
            postgresql_definition="INTEGER NOT NULL DEFAULT 0",
        )
        is False
    )


def test_upsert_daily_aggregate_inserts_and_updates(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    usage1 = database_module.Usage(
        ts="2026-04-17T10:00:00+00:00",
        provider="anthropic",
        model="claude-sonnet-4-6",
        client_source="claude-code",
        session_id="s1",
        endpoint="/v1/messages",
        prompt_tokens=100,
        prompt_length=500,
        completion_tokens=50,
        reasoning_tokens=10,
        cached_tokens=20,
        total_tokens=160,
        latency_ms=200,
        ttft_ms=50,
        tool_tokens=5,
        cache_creation_tokens=0,
        input_cost_usd=0.001,
        output_cost_usd=0.002,
        total_cost_usd=0.003,
        status=200,
        base_url_id=None,
    )
    database_module.log_usage(usage1, db_path=db_path)

    # Verify insert
    with database_module.get_engine(db_path).connect() as conn:
        rows = list(conn.execute(database_module.select(database_module.UsageDaily)))
    assert len(rows) == 1
    assert rows[0].request_count == 1
    assert rows[0].prompt_tokens == 100
    assert rows[0].latency_sum_ms == 200
    assert rows[0].successful_requests == 1
    assert rows[0].failed_requests == 0

    # Same date, provider, model, client_source -> upsert
    usage2 = database_module.Usage(
        ts="2026-04-17T11:00:00+00:00",
        provider="anthropic",
        model="claude-sonnet-4-6",
        client_source="claude-code",
        session_id="s1",
        endpoint="/v1/messages",
        prompt_tokens=200,
        prompt_length=1000,
        completion_tokens=100,
        reasoning_tokens=20,
        cached_tokens=40,
        total_tokens=320,
        latency_ms=300,
        ttft_ms=80,
        tool_tokens=10,
        cache_creation_tokens=0,
        input_cost_usd=0.002,
        output_cost_usd=0.004,
        total_cost_usd=0.006,
        status=500,
        base_url_id=None,
    )
    database_module.log_usage(usage2, db_path=db_path)

    with database_module.get_engine(db_path).connect() as conn:
        rows = list(conn.execute(database_module.select(database_module.UsageDaily)))
    assert len(rows) == 1
    assert rows[0].request_count == 2
    assert rows[0].prompt_tokens == 300
    assert rows[0].completion_tokens == 150
    assert rows[0].latency_sum_ms == 500
    assert rows[0].successful_requests == 1
    assert rows[0].failed_requests == 1
    assert float(rows[0].total_cost_usd) == 0.009


def test_upsert_daily_aggregate_handles_null_client_source(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    usage = database_module.Usage(
        ts="2026-04-17T10:00:00+00:00",
        provider="openai",
        model="gpt-4",
        client_source=None,
        session_id=None,
        endpoint="/v1/chat/completions",
        prompt_tokens=50,
        prompt_length=200,
        completion_tokens=25,
        reasoning_tokens=None,
        cached_tokens=None,
        total_tokens=75,
        latency_ms=100,
        ttft_ms=None,
        tool_tokens=None,
        cache_creation_tokens=None,
        input_cost_usd=0.001,
        output_cost_usd=0.002,
        total_cost_usd=0.003,
        status=200,
        base_url_id=None,
    )
    database_module.log_usage(usage, db_path=db_path)

    with database_module.get_engine(db_path).connect() as conn:
        rows = list(conn.execute(database_module.select(database_module.UsageDaily)))
    assert len(rows) == 1
    assert rows[0].client_source == ""
    assert rows[0].request_count == 1


def test_upsert_daily_aggregate_separates_by_date(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for ts in ["2026-04-17T10:00:00+00:00", "2026-04-18T10:00:00+00:00"]:
        usage = database_module.Usage(
            ts=ts,
            provider="anthropic",
            model="claude-sonnet-4-6",
            client_source="claude-code",
            session_id="s1",
            endpoint="/v1/messages",
            prompt_tokens=100,
            prompt_length=500,
            completion_tokens=50,
            reasoning_tokens=10,
            cached_tokens=20,
            total_tokens=160,
            latency_ms=200,
            ttft_ms=50,
            tool_tokens=5,
            cache_creation_tokens=0,
            input_cost_usd=0.001,
            output_cost_usd=0.002,
            total_cost_usd=0.003,
            status=200,
            base_url_id=None,
        )
        database_module.log_usage(usage, db_path=db_path)

    with database_module.get_engine(db_path).connect() as conn:
        rows = list(conn.execute(database_module.select(database_module.UsageDaily)))
    assert len(rows) == 2
    dates = {r.date for r in rows}
    assert dates == {"2026-04-17", "2026-04-18"}


def test_log_usage_automaticaly_upserts_daily_aggregate(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    database_module.log_usage(
        database_module.Usage(
            ts="2026-04-17T10:00:00+00:00",
            provider="anthropic",
            model="claude-sonnet-4-6",
            client_source="claude-code",
            session_id="s1",
            endpoint="/v1/messages",
            prompt_tokens=100,
            prompt_length=500,
            completion_tokens=50,
            reasoning_tokens=10,
            cached_tokens=20,
            total_tokens=160,
            latency_ms=200,
            ttft_ms=50,
            tool_tokens=5,
            cache_creation_tokens=0,
            input_cost_usd=0.001,
            output_cost_usd=0.002,
            total_cost_usd=0.003,
            status=200,
            base_url_id=None,
        ),
        db_path=db_path,
    )

    with database_module.get_engine(db_path).connect() as conn:
        rows = list(conn.execute(database_module.select(database_module.UsageDaily)))
    assert len(rows) == 1
    assert rows[0].request_count == 1
    assert rows[0].prompt_tokens == 100


def test_summarize_usage_daily_reads_from_aggregate_table(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    # Insert two rows on same day, same provider/model
    for prompt, comp, latency, status in [
        (100, 50, 200, 200),
        (200, 100, 300, 500),
    ]:
        usage = database_module.Usage(
            ts="2026-04-17T10:00:00+00:00",
            provider="anthropic",
            model="claude-sonnet-4-6",
            client_source="claude-code",
            session_id="s1",
            endpoint="/v1/messages",
            prompt_tokens=prompt,
            prompt_length=500,
            completion_tokens=comp,
            reasoning_tokens=10,
            cached_tokens=20,
            total_tokens=prompt + comp,
            latency_ms=latency,
            ttft_ms=50,
            tool_tokens=5,
            cache_creation_tokens=0,
            input_cost_usd=0.001,
            output_cost_usd=0.002,
            total_cost_usd=0.003,
            status=status,
            base_url_id=None,
        )
        database_module.log_usage(usage, db_path=db_path)

    summary = database_module.summarize_usage_daily()

    assert len(summary) == 1
    row = summary[0]
    assert row["provider"] == "anthropic"
    assert row["model"] == "claude-sonnet-4-6"
    assert row["requests"] == 2
    assert row["prompt_tokens"] == 300
    assert row["completion_tokens"] == 150
    assert row["avg_latency_ms"] == 250.0
    assert row["successful_requests"] == 1
    assert row["failed_requests"] == 1


def test_summarize_usage_daily_filters_by_provider(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for provider, model, ts in [
        ("anthropic", "claude-sonnet-4-6", "2026-04-17T10:00:00+00:00"),
        ("openai", "gpt-4", "2026-04-17T11:00:00+00:00"),
    ]:
        usage = database_module.Usage(
            ts=ts,
            provider=provider,
            model=model,
            client_source=None,
            session_id=None,
            endpoint="/v1/messages",
            prompt_tokens=100,
            prompt_length=500,
            completion_tokens=50,
            reasoning_tokens=None,
            cached_tokens=None,
            total_tokens=150,
            latency_ms=100,
            ttft_ms=None,
            tool_tokens=None,
            cache_creation_tokens=None,
            input_cost_usd=0.001,
            output_cost_usd=0.002,
            total_cost_usd=0.003,
            status=200,
            base_url_id=None,
        )
        database_module.log_usage(usage, db_path=db_path)

    summary = database_module.summarize_usage_daily(provider="anthropic")
    assert len(summary) == 1
    assert summary[0]["provider"] == "anthropic"


def test_summarize_usage_daily_filters_by_since(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for ts in ["2026-04-17T10:00:00+00:00", "2026-04-20T10:00:00+00:00"]:
        usage = database_module.Usage(
            ts=ts,
            provider="anthropic",
            model="claude-sonnet-4-6",
            client_source=None,
            session_id=None,
            endpoint="/v1/messages",
            prompt_tokens=100,
            prompt_length=500,
            completion_tokens=50,
            reasoning_tokens=None,
            cached_tokens=None,
            total_tokens=150,
            latency_ms=100,
            ttft_ms=None,
            tool_tokens=None,
            cache_creation_tokens=None,
            input_cost_usd=0.001,
            output_cost_usd=0.002,
            total_cost_usd=0.003,
            status=200,
            base_url_id=None,
        )
        database_module.log_usage(usage, db_path=db_path)

    summary = database_module.summarize_usage_daily(since="2026-04-20")
    assert len(summary) == 1
    assert summary[0]["requests"] == 1


def test_aggregate_daily_by_period_reads_from_aggregate_table(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for ts, tokens in [
        ("2026-04-17T10:00:00+00:00", 100),
        ("2026-04-17T11:00:00+00:00", 200),
        ("2026-04-18T10:00:00+00:00", 300),
    ]:
        usage = database_module.Usage(
            ts=ts,
            provider="anthropic",
            model="claude-sonnet-4-6",
            client_source=None,
            session_id=None,
            endpoint="/v1/messages",
            prompt_tokens=tokens,
            prompt_length=500,
            completion_tokens=tokens // 2,
            reasoning_tokens=None,
            cached_tokens=None,
            total_tokens=tokens + tokens // 2,
            latency_ms=100,
            ttft_ms=None,
            tool_tokens=None,
            cache_creation_tokens=None,
            input_cost_usd=0.001,
            output_cost_usd=0.002,
            total_cost_usd=0.003,
            status=200,
            base_url_id=None,
        )
        database_module.log_usage(usage, db_path=db_path)

    result = database_module.aggregate_daily_by_period()

    assert len(result) == 2
    assert result[0]["period"] == "2026-04-17"
    assert result[0]["requests"] == 2
    assert result[0]["prompt_tokens"] == 300
    assert result[0]["total_tokens"] == 450
    assert result[1]["period"] == "2026-04-18"
    assert result[1]["requests"] == 1
    assert result[1]["prompt_tokens"] == 300


def test_aggregate_daily_by_period_filters_by_provider(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for provider, model in [("anthropic", "claude-sonnet-4-6"), ("openai", "gpt-4")]:
        usage = database_module.Usage(
            ts="2026-04-17T10:00:00+00:00",
            provider=provider,
            model=model,
            client_source=None,
            session_id=None,
            endpoint="/v1/messages",
            prompt_tokens=100,
            prompt_length=500,
            completion_tokens=50,
            reasoning_tokens=None,
            cached_tokens=None,
            total_tokens=150,
            latency_ms=100,
            ttft_ms=None,
            tool_tokens=None,
            cache_creation_tokens=None,
            input_cost_usd=0.001,
            output_cost_usd=0.002,
            total_cost_usd=0.003,
            status=200,
            base_url_id=None,
        )
        database_module.log_usage(usage, db_path=db_path)

    result = database_module.aggregate_daily_by_period(provider="anthropic")
    assert len(result) == 1
    assert result[0]["requests"] == 1


def test_migrate_database_creates_usage_daily_table(
    database_module, schema_migrations_module, isolated_home
):
    import sqlite3

    db_file = isolated_home / "usage.db"
    connection = sqlite3.connect(db_file)
    connection.execute(
        """
        CREATE TABLE usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            reasoning_tokens INTEGER,
            cached_tokens INTEGER,
            total_tokens INTEGER,
            latency_ms INTEGER,
            ttft_ms INTEGER,
            tool_tokens INTEGER,
            cache_creation_tokens INTEGER,
            input_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
            output_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
            total_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
            status INTEGER
        )
        """
    )
    connection.execute(
        """
        INSERT INTO usage (ts, provider, model, endpoint, prompt_tokens,
            completion_tokens, reasoning_tokens, cached_tokens, total_tokens,
            latency_ms, ttft_ms, tool_tokens, cache_creation_tokens,
            input_cost_usd, output_cost_usd, total_cost_usd, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-04-17T10:00:00+00:00",
            "anthropic",
            "claude-sonnet-4-6",
            "/v1/messages",
            100,
            50,
            10,
            20,
            160,
            200,
            50,
            5,
            0,
            0.001,
            0.002,
            0.003,
            200,
        ),
    )
    connection.execute(
        """
        INSERT INTO usage (ts, provider, model, endpoint, prompt_tokens,
            completion_tokens, reasoning_tokens, cached_tokens, total_tokens,
            latency_ms, ttft_ms, tool_tokens, cache_creation_tokens,
            input_cost_usd, output_cost_usd, total_cost_usd, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-04-17T11:00:00+00:00",
            "anthropic",
            "claude-sonnet-4-6",
            "/v1/messages",
            200,
            100,
            20,
            40,
            320,
            300,
            80,
            10,
            0,
            0.002,
            0.004,
            0.006,
            500,
        ),
    )
    connection.commit()
    connection.close()

    changes = schema_migrations_module.migrate_database(str(db_file))

    assert schema_migrations_module._table_exists(
        database_module.get_engine(str(db_file)), "usage_daily"
    )
    assert "usage_daily.backfill" in changes

    # Verify backfill
    with database_module.get_engine(str(db_file)).connect() as conn:
        rows = list(conn.execute(database_module.select(database_module.UsageDaily)))
    assert len(rows) == 1
    assert rows[0].request_count == 2
    assert rows[0].prompt_tokens == 300
    assert rows[0].latency_sum_ms == 500
    assert rows[0].successful_requests == 1
    assert rows[0].failed_requests == 1


def test_migrate_database_backfill_idempotent(
    database_module, schema_migrations_module, isolated_home
):
    import sqlite3

    db_file = isolated_home / "usage.db"
    connection = sqlite3.connect(db_file)
    connection.execute(
        """
        CREATE TABLE usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            reasoning_tokens INTEGER,
            cached_tokens INTEGER,
            total_tokens INTEGER,
            latency_ms INTEGER,
            ttft_ms INTEGER,
            tool_tokens INTEGER,
            cache_creation_tokens INTEGER,
            input_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
            output_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
            total_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
            status INTEGER
        )
        """
    )
    connection.execute(
        """
        INSERT INTO usage (ts, provider, model, endpoint, prompt_tokens,
            completion_tokens, reasoning_tokens, cached_tokens, total_tokens,
            latency_ms, ttft_ms, tool_tokens, cache_creation_tokens,
            input_cost_usd, output_cost_usd, total_cost_usd, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-04-17T10:00:00+00:00",
            "anthropic",
            "claude-sonnet-4-6",
            "/v1/messages",
            100,
            50,
            10,
            20,
            160,
            200,
            50,
            5,
            0,
            0.001,
            0.002,
            0.003,
            200,
        ),
    )
    connection.commit()
    connection.close()

    schema_migrations_module.migrate_database(str(db_file))
    changes2 = schema_migrations_module.migrate_database(str(db_file))

    # Second run should not create or backfill again
    assert "usage_daily.create" not in changes2
    assert "usage_daily.backfill" not in changes2

    # Data should still be there, not duplicated
    with database_module.get_engine(str(db_file)).connect() as conn:
        rows = list(conn.execute(database_module.select(database_module.UsageDaily)))
    assert len(rows) == 1
    assert rows[0].request_count == 1


def test_aggregate_usage_by_period_hourly_with_tz_offset(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    # Two rows 1 hour apart in UTC
    for ts, tokens in [
        ("2026-05-05T10:30:00+00:00", 100),
        ("2026-05-05T11:45:00+00:00", 200),
    ]:
        database_module.log_usage(
            database_module.Usage(
                ts=ts,
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                client_source=None,
                session_id=None,
                endpoint="/v1/messages",
                prompt_tokens=50,
                completion_tokens=50,
                reasoning_tokens=None,
                cached_tokens=None,
                total_tokens=tokens,
                latency_ms=100,
                ttft_ms=None,
                tool_tokens=None,
                cache_creation_tokens=None,
                input_cost_usd=0.002,
                output_cost_usd=0.003,
                total_cost_usd=0.005,
                status=200,
                base_url_id=None,
            ),
            db_path=db_path,
        )

    # With +05:30 offset, 10:30 UTC -> 16:00 IST, 11:45 UTC -> 17:15 IST
    result = database_module.aggregate_usage_by_period(
        granularity="hour", tz_offset="+05:30"
    )
    assert len(result) == 2
    assert result[0]["period"] == "2026-05-05 16:00"
    assert result[0]["requests"] == 1
    assert result[0]["total_tokens"] == 100
    assert result[1]["period"] == "2026-05-05 17:00"
    assert result[1]["requests"] == 1
    assert result[1]["total_tokens"] == 200


def test_aggregate_usage_by_period_hourly_merges_same_hour(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    # Two rows in the same UTC hour
    for ts, prompt, completion in [
        ("2026-05-05T10:15:00+00:00", 50, 50),
        ("2026-05-05T10:45:00+00:00", 30, 70),
    ]:
        database_module.log_usage(
            database_module.Usage(
                ts=ts,
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                client_source=None,
                session_id=None,
                endpoint="/v1/messages",
                prompt_tokens=prompt,
                completion_tokens=completion,
                reasoning_tokens=None,
                cached_tokens=None,
                total_tokens=prompt + completion,
                latency_ms=200,
                ttft_ms=None,
                tool_tokens=None,
                cache_creation_tokens=None,
                input_cost_usd=0.001,
                output_cost_usd=0.002,
                total_cost_usd=0.003,
                status=200,
                base_url_id=None,
            ),
            db_path=db_path,
        )

    result = database_module.aggregate_usage_by_period(granularity="hour")
    assert len(result) == 1
    assert result[0]["period"] == "2026-05-05 10:00"
    assert result[0]["requests"] == 2
    assert result[0]["prompt_tokens"] == 80
    assert result[0]["completion_tokens"] == 120
    assert result[0]["total_tokens"] == 200
    assert result[0]["avg_latency_ms"] == 200


def test_aggregate_usage_by_period_hourly_counts_failures(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for ts, status in [
        ("2026-05-05T10:00:00+00:00", 200),
        ("2026-05-05T10:01:00+00:00", 500),
        ("2026-05-05T10:02:00+00:00", 200),
    ]:
        database_module.log_usage(
            database_module.Usage(
                ts=ts,
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                client_source=None,
                session_id=None,
                endpoint="/v1/messages",
                prompt_tokens=10,
                completion_tokens=10,
                reasoning_tokens=None,
                cached_tokens=None,
                total_tokens=20,
                latency_ms=100,
                ttft_ms=None,
                tool_tokens=None,
                cache_creation_tokens=None,
                input_cost_usd=0.001,
                output_cost_usd=0.001,
                total_cost_usd=0.002,
                status=status,
                base_url_id=None,
            ),
            db_path=db_path,
        )

    result = database_module.aggregate_usage_by_period(granularity="hour")
    assert len(result) == 1
    assert result[0]["requests"] == 3
    assert result[0]["successful_requests"] == 2
    assert result[0]["failed_requests"] == 1


def test_aggregate_usage_by_period_hourly_negative_tz_offset(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    database_module.log_usage(
        database_module.Usage(
            ts="2026-05-05T03:30:00+00:00",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            client_source=None,
            session_id=None,
            endpoint="/v1/messages",
            prompt_tokens=10,
            completion_tokens=10,
            reasoning_tokens=None,
            cached_tokens=None,
            total_tokens=20,
            latency_ms=100,
            ttft_ms=None,
            tool_tokens=None,
            cache_creation_tokens=None,
            input_cost_usd=0.001,
            output_cost_usd=0.001,
            total_cost_usd=0.002,
            status=200,
            base_url_id=None,
        ),
        db_path=db_path,
    )

    # 03:30 UTC with -05:00 offset = 22:30 previous day (2026-05-04 22:00)
    result = database_module.aggregate_usage_by_period(
        granularity="hour", tz_offset="-05:00"
    )
    assert len(result) == 1
    assert result[0]["period"] == "2026-05-04 22:00"
    assert result[0]["requests"] == 1
    assert result[0]["total_tokens"] == 20


def test_aggregate_daily_by_dimension_groups_by_model(database_module, isolated_home):
    """aggregate_daily_by_dimension returns daily data grouped by model."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    # Insert test data across 2 days for 2 models
    for ts, provider, model, tokens, cost in [
        ("2026-05-07T10:00:00+00:00", "anthropic", "claude-sonnet-4-6", 1000, 0.01),
        ("2026-05-08T10:00:00+00:00", "anthropic", "claude-sonnet-4-6", 2000, 0.02),
        ("2026-05-07T10:00:00+00:00", "openai", "gpt-4o", 500, 0.005),
    ]:
        database_module.log_usage(
            database_module.Usage(
                ts=ts,
                provider=provider,
                model=model,
                client_source=None,
                session_id=None,
                endpoint="/v1/messages",
                prompt_tokens=tokens // 2,
                completion_tokens=tokens // 2,
                reasoning_tokens=None,
                cached_tokens=None,
                total_tokens=tokens,
                latency_ms=500,
                ttft_ms=None,
                tool_tokens=None,
                cache_creation_tokens=None,
                input_cost_usd=cost / 2,
                output_cost_usd=cost / 2,
                total_cost_usd=cost,
                status=200,
                base_url_id=None,
            ),
            db_path=db_path,
        )

    result = database_module.aggregate_daily_by_dimension(
        dimension="model",
        since="2026-05-07T00:00:00Z",
        until="2026-05-09T00:00:00Z",
    )

    # Should have 3 entries: claude-sonnet-4-6 on 05-07, claude-sonnet-4-6 on 05-08, gpt-4o on 05-07
    assert len(result) == 3
    by_model_and_date = {(r["dimension"], r["period"]): r for r in result}
    assert (
        by_model_and_date[("claude-sonnet-4-6", "2026-05-07")]["total_tokens"] == 1000
    )
    assert (
        by_model_and_date[("claude-sonnet-4-6", "2026-05-08")]["total_tokens"] == 2000
    )
    assert by_model_and_date[("gpt-4o", "2026-05-07")]["total_tokens"] == 500


def test_aggregate_daily_by_dimension_groups_by_provider(
    database_module, isolated_home
):
    """aggregate_daily_by_dimension returns daily data grouped by provider."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for ts, provider, model, tokens, cost in [
        ("2026-05-07T10:00:00+00:00", "anthropic", "claude-sonnet-4-6", 1000, 0.01),
        ("2026-05-07T10:00:00+00:00", "openai", "gpt-4o", 500, 0.005),
    ]:
        database_module.log_usage(
            database_module.Usage(
                ts=ts,
                provider=provider,
                model=model,
                client_source=None,
                session_id=None,
                endpoint="/v1/messages",
                prompt_tokens=tokens // 2,
                completion_tokens=tokens // 2,
                reasoning_tokens=None,
                cached_tokens=None,
                total_tokens=tokens,
                latency_ms=300,
                ttft_ms=None,
                tool_tokens=None,
                cache_creation_tokens=None,
                input_cost_usd=cost / 2,
                output_cost_usd=cost / 2,
                total_cost_usd=cost,
                status=200,
                base_url_id=None,
            ),
            db_path=db_path,
        )

    result = database_module.aggregate_daily_by_dimension(
        dimension="provider",
        since="2026-05-07T00:00:00Z",
        until="2026-05-08T00:00:00Z",
    )

    assert len(result) == 2
    by_provider = {r["dimension"]: r for r in result}
    assert by_provider["anthropic"]["total_tokens"] == 1000
    assert by_provider["openai"]["total_tokens"] == 500


def test_fetch_sessions_groups_by_session_id(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for i in range(3):
        database_module.log_usage(
            database_module.Usage(
                ts=f"2026-05-09T10:0{i}:00+00:00",
                provider="anthropic",
                model="claude-sonnet-4-6",
                client_source="claude-code",
                session_id="sess-1",
                endpoint="/v1/messages",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                latency_ms=200,
                ttft_ms=100,
                input_cost_usd=0.001,
                output_cost_usd=0.002,
                total_cost_usd=0.003,
                status=200,
            ),
            db_path=db_path,
        )

    database_module.log_usage(
        database_module.Usage(
            ts="2026-05-09T11:00:00+00:00",
            provider="openai",
            model="gpt-4o",
            client_source="codex",
            session_id="sess-2",
            endpoint="/v1/chat/completions",
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            latency_ms=300,
            ttft_ms=150,
            input_cost_usd=0.005,
            output_cost_usd=0.01,
            total_cost_usd=0.015,
            status=200,
        ),
        db_path=db_path,
    )

    result = database_module.fetch_sessions(db_path=db_path)
    assert len(result) == 2
    assert result[0]["session_id"] == "sess-2"
    assert result[0]["request_count"] == 1
    assert result[0]["total_tokens"] == 300
    assert result[1]["session_id"] == "sess-1"
    assert result[1]["request_count"] == 3
    assert result[1]["total_tokens"] == 450


def test_fetch_sessions_excludes_null_session_id(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    database_module.log_usage(
        database_module.Usage(
            ts="2026-05-09T10:00:00+00:00",
            provider="anthropic",
            model="claude-sonnet-4-6",
            client_source="claude-code",
            session_id=None,
            endpoint="/v1/messages",
            prompt_tokens=100,
            total_tokens=100,
            input_cost_usd=0.001,
            output_cost_usd=0.001,
            total_cost_usd=0.002,
            status=200,
        ),
        db_path=db_path,
    )

    result = database_module.fetch_sessions(db_path=db_path)
    assert len(result) == 0


def test_fetch_sessions_filters_by_client_source(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for source, sid in [("claude-code", "s1"), ("codex", "s2")]:
        database_module.log_usage(
            database_module.Usage(
                ts="2026-05-09T10:00:00+00:00",
                provider="anthropic",
                model="claude-sonnet-4-6",
                client_source=source,
                session_id=sid,
                endpoint="/v1/messages",
                prompt_tokens=100,
                total_tokens=100,
                input_cost_usd=0.001,
                output_cost_usd=0.001,
                total_cost_usd=0.002,
                status=200,
            ),
            db_path=db_path,
        )

    result = database_module.fetch_sessions(client_source="codex", db_path=db_path)
    assert len(result) == 1
    assert result[0]["session_id"] == "s2"


def test_fetch_sessions_accepts_browser_iso_boundary_filters(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    database_module.log_usage(
        database_module.Usage(
            ts="2026-05-09T10:00:00+00:00",
            provider="anthropic",
            model="claude-sonnet-4-6",
            client_source="claude-code",
            session_id="boundary",
            endpoint="/v1/messages",
            prompt_tokens=100,
            total_tokens=100,
            input_cost_usd=0.001,
            output_cost_usd=0.001,
            total_cost_usd=0.002,
            status=200,
        ),
        db_path=db_path,
    )

    result = database_module.fetch_sessions(
        since="2026-05-09T10:00:00.000Z",
        until="2026-05-09T10:00:00.000Z",
        db_path=db_path,
    )

    assert [session["session_id"] for session in result] == ["boundary"]


def test_fetch_sessions_sorting(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for i, sid in enumerate(["s-low", "s-high"]):
        database_module.log_usage(
            database_module.Usage(
                ts=f"2026-05-09T1{i}:00:00+00:00",
                provider="anthropic",
                model="claude-sonnet-4-6",
                client_source="claude-code",
                session_id=sid,
                endpoint="/v1/messages",
                prompt_tokens=100 * (i + 1),
                total_tokens=100 * (i + 1),
                input_cost_usd=0.001,
                output_cost_usd=0.001,
                total_cost_usd=0.002,
                status=200,
            ),
            db_path=db_path,
        )

    result = database_module.fetch_sessions(
        sort_by="total_tokens", sort_order="asc", db_path=db_path
    )
    assert result[0]["session_id"] == "s-low"
    assert result[1]["session_id"] == "s-high"


def test_fetch_sessions_sort_by_duration(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    # Short session: single request
    database_module.log_usage(
        database_module.Usage(
            ts="2026-05-09T10:00:00+00:00",
            provider="anthropic",
            model="claude-sonnet-4-6",
            client_source="claude-code",
            session_id="short",
            endpoint="/v1/messages",
            prompt_tokens=100,
            total_tokens=100,
            input_cost_usd=0.001,
            output_cost_usd=0.001,
            total_cost_usd=0.002,
            status=200,
        ),
        db_path=db_path,
    )

    # Long session: spans 10 minutes
    for i in range(2):
        database_module.log_usage(
            database_module.Usage(
                ts=f"2026-05-09T10:0{i * 5}:00+00:00",
                provider="anthropic",
                model="claude-sonnet-4-6",
                client_source="claude-code",
                session_id="long",
                endpoint="/v1/messages",
                prompt_tokens=100,
                total_tokens=100,
                input_cost_usd=0.001,
                output_cost_usd=0.001,
                total_cost_usd=0.002,
                status=200,
            ),
            db_path=db_path,
        )

    result = database_module.fetch_sessions(
        sort_by="duration_s", sort_order="desc", db_path=db_path
    )
    assert result[0]["session_id"] == "long"
    assert result[1]["session_id"] == "short"


def test_fetch_sessions_pagination(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for i in range(5):
        database_module.log_usage(
            database_module.Usage(
                ts=f"2026-05-09T1{i}:00:00+00:00",
                provider="anthropic",
                model="claude-sonnet-4-6",
                client_source="claude-code",
                session_id=f"s{i}",
                endpoint="/v1/messages",
                prompt_tokens=100,
                total_tokens=100,
                input_cost_usd=0.001,
                output_cost_usd=0.001,
                total_cost_usd=0.002,
                status=200,
            ),
            db_path=db_path,
        )

    result = database_module.fetch_sessions(limit=2, offset=1, db_path=db_path)
    assert len(result) == 2


def test_count_sessions(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for sid in ["s1", "s2", "s1"]:
        database_module.log_usage(
            database_module.Usage(
                ts="2026-05-09T10:00:00+00:00",
                provider="anthropic",
                model="claude-sonnet-4-6",
                client_source="claude-code",
                session_id=sid,
                endpoint="/v1/messages",
                prompt_tokens=100,
                total_tokens=100,
                input_cost_usd=0.001,
                output_cost_usd=0.001,
                total_cost_usd=0.002,
                status=200,
            ),
            db_path=db_path,
        )

    assert database_module.count_sessions(db_path=db_path) == 2


def test_count_usage_with_session_id(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for sid in ["s1", "s1", "s2"]:
        database_module.log_usage(
            database_module.Usage(
                ts="2026-05-09T10:00:00+00:00",
                provider="anthropic",
                model="claude-sonnet-4-6",
                client_source="claude-code",
                session_id=sid,
                endpoint="/v1/messages",
                prompt_tokens=100,
                total_tokens=100,
                input_cost_usd=0.001,
                output_cost_usd=0.001,
                total_cost_usd=0.002,
                status=200,
            ),
            db_path=db_path,
        )

    assert database_module.count_usage(session_id="s1", db_path=db_path) == 2
    assert database_module.count_usage(session_id="s2", db_path=db_path) == 1
    assert database_module.count_usage(session_id="nonexistent", db_path=db_path) == 0


def test_count_usage_with_session_id_and_other_filters(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    # Same session, two different providers
    for provider in ["anthropic", "openai"]:
        database_module.log_usage(
            database_module.Usage(
                ts="2026-05-09T10:00:00+00:00",
                provider=provider,
                model="test-model",
                client_source="claude-code",
                session_id="s1",
                endpoint="/v1/messages",
                prompt_tokens=100,
                total_tokens=100,
                input_cost_usd=0.001,
                output_cost_usd=0.001,
                total_cost_usd=0.002,
                status=200,
            ),
            db_path=db_path,
        )

    # session_id + provider filter should narrow to 1
    assert (
        database_module.count_usage(
            session_id="s1", provider="anthropic", db_path=db_path
        )
        == 1
    )
    # session_id + client_source filter
    assert (
        database_module.count_usage(
            session_id="s1", client_source="claude-code", db_path=db_path
        )
        == 2
    )
    # session_id + mismatched provider
    assert (
        database_module.count_usage(session_id="s1", provider="google", db_path=db_path)
        == 0
    )


def test_summarize_sessions(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    for i in range(3):
        database_module.log_usage(
            database_module.Usage(
                ts=f"2026-05-09T10:0{i}:00+00:00",
                provider="anthropic",
                model="claude-sonnet-4-6",
                client_source="claude-code",
                session_id="s1",
                endpoint="/v1/messages",
                prompt_tokens=100,
                total_tokens=100,
                latency_ms=200,
                input_cost_usd=0.001,
                output_cost_usd=0.001,
                total_cost_usd=0.002,
                status=200,
            ),
            db_path=db_path,
        )

    database_module.log_usage(
        database_module.Usage(
            ts="2026-05-09T11:00:00+00:00",
            provider="openai",
            model="gpt-4o",
            client_source="codex",
            session_id="s2",
            endpoint="/v1/chat/completions",
            prompt_tokens=200,
            total_tokens=200,
            latency_ms=300,
            input_cost_usd=0.005,
            output_cost_usd=0.005,
            total_cost_usd=0.01,
            status=200,
        ),
        db_path=db_path,
    )

    result = database_module.summarize_sessions(db_path=db_path)
    assert result["session_count"] == 2
    assert result["total_tokens"] == 500
    assert result["total_cost_usd"] == pytest.approx(0.016)
    # s1 spans 10:00-10:02 (120s), s2 is a single request (0s), avg = 60s
    assert result["avg_duration_s"] == 60


def test_fetch_recent_usage_only_failed_filter(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    with database_module.Session(database_module.get_engine(db_path)) as session:
        session.add(
            database_module.Usage(
                ts="2024-01-01T00:00:00Z",
                provider="p1",
                model="m1",
                endpoint="/chat",
                status=200,
            )
        )
        session.add(
            database_module.Usage(
                ts="2024-01-01T00:00:01Z",
                provider="p1",
                model="m1",
                endpoint="/chat",
                status=500,
            )
        )
        session.commit()

    # When: fetch all
    all_rows = database_module.fetch_recent_usage(limit=10, db_path=db_path)
    assert len(all_rows) == 2

    # When: fetch only failed
    failed_rows = database_module.fetch_recent_usage(
        limit=10, only_failed=True, db_path=db_path
    )
    assert len(failed_rows) == 1
    assert failed_rows[0]["status"] == 500


def test_usage_daily_status_breakdown(database_module, isolated_home):
    db_path = str(isolated_home / "usage_status.db")
    database_module.init_db(db_path)

    # Record 4 requests with different status codes
    codes = [200, 429, 403, 500]
    for i, code in enumerate(codes):
        usage = database_module.Usage(
            ts=f"2024-01-01T00:00:{i:02d}Z",
            provider="p1",
            model="m1",
            endpoint="/chat",
            status=code,
            input_cost_usd=0,
            output_cost_usd=0,
            total_cost_usd=0,
            prompt_length=0,
        )
        database_module.upsert_daily_aggregate(usage, db_path=db_path)

    # Check aggregation
    summary = database_module.summarize_usage_daily(since="2024-01-01", db_path=db_path)
    assert len(summary) == 1
    row = summary[0]
    assert row["requests"] == 4
    assert row["successful_requests"] == 1
    assert row["failed_requests"] == 3
    assert row["status_429"] == 1
    assert row["status_4xx"] == 1  # 403
    assert row["status_5xx"] == 1
    assert row["status_unknown"] == 0


def test_migration_adds_status_columns(database_module, isolated_home, load_module):
    schema_migrations = load_module("src.schema_migrations")
    db_path = str(isolated_home / "migration_test.db")

    # 1. Create table without new columns
    engine = database_module.get_engine(db_path)
    with engine.begin() as conn:
        conn.execute(
            database_module.text("""
            CREATE TABLE usage_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                client_source TEXT NOT NULL DEFAULT '',
                request_count INTEGER NOT NULL DEFAULT 0,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                reasoning_tokens INTEGER NOT NULL DEFAULT 0,
                cached_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                tool_tokens INTEGER NOT NULL DEFAULT 0,
                cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
                prompt_length INTEGER NOT NULL DEFAULT 0,
                input_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
                output_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
                total_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
                successful_requests INTEGER NOT NULL DEFAULT 0,
                failed_requests INTEGER NOT NULL DEFAULT 0,
                latency_sum_ms INTEGER NOT NULL DEFAULT 0,
                UNIQUE(date, provider, model, client_source)
            )
        """)
        )

    # 2. Run migration
    applied = schema_migrations.migrate_database(db_path)
    assert any("usage_daily.status_429" in a for a in applied)
    assert any("usage_daily.status_4xx" in a for a in applied)
    assert any("usage_daily.status_5xx" in a for a in applied)
    assert any("usage_daily.status_unknown" in a for a in applied)

    # 3. Verify columns exist
    from sqlalchemy import inspect

    columns = [c["name"] for c in inspect(engine).get_columns("usage_daily")]
    assert "status_429" in columns
    assert "status_4xx" in columns
    assert "status_5xx" in columns
    assert "status_unknown" in columns


# ---------------------------------------------------------------------------
# Slice 0: Persist Sessions as First-Class Rows
# ---------------------------------------------------------------------------


def test_session_record_created_from_usage_ingestion(database_module, isolated_home):
    """TDD step 1: Ingesting two usage rows with same session_id creates one
    sessions row with summed tokens/cost/request count and min/max timestamps."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    database_module.log_usage(
        database_module.Usage(
            ts="2026-05-09T10:00:00+00:00",
            provider="anthropic",
            model="claude-sonnet-4-6",
            client_source="claude-code",
            session_id="sess-1",
            endpoint="/v1/messages",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            latency_ms=200,
            ttft_ms=100,
            input_cost_usd=0.001,
            output_cost_usd=0.002,
            total_cost_usd=0.003,
            status=200,
        ),
        db_path=db_path,
    )

    database_module.log_usage(
        database_module.Usage(
            ts="2026-05-09T10:05:00+00:00",
            provider="anthropic",
            model="claude-sonnet-4-6",
            client_source="claude-code",
            session_id="sess-1",
            endpoint="/v1/messages",
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            latency_ms=300,
            ttft_ms=150,
            input_cost_usd=0.002,
            output_cost_usd=0.004,
            total_cost_usd=0.006,
            status=200,
        ),
        db_path=db_path,
    )

    from sqlalchemy import select
    from sqlalchemy.orm import Session as OrmSession

    engine = database_module.get_engine(db_path)
    with OrmSession(engine) as orm:
        session = orm.scalar(
            select(database_module.SessionRecord).where(
                database_module.SessionRecord.session_id == "sess-1"
            )
        )

    assert session is not None, "SessionRecord should exist after ingesting usage rows"
    assert session.request_count == 2
    assert session.total_tokens == 450
    assert session.prompt_tokens == 300
    assert session.completion_tokens == 150
    assert float(session.total_cost_usd) == pytest.approx(0.009, abs=1e-6)
    assert session.started == "2026-05-09T10:00:00+00:00"
    assert session.ended == "2026-05-09T10:05:00+00:00"
    assert session.successful_requests == 2
    assert session.failed_requests == 0


def test_session_record_primary_model_picks_higher_cost(database_module, isolated_home):
    """TDD step 2: Two models in one session; primary_model picks the one
    with higher cumulative cost."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    # Model A: cost 0.003
    database_module.log_usage(
        database_module.Usage(
            ts="2026-05-09T10:00:00+00:00",
            provider="anthropic",
            model="claude-sonnet-4-6",
            client_source="claude-code",
            session_id="sess-1",
            endpoint="/v1/messages",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            latency_ms=200,
            ttft_ms=100,
            input_cost_usd=0.001,
            output_cost_usd=0.002,
            total_cost_usd=0.003,
            status=200,
        ),
        db_path=db_path,
    )

    # Model B: cost 0.015 (higher)
    database_module.log_usage(
        database_module.Usage(
            ts="2026-05-09T10:01:00+00:00",
            provider="openai",
            model="gpt-4o",
            client_source="claude-code",
            session_id="sess-1",
            endpoint="/v1/chat/completions",
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            latency_ms=300,
            ttft_ms=150,
            input_cost_usd=0.005,
            output_cost_usd=0.01,
            total_cost_usd=0.015,
            status=200,
        ),
        db_path=db_path,
    )

    from sqlalchemy import select
    from sqlalchemy.orm import Session as OrmSession

    engine = database_module.get_engine(db_path)
    with OrmSession(engine) as orm:
        session = orm.scalar(
            select(database_module.SessionRecord).where(
                database_module.SessionRecord.session_id == "sess-1"
            )
        )

    assert session.primary_model == "gpt-4o"
    assert session.primary_provider == "openai"

    import json

    models = json.loads(session.models_json)
    providers = json.loads(session.providers_json)
    assert set(models.keys()) == {"claude-sonnet-4-6", "gpt-4o"}
    assert set(providers.keys()) == {"anthropic", "openai"}


def test_fetch_sessions_reads_from_persisted_table(database_module, isolated_home):
    """TDD step 3: fetch_sessions() reads from the persisted sessions table,
    not freshly grouped usage."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    # Directly insert a SessionRecord (bypassing log_usage)
    from sqlalchemy.orm import Session

    engine = database_module.get_engine(db_path)
    with Session(engine) as session:
        session.add(
            database_module.SessionRecord(
                session_id="manual-sess",
                client_source="claude-code",
                started="2026-05-09T08:00:00+00:00",
                ended="2026-05-09T09:00:00+00:00",
                request_count=5,
                successful_requests=5,
                failed_requests=0,
                total_tokens=1000,
                prompt_tokens=800,
                completion_tokens=200,
                cached_tokens=0,
                total_cost_usd=0.05,
                latency_sum_ms=5000,
                avg_latency_ms=1000.0,
                avg_ttft_ms=200.0,
                primary_provider="anthropic",
                primary_model="claude-sonnet-4-6",
                models_json='{"claude-sonnet-4-6": 0.05}',
                providers_json='{"anthropic": 0.05}',
                last_usage_id=None,
                updated_at="2026-05-09T09:00:00+00:00",
            )
        )
        session.commit()

    result = database_module.fetch_sessions(db_path=db_path)
    assert len(result) == 1
    assert result[0]["session_id"] == "manual-sess"
    assert result[0]["request_count"] == 5
    assert result[0]["total_tokens"] == 1000
    assert result[0]["total_cost_usd"] == pytest.approx(0.05, abs=1e-6)
    assert result[0]["duration_s"] == 3600


def test_rebuild_sessions_from_usage(database_module, isolated_home):
    """TDD step 4: Seed usage rows, run rebuild_sessions_from_usage(),
    assert persisted rows match old aggregation behavior."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    # Seed usage rows for two sessions
    for i in range(3):
        database_module.log_usage(
            database_module.Usage(
                ts=f"2026-05-09T10:0{i}:00+00:00",
                provider="anthropic",
                model="claude-sonnet-4-6",
                client_source="claude-code",
                session_id="sess-1",
                endpoint="/v1/messages",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                latency_ms=200,
                ttft_ms=100,
                input_cost_usd=0.001,
                output_cost_usd=0.002,
                total_cost_usd=0.003,
                status=200,
            ),
            db_path=db_path,
        )

    database_module.log_usage(
        database_module.Usage(
            ts="2026-05-09T11:00:00+00:00",
            provider="openai",
            model="gpt-4o",
            client_source="codex",
            session_id="sess-2",
            endpoint="/v1/chat/completions",
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            latency_ms=300,
            ttft_ms=150,
            input_cost_usd=0.005,
            output_cost_usd=0.01,
            total_cost_usd=0.015,
            status=200,
        ),
        db_path=db_path,
    )

    # Clear sessions table and rebuild from scratch
    count = database_module.rebuild_sessions_from_usage(db_path=db_path)
    assert count == 2

    result = database_module.fetch_sessions(db_path=db_path)
    assert len(result) == 2

    by_id = {r["session_id"]: r for r in result}
    s1 = by_id["sess-1"]
    assert s1["request_count"] == 3
    assert s1["total_tokens"] == 450
    assert float(s1["total_cost_usd"]) == pytest.approx(0.009, abs=1e-6)
    assert s1["started"] == "2026-05-09T10:00:00+00:00"
    assert s1["ended"] == "2026-05-09T10:02:00+00:00"
    assert s1["successful_requests"] == 3

    s2 = by_id["sess-2"]
    assert s2["request_count"] == 1
    assert s2["total_tokens"] == 300
    assert float(s2["total_cost_usd"]) == pytest.approx(0.015, abs=1e-6)


# ---------------------------------------------------------------------------
# Slice 1: Store Manual Session Evaluations
# ---------------------------------------------------------------------------


def _insert_session_record(database_module, db_path, session_id="sess-1", **overrides):
    """Helper: insert a minimal SessionRecord for evaluation tests."""
    from sqlalchemy.orm import Session

    values = {
        "session_id": session_id,
        "client_source": "test",
        "started": "2026-05-11T10:00:00+00:00",
        "ended": "2026-05-11T10:30:00+00:00",
        "updated_at": "2026-05-11T10:30:00+00:00",
    }
    values.update(overrides)

    engine = database_module.get_engine(db_path)
    with Session(engine) as session:
        session.add(database_module.SessionRecord(**values))
        session.commit()


def test_upsert_session_evaluation_creates_new(database_module, isolated_home):
    """Upsert evaluation on an existing session sets evaluation columns."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path)

    database_module.upsert_session_evaluation(
        session_id="sess-1",
        outcome="solved",
        source="manual",
        confidence=None,
        task_title="Fixed dashboard navigation",
        summary=None,
        evidence=["User marked solved"],
        failure_reason=None,
        db_path=db_path,
    )

    result = database_module.get_session_evaluation("sess-1", db_path=db_path)
    assert result is not None
    assert result["outcome"] == "solved"
    assert result["source"] == "manual"
    assert result["task_title"] == "Fixed dashboard navigation"
    assert result["evidence"] == ["User marked solved"]
    assert result["failure_reason"] is None
    assert result["confidence"] is None
    assert result["evaluated_at"] is not None


def test_upsert_session_evaluation_overwrites_existing(database_module, isolated_home):
    """Second upsert replaces the first evaluation."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path)

    database_module.upsert_session_evaluation(
        session_id="sess-1",
        outcome="solved",
        source="manual",
        db_path=db_path,
    )
    database_module.upsert_session_evaluation(
        session_id="sess-1",
        outcome="failed",
        source="manual",
        failure_reason="Agent got stuck",
        db_path=db_path,
    )

    result = database_module.get_session_evaluation("sess-1", db_path=db_path)
    assert result is not None
    assert result["outcome"] == "failed"
    assert result["failure_reason"] == "Agent got stuck"


def test_upsert_session_evaluation_raises_when_session_not_found(
    database_module, isolated_home
):
    """Upsert raises ValueError when session doesn't exist."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    with pytest.raises(ValueError, match="Session not found"):
        database_module.upsert_session_evaluation(
            session_id="nonexistent",
            outcome="solved",
            source="manual",
            db_path=db_path,
        )


def test_get_session_evaluation_returns_none_when_not_evaluated(
    database_module, isolated_home
):
    """GET returns None when session exists but has no evaluation."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path)

    result = database_module.get_session_evaluation("sess-1", db_path=db_path)
    assert result is None


def test_get_session_evaluation_returns_none_when_session_absent(
    database_module, isolated_home
):
    """GET returns None when session doesn't exist."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    result = database_module.get_session_evaluation("nonexistent", db_path=db_path)
    assert result is None


def test_delete_session_evaluation_clears_columns(database_module, isolated_home):
    """DELETE clears evaluation columns and returns True."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path)

    database_module.upsert_session_evaluation(
        session_id="sess-1",
        outcome="solved",
        source="manual",
        db_path=db_path,
    )

    deleted = database_module.delete_session_evaluation("sess-1", db_path=db_path)
    assert deleted is True

    result = database_module.get_session_evaluation("sess-1", db_path=db_path)
    assert result is None


def test_delete_session_evaluation_returns_false_when_session_absent(
    database_module, isolated_home
):
    """DELETE returns False when session doesn't exist."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    deleted = database_module.delete_session_evaluation("nonexistent", db_path=db_path)
    assert deleted is False


# ---------------------------------------------------------------------------
# Slice 4: Model Effectiveness Aggregation API
# ---------------------------------------------------------------------------


def test_model_effectiveness_groups_by_primary_model(database_module, isolated_home):
    """Aggregation attributes each session to its primary_model only."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    _insert_session_record(
        database_module,
        db_path,
        "sess-solved",
        client_source="codex",
        primary_provider="openai",
        primary_model="gpt-5.5",
        models_json='{"gpt-5.5": 0.50, "claude-sonnet": 0.05}',
        providers_json='{"openai": 0.50, "anthropic": 0.05}',
        total_cost_usd=0.50,
        outcome="solved",
        source="manual",
    )
    _insert_session_record(
        database_module,
        db_path,
        "sess-partial",
        client_source="codex",
        primary_provider="openai",
        primary_model="gpt-5.5",
        total_cost_usd=0.25,
        outcome="partial",
        source="manual",
    )
    _insert_session_record(
        database_module,
        db_path,
        "sess-failed",
        client_source="claude-code",
        primary_provider="anthropic",
        primary_model="claude-sonnet",
        total_cost_usd=0.75,
        outcome="failed",
        source="manual",
    )

    result = database_module.aggregate_model_effectiveness(
        group_by="model",
        db_path=db_path,
    )

    by_key = {group["key"]: group for group in result["groups"]}
    assert set(by_key) == {"gpt-5.5", "claude-sonnet"}

    gpt = by_key["gpt-5.5"]
    assert gpt["session_count"] == 2
    assert gpt["evaluated_count"] == 2
    assert gpt["solved_count"] == 1
    assert gpt["partial_count"] == 1
    assert gpt["failed_count"] == 0
    assert gpt["solve_rate"] == pytest.approx(0.5)
    assert gpt["total_cost_usd"] == pytest.approx(0.75)
    assert gpt["cost_per_solved"] == pytest.approx(0.75)


def test_model_effectiveness_unknown_and_no_op_do_not_pollute_solve_rate(
    database_module, isolated_home
):
    """Unknown and no-op sessions are visible but excluded from solve_rate."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    _insert_session_record(
        database_module,
        db_path,
        "sess-solved",
        primary_model="gpt-5.5",
        total_cost_usd=0.40,
        outcome="solved",
        source="manual",
    )
    _insert_session_record(
        database_module,
        db_path,
        "sess-unknown-explicit",
        primary_model="gpt-5.5",
        total_cost_usd=0.20,
        outcome="unknown",
        source="manual",
    )
    _insert_session_record(
        database_module,
        db_path,
        "sess-unknown-null",
        primary_model="gpt-5.5",
        total_cost_usd=0.20,
    )
    _insert_session_record(
        database_module,
        db_path,
        "sess-no-op",
        primary_model="gpt-5.5",
        total_cost_usd=0.20,
        outcome="no_op",
        source="manual",
    )

    result = database_module.aggregate_model_effectiveness(
        group_by="model",
        db_path=db_path,
    )

    group = result["groups"][0]
    assert group["session_count"] == 4
    assert group["evaluated_count"] == 1
    assert group["solved_count"] == 1
    assert group["unknown_count"] == 2
    assert group["no_op_count"] == 1
    assert group["solve_rate"] == pytest.approx(1.0)
    assert group["cost_per_solved"] == pytest.approx(0.40)


def test_model_effectiveness_groups_by_source_and_filters(
    database_module, isolated_home
):
    """Aggregation supports client source grouping with date/source filters."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    _insert_session_record(
        database_module,
        db_path,
        "sess-in-range",
        client_source="codex",
        started="2026-05-11T10:00:00+00:00",
        ended="2026-05-11T10:20:00+00:00",
        total_cost_usd=0.25,
        outcome="solved",
        source="manual",
    )
    _insert_session_record(
        database_module,
        db_path,
        "sess-other-source",
        client_source="claude-code",
        started="2026-05-11T11:00:00+00:00",
        ended="2026-05-11T11:30:00+00:00",
        total_cost_usd=0.25,
        outcome="failed",
        source="manual",
    )
    _insert_session_record(
        database_module,
        db_path,
        "sess-out-of-range",
        client_source="codex",
        started="2026-05-10T10:00:00+00:00",
        ended="2026-05-10T10:30:00+00:00",
        total_cost_usd=0.25,
        outcome="failed",
        source="manual",
    )

    result = database_module.aggregate_model_effectiveness(
        group_by="source",
        since="2026-05-11T10:00:00.000Z",
        until="2026-05-11T10:20:00.000Z",
        client_source="codex",
        db_path=db_path,
    )

    assert [group["key"] for group in result["groups"]] == ["codex"]
    group = result["groups"][0]
    assert group["session_count"] == 1
    assert group["solved_count"] == 1
    assert group["failed_count"] == 0


def test_model_effectiveness_cost_per_solved_null_when_zero_solved(
    database_module, isolated_home
):
    """cost_per_solved is null when there are no solved sessions."""
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    _insert_session_record(
        database_module,
        db_path,
        "sess-failed",
        primary_provider="anthropic",
        total_cost_usd=0.25,
        outcome="failed",
        source="manual",
    )
    _insert_session_record(
        database_module,
        db_path,
        "sess-stuck",
        primary_provider="anthropic",
        total_cost_usd=0.25,
        outcome="stuck",
        source="manual",
    )

    result = database_module.aggregate_model_effectiveness(
        group_by="provider",
        db_path=db_path,
    )

    group = result["groups"][0]
    assert group["key"] == "anthropic"
    assert group["evaluated_count"] == 2
    assert group["stuck_count"] == 1
    assert group["solve_rate"] == pytest.approx(0.0)
    assert group["cost_per_solved"] is None


# ---------------------------------------------------------------------------
# Slice 8: Daily Effectiveness Report
# ---------------------------------------------------------------------------


def test_daily_effectiveness_report_aggregates_day_metrics_in_sql(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    _insert_session_record(
        database_module,
        db_path,
        "sess-solved",
        client_source="codex",
        primary_model="gpt-5.5",
        started="2026-05-10T09:00:00+00:00",
        ended="2026-05-10T09:20:00+00:00",
        total_cost_usd=0.40,
        outcome="solved",
        source="manual",
    )
    _insert_session_record(
        database_module,
        db_path,
        "sess-stuck",
        client_source="gemini",
        primary_model="gemini-flash",
        started="2026-05-10T10:00:00+00:00",
        ended="2026-05-10T10:20:00+00:00",
        total_cost_usd=0.10,
        outcome="stuck",
        source="llm",
    )
    _insert_session_record(
        database_module,
        db_path,
        "sess-no-op",
        client_source="claude-code",
        primary_model="claude-sonnet",
        started="2026-05-10T11:00:00+00:00",
        ended="2026-05-10T11:05:00+00:00",
        total_cost_usd=0.05,
        outcome="no_op",
        source="llm",
    )
    _insert_session_record(
        database_module,
        db_path,
        "sess-unknown",
        client_source="codex",
        primary_model="gpt-5.5",
        started="2026-05-10T12:00:00+00:00",
        ended="2026-05-10T12:05:00+00:00",
        total_cost_usd=0.05,
    )
    _insert_session_record(
        database_module,
        db_path,
        "sess-other-day",
        client_source="codex",
        primary_model="gpt-5.5",
        started="2026-05-11T09:00:00+00:00",
        ended="2026-05-11T09:20:00+00:00",
        total_cost_usd=9.00,
        outcome="failed",
        source="manual",
    )

    report = database_module.daily_session_effectiveness_report(
        date="2026-05-10",
        db_path=db_path,
    )

    assert report["date"] == "2026-05-10"
    assert report["session_count"] == 4
    assert report["evaluated_count"] == 2
    assert report["classified_count"] == 3
    assert report["solved_count"] == 1
    assert report["stuck_count"] == 1
    assert report["no_op_count"] == 1
    assert report["unknown_count"] == 1
    assert report["total_cost_usd"] == pytest.approx(0.60)
    assert "You ran 4 AI sessions" in report["summary"]
    assert report["highlights"]
    assert report["needs_attention"] == ["gemini / gemini-flash had 1 stuck session"]


def test_daily_effectiveness_report_returns_sql_model_source_groups(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    _insert_session_record(
        database_module,
        db_path,
        "sess-gpt-solved",
        client_source="codex",
        primary_model="gpt-5.5",
        started="2026-05-10T09:00:00+00:00",
        total_cost_usd=0.20,
        outcome="solved",
        source="manual",
    )
    _insert_session_record(
        database_module,
        db_path,
        "sess-gpt-failed",
        client_source="codex",
        primary_model="gpt-5.5",
        started="2026-05-10T10:00:00+00:00",
        total_cost_usd=0.30,
        outcome="failed",
        source="manual",
    )
    _insert_session_record(
        database_module,
        db_path,
        "sess-claude-solved",
        client_source="claude-code",
        primary_model="claude-sonnet",
        started="2026-05-10T11:00:00+00:00",
        total_cost_usd=0.60,
        outcome="solved",
        source="manual",
    )

    report = database_module.daily_session_effectiveness_report(
        date="2026-05-10",
        db_path=db_path,
    )

    groups = {
        (group["client_source"], group["model"]): group for group in report["groups"]
    }
    assert groups[("codex", "gpt-5.5")]["session_count"] == 2
    assert groups[("codex", "gpt-5.5")]["evaluated_count"] == 2
    assert groups[("codex", "gpt-5.5")]["solved_count"] == 1
    assert groups[("codex", "gpt-5.5")]["failed_count"] == 1
    assert groups[("codex", "gpt-5.5")]["solve_rate"] == pytest.approx(0.5)
    assert groups[("codex", "gpt-5.5")]["cost_per_solved"] == pytest.approx(0.50)
    assert (
        "claude-code / claude-sonnet solved 1/1 evaluated sessions"
        in report["model_takeaways"]
    )


def test_daily_effectiveness_report_rejects_invalid_date(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    with pytest.raises(ValueError, match="Invalid date"):
        database_module.daily_session_effectiveness_report(
            date="2026-02-30",
            db_path=db_path,
        )


# ---------------------------------------------------------------------------
# Slice 7: Session Evaluation Jobs
# ---------------------------------------------------------------------------


def test_create_session_evaluation_job_persists_queued_job(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(
        database_module,
        db_path,
        "sess-llm",
        client_source="codex",
    )

    job = database_module.create_session_evaluation_job(
        session_id="sess-llm",
        client_source="codex",
        db_path=db_path,
    )

    assert job["job_id"]
    assert job["kind"] == "session_evaluation"
    assert job["session_id"] == "sess-llm"
    assert job["status"] == "queued"
    assert job["error"] is None

    polled = database_module.get_evaluation_job(job["job_id"], db_path=db_path)
    assert polled == job


def test_create_session_evaluation_job_records_trigger(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(
        database_module, db_path, "sess-manual", client_source="codex"
    )

    manual = database_module.create_session_evaluation_job(
        session_id="sess-manual",
        client_source="codex",
        trigger="manual",
        db_path=db_path,
    )

    assert manual["trigger"] == "manual"


def test_create_session_evaluation_job_defaults_trigger_to_manual(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(
        database_module, db_path, "sess-default", client_source="codex"
    )

    job = database_module.create_session_evaluation_job(
        session_id="sess-default",
        client_source="codex",
        db_path=db_path,
    )

    assert job["trigger"] == "manual"


def test_find_active_session_evaluation_job_reuses_non_stale_job(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path, "sess-llm", client_source="codex")

    job = database_module.create_session_evaluation_job(
        session_id="sess-llm",
        client_source="codex",
        db_path=db_path,
    )

    active = database_module.find_active_session_evaluation_job(
        session_id="sess-llm",
        db_path=db_path,
    )

    assert active is not None
    assert active["job_id"] == job["job_id"]


def test_create_session_evaluation_job_reuses_active_job_after_unique_conflict(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path, "sess-llm", client_source="codex")

    first = database_module.create_session_evaluation_job(
        session_id="sess-llm",
        client_source="codex",
        db_path=db_path,
    )
    second = database_module.create_session_evaluation_job(
        session_id="sess-llm",
        client_source="codex",
        db_path=db_path,
    )

    assert second["job_id"] == first["job_id"]


def test_stale_session_evaluation_job_is_failed_before_new_job(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path, "sess-llm", client_source="codex")

    old_job = database_module.create_session_evaluation_job(
        session_id="sess-llm",
        client_source="codex",
        created_at="2026-05-11T10:00:00+00:00",
        db_path=db_path,
    )

    active = database_module.find_active_session_evaluation_job(
        session_id="sess-llm",
        now="2026-05-11T10:06:00+00:00",
        db_path=db_path,
    )

    assert active is None
    stale = database_module.get_evaluation_job(old_job["job_id"], db_path=db_path)
    assert stale is not None
    assert stale["status"] == "failed"
    assert stale["error"] == "Evaluation job timed out"


def test_running_session_evaluation_job_uses_started_at_for_stale_check(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(
        database_module, db_path, "sess-running", client_source="codex"
    )

    job = database_module.create_session_evaluation_job(
        session_id="sess-running",
        client_source="codex",
        created_at="2026-05-11T10:00:00+00:00",
        db_path=db_path,
    )
    claimed = database_module.claim_next_evaluation_job(
        now="2026-05-11T10:05:00+00:00",
        db_path=db_path,
    )

    active = database_module.find_active_session_evaluation_job(
        session_id="sess-running",
        now="2026-05-11T10:06:00+00:00",
        db_path=db_path,
    )

    assert claimed["job_id"] == job["job_id"]
    assert active is not None
    assert active["job_id"] == job["job_id"]
    assert active["status"] == "running"


def test_claim_next_evaluation_job_orders_manual_before_auto_then_newest_session(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(
        database_module,
        db_path,
        "old-auto",
        client_source="codex",
        updated_at="2026-05-14T10:00:00+00:00",
    )
    _insert_session_record(
        database_module,
        db_path,
        "new-auto",
        client_source="codex",
        updated_at="2026-05-14T11:00:00+00:00",
    )
    _insert_session_record(
        database_module,
        db_path,
        "manual",
        client_source="codex",
        updated_at="2026-05-14T09:00:00+00:00",
    )
    database_module.create_session_evaluation_job(
        session_id="old-auto",
        client_source="codex",
        trigger="auto",
        db_path=db_path,
    )
    database_module.create_session_evaluation_job(
        session_id="new-auto",
        client_source="codex",
        trigger="auto",
        db_path=db_path,
    )
    database_module.create_session_evaluation_job(
        session_id="manual",
        client_source="codex",
        trigger="manual",
        db_path=db_path,
    )

    first = database_module.claim_next_evaluation_job(db_path=db_path)
    second = database_module.claim_next_evaluation_job(db_path=db_path)
    third = database_module.claim_next_evaluation_job(db_path=db_path)

    assert first["session_id"] == "manual"
    assert first["status"] == "running"
    assert second["session_id"] == "new-auto"
    assert third["session_id"] == "old-auto"


def test_claim_next_evaluation_job_skips_candidate_claimed_by_competing_worker(
    database_module, isolated_home, monkeypatch
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(
        database_module,
        db_path,
        "first",
        client_source="codex",
        updated_at="2026-05-14T11:00:00+00:00",
    )
    _insert_session_record(
        database_module,
        db_path,
        "second",
        client_source="codex",
        updated_at="2026-05-14T10:00:00+00:00",
    )
    first = database_module.create_session_evaluation_job(
        session_id="first",
        client_source="codex",
        trigger="manual",
        db_path=db_path,
    )
    second = database_module.create_session_evaluation_job(
        session_id="second",
        client_source="codex",
        trigger="manual",
        db_path=db_path,
    )

    original_next_queued_job_id = database_module.evaluation_jobs._next_queued_job_id
    returned_stale_candidate = False

    def stale_candidate_once(session):
        nonlocal returned_stale_candidate
        if returned_stale_candidate:
            return original_next_queued_job_id(session)
        returned_stale_candidate = True
        with database_module.Session(database_module.get_engine(db_path)) as session:
            job = session.get(database_module.EvaluationJob, first["job_id"])
            job.status = "running"
            job.started_at = "2026-05-14T11:01:00+00:00"
            session.commit()
        return first["job_id"]

    monkeypatch.setattr(
        database_module.evaluation_jobs,
        "_next_queued_job_id",
        stale_candidate_once,
    )

    claimed = database_module.claim_next_evaluation_job(
        now="2026-05-14T11:02:00+00:00",
        db_path=db_path,
    )

    assert claimed["job_id"] == second["job_id"]
    assert (
        database_module.get_evaluation_job(first["job_id"], db_path=db_path)[
            "started_at"
        ]
        == "2026-05-14T11:01:00+00:00"
    )


def test_get_evaluation_job_progress_reports_queue_position(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path, "running", client_source="codex")
    _insert_session_record(database_module, db_path, "queued-1", client_source="codex")
    _insert_session_record(database_module, db_path, "queued-2", client_source="codex")

    running = database_module.create_session_evaluation_job(
        session_id="running",
        client_source="codex",
        trigger="manual",
        db_path=db_path,
    )
    queued_1 = database_module.create_session_evaluation_job(
        session_id="queued-1",
        client_source="codex",
        trigger="manual",
        db_path=db_path,
    )
    queued_2 = database_module.create_session_evaluation_job(
        session_id="queued-2",
        client_source="codex",
        trigger="auto",
        db_path=db_path,
    )
    database_module.claim_next_evaluation_job(db_path=db_path)

    assert (
        database_module.get_evaluation_job_progress(running["job_id"], db_path=db_path)[
            "queue_position"
        ]
        == 1
    )
    queued_progress = database_module.get_evaluation_job_progress(
        queued_1["job_id"], db_path=db_path
    )
    assert queued_progress["ahead_count"] == 1
    assert queued_progress["queue_position"] == 2
    assert (
        database_module.get_evaluation_job_progress(
            queued_2["job_id"], db_path=db_path
        )["queue_position"]
        == 3
    )


def test_evaluation_job_active_helpers_count_list_and_fail_stale_running_jobs(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path, "stale", client_source="codex")
    _insert_session_record(database_module, db_path, "fresh", client_source="codex")

    stale = database_module.create_session_evaluation_job(
        session_id="stale",
        client_source="codex",
        trigger="manual",
        created_at="2026-05-14T09:00:00+00:00",
        db_path=db_path,
    )
    fresh = database_module.create_session_evaluation_job(
        session_id="fresh",
        client_source="codex",
        trigger="auto",
        created_at="2026-05-14T09:03:00+00:00",
        db_path=db_path,
    )
    first = database_module.claim_next_evaluation_job(
        now="2026-05-14T09:00:00+00:00",
        db_path=db_path,
    )
    second = database_module.claim_next_evaluation_job(
        now="2026-05-14T09:03:00+00:00",
        db_path=db_path,
    )

    assert [first["job_id"], second["job_id"]] == [stale["job_id"], fresh["job_id"]]
    assert database_module.count_running_evaluation_jobs(db_path=db_path) == 2
    active = database_module.list_active_evaluation_jobs(
        session_ids=["fresh"],
        db_path=db_path,
    )
    assert [job["job_id"] for job in active] == [fresh["job_id"]]

    failed_count = database_module.fail_stale_running_evaluation_jobs(
        now="2026-05-14T09:06:00+00:00",
        db_path=db_path,
    )

    assert failed_count == 1
    assert database_module.count_running_evaluation_jobs(db_path=db_path) == 1
    assert (
        database_module.get_evaluation_job(
            stale["job_id"],
            db_path=db_path,
        )["status"]
        == "failed"
    )
    assert (
        database_module.get_evaluation_job(
            fresh["job_id"],
            db_path=db_path,
        )["status"]
        == "running"
    )


def test_fail_stale_running_evaluation_jobs_does_not_overwrite_terminal_update(
    database_module, isolated_home, monkeypatch
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path, "stale", client_source="codex")

    job = database_module.create_session_evaluation_job(
        session_id="stale",
        client_source="codex",
        trigger="manual",
        created_at="2026-05-14T09:00:00+00:00",
        db_path=db_path,
    )
    database_module.claim_next_evaluation_job(
        now="2026-05-14T09:00:00+00:00",
        db_path=db_path,
    )
    original_fail_stale_job = getattr(
        database_module.evaluation_jobs,
        "_fail_stale_evaluation_job",
        None,
    )

    def terminal_update_before_stale_fail(session, stale_job, finished_at):
        session.execute(
            database_module.evaluation_jobs.update(database_module.EvaluationJob)
            .where(database_module.EvaluationJob.job_id == stale_job.job_id)
            .values(
                status="succeeded",
                finished_at="2026-05-14T09:05:30+00:00",
                error=None,
            )
            .execution_options(synchronize_session=False)
        )
        return original_fail_stale_job(session, stale_job, finished_at)

    monkeypatch.setattr(
        database_module.evaluation_jobs,
        "_fail_stale_evaluation_job",
        terminal_update_before_stale_fail,
        raising=False,
    )

    failed_count = database_module.fail_stale_running_evaluation_jobs(
        now="2026-05-14T09:06:00+00:00",
        db_path=db_path,
    )

    current = database_module.get_evaluation_job(job["job_id"], db_path=db_path)
    assert failed_count == 0
    assert current["status"] == "succeeded"
    assert current["finished_at"] == "2026-05-14T09:05:30+00:00"


def test_find_active_session_evaluation_job_does_not_overwrite_terminal_update(
    database_module, isolated_home, monkeypatch
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path, "stale", client_source="codex")

    job = database_module.create_session_evaluation_job(
        session_id="stale",
        client_source="codex",
        trigger="manual",
        created_at="2026-05-14T09:00:00+00:00",
        db_path=db_path,
    )
    original_fail_stale_job = getattr(
        database_module.evaluation_jobs,
        "_fail_stale_evaluation_job",
        None,
    )

    def terminal_update_before_stale_fail(session, stale_job, finished_at):
        session.execute(
            database_module.evaluation_jobs.update(database_module.EvaluationJob)
            .where(database_module.EvaluationJob.job_id == stale_job.job_id)
            .values(
                status="succeeded",
                finished_at="2026-05-14T09:05:30+00:00",
                error=None,
            )
            .execution_options(synchronize_session=False)
        )
        return original_fail_stale_job(session, stale_job, finished_at)

    monkeypatch.setattr(
        database_module.evaluation_jobs,
        "_fail_stale_evaluation_job",
        terminal_update_before_stale_fail,
        raising=False,
    )

    active = database_module.find_active_session_evaluation_job(
        session_id="stale",
        now="2026-05-14T09:06:00+00:00",
        db_path=db_path,
    )

    current = database_module.get_evaluation_job(job["job_id"], db_path=db_path)
    assert active is None
    assert current["status"] == "succeeded"
    assert current["finished_at"] == "2026-05-14T09:05:30+00:00"


def test_mark_evaluation_job_succeeded_does_not_overwrite_failed_job(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path, "failed", client_source="codex")

    job = database_module.create_session_evaluation_job(
        session_id="failed",
        client_source="codex",
        trigger="manual",
        db_path=db_path,
    )
    database_module.claim_next_evaluation_job(db_path=db_path)
    database_module.mark_evaluation_job_failed(
        job["job_id"],
        "first failure",
        db_path=db_path,
    )

    database_module.mark_evaluation_job_succeeded(job["job_id"], db_path=db_path)

    current = database_module.get_evaluation_job(job["job_id"], db_path=db_path)
    assert current["status"] == "failed"
    assert current["error"] == "first failure"


def test_mark_evaluation_job_running_does_not_revive_failed_job(
    database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path, "failed", client_source="codex")

    job = database_module.create_session_evaluation_job(
        session_id="failed",
        client_source="codex",
        trigger="manual",
        db_path=db_path,
    )
    database_module.claim_next_evaluation_job(db_path=db_path)
    database_module.mark_evaluation_job_failed(
        job["job_id"],
        "first failure",
        db_path=db_path,
    )

    changed = database_module.mark_evaluation_job_running(
        job["job_id"], db_path=db_path
    )

    current = database_module.get_evaluation_job(job["job_id"], db_path=db_path)
    assert changed is False
    assert current["status"] == "failed"
    assert current["error"] == "first failure"


def test_migrate_database_creates_evaluation_jobs_table(
    database_module, schema_migrations_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    engine = database_module.get_engine(db_path)
    database_module.metadata.drop_all(engine)

    applied = schema_migrations_module.migrate_database(db_path)

    assert "evaluation_jobs.create" in applied
    assert "evaluation_jobs.active_unique_index" in applied
    assert schema_migrations_module._table_exists(engine, "evaluation_jobs")
    assert {
        "job_id",
        "kind",
        "session_id",
        "client_source",
        "status",
        "created_at",
        "started_at",
        "finished_at",
        "error",
    }.issubset(schema_migrations_module._table_column_names(engine, "evaluation_jobs"))
    assert "ix_evaluation_jobs_one_active_per_session" in (
        schema_migrations_module._index_names(engine, "evaluation_jobs")
    )


def test_migrate_database_adds_evaluation_job_trigger(
    schema_migrations_module, database_module, isolated_home
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    engine = database_module.get_engine(db_path)

    with engine.begin() as connection:
        connection.execute(
            database_module.text("ALTER TABLE evaluation_jobs DROP COLUMN trigger")
        )

    applied = schema_migrations_module.migrate_database(db_path)

    assert "evaluation_jobs.trigger" in applied
    assert "trigger" in schema_migrations_module._table_column_names(
        engine, "evaluation_jobs"
    )
