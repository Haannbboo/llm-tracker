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

    rows = database_module.fetch_recent_usage(limit=10)

    assert rows == [
        {
            "id": 1,
            "ts": "2026-04-17T00:00:00+00:00",
            "provider": "test-provider",
            "model": "test-model",
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
            "status": 200,
        }
    ]


def test_init_db_adds_prompt_length_to_existing_usage_table(
    database_module, isolated_home
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

    rows = database_module.fetch_recent_usage(limit=10)
    assert rows[0]["prompt_length"] == 0


def test_ensure_usage_columns_ignores_duplicate_column_from_concurrent_migration(
    database_module, monkeypatch
):
    state = {"column_exists": False}

    class FakeInspector:
        def get_table_names(self):
            return ["usage"]

        def get_columns(self, table_name):
            columns = [{"name": "id"}, {"name": "prompt_tokens"}]
            if state["column_exists"]:
                columns.append({"name": "prompt_length"})
            return columns

    class FakeConnection:
        def execute(self, statement):
            state["column_exists"] = True
            raise database_module.SQLAlchemyError(
                "duplicate column name: prompt_length"
            )

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

    monkeypatch.setattr(database_module, "inspect", lambda engine: FakeInspector())

    database_module._ensure_usage_columns(FakeEngine())
