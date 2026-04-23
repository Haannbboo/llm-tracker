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
        base_url_id=base_url_id,
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
            "base_url_id": base_url_id,
            "base_url": "https://api.example.com/v1",
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
    assert rows[0]["base_url_id"] is None
    assert rows[0]["base_url"] is None


def test_init_db_adds_base_url_id_to_existing_usage_table(
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
    connection.commit()
    connection.close()

    database_module.init_db(str(db_file))

    column_names = database_module._usage_column_names(
        database_module.get_engine(str(db_file))
    )
    assert "base_url_id" in column_names


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
        rows = connection.execute(
            database_module.select(database_module.base_urls_table)
        ).all()

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

    class FakeResult:
        inserted_primary_key = [99]

    state = {"attempt": -1, "updated": False}

    class FakeConnection:
        def __init__(self, attempt: int):
            self.attempt = attempt

        def execute(self, statement, params=None):
            sql = str(statement)
            if sql.startswith("INSERT INTO base_urls"):
                raise database_module.IntegrityError("INSERT", params, Exception("dup"))
            if sql.startswith("UPDATE base_urls"):
                state["updated"] = True
                return FakeResult()
            raise AssertionError(f"unexpected SQL: {sql}")

    class FakeBegin:
        def __init__(self, attempt: int):
            self.connection = FakeConnection(attempt)

        def __enter__(self):
            return self.connection

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def begin(self):
            state["attempt"] += 1
            return FakeBegin(state["attempt"])

    def fake_base_url_row(base_url, connection):
        if connection.attempt == 0:
            return None
        return FakeRow()

    monkeypatch.setattr(
        database_module, "get_engine", lambda db_path=None: FakeEngine()
    )
    monkeypatch.setattr(database_module, "_base_url_row", fake_base_url_row)

    base_url_id = database_module.get_or_create_base_url(
        "https://race.example/v1",
        provider_name="OpenAI",
        source="proxy_config",
    )

    assert base_url_id == 7
    assert state["updated"] is True


def test_init_db_drops_removed_base_url_columns(database_module, isolated_home):
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

    database_module.init_db(str(db_file))

    column_names = database_module._base_url_column_names(
        database_module.get_engine(str(db_file))
    )
    assert "validation_status" not in column_names
    assert "last_error" not in column_names


def test_ensure_usage_columns_ignores_duplicate_column_from_concurrent_migration(
    database_module, monkeypatch
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
                raise database_module.SQLAlchemyError(
                    "duplicate column name: prompt_length"
                )
            if "base_url_id" in sql:
                state["column_exists"].add("base_url_id")
                raise database_module.SQLAlchemyError(
                    "duplicate column name: base_url_id"
                )
            raise database_module.SQLAlchemyError("duplicate column")

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
