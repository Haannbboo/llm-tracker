"""Sign-in, credentials, and sign-out for this machine.

Credentials live in ``$LLM_TRACKER_HOME/credentials.json`` with mode 0600. The
device keeps its own CLI and ingestion tokens; re-logging in to the same server
presents the previous tokens so the server can hold the device identity steady
across rotation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from client.paths import (
    client_commit,
    client_version,
    credentials_path,
    installation_path,
    read_object,
)
from protocol import CURRENT_GENERATION


def load_credentials() -> dict[str, Any] | None:
    return read_object(credentials_path())


def _save_private_object(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def save_credentials(data: dict[str, Any]) -> None:
    _save_private_object(credentials_path(), data)


def clear_credentials() -> bool:
    """Remove this machine's credentials. False when there were none."""
    path = credentials_path()
    if not path.exists():
        return False
    path.unlink()
    return True


def installation_key(server: str) -> str:
    """Derive a stable, server-specific installation proof."""
    path = installation_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"installation_key": secrets.token_urlsafe(32)}, handle)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
    data = read_object(path)
    key = data.get("installation_key") if data else None
    if not isinstance(key, str) or len(key) < 43:
        raise ValueError(f"invalid installation key in {path}")
    path.chmod(0o600)
    # The master never leaves this machine. Different hosted servers receive
    # unrelated proofs even if the same client logs in to both.
    return hmac.new(
        key.encode("utf-8"), server.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def normalize_server_url(raw: str) -> str:
    """Reduce a user-supplied server URL to a bare origin, rejecting anything else."""
    try:
        parsed = urlparse(raw)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid server URL") from exc
    if (
        not host
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.scheme not in ("https", "http")
        or (parsed.scheme == "http" and host not in {"localhost", "127.0.0.1"})
    ):
        raise ValueError(
            "server URL must be an HTTPS origin (HTTP is allowed for localhost)"
        )
    authority = f"[{host}]" if ":" in host else host
    default_port = 443 if parsed.scheme == "https" else 80
    if port is not None and port != default_port:
        authority += f":{port}"
    return f"{parsed.scheme}://{authority}"


def valid_logs_endpoint(raw: str) -> bool:
    try:
        parsed = urlparse(raw)
        _ = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.hostname
        and not parsed.username
        and not parsed.password
        and (
            parsed.scheme == "https"
            or (
                parsed.scheme == "http"
                and parsed.hostname in {"localhost", "127.0.0.1"}
            )
        )
        and parsed.path.endswith("/v1/logs")
        and not parsed.query
        and not parsed.fragment
    )


def _device_name(raw: str | None) -> str:
    cleaned = "".join(char for char in (raw or "").strip() if char.isprintable())
    return cleaned[:64] or "cli-device"


def check_server(server: str) -> int:
    """Verify reachability and wire protocol before login or activation."""
    try:
        response = httpx.get(f"{server}/version", timeout=5)
        response.raise_for_status()
        data = response.json()
        minimum = int(data["protocol_min"])
        maximum = int(data["protocol_max"])
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        print(
            f"llm-tracker server unavailable or incompatible at {server}: {exc}",
            file=sys.stderr,
        )
        return 1
    if not minimum <= CURRENT_GENERATION <= maximum:
        print(
            "This llm-tracker version is incompatible with the dashboard. "
            "Ask its administrator to update it.",
            file=sys.stderr,
        )
        return 1
    return 0


def resolve_server(explicit: str | None) -> str | None:
    """--server, then the environment, then whatever we logged in to before."""
    raw = (
        explicit
        or os.environ.get("LLMTRACKER_SERVER")
        or (load_credentials() or {}).get("server_url")
    )
    return str(raw) if raw else None


def stored_collector() -> str | None:
    """The collector recorded at login, or None for a login that predates it."""
    endpoint = (load_credentials() or {}).get("otlp_logs_endpoint")
    return endpoint if isinstance(endpoint, str) and endpoint else None


def remember_collector(endpoint: str) -> None:
    """Record the collector so later commands need no network round trip."""
    credentials = load_credentials()
    if credentials is None or credentials.get("otlp_logs_endpoint") == endpoint:
        return
    credentials["otlp_logs_endpoint"] = endpoint
    save_credentials(credentials)


def discover_collector() -> str | None:
    """The collector to wire agents at, from the server this machine signed in to.

    Logins made before the client recorded the endpoint have none, and a remote
    server's collector cannot be derived from the local config — the OTLP port
    is usually not the API port. So ask the server, then remember the answer.
    """
    stored = stored_collector()
    if stored:
        return stored
    server = resolve_server(None)
    if not server:
        return None
    try:
        response = httpx.get(f"{server}/version", timeout=5)
        response.raise_for_status()
        endpoint = response.json().get("otlp_logs_endpoint")
    except (httpx.HTTPError, ValueError, AttributeError):
        return None
    if not isinstance(endpoint, str) or not valid_logs_endpoint(endpoint):
        return None
    remember_collector(endpoint)
    return endpoint


