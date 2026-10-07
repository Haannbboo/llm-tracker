"""Tests for PR 1 auth foundation (docs/design/specs/pr1-auth-foundation.md)."""

from fastapi.testclient import TestClient
from sqlalchemy import text


def _mint(fresh_db, email="a@example.com", kind="cli", device_name=None):
    from src.auth.tokens import mint_token

    return mint_token(
        email, kind=kind, device_name=device_name, db_path=fresh_db.db_path
    )


def test_mint_and_resolve_roundtrip(fresh_db):
    from src.auth.tokens import resolve_token

    token, user = _mint(fresh_db, device_name="laptop")
    assert token.startswith("tokenage_cli_")
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
    from src.auth.tokens import resolve_token

    assert resolve_token("tokenage_cli_deadbeef", db_path=fresh_db.db_path) is None


def test_resolve_revoked_token(fresh_db):
    from src.auth.tokens import resolve_token

    token, _ = _mint(fresh_db)
    engine = fresh_db.database_module.get_engine(fresh_db.db_path)
    with engine.begin() as conn:
        conn.execute(text("UPDATE auth_tokens SET revoked_at = 1"))
    assert resolve_token(token, db_path=fresh_db.db_path) is None


def test_resolve_updates_last_used_at(fresh_db):
    from src.auth.tokens import resolve_token

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


def test_migrate_existing_auth_tokens_adds_device_link(
    database_module, schema_migrations_module, isolated_home
):
    import sqlite3

    from sqlalchemy import inspect

    db_file = isolated_home / "usage.db"
    with sqlite3.connect(db_file) as connection:
        connection.execute(
            "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, "
            "name TEXT, created_at BIGINT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE auth_tokens (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, "
            "kind TEXT NOT NULL, device_name TEXT, token_hash TEXT NOT NULL UNIQUE, "
            "created_at BIGINT NOT NULL, last_used_at BIGINT, revoked_at BIGINT)"
        )
        connection.execute(
            "INSERT INTO users (id, email, created_at) VALUES ('u1', 'a@example.com', 1)"
        )
        connection.execute(
            "INSERT INTO auth_tokens (id, user_id, kind, token_hash, created_at) "
            "VALUES ('t1', 'u1', 'cli', 'hash', 1)"
        )

    applied = schema_migrations_module.migrate_database(str(db_file))
    engine = database_module.get_engine(str(db_file))
    inspector = inspect(engine)
    assert "devices" in inspector.get_table_names()
    assert "device_id" in {
        column["name"] for column in inspector.get_columns("auth_tokens")
    }
    assert "auth_tokens.device_id" in applied
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT device_id FROM auth_tokens WHERE id = 't1'")
            ).scalar_one()
            is None
        )
    assert "auth_tokens.device_id" not in schema_migrations_module.migrate_database(
        str(db_file)
    )


def test_auth_me_local_loopback_is_the_owner(api_module):
    body = TestClient(api_module.app).get("/auth/me").json()
    assert body["provider"] == "local"
    assert body["user"]["email"] == "owner@localhost"
    assert body["token"] is None


def test_auth_me_local_remote_has_no_user(api_module):
    remote = TestClient(
        api_module.app, client=("203.0.113.9", 5), base_url="http://tracker.example"
    )
    assert remote.get("/auth/me").json() == {"provider": "local", "user": None}


def test_auth_me_google(api_module, fresh_db, monkeypatch):
    import src.config.app

    monkeypatch.setitem(
        src.config.app.CONFIG, "auth", {"provider": "google", "allowlist": []}
    )
    token, _ = _mint(fresh_db, device_name="unraid-vm")
    client = TestClient(api_module.app)

    # Unresolved is a 200 with no user, never the loopback owner under google.
    signed_out = {"provider": "google", "user": None}
    assert client.get("/auth/me").json() == signed_out
    assert (
        client.get("/auth/me", headers={"Authorization": "garbage"}).json()
        == signed_out
    )
    assert (
        client.get(
            "/auth/me", headers={"Authorization": "Bearer tokenage_cli_wrong"}
        ).json()
        == signed_out
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "google"
    assert body["user"]["email"] == "a@example.com"
    assert body["token"] == {"kind": "cli", "device_name": "unraid-vm"}

    engine = fresh_db.database_module.get_engine(fresh_db.db_path)
    with engine.begin() as conn:
        conn.execute(text("UPDATE auth_tokens SET revoked_at = 1"))
    revoked = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert revoked.json() == signed_out
    assert client.get("/usage/count").status_code == 401


def test_ingest_token_cannot_authenticate_api(api_module, fresh_db, monkeypatch):
    import src.config.app

    monkeypatch.setitem(
        src.config.app.CONFIG, "auth", {"provider": "google", "allowlist": []}
    )
    token, _ = _mint(fresh_db, kind="ingest")

    response = TestClient(api_module.app).get(
        "/usage/count", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


def test_auth_me_db_error_is_500_not_none(api_module, monkeypatch):
    import src.auth.routes as auth_routes
    import src.config.app

    monkeypatch.setitem(
        src.config.app.CONFIG, "auth", {"provider": "google", "allowlist": []}
    )

    def boom(token):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(auth_routes, "resolve_token", boom)
    client = TestClient(api_module.app, raise_server_exceptions=False)
    response = client.get(
        "/auth/me", headers={"Authorization": "Bearer tokenage_cli_x"}
    )
    assert response.status_code == 500


def test_unknown_token_with_no_users_is_401_not_500(api_module, fresh_db, monkeypatch):
    import src.config.app

    monkeypatch.setitem(
        src.config.app.CONFIG, "auth", {"provider": "google", "allowlist": []}
    )
    response = TestClient(api_module.app).get(
        "/usage/count", headers={"Authorization": "Bearer tokenage_cli_x"}
    )
    assert response.status_code == 401


def test_get_or_create_user_retries_on_integrity_error(monkeypatch):
    """The loser of a concurrent first-login race re-selects the winner's row."""
    from sqlalchemy.exc import IntegrityError

    from src.auth import tokens

    class FakeUser:
        id = 1
        email = "a@example.com"

    calls = {"selects": 0, "commits": 0}

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def execute(self, *args, **kwargs):
            calls["selects"] += 1
            user = FakeUser() if calls["selects"] > 1 else None

            class Result:
                @staticmethod
                def scalar_one_or_none():
                    return user

            return Result()

        def add(self, *args):
            pass

        def commit(self):
            calls["commits"] += 1
            if calls["commits"] == 1:
                raise IntegrityError("stmt", {}, Exception("unique violation"))

        def rollback(self):
            pass

    monkeypatch.setattr(tokens, "Session", FakeSession)
    monkeypatch.setattr(tokens, "get_engine", lambda db_path: object())

    user = tokens.get_or_create_user("A@EXAMPLE.COM")
    assert user.email == "a@example.com"
    assert calls == {"selects": 2, "commits": 1}


def test_token_create_cli(cli_module, capsys):
    exit_code = cli_module.main(
        ["token", "create", "--email", "cli@example.com", "--name", "laptop"]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "tokenage_cli_" in captured.out
    assert "cli@example.com" in captured.out


def test_token_create_cli_rejects_blank_email(cli_module, capsys):
    exit_code = cli_module.main(["token", "create", "--email", "   "])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "email" in captured.err.lower()
