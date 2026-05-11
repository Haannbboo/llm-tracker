"""BaseUrl entity operations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import BaseUrl
from .engine import get_engine


def _apply_base_url_updates(
    row: BaseUrl,
    *,
    provider_name: str | None,
    source: str | None,
) -> bool:
    updated = False
    if provider_name and (not row.provider_name or row.provider_name == "unknown"):
        row.provider_name = provider_name
        updated = True
    if source and not row.source:
        row.source = source
        updated = True
    return updated


def get_or_create_base_url(
    base_url: str,
    *,
    db_path: str | None = None,
    provider_name: str | None = None,
    source: str | None = None,
) -> int:
    """Resolve a stable `base_urls.id`, updating missing metadata when possible."""
    engine = get_engine(db_path)

    for attempt in range(2):
        with Session(engine) as session:
            row = session.scalar(select(BaseUrl).where(BaseUrl.base_url == base_url))
            if row is not None:
                if _apply_base_url_updates(
                    row,
                    provider_name=provider_name,
                    source=source,
                ):
                    session.commit()
                return int(row.id)

            row = BaseUrl(
                base_url=base_url,
                provider_name=provider_name,
                source=source,
            )
            session.add(row)
            try:
                session.commit()
                return int(row.id)
            except IntegrityError:
                # On PostgreSQL, the transaction is aborted after an IntegrityError.
                # Retry in a fresh transaction so we can observe the winning row.
                session.rollback()
                if attempt == 0:
                    continue
                raise

    raise RuntimeError(f"Failed to resolve base_url id for {base_url}")


def resolve_base_url_id(
    *,
    base_url: str | None,
    db_path: str | None = None,
    provider_name: str | None = None,
    source: str | None = None,
) -> int | None:
    if not base_url:
        return None

    return get_or_create_base_url(
        base_url,
        db_path=db_path,
        provider_name=provider_name,
        source=source,
    )
