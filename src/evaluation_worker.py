"""Automatic session evaluation worker."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from config.app import CONFIG

from .database import (
    EvaluationJob,
    SessionRecord,
    claim_next_evaluation_job,
    count_running_evaluation_jobs,
    create_session_evaluation_job,
    fail_stale_running_evaluation_jobs,
    get_engine,
    list_active_evaluation_jobs,
)
from .database.evaluation_jobs import (
    ACTIVE_EVALUATION_JOB_STATUSES,
    SESSION_EVALUATION_JOB_KIND,
)
from .evaluation import (
    LocalSessionTranscriptIndex,
    build_local_session_transcript_index,
    execute_session_evaluation_job,
    has_local_session_transcript,
    is_local_evaluator_session,
    mark_evaluator_session_no_op,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvaluationWorkerConfig:
    auto_enabled: bool = True
    quiet_delay_seconds: int = 600
    max_concurrent_jobs: int = 1
    queue_buffer_multiplier: int = 2
    idle_sleep_cap_seconds: int = 30
    worker_tick_timeout_seconds: int = 120


def load_evaluation_worker_config(
    config: dict[str, Any] | None = None,
) -> EvaluationWorkerConfig:
    raw = (config or CONFIG).get("evaluation", {})
    return EvaluationWorkerConfig(
        auto_enabled=bool(raw.get("auto_enabled", True)),
        quiet_delay_seconds=max(1, int(raw.get("quiet_delay_seconds", 600))),
        max_concurrent_jobs=max(1, int(raw.get("max_concurrent_jobs", 1))),
        queue_buffer_multiplier=max(1, int(raw.get("queue_buffer_multiplier", 2))),
        idle_sleep_cap_seconds=max(1, int(raw.get("idle_sleep_cap_seconds", 30))),
        worker_tick_timeout_seconds=max(
            1,
            int(raw.get("worker_tick_timeout_seconds", 120)),
        ),
    )


def _parse_iso(value: str) -> datetime:
    normalized = f"{value[:-1]}+00:00" if value.endswith(("Z", "z")) else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def select_auto_evaluation_candidates(
    *,
    quiet_delay_seconds: int,
    limit: int,
    now: str | None = None,
    db_path: str | None = None,
) -> list[dict[str, str | None]]:
    if limit <= 0:
        return []

    now_dt = _parse_iso(now) if now is not None else datetime.now(timezone.utc)
    quiet_cutoff = (now_dt - timedelta(seconds=quiet_delay_seconds)).isoformat()
    latest_failed_auto = (
        select(func.max(EvaluationJob.finished_at))
        .where(
            and_(
                EvaluationJob.kind == SESSION_EVALUATION_JOB_KIND,
                EvaluationJob.trigger == "auto",
                EvaluationJob.status == "failed",
                EvaluationJob.session_id == SessionRecord.session_id,
            )
        )
        .correlate(SessionRecord)
        .scalar_subquery()
    )
    active_job_exists = exists().where(
        and_(
            EvaluationJob.kind == SESSION_EVALUATION_JOB_KIND,
            EvaluationJob.session_id == SessionRecord.session_id,
            EvaluationJob.status.in_(ACTIVE_EVALUATION_JOB_STATUSES),
        )
    )
    query = (
        select(SessionRecord)
        .where(
            and_(
                SessionRecord.updated_at <= quiet_cutoff,
                or_(SessionRecord.source.is_(None), SessionRecord.source != "manual"),
                or_(
                    SessionRecord.evaluated_at.is_(None),
                    SessionRecord.updated_at > SessionRecord.evaluated_at,
                ),
                or_(
                    latest_failed_auto.is_(None),
                    SessionRecord.updated_at > latest_failed_auto,
                ),
                ~active_job_exists,
            )
        )
        .order_by(SessionRecord.updated_at.desc())
        .limit(max(limit * 10, 50))
    )

    with Session(get_engine(db_path)) as session:
        records = session.execute(query).scalars().all()

    local_index = build_local_session_transcript_index()
    candidates: list[dict[str, str | None]] = []
    for record in records:
        if not has_local_session_transcript(
            record.client_source,
            record.session_id,
            local_index=local_index,
        ):
            continue
        candidates.append(
            {
                "session_id": record.session_id,
                "client_source": record.client_source,
                "updated_at": record.updated_at,
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


def enqueue_auto_evaluation_jobs(
    *,
    config: EvaluationWorkerConfig,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    if not config.auto_enabled:
        return []

    active_jobs = list_active_evaluation_jobs(db_path=db_path)
    target_depth = config.max_concurrent_jobs * config.queue_buffer_multiplier
    slots = max(0, target_depth - len(active_jobs))
    if slots == 0:
        return []

    candidates = select_auto_evaluation_candidates(
        quiet_delay_seconds=config.quiet_delay_seconds,
        limit=slots * 5,
        db_path=db_path,
    )
    jobs: list[dict[str, Any]] = []
    for candidate in candidates[:slots]:
        jobs.append(
            create_session_evaluation_job(
                session_id=str(candidate["session_id"]),
                client_source=candidate["client_source"],
                trigger="auto",
                db_path=db_path,
            )
        )
    return jobs


def classify_local_evaluator_sessions(
    *,
    limit: int,
    db_path: str | None = None,
) -> int:
    if limit <= 0:
        return 0
    query = (
        select(SessionRecord)
        .where(
            and_(
                SessionRecord.client_source == "codex",
                or_(SessionRecord.source.is_(None), SessionRecord.source != "manual"),
                or_(SessionRecord.outcome.is_(None), SessionRecord.outcome != "no_op"),
            )
        )
        .order_by(SessionRecord.updated_at.desc())
        .limit(limit)
    )
    with Session(get_engine(db_path)) as session:
        records = session.execute(query).scalars().all()

    local_index = build_local_session_transcript_index()
    classified = 0
    for record in records:
        if not has_local_session_transcript(
            record.client_source,
            record.session_id,
            local_index=local_index,
        ):
            continue
        if not is_local_evaluator_session(record.client_source, record.session_id):
            continue
        if mark_evaluator_session_no_op(record.session_id, db_path=db_path):
            classified += 1
    classified += classify_transcriptless_evaluator_telemetry(
        limit=limit,
        db_path=db_path,
        local_index=local_index,
    )
    return classified


def _record_overlaps_evaluation_job(
    record: SessionRecord,
    jobs: list[EvaluationJob],
    *,
    now: datetime,
    grace_seconds: int,
) -> bool:
    try:
        record_started = _parse_iso(record.started)
    except ValueError:
        return False

    grace = timedelta(seconds=grace_seconds)
    for job in jobs:
        if job.session_id == record.session_id or job.started_at is None:
            continue
        try:
            started_at = _parse_iso(job.started_at)
            finished_at = _parse_iso(job.finished_at) if job.finished_at else now
        except ValueError:
            continue
        if started_at - grace <= record_started <= finished_at + grace:
            return True
    return False


def classify_transcriptless_evaluator_telemetry(
    *,
    limit: int,
    db_path: str | None = None,
    grace_seconds: int = 60,
    local_index: LocalSessionTranscriptIndex | None = None,
) -> int:
    """Mark Codex OTLP emitted by ephemeral evaluator runs as no-op.

    Codex evaluator runs may emit OTLP even when they do not persist a local
    session file. In that case prompt-based detection cannot inspect the
    transcript, so we only classify one-request transcriptless Codex sessions
    whose start time overlaps a real evaluation job window.
    """
    if limit <= 0:
        return 0

    with Session(get_engine(db_path)) as session:
        records = (
            session.execute(
                select(SessionRecord)
                .where(
                    and_(
                        SessionRecord.client_source == "codex",
                        SessionRecord.request_count == 1,
                        or_(
                            SessionRecord.source.is_(None),
                            SessionRecord.source != "manual",
                        ),
                        or_(
                            SessionRecord.outcome.is_(None),
                            SessionRecord.outcome != "no_op",
                        ),
                    )
                )
                .order_by(SessionRecord.updated_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        jobs = (
            session.execute(
                select(EvaluationJob)
                .where(
                    and_(
                        EvaluationJob.kind == SESSION_EVALUATION_JOB_KIND,
                        EvaluationJob.started_at.is_not(None),
                    )
                )
                .order_by(EvaluationJob.started_at.desc())
                .limit(max(limit * 5, 50))
            )
            .scalars()
            .all()
        )

    if not records or not jobs:
        return 0

    index = local_index or build_local_session_transcript_index()
    now = datetime.now(timezone.utc)
    classified = 0
    for record in records:
        if any(record.session_id in path_name for path_name in index.codex_path_names):
            continue
        if not _record_overlaps_evaluation_job(
            record,
            jobs,
            now=now,
            grace_seconds=grace_seconds,
        ):
            continue
        if mark_evaluator_session_no_op(record.session_id, db_path=db_path):
            classified += 1
    return classified


def _claim_evaluation_jobs(
    *,
    config: EvaluationWorkerConfig,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    fail_stale_running_evaluation_jobs(db_path=db_path)
    classify_local_evaluator_sessions(
        limit=max(config.max_concurrent_jobs * config.queue_buffer_multiplier * 10, 50),
        db_path=db_path,
    )
    enqueue_auto_evaluation_jobs(config=config, db_path=db_path)

    jobs: list[dict[str, Any]] = []
    while count_running_evaluation_jobs(db_path=db_path) < config.max_concurrent_jobs:
        job = claim_next_evaluation_job(db_path=db_path)
        if job is None:
            break
        jobs.append(job)
    return jobs


async def run_evaluation_worker_once(
    *,
    config: EvaluationWorkerConfig,
    db_path: str | None = None,
    active_tasks: set[asyncio.Task] | None = None,
) -> int:
    jobs = await asyncio.to_thread(
        _claim_evaluation_jobs,
        config=config,
        db_path=db_path,
    )
    for job in jobs:
        task = asyncio.create_task(
            asyncio.to_thread(
                execute_session_evaluation_job,
                job["job_id"],
                db_path=db_path,
            )
        )
        if active_tasks is not None:
            active_tasks.add(task)
            task.add_done_callback(active_tasks.discard)
    return len(jobs)


async def run_evaluation_worker(
    *,
    stop_event: asyncio.Event,
    config: EvaluationWorkerConfig | None = None,
    db_path: str | None = None,
) -> None:
    worker_config = config or load_evaluation_worker_config()
    active_tasks: set[asyncio.Task] = set()
    tick_task: asyncio.Task[int] | None = None
    while not stop_event.is_set():
        if tick_task is None:
            tick_task = asyncio.create_task(
                run_evaluation_worker_once(
                    config=worker_config,
                    db_path=db_path,
                    active_tasks=active_tasks,
                )
            )

        done, _pending = await asyncio.wait(
            {tick_task},
            timeout=worker_config.worker_tick_timeout_seconds,
        )
        if done:
            try:
                await tick_task
            except Exception:
                logger.exception("Evaluation worker tick failed")
            tick_task = None
        else:
            logger.error("Evaluation worker tick timed out")

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=worker_config.idle_sleep_cap_seconds,
            )
        except asyncio.TimeoutError:
            continue
    if tick_task is not None and not tick_task.done():
        tick_task.cancel()
    if active_tasks:
        await asyncio.gather(*active_tasks, return_exceptions=True)
