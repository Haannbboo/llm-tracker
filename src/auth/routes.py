import logging
import secrets
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from config.app import CONFIG
from config.server_config import resolve_server_urls

from ..database import AuthToken, User
from . import google as auth_google
from .tokens import (
    list_user_tokens,
    mint_token,
    resolve_token,
    revoke_token,
    update_user_name,
)

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "llm_tracker_session"

router = APIRouter()


def _auth_enabled() -> bool:
    return bool(CONFIG.get("auth", {}).get("enabled"))


def _request_token(request: Request) -> str | None:
    """Extract a session token from the Authorization header or session cookie."""
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    token = token.strip()
    if scheme.lower() == "bearer" and token:
        return token
    return request.cookies.get(SESSION_COOKIE_NAME)


def _resolve_request_user(
    request: Request,
) -> tuple[User, AuthToken] | None:
    """Resolve the request's bearer/cookie token to (user, auth_token), or None."""
    token = _request_token(request)
    if not token:
        return None
    resolved = resolve_token(token)
    if resolved is None:
        return None
    user, auth_token = resolved
    request.state.user = user
    request.state.auth_token = auth_token
    return user, auth_token


def get_current_user(request: Request) -> User | None:
    """Resolve the request's session (bearer token or cookie) to a user.

    Returns None when auth is disabled. When enabled, raises 401 for
    missing/malformed/unknown/revoked tokens (one message for all cases —
    callers must not learn which). DB errors propagate as 500: fail closed.
    """
    if not _auth_enabled():
        return None
    user = getattr(request.state, "user", None)
    if user is not None:
        return user
    resolved = _resolve_request_user(request)
    if resolved is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return resolved[0]


def _cookie_is_secure() -> bool:
    """`Secure` on the session cookie iff the public API URL is HTTPS.

    Derived from server.base_url (the same source of truth as the OAuth
    redirect URI) — not from the incoming request's scheme, which is wrong
    behind a TLS-terminating reverse proxy.
    """
    return resolve_server_urls(CONFIG)["api_url"].startswith("https://")


def _google_redirect_uri() -> str:
    return resolve_server_urls(CONFIG)["api_url"] + "/auth/google/callback"


def _frontend_redirect(
    origin: str | None = None, auth_error: str | None = None
) -> RedirectResponse:
    """Redirect back to the frontend, preserving its origin when known.

    The origin is captured from the login request, so in Vite dev the browser
    lands back on the dev server; production (frontend served by this app)
    gets an identical same-origin redirect.
    """
    base = f"{origin}/" if origin else "/"
    location = f"{base}?auth_error={auth_error}" if auth_error else base
    return RedirectResponse(location, status_code=302)


_DEV_FRONTEND_HOSTS = ("localhost", "127.0.0.1")
_DEV_FRONTEND_PORT = 5173


def _request_frontend_origin(request: Request) -> str | None:
    """The Vite dev server's origin, when the login request came from it.

    Production serves the frontend from this same app (mounted at "/"), so a
    relative "/" redirect is already correct there. The only case worth
    trusting here is the well-known Vite dev port — never an arbitrary
    client-supplied origin, which would make this an open redirect.
    """
    raw = request.headers.get("origin") or request.headers.get("referer")
    if not raw:
        return None
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    if (
        parsed.scheme != "http"
        or parsed.hostname not in _DEV_FRONTEND_HOSTS
        or parsed.port != _DEV_FRONTEND_PORT
    ):
        return None
    return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"


@router.get("/auth/me")
def auth_me(request: Request, user: User | None = Depends(get_current_user)):
    if user is None:
        return {"auth_enabled": False, "user": None}
    auth_token = request.state.auth_token
    return {
        "auth_enabled": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "created_at": user.created_at,
        },
        "token": (
            {"kind": auth_token.kind, "device_name": auth_token.device_name}
            if auth_token
            else None
        ),
    }


