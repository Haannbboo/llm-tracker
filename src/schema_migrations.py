from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from .database import get_engine, init_db


def _table_exists(engine: Engine, table_name: str) -> bool:
    return table_name in inspect(engine).get_table_names()


def _table_column_names(engine: Engine, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


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
    init_db(db_path)
    engine = get_engine(db_path)
    applied: list[str] = []

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
                    latency_sum_ms INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(date, provider, model, client_source)
                )
            """
        with engine.begin() as connection:
            connection.execute(text(create_sql))
        applied.append("usage_daily.create")

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
                            successful_requests, failed_requests, latency_sum_ms
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
                            COALESCE(SUM(latency_ms), 0)
                        FROM usage
                        GROUP BY substr(ts, 1, 10), provider, model, COALESCE(client_source, '')
                    """)
                )
            applied.append("usage_daily.backfill")

    return applied
