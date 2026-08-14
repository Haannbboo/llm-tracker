"""Google OAuth web login flow (docs/design/specs/pr2-google-oauth-web-login.md).

authlib handles the OAuth2/OIDC handshake (authorization URL construction,
code exchange, ID-token verification). OAuth ``state`` values are tracked
server-side in a JSON file under the tracker home, guarded by ``flock`` —
there is no client-side signed session.
"""

from __future__ import annotations

import fcntl
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
from authlib.integrations.base_client import OAuthError
from authlib.integrations.starlette_client import OAuth
from joserfc.errors import JoseError

from config.app import CONFIG
from config.models import get_tracker_home

logger = logging.getLogger(__name__)

STATE_FILE_NAME = "oauth_state.json"
STATE_TTL_SECONDS = 5 * 60
MAX_PENDING_STATES = 512

# Google endpoints are pinned (no discovery-document fetch at runtime); the
# only outbound calls are the token exchange and the JWKS fetch.
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUER = "https://accounts.google.com"

oauth = OAuth()


class OAuthFlowError(Exception):
    """The Google handshake failed (misconfiguration, exchange, or verify)."""


def google_credentials() -> tuple[str, str] | None:
    """Return (client_id, client_secret) from env-backed config, or None."""
    auth = CONFIG.get("auth", {})
    client_id = str(auth.get("google_client_id", "") or "")
    client_secret = str(auth.get("google_client_secret", "") or "")
    if not client_id or not client_secret:
        return None
    return client_id, client_secret


def _ensure_registered() -> None:
    credentials = google_credentials()
    if credentials is None:
        raise OAuthFlowError("google oauth is not configured")
    client_id, client_secret = credentials
    oauth.register(
        "google",
        client_id=client_id,
        client_secret=client_secret,
        authorize_url=GOOGLE_AUTHORIZE_URL,
        access_token_url=GOOGLE_TOKEN_URL,
        client_kwargs={"scope": "openid email profile"},
        jwks_uri=GOOGLE_JWKS_URI,
        issuer=GOOGLE_ISSUER,
    )


async def build_authorize_url(redirect_uri: str, state: str, nonce: str) -> str:
    """Build the Google consent-screen URL for this state/nonce."""
    _ensure_registered()
    result = await oauth.google.create_authorization_url(
        redirect_uri, state=state, nonce=nonce
    )
    return str(result["url"])


async def exchange_code(redirect_uri: str, code: str) -> dict[str, Any]:
    """Exchange an authorization code for tokens (authlib/httpx)."""
    _ensure_registered()
    try:
        token = await oauth.google.fetch_access_token(
            redirect_uri=redirect_uri, code=code
        )
    except (OAuthError, httpx.HTTPError) as exc:
        logger.warning("Google token exchange failed: %s", exc)
        raise OAuthFlowError("token exchange failed") from exc
    return dict(token)


async def verify_id_token(token: dict[str, Any], nonce: str) -> dict[str, Any]:
    """Verify the ID token (signature, nonce, issuer, audience) and return claims."""
    _ensure_registered()
    try:
        claims = await oauth.google.parse_id_token(token, nonce=nonce)
    except (OAuthError, JoseError, httpx.HTTPError) as exc:
        # httpx.HTTPError covers the JWKS fetch: authlib's fetch_jwk_set calls
        # raise_for_status(), which raises HTTPStatusError on a bad response
        # and transport errors on connectivity failures.
        logger.warning("Google ID-token verification failed: %s", exc)
        raise OAuthFlowError("id token verification failed") from exc
    return dict(claims)


def _state_path() -> Path:
    return Path(get_tracker_home()) / STATE_FILE_NAME


def _load_states_unlocked(handle) -> dict[str, Any]:
    handle.seek(0)
    raw = handle.read()
    if not raw.strip():
        return {}
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return loaded


def _prune_expired(states: dict[str, Any], now: float) -> None:
    for key in [
        key
        for key, entry in states.items()
        if not isinstance(entry, dict)
        or not isinstance(entry.get("exp"), (int, float))
        or float(entry["exp"]) <= now
    ]:
        del states[key]


def store_oauth_state(state: str, data: dict[str, Any]) -> None:
    """Persist a state with a TTL, pruning expired entries first."""
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            states = _load_states_unlocked(handle)
            _prune_expired(states, time.time())
            if len(states) >= MAX_PENDING_STATES:
                # A burst of /auth/google/login calls (public whenever auth
                # is enabled) shouldn't grow the file without bound inside
                # the TTL window; drop the oldest pending states to make room.
                oldest_first = sorted(states, key=lambda key: states[key]["exp"])
                for key in oldest_first[: len(states) - MAX_PENDING_STATES + 1]:
                    del states[key]
            states[state] = {"exp": time.time() + STATE_TTL_SECONDS, **data}
            handle.seek(0)
            handle.truncate()
            json.dump(states, handle)
            handle.flush()
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def pop_oauth_state(state: str) -> dict[str, Any] | None:
    """Consume a state single-use. Returns its data or None when missing/expired."""
    if not state:
        return None
    path = _state_path()
    if not path.exists():
        return None
    with open(path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            states = _load_states_unlocked(handle)
            if not states:
                return None
            entry = states.pop(state, None)
            _prune_expired(states, time.time())
            handle.seek(0)
            handle.truncate()
            json.dump(states, handle)
            handle.flush()
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    if not isinstance(entry, dict) or not isinstance(entry.get("exp"), (int, float)):
        return None
    if float(entry["exp"]) <= time.time():
        return None
    return entry
