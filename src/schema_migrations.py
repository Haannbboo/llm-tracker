from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from .database import get_engine, init_db


def _ts_date_expr(dialect: str, col: str = "ts") -> str:
    """Return SQL expression that extracts a date string from ts.

    Handles both ISO string and integer microsecond formats.
    """
    if dialect == "postgresql":
        return (
            f"CASE WHEN {col}::text ~ '^[0-9]{{10,}}$' "
            f"THEN TO_TIMESTAMP({col} / 1000000.0)::date::text "
            f"ELSE SUBSTRING({col}::text, 1, 10) END"
        )
    return (
        f"CASE WHEN typeof({col}) = 'integer' "
        f"THEN date({col} / 1000000, 'unixepoch') "
        f"ELSE substr({col}, 1, 10) END"
    )


def _table_exists(engine: Engine, table_name: str) -> bool:
    return table_name in inspect(engine).get_table_names()


def _table_column_names(engine: Engine, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


def _index_names(engine: Engine, table_name: str) -> set[str]:
    return {index["name"] for index in inspect(engine).get_indexes(table_name)}  # type: ignore[misc]


def _ensure_evaluation_jobs_active_unique_index(engine: Engine) -> bool:
    index_name = "ix_evaluation_jobs_one_active_per_session"
    if index_name in _index_names(engine, "evaluation_jobs"):
        return False

    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(
                text(
                    f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS {index_name}
                    ON evaluation_jobs (kind, session_id)
                    WHERE status IN ('queued', 'running')
                    """
                )
            )
        else:
            connection.execute(
                text(
                    f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS {index_name}
                    ON evaluation_jobs (kind, session_id)
                    WHERE status IN ('queued', 'running')
                    """
                )
            )
    return True


def _ensure_index(engine: Engine, table_name: str, index_name: str, sql: str) -> bool:
    if index_name in _index_names(engine, table_name):
        return False
    with engine.begin() as connection:
        connection.execute(text(sql))
    return True


def _ensure_column(
    engine: Engine,
    table_name: str,
    column_name: str,
    *,
    sqlite_definition: str,
    postgresql_definition: str,
) -> bool:
    if column_name in _table_column_names(engine, table_name):
        return False

    definition = (
        postgresql_definition
        if engine.dialect.name == "postgresql"
        else sqlite_definition
    )

    with engine.begin() as connection:
        try:
            if engine.dialect.name == "postgresql":
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {definition}"
                    )
                )
            else:
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
                    )
                )
            return True
        except SQLAlchemyError:
            if column_name not in _table_column_names(engine, table_name):
                raise
            return False


def _drop_column(engine: Engine, table_name: str, column_name: str) -> bool:
    if column_name not in _table_column_names(engine, table_name):
        return False

    with engine.begin() as connection:
        try:
            if engine.dialect.name == "postgresql":
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS {column_name}"
                    )
                )
            else:
                connection.execute(
                    text(f"ALTER TABLE {table_name} DROP COLUMN {column_name}")
                )
            return True
        except SQLAlchemyError:
            if column_name in _table_column_names(engine, table_name):
                raise
            return False


