"""User and auth-token operations.

Tokens are opaque (`llmt_<kind>_<hex>`), shown once at mint time, and stored
only as sha256 hashes.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database.engine import get_engine
from ..database.models import AuthToken, User

TOKEN_KINDS = ("cli", "ingest", "web")


def _now_micros() -> int:
    return time.time_ns() // 1000


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mint_token(
    email: str,
    kind: str = "cli",
    device_name: str | None = None,
    db_path: str | None = None,
) -> tuple[str, User]:
    """Mint a token for the user with this email, creating the user if new.

    Returns the plaintext token (the only time it is available) and the user.
    """
    if kind not in TOKEN_KINDS:
        raise ValueError(
            f"invalid token kind: {kind!r} (expected one of {TOKEN_KINDS})"
        )
    email = email.strip().lower()
    if not email:
        raise ValueError("email must not be empty")
    token = f"llmt_{kind}_{secrets.token_hex(24)}"
    engine = get_engine(db_path)
    with Session(engine, expire_on_commit=False) as session:
        user = session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        if user is None:
            user = User(email=email, created_at=_now_micros())
            session.add(user)
            session.flush()
        session.add(
            AuthToken(
                user_id=user.id,
                kind=kind,
                device_name=device_name,
                token_hash=hash_token(token),
                created_at=_now_micros(),
            )
        )
        session.commit()
    return token, user


def resolve_token(
    token: str, db_path: str | None = None
) -> tuple[User, AuthToken] | None:
    """Return the token's user and the token row, or None for unknown/revoked.

    DB errors propagate (fail closed); only a failed last_used_at update is
    swallowed.
    """
    engine = get_engine(db_path)
    with Session(engine, expire_on_commit=False) as session:
        row = session.execute(
            select(AuthToken, User)
            .join(User, AuthToken.user_id == User.id)
            .where(AuthToken.token_hash == hash_token(token))
        ).first()
        if row is None:
            return None
        auth_token, user = row
        if auth_token.revoked_at is not None:
            return None
        session.expunge_all()
    try:
        with Session(engine, expire_on_commit=False) as update_session:
            update_session.execute(
                sa_update(AuthToken)
                .where(AuthToken.id == auth_token.id)
                .values(last_used_at=_now_micros())
            )
            update_session.commit()
    except SQLAlchemyError:
        logging.getLogger(__name__).warning(
            "Failed to update last_used_at for token id=%s", auth_token.id
        )
    return user, auth_token


def update_user_name(
    user_id: str, name: str | None, db_path: str | None = None
) -> None:
    """Backfill a user's name from an OAuth profile, only while it is unset.

    A name already set (first login happened) is never overwritten.
    """
    engine = get_engine(db_path)
    with Session(engine, expire_on_commit=False) as session:
        session.execute(
            sa_update(User)
            .where(User.id == user_id, User.name.is_(None))
            .values(name=name)
        )
        session.commit()


def revoke_token(token_id: str, user_id: str, db_path: str | None = None) -> bool:
    """Revoke a token owned by this user. Returns False if absent/already revoked."""
    engine = get_engine(db_path)
    with Session(engine, expire_on_commit=False) as session:
        result = session.execute(
            sa_update(AuthToken)
            .where(
                AuthToken.id == token_id,
                AuthToken.user_id == user_id,
                AuthToken.revoked_at.is_(None),
            )
            .values(revoked_at=_now_micros())
        )
        changed = result.rowcount > 0  # type: ignore[attr-defined]
        session.commit()
    return changed


def list_user_tokens(user_id: str, db_path: str | None = None) -> list[AuthToken]:
    """Return the user's active (non-revoked) tokens, newest first."""
    engine = get_engine(db_path)
    with Session(engine, expire_on_commit=False) as session:
        rows = (
            session.execute(
                select(AuthToken)
                .where(AuthToken.user_id == user_id, AuthToken.revoked_at.is_(None))
                .order_by(AuthToken.created_at.desc())
            )
            .scalars()
            .all()
        )
        session.expunge_all()
        return list(rows)
