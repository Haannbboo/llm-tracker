"""Device status reporting: POST/GET /devices/status storage and scoping."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

INSTALLATION_KEY = "k" * 43
ENDPOINT = "http://localhost:4005/v1/logs"

CLAUDE = {
    "configured": True,
    "endpoint_matches": True,
    "configured_endpoint": ENDPOINT,
    "expected_endpoint": ENDPOINT,
    "status": "ready",
}
CODEX = {
    "configured": False,
    "endpoint_matches": False,
    "configured_endpoint": None,
    "expected_endpoint": ENDPOINT,
    "status": "missing_config",
}


def _report(**overrides) -> dict:
    report = {
        "device_name": "laptop",
        "client_version": "0.1.200",
        "client_commit": "a" * 40,
        "collected_at": 1770000000,
        "agents": {"claude": dict(CLAUDE), "codex": dict(CODEX)},
        "detected": {"claude": {"found": True}},
    }
    report.update(overrides)
    return report


def _enable_auth(monkeypatch) -> None:
    import src.config.app

    monkeypatch.setitem(
        src.config.app.CONFIG, "auth", {"enabled": True, "allowlist": []}
    )


def test_post_requires_a_valid_installation_key_when_auth_disabled(
    api_module, fresh_db
):
    client = TestClient(api_module.app)

    assert client.post("/devices/status", json=_report()).status_code == 422
    assert (
        client.post(
            "/devices/status", json=_report(installation_key="too-short")
        ).status_code
        == 422
    )


def test_post_persists_and_get_returns_the_report(api_module, fresh_db):
    from src.auth.tokens import hash_token
    from src.database import list_device_statuses

    client = TestClient(api_module.app)
    response = client.post(
        "/devices/status", json=_report(installation_key=INSTALLATION_KEY)
    )
    assert response.status_code == 204

    devices = client.get("/devices/status").json()["devices"]
    assert len(devices) == 1
    device = devices[0]
    assert device["device_id"] is None
    assert device["device_name"] == "laptop"
    assert device["client_version"] == "0.1.200"
    assert device["client_commit"] == "a" * 40
    assert isinstance(device["reported_at"], int) and device["reported_at"] > 0
    assert device["status"]["agents"]["claude"]["expected_endpoint"] == ENDPOINT
    assert device["status"]["agents"]["claude"]["status"] == "ready"
    assert "installation_key" not in json.dumps(device)

    rows = list_device_statuses(db_path=fresh_db.db_path)
    assert len(rows) == 1
    assert rows[0].installation_hash == hash_token(INSTALLATION_KEY)


def test_post_ignores_a_client_supplied_installation_key_when_auth_enabled(
    api_module, fresh_db, monkeypatch
):
    from src.auth.tokens import hash_token, mint_device_tokens, mint_token
    from src.database import list_device_statuses

    _enable_auth(monkeypatch)
    _, user = mint_token("a@example.com", kind="web", db_path=fresh_db.db_path)
    cli_token, _, device = mint_device_tokens(
        user.id, "d" * 43, "laptop", db_path=fresh_db.db_path
    )

    client = TestClient(api_module.app)
    client.headers["Authorization"] = f"Bearer {cli_token}"
    response = client.post(
        "/devices/status",
        json=_report(installation_key=INSTALLATION_KEY, device_name="ignored"),
    )
    assert response.status_code == 204

    rows = list_device_statuses(db_path=fresh_db.db_path)
    assert [row.installation_hash for row in rows] == [device.installation_hash]
    assert hash_token(INSTALLATION_KEY) != device.installation_hash


def test_post_rejects_tokens_without_a_device_when_auth_enabled(
    api_module, fresh_db, monkeypatch
):
    from src.auth.tokens import mint_token

    _enable_auth(monkeypatch)
    token, _ = mint_token("a@example.com", kind="cli", db_path=fresh_db.db_path)

    client = TestClient(api_module.app)
    client.headers["Authorization"] = f"Bearer {token}"
    assert (
        client.post(
            "/devices/status", json=_report(installation_key=INSTALLATION_KEY)
        ).status_code
        == 400
    )


def test_get_is_user_scoped_when_auth_enabled(api_module, fresh_db, monkeypatch):
    from src.auth.tokens import mint_device_tokens, mint_token

    _enable_auth(monkeypatch)
    _, user_a = mint_token("a@example.com", kind="web", db_path=fresh_db.db_path)
    _, user_b = mint_token("b@example.com", kind="web", db_path=fresh_db.db_path)
    cli_a, _, device_a = mint_device_tokens(
        user_a.id, "a" * 43, "laptop-a", db_path=fresh_db.db_path
    )
    cli_b, _, device_b = mint_device_tokens(
        user_b.id, "b" * 43, "laptop-b", db_path=fresh_db.db_path
    )

    client_a = TestClient(api_module.app)
    client_a.headers["Authorization"] = f"Bearer {cli_a}"
    client_b = TestClient(api_module.app)
    client_b.headers["Authorization"] = f"Bearer {cli_b}"

    assert (
        client_a.post(
            "/devices/status", json=_report(device_name="laptop-a")
        ).status_code
        == 204
    )
    assert (
        client_b.post(
            "/devices/status", json=_report(device_name="laptop-b")
        ).status_code
        == 204
    )

    devices_a = client_a.get("/devices/status").json()["devices"]
    assert [(device["device_id"], device["device_name"]) for device in devices_a] == [
        (device_a.id, "laptop-a")
    ]
    devices_b = client_b.get("/devices/status").json()["devices"]
    assert [(device["device_id"], device["device_name"]) for device in devices_b] == [
        (device_b.id, "laptop-b")
    ]


def test_get_returns_401_without_a_token_when_auth_enabled(
    api_module, fresh_db, monkeypatch
):
    _enable_auth(monkeypatch)
    client = TestClient(api_module.app)
    assert client.get("/devices/status").status_code == 401
    assert (
        client.post(
            "/devices/status", json=_report(installation_key=INSTALLATION_KEY)
        ).status_code
        == 401
    )


def test_post_accepts_agents_the_server_does_not_know(api_module, fresh_db):
    # Clients release independently; a new agent must not be rejected.
    client = TestClient(api_module.app)
    report = _report(installation_key=INSTALLATION_KEY)
    report["agents"]["gemini"] = dict(CLAUDE, status="some_new_status")
    report["detected"]["gemini"] = {"found": True}
    assert client.post("/devices/status", json=report).status_code == 204


def test_post_rejects_overlong_strings_and_oversized_maps(api_module, fresh_db):
    client = TestClient(api_module.app)

    overlong = _report(installation_key=INSTALLATION_KEY)
    overlong["agents"]["claude"]["configured_endpoint"] = "x" * 513
    assert client.post("/devices/status", json=overlong).status_code == 422

    long_name = _report(installation_key=INSTALLATION_KEY)
    long_name["agents"]["x" * 33] = dict(CLAUDE)
    assert client.post("/devices/status", json=long_name).status_code == 422

    too_many = _report(installation_key=INSTALLATION_KEY)
    too_many["detected"] = {f"agent{i}": {"found": True} for i in range(33)}
    assert client.post("/devices/status", json=too_many).status_code == 422


def test_get_returns_null_status_for_corrupt_stored_json(api_module, fresh_db):
    from src.auth.tokens import hash_token
    from src.database import upsert_device_status

    upsert_device_status(
        hash_token(INSTALLATION_KEY),
        "not-json",
        db_path=fresh_db.db_path,
    )

    devices = TestClient(api_module.app).get("/devices/status").json()["devices"]
    assert len(devices) == 1
    assert devices[0]["status"] is None


def test_devices_routes_are_classified_for_the_auth_gate(api_module):
    assert "/devices" in api_module._SPA_API_PREFIXES
    api_module._assert_api_routes_classified()