def _migrate_usage_id_to_uuid(engine: Engine) -> bool:
    """Convert usage.id from INTEGER autoincrement to TEXT UUID (client-generated).

    Also clears sessions.last_usage_id to NULL — it was an INTEGER ref to the old
    usage.id and is no longer meaningful. The column type is also changed to TEXT
    so future upserts (which write UUID strings) don't fail.
    Returns True if migration was applied, False if already migrated.
    """
    from sqlalchemy import inspect as sa_inspect

    usage_cols = {c["name"]: c for c in sa_inspect(engine).get_columns("usage")}
    id_type = str(usage_cols["id"]["type"])
    if "INT" not in id_type.upper():
        return False

    dialect = engine.dialect.name
    has_sessions = _table_exists(engine, "sessions")

    with engine.begin() as connection:
        if dialect == "postgresql":
            # Generate UUIDs for existing rows in a single UPDATE
            connection.execute(text("ALTER TABLE usage ADD COLUMN id_new TEXT"))
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            connection.execute(
                text("UPDATE usage SET id_new = gen_random_uuid()::text")
            )
            # Find and drop the actual PK constraint name
            pk_name = connection.execute(
                text(
                    "SELECT constraint_name FROM information_schema.table_constraints "
                    "WHERE table_name = 'usage' AND constraint_type = 'PRIMARY KEY'"
                )
            ).scalar()
            if pk_name:
                connection.execute(text(f"ALTER TABLE usage DROP CONSTRAINT {pk_name}"))
            connection.execute(text("ALTER TABLE usage DROP COLUMN id"))
            connection.execute(text("ALTER TABLE usage RENAME COLUMN id_new TO id"))
            connection.execute(text("ALTER TABLE usage ADD PRIMARY KEY (id)"))

            if has_sessions:
                connection.execute(text("UPDATE sessions SET last_usage_id = NULL"))
                sessions_cols = {
                    c["name"]: c for c in sa_inspect(engine).get_columns("sessions")
                }
                lui_type = str(sessions_cols["last_usage_id"]["type"])
                if "INT" in lui_type.upper() and "TEXT" not in lui_type.upper():
                    connection.execute(
                        text(
                            "ALTER TABLE sessions ALTER COLUMN last_usage_id TYPE TEXT"
                        )
                    )
        elif dialect == "sqlite":
            # Get existing column info
            result = connection.execute(text("PRAGMA table_info(usage)"))
            columns = result.fetchall()

            # Build new table with TEXT id and bulk insert with SQL-level UUID gen
            new_col_defs = []
            select_parts = []
            for col in columns:
                col_name = col[1]
                col_type = col[2]
                not_null = col[3]
                default_val = col[4]

                if col_name == "id":
                    new_col_defs.append("id TEXT PRIMARY KEY")
                    uuid_expr = (
                        "lower(hex(randomblob(4))) || '-' || "
                        "lower(hex(randomblob(2))) || '-4' || "
                        "lower(substr(hex(randomblob(2)), 2)) || '-' || "
                        "printf('%x', (abs(random()) % 4 + 8)) || "
                        "lower(substr(hex(randomblob(2)), 2)) || '-' || "
                        "lower(hex(randomblob(6)))"
                    )
                    select_parts.append(uuid_expr)
                else:
                    default_clause = (
                        f" DEFAULT {default_val}" if default_val is not None else ""
                    )
                    new_col_defs.append(
                        f"{col_name} {col_type}"
                        f"{' NOT NULL' if not_null else ''}{default_clause}"
                    )
                    select_parts.append(col_name)

            new_table = "usage_new"
            cols_sql = ", ".join(new_col_defs)
            select_sql = ", ".join(select_parts)
            connection.execute(text(f"CREATE TABLE {new_table} ({cols_sql})"))
            connection.execute(
                text(f"INSERT INTO {new_table} SELECT {select_sql} FROM usage")
            )

            connection.execute(text("DROP TABLE usage"))
            connection.execute(text(f"ALTER TABLE {new_table} RENAME TO usage"))

            # Recreate indexes on usage
            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS ix_usage_ts ON usage (ts)",
            ]:
                connection.execute(text(idx_sql))

            # Migrate sessions.last_usage_id if needed
            if has_sessions:
                connection.execute(text("UPDATE sessions SET last_usage_id = NULL"))
                sessions_cols = {
                    c["name"]: c for c in sa_inspect(engine).get_columns("sessions")
                }
                lui_type = str(sessions_cols["last_usage_id"]["type"])
                if "INT" in lui_type.upper() and "TEXT" not in lui_type.upper():
                    _sqlite_recreate_with_column_type_change(
                        connection,
                        "sessions",
                        "last_usage_id",
                        "TEXT",
                    )
        else:
            raise ValueError(
                f"Unsupported dialect for usage_id_to_uuid migration: {dialect}"
            )

    return True


