"""Engine management for llm-tracker database connections."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from config.app import CONFIG
from .models import Base


DB_URL_ENV_VAR = "LLM_TRACKER_DB_URL"

_engine_cache: dict[str, Engine] = {}


def get_db_url(db_path: str | None = None) -> str:
    """Resolve an explicit DB target, env override, or configured default."""
    if db_path and "://" in db_path:
        return db_path
    if db_path:
        return f"sqlite:///{db_path}"

    env_url = os.environ.get(DB_URL_ENV_VAR)
    if env_url:
        return env_url

    return str(CONFIG["db"]["url"])


def _connect_args(db_url: str) -> dict[str, Any]:
    if db_url.startswith("sqlite:///"):
        return {"check_same_thread": False}
    return {}


def get_engine(db_path: str | None = None) -> Engine:
    """Return a cached engine for the requested database URL/path."""
    db_url = get_db_url(db_path)
    if db_url not in _engine_cache:
        if db_url.startswith("sqlite:///"):
            sqlite_path = db_url[10:]
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        _engine_cache[db_url] = create_engine(
            db_url,
            future=True,
            pool_pre_ping=True,
            connect_args=_connect_args(db_url),
        )
    return _engine_cache[db_url]


def init_db(db_path: str | None = None) -> None:
    """Create ORM-managed tables if they do not already exist."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