@router.get("/auth/google/login")
async def auth_google_login(request: Request):
    """Start the Google authorization-code flow (public when auth enabled)."""
    if not _auth_enabled():
        raise HTTPException(status_code=404, detail="not found")
    if auth_google.google_credentials() is None:
        raise HTTPException(status_code=503, detail="google oauth not configured")
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    redirect_uri = _google_redirect_uri()
    origin = _request_frontend_origin(request)
    try:
        url = await auth_google.build_authorize_url(redirect_uri, state, nonce)
    except auth_google.OAuthFlowError:
        logger.exception("Failed to build Google authorize URL")
        raise HTTPException(status_code=503, detail="google oauth not configured")
    auth_google.store_oauth_state(
        state, {"nonce": nonce, "redirect_uri": redirect_uri, "origin": origin}
    )
    return RedirectResponse(url, status_code=302)


@router.get("/auth/google/callback")
async def auth_google_callback(request: Request):
    """Complete the Google flow: verify state, exchange the code, set the cookie."""
    if not _auth_enabled():
        raise HTTPException(status_code=404, detail="not found")
    state = request.query_params.get("state", "")
    data = auth_google.pop_oauth_state(state)
    if data is None:
        return _frontend_redirect(auth_error="invalid_state")
    origin = data.get("origin")
    if request.query_params.get("error") or not request.query_params.get("code"):
        return _frontend_redirect(origin, auth_error="oauth_failed")
    code = request.query_params["code"]
    try:
        token = await auth_google.exchange_code(data["redirect_uri"], code)
        claims = await auth_google.verify_id_token(token, data["nonce"])
    except auth_google.OAuthFlowError:
        logger.exception("Google OAuth callback failed")
        return _frontend_redirect(origin, auth_error="oauth_failed")
    if claims.get("email_verified") is not True:
        return _frontend_redirect(origin, auth_error="email_unverified")
    email = str(claims.get("email", "")).strip().lower()
    if not email:
        return _frontend_redirect(origin, auth_error="email_unverified")
    allowlist = CONFIG.get("auth", {}).get("allowlist") or []
    normalized_allowlist = [str(entry).strip().lower() for entry in allowlist if entry]
    if normalized_allowlist and email not in normalized_allowlist:
        # No user/token row is created for a rejected email.
        return _frontend_redirect(origin, auth_error="not_allowlisted")
    plaintext_token, user = mint_token(email, kind="web", device_name="browser")
    update_user_name(user.id, str(claims.get("name") or "").strip() or None)
    response = _frontend_redirect(origin)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        plaintext_token,
        httponly=True,
        samesite="lax",
        secure=_cookie_is_secure(),
    )
    return response


@router.post("/auth/logout")
def auth_logout(request: Request, user: User | None = Depends(get_current_user)):
    """Revoke the authenticating token and clear the session cookie."""
    if user is None:
        raise HTTPException(status_code=404, detail="not found")
    auth_token = getattr(request.state, "auth_token", None)
    if auth_token is not None:
        revoke_token(auth_token.id, user.id)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/auth/devices")
def auth_devices(request: Request, user: User | None = Depends(get_current_user)):
    """List the caller's active tokens; `current` marks the authenticating one."""
    if user is None:
        raise HTTPException(status_code=404, detail="not found")
    auth_token = getattr(request.state, "auth_token", None)
    current_id = auth_token.id if auth_token is not None else None
    return {
        "devices": [
            {
                "id": device.id,
                "kind": device.kind,
                "device_name": device.device_name,
                "created_at": device.created_at,
                "last_used_at": device.last_used_at,
                "current": device.id == current_id,
            }
            for device in list_user_tokens(user.id)
        ]
    }


@router.post("/auth/devices/{device_id}/revoke")
def auth_devices_revoke(
    device_id: str,
    request: Request,
    user: User | None = Depends(get_current_user),
):
    """Revoke a token owned by the caller. 404 for unknown or other-owned ids."""
    if user is None:
        raise HTTPException(status_code=404, detail="not found")
    if not revoke_token(device_id, user.id):
        raise HTTPException(status_code=404, detail="not found")
    return Response(status_code=204)
