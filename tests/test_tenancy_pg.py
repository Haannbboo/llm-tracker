"""Postgres tests for the PR 4 tenancy schema (docs/quick/postgres-testing.md).

Local-only: every test in this module skips unless LLM_TRACKER_TEST_PG_URL
points at a dedicated scratch database. CI stays SQLite-only.
"""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import inspect, text

TS_2026_04_17_10 = 1776420000000000

OLD_USAGE_DDL = """
CREATE TABLE usage (
    id TEXT PRIMARY KEY,
    ts BIGINT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    client_source TEXT,
    session_id TEXT,
    endpoint TEXT NOT NULL,
    prompt_tokens INTEGER,
    prompt_length INTEGER NOT NULL DEFAULT 0,
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
    status INTEGER,
    client_ip TEXT
)
"""

OLD_USAGE_DAILY_DDL = """
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

OLD_SESSIONS_DDL = """
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    client_source TEXT,
    started BIGINT NOT NULL,
    ended BIGINT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    successful_requests INTEGER NOT NULL DEFAULT 0,
    failed_requests INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    total_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
    latency_sum_ms INTEGER NOT NULL DEFAULT 0,
    avg_latency_ms NUMERIC(18, 4),
    avg_ttft_ms NUMERIC(18, 4),
    primary_provider TEXT,
    primary_model TEXT,
    providers_json TEXT,
    models_json TEXT,
    tool_calls_json TEXT DEFAULT '{}',
    last_usage_id TEXT,
    updated_at TEXT NOT NULL
)
"""

OLD_EVALUATION_JOBS_DDL = """
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


def _table_column_names(engine, table_name: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table_name)}


def _usage_daily_unique_constraints(engine) -> list[str]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT constraint_name FROM information_schema.table_constraints "
                    "WHERE table_name = 'usage_daily' AND constraint_type = 'UNIQUE'"
                )
            ).scalars()
        )


def _daily_row(engine):
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT user_id, request_count, prompt_tokens FROM usage_daily "
                "ORDER BY id"
            )
        ).all()


def _make_usage(*, user_id: str | None = None, **overrides):
    from src.database.models import Usage

    fields = dict(
        ts=TS_2026_04_17_10,
        provider="anthropic",
        model="claude-sonnet-4-6",
        user_id=user_id,
        client_source="claude-code",
        session_id="sess-1",
        endpoint="/v1/messages",
        prompt_tokens=100,
        prompt_length=500,
        completion_tokens=50,
        reasoning_tokens=0,
        cached_tokens=0,
        total_tokens=150,
        latency_ms=200,
        ttft_ms=50,
        input_cost_usd=0.001,
        output_cost_usd=0.002,
        total_cost_usd=0.003,
        status=200,
    )
    fields.update(overrides)
    return Usage(**fields)


def test_fresh_migrate_creates_tenancy_shapes(pg_db, pg_engine):
    from src.schema_migrations import migrate_database

    migrate_database(pg_db)

    for table in ("usage", "usage_daily", "sessions", "tool_calls", "evaluation_jobs"):
        assert "user_id" in _table_column_names(pg_engine, table)

    daily_indexes = {
        index["name"]: index for index in inspect(pg_engine).get_indexes("usage_daily")
    }
    assert daily_indexes["uq_usage_daily_local"]["unique"]
    assert daily_indexes["uq_usage_daily_user"]["unique"]

    for table, index_name in [
        ("usage", "ix_usage_user_id"),
        ("sessions", "ix_sessions_user_id"),
        ("tool_calls", "ix_tool_calls_user_id"),
    ]:
        assert index_name in {
            index["name"] for index in inspect(pg_engine).get_indexes(table)
        }

    assert "ix_evaluation_jobs_one_active_per_session" in {
        index["name"] for index in inspect(pg_engine).get_indexes("evaluation_jobs")
    }