def _sqlite_recreate_with_column_type_change(
    connection,
    table_name: str,
    column_name: str,
    new_type: str,
) -> None:
    """Recreate a SQLite table with one column's type changed."""
    result = connection.execute(text(f"PRAGMA table_info({table_name})"))
    columns = result.fetchall()

    new_col_defs = []
    select_parts = []
    for col in columns:
        col_name = col[1]
        col_type = col[2]
        not_null = col[3]
        default_val = col[4]

        if col_name == column_name:
            type_str = f"{new_type} NOT NULL" if not_null else new_type
            new_col_defs.append(f"{col_name} {type_str}")
            select_parts.append(f"CAST({col_name} AS {new_type})")
        else:
            default_clause = (
                f" DEFAULT {default_val}" if default_val is not None else ""
            )
            new_col_defs.append(
                f"{col_name} {col_type}{' NOT NULL' if not_null else ''}{default_clause}"
            )
            select_parts.append(col_name)

    pk_cols = [c[1] for c in columns if c[5]]
    if pk_cols:
        new_col_defs_clean = []
        for d in new_col_defs:
            col_name = d.split()[0]
            if col_name in pk_cols:
                new_col_defs_clean.append(d.replace(" PRIMARY KEY", ""))
            else:
                new_col_defs_clean.append(d)
        new_col_defs_clean.append(f"PRIMARY KEY ({', '.join(pk_cols)})")
        new_col_defs = new_col_defs_clean

    new_table = f"{table_name}_new"
    cols_sql = ", ".join(new_col_defs)
    select_sql = ", ".join(select_parts)

    connection.execute(text(f"CREATE TABLE {new_table} ({cols_sql})"))
    connection.execute(
        text(f"INSERT INTO {new_table} SELECT {select_sql} FROM {table_name}")
    )
    connection.execute(text(f"DROP TABLE {table_name}"))
    connection.execute(text(f"ALTER TABLE {new_table} RENAME TO {table_name}"))


def _migrate_ts_to_int(engine: Engine) -> bool:
    """Convert usage.ts, sessions.started, sessions.ended from REAL/FLOAT to INTEGER microseconds.

    Returns True if migration was applied, False if already migrated.
    """
    from sqlalchemy import inspect as sa_inspect

    usage_cols = {c["name"]: c for c in sa_inspect(engine).get_columns("usage")}
    col_type = str(usage_cols["ts"]["type"])
    if "INT" in col_type.upper():
        return False

    has_sessions = _table_exists(engine, "sessions")
    dialect = engine.dialect.name

    with engine.begin() as connection:
        if dialect == "postgresql":
            connection.execute(
                text(
                    "ALTER TABLE usage ALTER COLUMN ts TYPE BIGINT "
                    "USING ROUND(ts * 1000000)::BIGINT"
                )
            )
            if has_sessions:
                connection.execute(
                    text(
                        "ALTER TABLE sessions ALTER COLUMN started TYPE BIGINT "
                        "USING ROUND(started * 1000000)::BIGINT"
                    )
                )
                connection.execute(
                    text(
                        "ALTER TABLE sessions ALTER COLUMN ended TYPE BIGINT "
                        "USING ROUND(ended * 1000000)::BIGINT"
                    )
                )
        elif dialect == "sqlite":
            _sqlite_recreate_with_int_ts(connection, "usage", "ts")
            if has_sessions:
                _sqlite_recreate_with_int_ts(connection, "sessions", "started")
                _sqlite_recreate_with_int_ts(connection, "sessions", "ended")

            if has_sessions:
                for idx_sql in [
                    "CREATE INDEX IF NOT EXISTS ix_sessions_started_desc "
                    "ON sessions (started DESC)",
                    "CREATE INDEX IF NOT EXISTS ix_sessions_client_source_started_desc "
                    "ON sessions (client_source, started DESC)",
                ]:
                    connection.execute(text(idx_sql))
        else:
            raise ValueError(f"Unsupported dialect for ts_to_int migration: {dialect}")

        index_name = "ix_usage_ts"
        existing_indexes = {
            idx["name"] for idx in sa_inspect(engine).get_indexes("usage")
        }
        if index_name not in existing_indexes:
            connection.execute(text(f"CREATE INDEX {index_name} ON usage (ts)"))

    return True


