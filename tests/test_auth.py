"""Tests for PR 1 auth foundation (docs/design/specs/pr1-auth-foundation.md)."""

from fastapi.testclient import TestClient
from sqlalchemy import text


def _mint(fresh_db, email="a@example.com", kind="cli", device_name=None):
    from src.database.auth import mint_token

    return mint_token(
        email, kind=kind, device_name=device_name, db_path=fresh_db.db_path
    )


def test_mint_and_resolve_roundtrip(fresh_db):
    from src.database.auth import resolve_token

    token, user = _mint(fresh_db, device_name="laptop")
    assert token.startswith("llmt_cli_")
    resolved = resolve_token(token, db_path=fresh_db.db_path)
    assert resolved is not None
    resolved_user, resolved_token = resolved
    assert resolved_user.id == user.id
    assert resolved_user.email == "a@example.com"
    assert resolved_token.kind == "cli"
    assert resolved_token.device_name == "laptop"


def test_mint_rejects_invalid_kind(fresh_db):
    import pytest

    with pytest.raises(ValueError):
        _mint(fresh_db, kind="nope")


def test_mint_twice_reuses_user(fresh_db):
    _mint(fresh_db)
    _mint(fresh_db)
    engine = fresh_db.database_module.get_engine(fresh_db.db_path)
    with engine.connect() as conn:
        users = conn.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
        tokens = conn.execute(text("SELECT COUNT(*) FROM auth_tokens")).scalar_one()
    assert users == 1
    assert tokens == 2


def test_plaintext_token_not_stored(fresh_db):
    token, _ = _mint(fresh_db)
    secret_part = token.rsplit("_", 1)[-1]
    engine = fresh_db.database_module.get_engine(fresh_db.db_path)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM auth_tokens")).mappings().all()
    dumped = str(rows)
    assert token not in dumped
    assert secret_part not in dumped


def test_resolve_unknown_token(fresh_db):
    from src.database.auth import resolve_token

    assert resolve_token("llmt_cli_deadbeef", db_path=fresh_db.db_path) is None


def test_resolve_revoked_token(fresh_db):
    from src.database.auth import resolve_token

    token, _ = _mint(fresh_db)
    engine = fresh_db.database_module.get_engine(fresh_db.db_path)
    with engine.begin() as conn:
        conn.execute(text("UPDATE auth_tokens SET revoked_at = 1"))
    assert resolve_token(token, db_path=fresh_db.db_path) is None


def test_resolve_updates_last_used_at(fresh_db):
    from src.database.auth import resolve_token

    token, _ = _mint(fresh_db)
    resolve_token(token, db_path=fresh_db.db_path)
    engine = fresh_db.database_module.get_engine(fresh_db.db_path)
    with engine.connect() as conn:
        last_used = conn.execute(
            text("SELECT last_used_at FROM auth_tokens")
        ).scalar_one()
    assert last_used is not None


def test_mint_normalizes_email(fresh_db):
    _mint(fresh_db, email="  A@Example.COM ")
    _mint(fresh_db, email="a@example.com")
    engine = fresh_db.database_module.get_engine(fresh_db.db_path)
    with engine.connect() as conn:
        emails = conn.execute(text("SELECT email FROM users")).scalars().all()
    assert emails == ["a@example.com"]


def test_mint_rejects_empty_email(fresh_db):
    import pytest

    with pytest.raises(ValueError):
        _mint(fresh_db, email="   ")


def test_migrate_old_schema_creates_auth_tables(
    database_module, schema_migrations_module, isolated_home
):
    """A pre-auth DB (bare usage table) gains users/auth_tokens on migrate."""
    import sqlite3

    from sqlalchemy import inspect

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
    connection.commit()
    connection.close()

    schema_migrations_module.migrate_database(str(db_file))

    tables = inspect(database_module.get_engine(str(db_file))).get_table_names()
    assert "users" in tables
    assert "auth_tokens" in tables


def test_auth_me_disabled(api_module):
    response = TestClient(api_module.app).get("/auth/me")
    assert response.status_code == 200
    assert response.json() == {"auth_enabled": False, "user": None}


def test_auth_me_enabled(api_module, fresh_db, monkeypatch):
    import config.app

    monkeypatch.setitem(config.app.CONFIG, "auth", {"enabled": True, "allowlist": []})
    token, _ = _mint(fresh_db, device_name="unraid-vm")
    client = TestClient(api_module.app)

    assert client.get("/auth/me").status_code == 401
    assert (
        client.get("/auth/me", headers={"Authorization": "garbage"}).status_code == 401
    )
    assert (
        client.get(
            "/auth/me", headers={"Authorization": "Bearer llmt_cli_wrong"}
        ).status_code
        == 401
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["auth_enabled"] is True
    assert body["user"]["email"] == "a@example.com"
    assert body["token"] == {"kind": "cli", "device_name": "unraid-vm"}

    engine = fresh_db.database_module.get_engine(fresh_db.db_path)
    with engine.begin() as conn:
        conn.execute(text("UPDATE auth_tokens SET revoked_at = 1"))
    revoked = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert revoked.status_code == 401
    assert revoked.json() == {"detail": "invalid token"}


def test_auth_me_db_error_is_500_not_none(api_module, monkeypatch):
    import config.app

    monkeypatch.setitem(config.app.CONFIG, "auth", {"enabled": True, "allowlist": []})

    def boom(token):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(api_module, "resolve_token", boom)
    client = TestClient(api_module.app, raise_server_exceptions=False)
    response = client.get("/auth/me", headers={"Authorization": "Bearer llmt_cli_x"})
    assert response.status_code == 500


def test_auth_me_enabled_no_users_is_401_not_500(api_module, fresh_db, monkeypatch):
    import config.app

    monkeypatch.setitem(config.app.CONFIG, "auth", {"enabled": True, "allowlist": []})
    response = TestClient(api_module.app).get(
        "/auth/me", headers={"Authorization": "Bearer llmt_cli_x"}
    )
    assert response.status_code == 401


def test_token_create_cli(cli_module, capsys):
    exit_code = cli_module.main(
        ["token", "create", "--email", "cli@example.com", "--name", "laptop"]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "llmt_cli_" in captured.out
    assert "cli@example.com" in captured.out