def test_old_shape_migration_swaps_unique_and_preserves_data(pg_clean):
    from src.schema_migrations import migrate_database

    with pg_clean.begin() as connection:
        for ddl in (
            OLD_USAGE_DDL,
            OLD_USAGE_DAILY_DDL,
            OLD_SESSIONS_DDL,
            OLD_EVALUATION_JOBS_DDL,
        ):
            connection.execute(text(ddl))
        connection.execute(
            text(
                "INSERT INTO usage (id, ts, provider, model, client_source, session_id, "
                "endpoint, prompt_tokens, completion_tokens, total_tokens, latency_ms, "
                "status, input_cost_usd, output_cost_usd, total_cost_usd) VALUES "
                "('uuid-1', 1776420000000000, 'anthropic', 'm1', 'claude-code', "
                "'sess-1', '/v1/messages', 10, 5, 15, 100, 200, 0.001, 0.002, 0.003)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO usage_daily (date, provider, model, client_source, "
                "request_count, prompt_tokens) VALUES "
                "('2026-04-17', 'anthropic', 'm1', 'claude-code', 42, 4242)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO sessions (session_id, started, ended, request_count, "
                "updated_at) VALUES "
                "('sess-1', 1776420000000000, 1776420000000000, 42, "
                "'2026-04-17T00:00:00+00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO evaluation_jobs (job_id, kind, session_id, status, "
                "created_at) VALUES "
                "('job-1', 'session_evaluation', 'sess-1', 'queued', "
                "'2026-04-17T00:00:00+00:00')"
            )
        )

    url = pg_clean.url.render_as_string(hide_password=False)
    changes = migrate_database(url)

    assert "usage.user_id" in changes
    assert "usage_daily.user_id" in changes
    assert "sessions.user_id" in changes
    assert "evaluation_jobs.user_id" in changes
    assert "usage_daily.unique_swap" in changes

    # Data preserved
    with pg_clean.connect() as connection:
        usage_rows = connection.execute(
            text("SELECT id, user_id, prompt_tokens FROM usage")
        ).all()
        assert usage_rows == [("uuid-1", None, 10)]
        sessions_rows = connection.execute(
            text("SELECT session_id, request_count, user_id FROM sessions")
        ).all()
        assert sessions_rows == [("sess-1", 42, None)]
        jobs_rows = connection.execute(
            text("SELECT job_id, user_id FROM evaluation_jobs")
        ).all()
        assert jobs_rows == [("job-1", None)]
    assert _daily_row(pg_clean) == [(None, 42, 4242)]

    # Old UNIQUE dropped, partial indexes in place, sessions PK unchanged
    assert _usage_daily_unique_constraints(pg_clean) == []
    daily_indexes = {
        index["name"]: index for index in inspect(pg_clean).get_indexes("usage_daily")
    }
    assert daily_indexes["uq_usage_daily_local"]["unique"]
    assert daily_indexes["uq_usage_daily_user"]["unique"]
    assert inspect(pg_clean).get_pk_constraint("sessions") == {
        "constrained_columns": ["session_id"],
        "name": "sessions_pkey",
    }

    # Second run is a no-op for the tenancy steps
    tenancy_changes = {
        change
        for change in migrate_database(url)
        if "user_id" in change or change == "usage_daily.unique_swap"
    }
    assert tenancy_changes == set()


