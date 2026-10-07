"""Device status report persistence helpers."""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from .engine import get_engine
from .models import DeviceStatus


def _now_micros() -> int:
    """Same microsecond clock the devices table uses."""
    return time.time_ns() // 1000


def upsert_device_status(
    installation_hash: str,
    status_json: str,
    *,
    db_path: str | None = None,
) -> None:
    """Store the latest report for an installation, replacing any older one."""
    reported_at = _now_micros()
    engine = get_engine(db_path)
    with Session(engine) as session:
        row = session.get(DeviceStatus, installation_hash)
        if row is None:
            session.add(
                DeviceStatus(
                    installation_hash=installation_hash,
                    status_json=status_json,
                    reported_at=reported_at,
                )
            )
        else:
            row.status_json = status_json
            row.reported_at = reported_at
        session.commit()


def list_device_statuses(
    installation_hashes: list[str] | None = None,
    *,
    db_path: str | None = None,
) -> list[DeviceStatus]:
    """Latest reports, newest first; optionally scoped to installation hashes."""
    query = select(DeviceStatus)
    if installation_hashes is not None:
        query = query.where(DeviceStatus.installation_hash.in_(installation_hashes))
    query = query.order_by(DeviceStatus.reported_at.desc())
    with Session(get_engine(db_path), expire_on_commit=False) as session:
        rows = session.execute(query).scalars().all()
        session.expunge_all()
        return list(rows)