def _sqlite_recreate_with_int_ts(connection, table_name: str, column_name: str) -> None:
    """Recreate a SQLite table with a REAL column converted to INTEGER microseconds."""
    result = connection.execute(text(f"PRAGMA table_info({table_name})"))
    columns = result.fetchall()

    new_col_defs = []
    select_parts = []
    for col in columns:
        col_name = col[1]
        col_type = col[2]
        not_null = col[3]
        default_val = col[4]

        if col_name == column_name:
            new_type = "INTEGER NOT NULL" if not_null else "INTEGER"
            new_col_defs.append(f"{col_name} {new_type}")
            select_parts.append(f"CAST(ROUND({col_name} * 1000000) AS INTEGER)")
        else:
            default_clause = (
                f" DEFAULT {default_val}" if default_val is not None else ""
            )
            new_col_defs.append(
                f"{col_name} {col_type}{' NOT NULL' if not_null else ''}{default_clause}"
            )
            select_parts.append(col_name)

    pk_cols = [c[1] for c in columns if c[5]]
    if pk_cols:
        new_col_defs_clean = []
        for d in new_col_defs:
            col_name = d.split()[0]
            if col_name in pk_cols:
                new_col_defs_clean.append(d.replace(" PRIMARY KEY", ""))
            else:
                new_col_defs_clean.append(d)
        new_col_defs_clean.append(f"PRIMARY KEY ({', '.join(pk_cols)})")
        new_col_defs = new_col_defs_clean

    new_table = f"{table_name}_new"
    cols_sql = ", ".join(new_col_defs)
    select_sql = ", ".join(select_parts)

    connection.execute(text(f"CREATE TABLE {new_table} ({cols_sql})"))
    connection.execute(
        text(f"INSERT INTO {new_table} SELECT {select_sql} FROM {table_name}")
    )
    connection.execute(text(f"DROP TABLE {table_name}"))
    connection.execute(text(f"ALTER TABLE {new_table} RENAME TO {table_name}"))


