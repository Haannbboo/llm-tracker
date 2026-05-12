"""Database models and query helpers for llm-tracker.

The steady-state pattern in this module is:
- ORM models for entity lifecycle operations such as inserts and base URL resolution
- `select(...)`-style projection queries for usage reporting and aggregation
"""

from .models import (
    Base,
    BaseUrl,
    SessionRecord,
    Usage,
    UsageDaily,
    VALID_OUTCOMES,
    VALID_SOURCES,
    metadata,
)
from .engine import DB_URL_ENV_VAR, get_db_url, get_engine, init_db
from .base_url import get_or_create_base_url, resolve_base_url_id
from .sessions import (
    count_sessions,
    delete_session_evaluation,
    fetch_sessions,
    get_session_evaluation,
    rebuild_sessions_from_usage,
    summarize_sessions,
    upsert_session_evaluation,
    upsert_session_from_usage,
)
from .usage import (
    USAGE_COPY_FIELDS,
    aggregate_daily_by_dimension,
    aggregate_daily_by_period,
    aggregate_usage_by_period,
    count_usage,
    distinct_client_sources,
    fetch_recent_usage,
    get_usage_high_watermark,
    log_usage,
    merge_usage_database,
    summarize_usage_by_provider,
    summarize_usage_by_source,
    summarize_usage_daily,
    summarize_usage_window,
    upsert_daily_aggregate,
)

# Re-export sqlalchemy helpers used by tests and consumers via this module
from sqlalchemy import select, text
from sqlalchemy.orm import Session

__all__ = [
    "Base",
    "BaseUrl",
    "DB_URL_ENV_VAR",
    "Session",
    "SessionRecord",
    "USAGE_COPY_FIELDS",
    "Usage",
    "UsageDaily",
    "VALID_OUTCOMES",
    "VALID_SOURCES",
    "aggregate_daily_by_dimension",
    "aggregate_daily_by_period",
    "aggregate_usage_by_period",
    "count_sessions",
    "count_usage",
    "delete_session_evaluation",
    "distinct_client_sources",
    "fetch_recent_usage",
    "fetch_sessions",
    "get_db_url",
    "get_engine",
    "get_or_create_base_url",
    "get_session_evaluation",
    "get_usage_high_watermark",
    "init_db",
    "log_usage",
    "merge_usage_database",
    "metadata",
    "rebuild_sessions_from_usage",
    "resolve_base_url_id",
    "select",
    "summarize_sessions",
    "summarize_usage_by_provider",
    "summarize_usage_by_source",
    "summarize_usage_daily",
    "summarize_usage_window",
    "text",
    "upsert_daily_aggregate",
    "upsert_session_evaluation",
    "upsert_session_from_usage",
]
