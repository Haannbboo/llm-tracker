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

    if _table_exists(engine, "base_urls"):
        if _drop_column(engine, "base_urls", "validation_status"):
            applied.append("base_urls.validation_status")
        if _drop_column(engine, "base_urls", "last_error"):
            applied.append("base_urls.last_error")

    return applied