def test_old_shape_migration_merges_duplicate_rows(pg_clean):
    """Create-all-era Postgres tables never had the old UNIQUE; duplicate
    rows must be merged (summed) before the partial indexes are created."""
    from src.schema_migrations import migrate_database

    daily_ddl = OLD_USAGE_DAILY_DDL.replace(
        ",\n    UNIQUE(date, provider, model, client_source)", ""
    )

    with pg_clean.begin() as connection:
        connection.execute(text(daily_ddl))
        connection.execute(
            text(
                "INSERT INTO usage_daily (date, provider, model, client_source, "
                "request_count, prompt_tokens, total_cost_usd, latency_sum_ms) "
                "VALUES ('2026-04-17', 'anthropic', 'm1', 'claude-code', 1, 10, "
                "0.003, 100)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO usage_daily (date, provider, model, client_source, "
                "request_count, prompt_tokens, total_cost_usd, latency_sum_ms) "
                "VALUES ('2026-04-17', 'anthropic', 'm1', 'claude-code', 2, 20, "
                "0.006, 200)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO usage_daily (date, provider, model, client_source, "
                "request_count, prompt_tokens) "
                "VALUES ('2026-04-18', 'anthropic', 'm1', 'claude-code', 7, 70)"
            )
        )

    url = pg_clean.url.render_as_string(hide_password=False)
    changes = migrate_database(url)
    assert "usage_daily.unique_swap" in changes

    with pg_clean.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT date, request_count, prompt_tokens, latency_sum_ms, user_id "
                "FROM usage_daily ORDER BY date"
            )
        ).all()
    assert rows == [
        ("2026-04-17", 3, 30, 300, None),
        ("2026-04-18", 7, 70, 0, None),
    ]

    assert _usage_daily_unique_constraints(pg_clean) == []
    daily_indexes = {
        index["name"]: index for index in inspect(pg_clean).get_indexes("usage_daily")
    }
    assert daily_indexes["uq_usage_daily_local"]["unique"]
    assert daily_indexes["uq_usage_daily_user"]["unique"]

    tenancy_changes = {
        change
        for change in migrate_database(url)
        if "user_id" in change or change == "usage_daily.unique_swap"
    }
    assert tenancy_changes == set()


def test_upsert_daily_aggregate_on_conflict_sums(pg_db):
    from src.database.usage import upsert_daily_aggregate

    upsert_daily_aggregate(_make_usage(), db_path=pg_db)
    upsert_daily_aggregate(
        _make_usage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
        db_path=pg_db,
    )

    rows = _daily_row(pg_db)
    assert len(rows) == 1
    assert rows[0].user_id is None
    assert rows[0].request_count == 2
    assert rows[0].prompt_tokens == 120

    upsert_daily_aggregate(_make_usage(user_id="u1", prompt_tokens=7), db_path=pg_db)
    upsert_daily_aggregate(
        _make_usage(user_id="u1", prompt_tokens=1, status=429), db_path=pg_db
    )

    rows = _daily_row(pg_db)
    assert len(rows) == 2
    by_user = {row.user_id: row for row in rows}
    assert by_user[None].request_count == 2
    assert by_user[None].prompt_tokens == 120
    assert by_user["u1"].request_count == 2
    assert by_user["u1"].prompt_tokens == 8


def test_upsert_daily_aggregate_concurrent_writes_sum(pg_db):
    from src.database.usage import upsert_daily_aggregate

    thread_count = 8

    def worker():
        upsert_daily_aggregate(
            _make_usage(prompt_tokens=1, completion_tokens=0, total_tokens=1),
            db_path=pg_db,
        )

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    rows = _daily_row(pg_db)
    assert len(rows) == 1
    assert rows[0].request_count == thread_count
    assert rows[0].prompt_tokens == thread_count


def test_session_upsert_isolates_tenants_and_fails_cleanly_on_collision(pg_db):
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session as OrmSession

    from src.database.engine import get_engine
    from src.database.sessions import get_session_record, upsert_session_from_usage

    upsert_session_from_usage(_make_usage(user_id="u1"), db_path=pg_db)
    upsert_session_from_usage(
        _make_usage(session_id="sess-2", user_id="u2"), db_path=pg_db
    )

    engine = get_engine(pg_db)
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT session_id, user_id FROM sessions ORDER BY session_id")
        ).all()
    assert rows == [("sess-1", "u1"), ("sess-2", "u2")]

    with OrmSession(engine) as session:
        record_u1 = get_session_record(session, "sess-1", user_id="u1")
        assert record_u1 is not None
        assert record_u1.user_id == "u1"
        assert get_session_record(session, "sess-2", user_id="u2").user_id == "u2"
        assert get_session_record(session, "sess-1", user_id=None) is None
        assert get_session_record(session, "sess-1", user_id="u3") is None

    # Tenant-poison guard: a second user writing the same session_id fails
    # cleanly (bare session_id PK) instead of polluting the first user's row.
    with pytest.raises(IntegrityError):
        upsert_session_from_usage(_make_usage(user_id="u2"), db_path=pg_db)
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT user_id FROM sessions WHERE session_id = 'sess-1'")
        ).one()
    assert row.user_id == "u1"
