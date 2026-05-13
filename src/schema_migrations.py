from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from .database import get_engine, init_db


def _table_exists(engine: Engine, table_name: str) -> bool:
    return table_name in inspect(engine).get_table_names()


def _table_column_names(engine: Engine, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


def _index_names(engine: Engine, table_name: str) -> set[str]:
    return {index["name"] for index in inspect(engine).get_indexes(table_name)}


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
        with engine.begin() as connection:
            if engine.dialect.name == "postgresql":
                connection.execute(
                    text(
                        """
                        UPDATE usage_daily
                        SET 
                            status_429 = sub.s429,
                            status_4xx = sub.s4xx,
                            status_5xx = sub.s5xx,
                            status_unknown = 0
                        FROM (
                            SELECT 
                                SUBSTRING(ts, 1, 10) as date,
                                provider, model, COALESCE(client_source, '') as client_source,
                                SUM(CASE WHEN status = 429 THEN 1 ELSE 0 END) as s429,
                                SUM(CASE WHEN status >= 400 AND status < 500 AND status != 429 THEN 1 ELSE 0 END) as s4xx,
                                SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END) as s5xx
                            FROM usage
                            GROUP BY SUBSTRING(ts, 1, 10), provider, model, COALESCE(client_source, '')
                        ) AS sub
                        WHERE usage_daily.date = sub.date 
                          AND usage_daily.provider = sub.provider 
                          AND usage_daily.model = sub.model 
                          AND usage_daily.client_source = sub.client_source
                    """
                    )
                )
            else:
                # SQLite-compatible update (supports UPDATE FROM in 3.33+, but we'll use a safer approach if possible)
                # Actually, most modern SQLite environments for this app will have 3.33+.
                # Let's use a standard correlated update for maximum compatibility if we're worried,
                # but UPDATE FROM is much cleaner.
                connection.execute(
                    text(
                        """
                        UPDATE usage_daily
                        SET 
                            status_429 = (
                                SELECT SUM(CASE WHEN status = 429 THEN 1 ELSE 0 END)
                                FROM usage u
                                WHERE substr(u.ts, 1, 10) = usage_daily.date
                                  AND u.provider = usage_daily.provider
                                  AND u.model = usage_daily.model
                                  AND COALESCE(u.client_source, '') = usage_daily.client_source
                            ),
                            status_4xx = (
                                SELECT SUM(CASE WHEN status >= 400 AND status < 500 AND status != 429 THEN 1 ELSE 0 END)
                                FROM usage u
                                WHERE substr(u.ts, 1, 10) = usage_daily.date
                                  AND u.provider = usage_daily.provider
                                  AND u.model = usage_daily.model
                                  AND COALESCE(u.client_source, '') = usage_daily.client_source
                            ),
                            status_5xx = (
                                SELECT SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END)
                                FROM usage u
                                WHERE substr(u.ts, 1, 10) = usage_daily.date
                                  AND u.provider = usage_daily.provider
                                  AND u.model = usage_daily.model
                                  AND COALESCE(u.client_source, '') = usage_daily.client_source
                            ),
                            status_unknown = 0
                        WHERE EXISTS (
                            SELECT 1 FROM usage u 
                            WHERE substr(u.ts, 1, 10) = usage_daily.date
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
            with engine.begin() as connection:
                connection.execute(
                    text("""
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
                            substr(ts, 1, 10) as date,
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
                        GROUP BY substr(ts, 1, 10), provider, model, COALESCE(client_source, '')
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
            ("summary", "TEXT"),
            ("evidence_json", "TEXT"),
            ("failure_reason", "TEXT"),
            ("evaluated_at", "TEXT"),
        ]:
            if _ensure_column(
                engine,
                "sessions",
                col,
                sqlite_definition=definition,
                postgresql_definition=definition,
            ):
                applied.append(f"sessions.{col}")

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

    return applied
