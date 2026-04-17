import sqlite3
from pathlib import Path
from typing import Any
from .config import CONFIG

def connect_db(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection

def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect_db(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS usage (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                ts                TEXT NOT NULL,
                provider          TEXT NOT NULL,
                model             TEXT NOT NULL,
                endpoint          TEXT NOT NULL,
                prompt_tokens     INTEGER,
                completion_tokens INTEGER,
                reasoning_tokens  INTEGER,
                cached_tokens     INTEGER,
                total_tokens      INTEGER,
                latency_ms        INTEGER,
                status            INTEGER
            )
            """
        )

def log_usage(db_path: str, **fields: Any) -> None:
    with connect_db(db_path) as connection:
        connection.execute(
            """
            INSERT INTO usage (
                ts, provider, model, endpoint, prompt_tokens, completion_tokens,
                reasoning_tokens, cached_tokens, total_tokens, latency_ms, status
            ) VALUES (
                :ts, :provider, :model, :endpoint, :prompt_tokens, :completion_tokens,
                :reasoning_tokens, :cached_tokens, :total_tokens, :latency_ms, :status
            )
            """,
            fields,
        )

def fetch_usage_rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connect_db(CONFIG["db"]["path"]) as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]
