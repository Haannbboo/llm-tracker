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
    assert "usage.prompt_length" in changes
    assert "usage.base_url_id" in changes
    assert "usage.input_cost_usd" in changes
    assert "usage.output_cost_usd" in changes
    assert "usage.total_cost_usd" in changes

    import sqlite3

    connection = sqlite3.connect(db_file)
    table_info = connection.execute("PRAGMA table_info(usage)").fetchall()
    connection.close()

    defaults = {row[1]: row[4] for row in table_info}
    assert defaults["input_cost_usd"] == "0"
    assert defaults["output_cost_usd"] == "0"
    assert defaults["total_cost_usd"] == "0"


def test_summarize_usage_includes_cost_totals(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    database_module.log_usage(
        database_module.Usage(
            ts="2026-04-17T00:00:00+00:00",
            provider="test-provider",
            model="test-model",
            endpoint="/v1/responses",
            prompt_tokens=10,
            completion_tokens=5,
            reasoning_tokens=1,
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
            ts="2026-04-17T01:00:00+00:00",
            provider="test-provider",
            model="test-model",
            endpoint="/v1/responses",
            prompt_tokens=20,
            completion_tokens=10,
            reasoning_tokens=2,
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

    summary = database_module.summarize_usage()

    assert summary == [
        {
            "provider": "test-provider",
            "model": "test-model",
            "requests": 2,
            "prompt_tokens": 30,
            "completion_tokens": 15,
            "reasoning_tokens": 3,
            "cached_tokens": 6,
            "total_tokens": 45,
            "avg_latency_ms": 150.0,
            "input_cost_usd": 6e-05,
            "output_cost_usd": 9e-05,
            "total_cost_usd": 0.00015,
            "successful_requests": 2,
            "failed_requests": 0,
        }
    ]


def test_summarize_usage_counts_failed_requests(database_module, isolated_home):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    database_module.log_usage(
        database_module.Usage(
            ts="2026-04-17T00:00:00+00:00",
            provider="test-provider",
            model="test-model",
            endpoint="/v1/responses",
            prompt_tokens=10,
            completion_tokens=5,
            reasoning_tokens=1,
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
            ts="2026-04-17T01:00:00+00:00",
            provider="test-provider",
            model="test-model",
            endpoint="/v1/responses",
            prompt_tokens=20,
            completion_tokens=10,
            reasoning_tokens=2,
            cached_tokens=4,
            total_tokens=30,
            latency_ms=200,
            ttft_ms=None,
            tool_tokens=None,
            cache_creation_tokens=None,
            input_cost_usd=0.00004,
            output_cost_usd=0.00006,
            total_cost_usd=0.0001,
            status=503,
            base_url_id=None,
        ),
        db_path=db_path,
    )
    database_module.log_usage(
        database_module.Usage(
            ts="2026-04-17T02:00:00+00:00",
            provider="test-provider",
            model="test-model",
            endpoint="/v1/responses",
            prompt_tokens=30,
            completion_tokens=15,
            reasoning_tokens=3,
            cached_tokens=6,
            total_tokens=45,
            latency_ms=300,
            ttft_ms=None,
            tool_tokens=None,
            cache_creation_tokens=None,
            input_cost_usd=0.00006,
            output_cost_usd=0.00009,
            total_cost_usd=0.00015,
            status=None,
            base_url_id=None,
        ),
        db_path=db_path,
    )

    summary = database_module.summarize_usage()

    assert summary == [
        {
            "provider": "test-provider",
            "model": "test-model",
            "requests": 3,
            "prompt_tokens": 60,
            "completion_tokens": 30,
            "reasoning_tokens": 6,
            "cached_tokens": 12,
            "total_tokens": 90,
            "avg_latency_ms": 200.0,
            "input_cost_usd": 0.00012,
            "output_cost_usd": 0.00018,
            "total_cost_usd": 0.0003,
            "successful_requests": 2,
            "failed_requests": 1,
        }
    ]


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
            "cached_tokens": 6,
            "total_tokens": 45,
            "input_cost_usd": 6e-05,
            "output_cost_usd": 9e-05,
            "total_cost_usd": 0.00015,
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
                raise database_module.IntegrityError("INSERT", None, Exception("dup"))
            state["updated"] = True

        def rollback(self):
            state["rolled_back"] = True

    monkeypatch.setattr(database_module, "get_engine", lambda db_path=None: object())
    monkeypatch.setattr(database_module, "Session", FakeSession)

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