def migrate_database(db_path: str | None = None) -> list[str]:
    engine = get_engine(db_path)
    applied: list[str] = []

    if not _table_exists(engine, "evaluation_jobs"):
        if engine.dialect.name == "postgresql":
            create_sql = """
                CREATE TABLE evaluation_jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    client_source TEXT,
                    trigger TEXT NOT NULL DEFAULT 'manual',
                    evaluator_type TEXT NOT NULL DEFAULT 'codex',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    error TEXT
                )
            """
        else:
            create_sql = """
                CREATE TABLE evaluation_jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    client_source TEXT,
                    trigger TEXT NOT NULL DEFAULT 'manual',
                    evaluator_type TEXT NOT NULL DEFAULT 'codex',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    error TEXT
                )
            """
        with engine.begin() as connection:
            connection.execute(text(create_sql))
        applied.append("evaluation_jobs.create")

    init_db(db_path)

    if _table_exists(engine, "evaluation_jobs"):
        if _ensure_evaluation_jobs_active_unique_index(engine):
            applied.append("evaluation_jobs.active_unique_index")
        if _ensure_column(
            engine,
            "evaluation_jobs",
            "trigger",
            sqlite_definition="TEXT NOT NULL DEFAULT 'manual'",
            postgresql_definition="TEXT NOT NULL DEFAULT 'manual'",
        ):
            applied.append("evaluation_jobs.trigger")
        if _ensure_column(
            engine,
            "evaluation_jobs",
            "evaluator_type",
            sqlite_definition="TEXT NOT NULL DEFAULT 'codex'",
            postgresql_definition="TEXT NOT NULL DEFAULT 'codex'",
        ):
            applied.append("evaluation_jobs.evaluator_type")

    if _table_exists(engine, "usage"):
        if _ensure_column(
            engine,
            "usage",
            "prompt_length",
            sqlite_definition="INTEGER NOT NULL DEFAULT 0",
            postgresql_definition="INTEGER NOT NULL DEFAULT 0",
        ):
            applied.append("usage.prompt_length")
        if _ensure_column(
            engine,
            "usage",
            "base_url_id",
            sqlite_definition="INTEGER REFERENCES base_urls(id)",
            postgresql_definition="INTEGER REFERENCES base_urls(id)",
        ):
            applied.append("usage.base_url_id")
        if _ensure_column(
            engine,
            "usage",
            "input_cost_usd",
            sqlite_definition="NUMERIC(18, 8) NOT NULL DEFAULT 0",
            postgresql_definition="NUMERIC(18, 8) NOT NULL DEFAULT 0",
        ):
            applied.append("usage.input_cost_usd")
        if _ensure_column(
            engine,
            "usage",
            "output_cost_usd",
            sqlite_definition="NUMERIC(18, 8) NOT NULL DEFAULT 0",
            postgresql_definition="NUMERIC(18, 8) NOT NULL DEFAULT 0",
        ):
            applied.append("usage.output_cost_usd")
        if _ensure_column(
            engine,
            "usage",
            "total_cost_usd",
            sqlite_definition="NUMERIC(18, 8) NOT NULL DEFAULT 0",
            postgresql_definition="NUMERIC(18, 8) NOT NULL DEFAULT 0",
        ):
            applied.append("usage.total_cost_usd")
        if _ensure_column(
            engine,
            "usage",
            "client_source",
            sqlite_definition="TEXT",
            postgresql_definition="TEXT",
        ):
            applied.append("usage.client_source")
        if _ensure_column(
            engine,
            "usage",
            "session_id",
            sqlite_definition="TEXT",
            postgresql_definition="TEXT",
        ):
            applied.append("usage.session_id")
        if _ensure_column(
            engine,
            "usage",
            "client_ip",
            sqlite_definition="TEXT",
            postgresql_definition="TEXT",
        ):
            applied.append("usage.client_ip")
        if _ensure_column(
            engine,
            "usage",
            "cache_creation_tokens",
            sqlite_definition="INTEGER",
            postgresql_definition="INTEGER",
        ):
            applied.append("usage.cache_creation_tokens")
        if _ensure_index(
            engine,
            "usage",
            "ix_usage_client_ip",
            "CREATE INDEX IF NOT EXISTS ix_usage_client_ip ON usage (client_ip)",
        ):
            applied.append("usage.ix_client_ip")
        if _ensure_index(
            engine,
            "usage",
            "ix_usage_session_id",
            "CREATE INDEX IF NOT EXISTS ix_usage_session_id ON usage (session_id)",
        ):
            applied.append("usage.ix_session_id")

    if _table_exists(engine, "base_urls"):
        if _drop_column(engine, "base_urls", "validation_status"):
            applied.append("base_urls.validation_status")
        if _drop_column(engine, "base_urls", "last_error"):
            applied.append("base_urls.last_error")

    if not _table_exists(engine, "usage_daily"):
        if engine.dialect.name == "postgresql":
            create_sql = """
                CREATE TABLE usage_daily (
                    id SERIAL PRIMARY KEY,
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
                    status_429 INTEGER NOT NULL DEFAULT 0,
                    status_4xx INTEGER NOT NULL DEFAULT 0,
                    status_5xx INTEGER NOT NULL DEFAULT 0,
                    status_unknown INTEGER NOT NULL DEFAULT 0,
                    latency_sum_ms INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(date, provider, model, client_source)
                )
            """
        else:
            create_sql = """
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
                    status_429 INTEGER NOT NULL DEFAULT 0,
                    status_4xx INTEGER NOT NULL DEFAULT 0,
                    status_5xx INTEGER NOT NULL DEFAULT 0,
                    status_unknown INTEGER NOT NULL DEFAULT 0,
                    latency_sum_ms INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(date, provider, model, client_source)
                )
            """
        with engine.begin() as connection:
            connection.execute(text(create_sql))
        applied.append("usage_daily.create")

    status_cols_added = False
    if _table_exists(engine, "usage_daily"):
        for col in ["status_429", "status_4xx", "status_5xx", "status_unknown"]:
            if _ensure_column(
                engine,
                "usage_daily",
                col,
                sqlite_definition="INTEGER NOT NULL DEFAULT 0",
                postgresql_definition="INTEGER NOT NULL DEFAULT 0",
            ):
                applied.append(f"usage_daily.{col}")
                status_cols_added = True

        # Also check if backfill is needed even if columns were already there (from a previous session)
        if not status_cols_added:
            with engine.connect() as connection:
                # Check if we have any failures that haven't been categorized yet
                needs_backfill = connection.execute(
                    text(
                        "SELECT 1 FROM usage_daily WHERE failed_requests > 0 AND (status_429 + status_4xx + status_5xx + status_unknown) = 0 LIMIT 1"
                    )
                ).scalar()
                if needs_backfill:
                    status_cols_added = True

    if status_cols_added:
        # Backfill existing records in usage_daily from the raw usage table
        date_expr = _ts_date_expr(engine.dialect.name)
        u_date_expr = _ts_date_expr(engine.dialect.name, "u.ts")
        with engine.begin() as connection:
            if engine.dialect.name == "postgresql":
                connection.execute(
                    text(
                        f"""
                        UPDATE usage_daily
                        SET
                            status_429 = sub.s429,
                            status_4xx = sub.s4xx,
                            status_5xx = sub.s5xx,
                            status_unknown = 0
                        FROM (
                            SELECT
                                {date_expr} as date,
                                provider, model, COALESCE(client_source, '') as client_source,
                                SUM(CASE WHEN status = 429 THEN 1 ELSE 0 END) as s429,
                                SUM(CASE WHEN status >= 400 AND status < 500 AND status != 429 THEN 1 ELSE 0 END) as s4xx,
                                SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END) as s5xx
                            FROM usage
                            GROUP BY {date_expr}, provider, model, COALESCE(client_source, '')
                        ) AS sub
                        WHERE usage_daily.date = sub.date
                          AND usage_daily.provider = sub.provider
                          AND usage_daily.model = sub.model
                          AND usage_daily.client_source = sub.client_source
                    """
                    )
                )
            else:
                connection.execute(
                    text(
                        f"""
                        UPDATE usage_daily
                        SET
                            status_429 = (
                                SELECT SUM(CASE WHEN status = 429 THEN 1 ELSE 0 END)
                                FROM usage u
                                WHERE {u_date_expr} = usage_daily.date
                                  AND u.provider = usage_daily.provider
                                  AND u.model = usage_daily.model
                                  AND COALESCE(u.client_source, '') = usage_daily.client_source
                            ),
                            status_4xx = (
                                SELECT SUM(CASE WHEN status >= 400 AND status < 500 AND status != 429 THEN 1 ELSE 0 END)
                                FROM usage u
                                WHERE {u_date_expr} = usage_daily.date
                                  AND u.provider = usage_daily.provider
                                  AND u.model = usage_daily.model
                                  AND COALESCE(u.client_source, '') = usage_daily.client_source
                            ),
                            status_5xx = (
                                SELECT SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END)
                                FROM usage u
                                WHERE {u_date_expr} = usage_daily.date
                                  AND u.provider = usage_daily.provider
                                  AND u.model = usage_daily.model
                                  AND COALESCE(u.client_source, '') = usage_daily.client_source
                            ),
                            status_unknown = 0
                        WHERE EXISTS (
                            SELECT 1 FROM usage u
                            WHERE {u_date_expr} = usage_daily.date
                              AND u.provider = usage_daily.provider
                              AND u.model = usage_daily.model
                              AND COALESCE(u.client_source, '') = usage_daily.client_source
                        )
                    """
                    )
                )
        applied.append("usage_daily.status_backfill")

    if _table_exists(engine, "usage_daily") and _table_exists(engine, "usage"):
        with engine.connect() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM usage_daily")
            ).scalar()
        if count == 0:
            date_expr = _ts_date_expr(engine.dialect.name)
            with engine.begin() as connection:
                connection.execute(
                    text(f"""
                        INSERT INTO usage_daily (
                            date, provider, model, client_source,
                            request_count, prompt_tokens, completion_tokens,
                            reasoning_tokens, cached_tokens, total_tokens,
                            tool_tokens, cache_creation_tokens, prompt_length,
                            input_cost_usd, output_cost_usd, total_cost_usd,
                            successful_requests, failed_requests,
                            status_429, status_4xx, status_5xx, status_unknown,
                            latency_sum_ms
                        )
                        SELECT
                            {date_expr} as date,
                            provider, model, COALESCE(client_source, ''),
                            COUNT(*),
                            COALESCE(SUM(prompt_tokens), 0),
                            COALESCE(SUM(completion_tokens), 0),
                            COALESCE(SUM(reasoning_tokens), 0),
                            COALESCE(SUM(cached_tokens), 0),
                            COALESCE(SUM(total_tokens), 0),
                            COALESCE(SUM(tool_tokens), 0),
                            COALESCE(SUM(cache_creation_tokens), 0),
                            COALESCE(SUM(prompt_length), 0),
                            COALESCE(SUM(input_cost_usd), 0),
                            COALESCE(SUM(output_cost_usd), 0),
                            COALESCE(SUM(total_cost_usd), 0),
                            SUM(CASE WHEN status IS NULL OR status < 400 THEN 1 ELSE 0 END),
                            SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END),
                            SUM(CASE WHEN status = 429 THEN 1 ELSE 0 END),
                            SUM(CASE WHEN status >= 400 AND status < 500 AND status != 429 THEN 1 ELSE 0 END),
                            SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END),
                            0, -- status_unknown
                            COALESCE(SUM(latency_ms), 0)
                        FROM usage
                        GROUP BY {date_expr}, provider, model, COALESCE(client_source, '')
                    """)
                )
            applied.append("usage_daily.backfill")

    # Slice 2: Add evaluation columns to sessions table (consolidated from session_evaluations)
    if _table_exists(engine, "sessions"):
        for col, definition in [
            ("outcome", "TEXT"),
            ("source", "TEXT"),
            ("confidence", "NUMERIC(5, 4)"),
            ("task_title", "TEXT"),
            ("task_title_zh", "TEXT"),
            ("summary", "TEXT"),
            ("evidence_json", "TEXT"),
            ("failure_reason", "TEXT"),
            ("evaluated_at", "TEXT"),
            ("project", "TEXT"),
        ]:
            if _ensure_column(
                engine,
                "sessions",
                col,
                sqlite_definition=definition,
                postgresql_definition=definition,
            ):
                applied.append(f"sessions.{col}")

    sessions_cache_creation_added = False
    if _table_exists(engine, "sessions"):
        sessions_cache_creation_added = _ensure_column(
            engine,
            "sessions",
            "cache_creation_tokens",
            sqlite_definition="INTEGER NOT NULL DEFAULT 0",
            postgresql_definition="INTEGER NOT NULL DEFAULT 0",
        )
        if sessions_cache_creation_added:
            applied.append("sessions.cache_creation_tokens")

        # Also check if backfill is needed even if the column already existed
        # (e.g. a previous run added the column but crashed/restarted before
        # the backfill below completed).
        if not sessions_cache_creation_added and _table_exists(engine, "usage"):
            with engine.connect() as connection:
                needs_backfill = connection.execute(
                    text(
                        "SELECT 1 FROM sessions s WHERE s.cache_creation_tokens = 0 "
                        "AND EXISTS (SELECT 1 FROM usage u WHERE u.session_id = s.session_id "
                        "AND u.cache_creation_tokens > 0) LIMIT 1"
                    )
                ).scalar()
                if needs_backfill:
                    sessions_cache_creation_added = True

    # New column defaults existing rows to 0; backfill from usage so sessions
    # created before this migration report accurate cache-write totals. A
    # targeted UPDATE (not rebuild_sessions_from_usage, which deletes and
    # recreates rows and would drop evaluation columns it doesn't set).
    if sessions_cache_creation_added and _table_exists(engine, "usage"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE sessions
                    SET cache_creation_tokens = (
                        SELECT COALESCE(SUM(u.cache_creation_tokens), 0)
                        FROM usage u
                        WHERE u.session_id = sessions.session_id
                    )
                    WHERE EXISTS (
                        SELECT 1 FROM usage u WHERE u.session_id = sessions.session_id
                    )
                    """
                )
            )
        applied.append("sessions.cache_creation_tokens_backfill")

    if _table_exists(engine, "sessions"):
        if _ensure_index(
            engine,
            "sessions",
            "ix_sessions_started_desc",
            "CREATE INDEX IF NOT EXISTS ix_sessions_started_desc ON sessions (started DESC)",
        ):
            applied.append("sessions.ix_sessions_started_desc")
        if _ensure_index(
            engine,
            "sessions",
            "ix_sessions_client_source_started_desc",
            "CREATE INDEX IF NOT EXISTS ix_sessions_client_source_started_desc ON sessions (client_source, started DESC)",
        ):
            applied.append("sessions.ix_sessions_client_source_started_desc")

    # Slice 0: Backfill sessions table from usage when there are usage rows
    # with session_ids that don't have a corresponding session record yet.
    # The sessions table is created by init_db() via metadata.create_all().
    if _table_exists(engine, "sessions") and _table_exists(engine, "usage"):
        with engine.connect() as connection:
            unbackfilled = connection.execute(
                text(
                    "SELECT COUNT(*) FROM usage "
                    "WHERE session_id IS NOT NULL AND session_id != '' "
                    "AND session_id NOT IN (SELECT session_id FROM sessions)"
                )
            ).scalar()
        if unbackfilled and unbackfilled > 0:
            from .database import rebuild_sessions_from_usage

            rebuild_sessions_from_usage(db_path=db_path)
            applied.append("sessions.backfill")

    if _table_exists(engine, "usage"):
        if _migrate_ts_to_int(engine):
            applied.append("usage.ts_to_int")

    if _table_exists(engine, "usage"):
        if _migrate_usage_id_to_uuid(engine):
            applied.append("usage.id_to_uuid")

    # tool_calls table (postgresql and sqlite3 have same dialect here)
    if not _table_exists(engine, "tool_calls"):
        create_sql = """
            CREATE TABLE tool_calls (
                tool_use_id TEXT PRIMARY KEY,
                usage_id TEXT REFERENCES usage(id),
                session_id TEXT,
                tool_name TEXT NOT NULL,
                client_source TEXT,
                ts BIGINT NOT NULL
            )
        """
        with engine.begin() as connection:
            connection.execute(text(create_sql))
        applied.append("tool_calls.create")

    if _table_exists(engine, "tool_calls"):
        if _ensure_index(
            engine,
            "tool_calls",
            "ix_tool_calls_usage_id",
            "CREATE INDEX IF NOT EXISTS ix_tool_calls_usage_id ON tool_calls (usage_id)",
        ):
            applied.append("tool_calls.ix_usage_id")
        if _ensure_index(
            engine,
            "tool_calls",
            "ix_tool_calls_session_id",
            "CREATE INDEX IF NOT EXISTS ix_tool_calls_session_id ON tool_calls (session_id)",
        ):
            applied.append("tool_calls.ix_session_id")

    # tool_calls_json on sessions
    if _table_exists(engine, "sessions"):
        if _ensure_column(
            engine,
            "sessions",
            "tool_calls_json",
            sqlite_definition="TEXT DEFAULT '{}'",
            postgresql_definition="TEXT DEFAULT '{}'",
        ):
            applied.append("sessions.tool_calls_json")

    return applied