def login(
    server_arg: str | None, *, device_name_arg: str | None, no_browser: bool
) -> int:
    from client.setup import wire_agents

    try:
        previous = load_credentials() or {}
        raw_server = resolve_server(server_arg)
        if not raw_server:
            print("server URL required: use login --server URL", file=sys.stderr)
            return 2
        server = normalize_server_url(raw_server)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if check_server(server) != 0:
        return 1

    verifier, challenge = _pkce_pair()
    device_name = _device_name(device_name_arg or socket.gethostname())
    login_url = f"{server}/auth/cli/start?" + urlencode(
        {"code_challenge": challenge, "device_name": device_name}
    )
    print(f"Open this URL in your browser to continue login:\n  {login_url}")
    if not no_browser and not (
        os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY")
    ):
        webbrowser.open(login_url)

    try:
        key = installation_key(server)
    except (OSError, ValueError) as exc:
        print(f"cannot prepare installation identity: {exc}", file=sys.stderr)
        return 1
    body: dict[str, str] = {
        "code_verifier": verifier,
        "installation_key": key,
        "client_version": client_version(),
    }
    commit = client_commit()
    if commit:
        body["client_commit"] = commit
    if previous.get("server_url") == server:
        for kind in ("cli", "ingest"):
            old_token = previous.get(f"{kind}_token")
            if isinstance(old_token, str) and old_token:
                body[f"prior_{kind}_token"] = old_token

    for attempt in range(3):
        try:
            raw_code = input("Paste the code shown in your browser: ")
        except EOFError:
            raw_code = ""
        if not raw_code.strip():
            print("no code entered; no credentials written", file=sys.stderr)
            return 1
        body["code"] = "".join(raw_code.split()).upper().replace("-", "")
        try:
            response = httpx.post(f"{server}/auth/cli/exchange", json=body, timeout=10)
        except httpx.HTTPError as exc:
            print(
                "login exchange could not be confirmed; your previous tokens may "
                f"no longer work. Run llm-tracker login again. Details: {exc}",
                file=sys.stderr,
            )
            return 1
        if response.status_code == 200:
            break
        if response.status_code == 400 and attempt < 2:
            print("invalid or expired code — paste it again", file=sys.stderr)
            continue
        # 400 after the last attempt, or a non-code rejection (422 on a
        # malformed client_version/commit) — show why rather than the bare code.
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        suffix = f": {detail}" if isinstance(detail, str) else ""
        print(f"login failed: HTTP {response.status_code}{suffix}", file=sys.stderr)
        return 1
    try:
        payload = response.json()
        user = payload["user"]
        token = payload["ingest_token"]
        endpoint = payload["otlp"]["logs_endpoint"]
        device_id = payload["device_id"]
        if not all(
            isinstance(value, str) and value for value in (token, endpoint, device_id)
        ):
            raise ValueError("missing device credentials")
        if not valid_logs_endpoint(endpoint):
            raise ValueError("invalid OTLP endpoint")
        if not isinstance(user, dict) or not isinstance(user.get("email"), str):
            raise ValueError("missing user")
        if not isinstance(payload.get("cli_token"), str):
            raise ValueError("missing CLI token")
        save_credentials(
            {
                "server_url": server,
                "user_id": user.get("id"),
                "email": user["email"],
                "device_id": device_id,
                "device_name": payload.get("device_name"),
                "cli_token": payload["cli_token"],
                "ingest_token": token,
                "otlp_logs_endpoint": endpoint,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        print(
            "login could not use the new credentials. Your previous tokens may "
            f"no longer work; run llm-tracker login again. Details: {exc}",
            file=sys.stderr,
        )
        return 1

    print(f"Logged in as {user['email']} (device: {payload.get('device_name')})")
    print(f"Credentials saved to {credentials_path()}")
    print(f"Dashboard: {server}")
    wired = wire_agents(logs_endpoint=endpoint, token=token)
    if wired:
        print("Wired agents: " + ", ".join(wired))
    else:
        print("No tracked agents detected; nothing to wire.")
    return 0


def logout(*, keep_agents: bool) -> int:
    from client.setup import disable_agents

    previous = load_credentials() or {}
    # Captured before the credentials go, so un-wiring knows which collector
    # these agent files were pointing at and leaves anyone else's alone.
    collector = previous.get("otlp_logs_endpoint")
    if not clear_credentials():
        print("Not signed in; nothing to remove.", file=sys.stderr)
        return 1
    print(f"  removed   {credentials_path()}")
    if keep_agents:
        endpoint = previous.get("server_url")
        print(
            "  warning   agents still point at the last configured collector"
            + (f" ({endpoint})" if endpoint else "")
            + " and will be rejected",
            file=sys.stderr,
        )
    else:
        removed = disable_agents(
            expected_endpoint=collector if isinstance(collector, str) else None
        )
        if removed:
            print("  un-wired  " + ", ".join(removed))
    print(
        "Signed out. The device stays listed in Settings → Devices until you remove it."
    )
    return 0
