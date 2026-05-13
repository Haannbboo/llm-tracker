"""Persistence helpers for asynchronous session evaluation jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .engine import get_engine
from .models import EvaluationJob

SESSION_EVALUATION_JOB_KIND = "session_evaluation"
ACTIVE_EVALUATION_JOB_STATUSES = {"queued", "running"}
EVALUATION_JOB_TIMEOUT_SECONDS = 5 * 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    normalized = f"{value[:-1]}+00:00" if value.endswith(("Z", "z")) else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _job_to_dict(job: EvaluationJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "kind": job.kind,
        "session_id": job.session_id,
        "status": job.status,
        "error": job.error,
    }


def create_session_evaluation_job(
    *,
    session_id: str,
    client_source: str | None,
    created_at: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    job = EvaluationJob(
        job_id=str(uuid4()),
        kind=SESSION_EVALUATION_JOB_KIND,
        session_id=session_id,
        client_source=client_source,
        status="queued",
        created_at=created_at or _now_iso(),
    )

    with Session(get_engine(db_path)) as session:
        session.add(job)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            active_job = (
                session.execute(
                    select(EvaluationJob)
                    .where(
                        and_(
                            EvaluationJob.kind == SESSION_EVALUATION_JOB_KIND,
                            EvaluationJob.session_id == session_id,
                            EvaluationJob.status.in_(ACTIVE_EVALUATION_JOB_STATUSES),
                        )
                    )
                    .order_by(EvaluationJob.created_at.desc())
                )
                .scalars()
                .first()
            )
            if active_job is None:
                raise
            return _job_to_dict(active_job)
        session.refresh(job)
        return _job_to_dict(job)


def get_evaluation_job(
    job_id: str,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    with Session(get_engine(db_path)) as session:
        job = session.get(EvaluationJob, job_id)
        return _job_to_dict(job) if job else None


def find_active_session_evaluation_job(
    *,
    session_id: str,
    now: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    now_dt = _parse_iso(now) if now is not None else datetime.now(timezone.utc)
    stale_before = now_dt - timedelta(seconds=EVALUATION_JOB_TIMEOUT_SECONDS)

    with Session(get_engine(db_path)) as session:
        jobs = (
            session.execute(
                select(EvaluationJob)
                .where(
                    and_(
                        EvaluationJob.kind == SESSION_EVALUATION_JOB_KIND,
                        EvaluationJob.session_id == session_id,
                        EvaluationJob.status.in_(ACTIVE_EVALUATION_JOB_STATUSES),
                    )
                )
                .order_by(EvaluationJob.created_at.desc())
            )
            .scalars()
            .all()
        )

        for job in jobs:
            if _parse_iso(job.created_at) <= stale_before:
                job.status = "failed"
                job.error = "Evaluation job timed out"
                job.finished_at = now_dt.isoformat()
                continue

            session.commit()
            return _job_to_dict(job)

        session.commit()
        return None


def mark_evaluation_job_running(
    job_id: str,
    *,
    db_path: str | None = None,
) -> None:
    now = _now_iso()
    with Session(get_engine(db_path)) as session:
        job = session.get(EvaluationJob, job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = now
        job.error = None
        session.commit()


def mark_evaluation_job_succeeded(
    job_id: str,
    *,
    db_path: str | None = None,
) -> None:
    now = _now_iso()
    with Session(get_engine(db_path)) as session:
        job = session.get(EvaluationJob, job_id)
        if not job:
            return
        job.status = "succeeded"
        job.finished_at = now
        job.error = None
        session.commit()


def mark_evaluation_job_failed(
    job_id: str,
    error: str,
    *,
    db_path: str | None = None,
) -> None:
    now = _now_iso()
    with Session(get_engine(db_path)) as session:
        job = session.get(EvaluationJob, job_id)
        if not job:
            return
        job.status = "failed"
        job.finished_at = now
        job.error = error
        session.commit()
