from __future__ import annotations

import asyncio
import json


def _insert_session_record(database_module, db_path, session_id: str, **overrides):
    values = {
        "session_id": session_id,
        "client_source": "codex",
        "started": "2026-05-14T09:00:00+00:00",
        "ended": "2026-05-14T09:30:00+00:00",
        "updated_at": "2026-05-14T10:00:00+00:00",
    }
    values.update(overrides)

    with database_module.Session(database_module.get_engine(db_path)) as session:
        session.add(database_module.SessionRecord(**values))
        session.commit()


def test_select_auto_evaluation_candidates_filters_quiet_manual_active_and_local(
    evaluation_worker_module, database_module, isolated_home, monkeypatch
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path, "eligible")
    _insert_session_record(
        database_module,
        db_path,
        "manual",
        source="manual",
        outcome="solved",
        evaluated_at="2026-05-14T09:00:00+00:00",
    )
    _insert_session_record(
        database_module,
        db_path,
        "too-recent",
        updated_at="2026-05-14T10:55:00+00:00",
    )
    _insert_session_record(database_module, db_path, "active")
    _insert_session_record(database_module, db_path, "missing-local")
    database_module.create_session_evaluation_job(
        session_id="active",
        client_source="codex",
        trigger="auto",
        db_path=db_path,
    )
    monkeypatch.setattr(
        evaluation_worker_module,
        "has_local_session_transcript",
        lambda source, session_id, **kwargs: session_id != "missing-local",
    )

    candidates = evaluation_worker_module.select_auto_evaluation_candidates(
        quiet_delay_seconds=600,
        limit=10,
        now="2026-05-14T11:00:01+00:00",
        db_path=db_path,
    )

    assert [candidate["session_id"] for candidate in candidates] == ["eligible"]


def test_select_auto_evaluation_candidates_requires_stale_or_missing_evaluation(
    evaluation_worker_module, database_module, isolated_home, monkeypatch
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(
        database_module,
        db_path,
        "not-evaluated",
        evaluated_at=None,
        source=None,
    )
    _insert_session_record(
        database_module,
        db_path,
        "changed-after-llm",
        source="llm",
        outcome="partial",
        updated_at="2026-05-14T10:01:00+00:00",
        evaluated_at="2026-05-14T09:00:00+00:00",
    )
    _insert_session_record(
        database_module,
        db_path,
        "already-current",
        source="llm",
        outcome="solved",
        updated_at="2026-05-14T10:00:00+00:00",
        evaluated_at="2026-05-14T10:00:00+00:00",
    )
    monkeypatch.setattr(
        evaluation_worker_module,
        "has_local_session_transcript",
        lambda source, session_id, **kwargs: True,
    )

    candidates = evaluation_worker_module.select_auto_evaluation_candidates(
        quiet_delay_seconds=600,
        limit=10,
        now="2026-05-14T11:00:01+00:00",
        db_path=db_path,
    )

    assert [candidate["session_id"] for candidate in candidates] == [
        "changed-after-llm",
        "not-evaluated",
    ]


def test_select_auto_evaluation_candidates_retries_failed_auto_only_after_change(
    evaluation_worker_module, database_module, isolated_home, monkeypatch
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(
        database_module,
        db_path,
        "failed-unchanged",
        updated_at="2026-05-14T10:00:00+00:00",
    )
    _insert_session_record(
        database_module,
        db_path,
        "failed-changed",
        updated_at="2026-05-14T10:30:00+00:00",
    )
    for session_id in ("failed-unchanged", "failed-changed"):
        job = database_module.create_session_evaluation_job(
            session_id=session_id,
            client_source="codex",
            trigger="auto",
            db_path=db_path,
        )
        database_module.mark_evaluation_job_running(job["job_id"], db_path=db_path)
        database_module.mark_evaluation_job_failed(
            job["job_id"],
            "Evaluation agent failed",
            db_path=db_path,
        )
    with database_module.Session(database_module.get_engine(db_path)) as session:
        for job in session.execute(
            database_module.select(database_module.EvaluationJob)
        ).scalars():
            job.finished_at = "2026-05-14T10:15:00+00:00"
        session.commit()
    monkeypatch.setattr(
        evaluation_worker_module,
        "has_local_session_transcript",
        lambda source, session_id, **kwargs: True,
    )

    candidates = evaluation_worker_module.select_auto_evaluation_candidates(
        quiet_delay_seconds=600,
        limit=10,
        now="2026-05-14T11:00:01+00:00",
        db_path=db_path,
    )

    assert [candidate["session_id"] for candidate in candidates] == ["failed-changed"]


def test_select_auto_evaluation_candidates_orders_by_updated_at_desc_and_limits(
    evaluation_worker_module, database_module, isolated_home, monkeypatch
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(
        database_module,
        db_path,
        "oldest",
        updated_at="2026-05-14T09:00:00+00:00",
    )
    _insert_session_record(
        database_module,
        db_path,
        "newest",
        updated_at="2026-05-14T10:30:00+00:00",
    )
    _insert_session_record(
        database_module,
        db_path,
        "middle",
        updated_at="2026-05-14T10:00:00+00:00",
    )
    monkeypatch.setattr(
        evaluation_worker_module,
        "has_local_session_transcript",
        lambda source, session_id, **kwargs: True,
    )

    candidates = evaluation_worker_module.select_auto_evaluation_candidates(
        quiet_delay_seconds=600,
        limit=2,
        now="2026-05-14T11:00:01+00:00",
        db_path=db_path,
    )

    assert [candidate["session_id"] for candidate in candidates] == [
        "newest",
        "middle",
    ]


def test_enqueue_auto_evaluation_jobs_fills_bounded_buffer(
    evaluation_worker_module,
    database_module,
    isolated_home,
    monkeypatch,
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path, "s1", client_source="codex")
    _insert_session_record(database_module, db_path, "s2", client_source="codex")
    _insert_session_record(database_module, db_path, "s3", client_source="codex")
    monkeypatch.setattr(
        evaluation_worker_module,
        "select_auto_evaluation_candidates",
        lambda **kwargs: [
            {"session_id": "s1", "client_source": "codex", "updated_at": None},
            {"session_id": "s2", "client_source": "codex", "updated_at": None},
            {"session_id": "s3", "client_source": "codex", "updated_at": None},
        ],
    )

    jobs = evaluation_worker_module.enqueue_auto_evaluation_jobs(
        config=evaluation_worker_module.EvaluationWorkerConfig(
            auto_enabled=True,
            max_concurrent_jobs=1,
            queue_buffer_multiplier=2,
        ),
        db_path=db_path,
    )

    assert [job["session_id"] for job in jobs] == ["s1", "s2"]
    assert all(job["trigger"] == "auto" for job in jobs)


def test_classify_local_evaluator_sessions_marks_no_op_without_job(
    evaluation_worker_module,
    evaluation_module,
    database_module,
    isolated_home,
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(
        database_module, db_path, "eval-session", client_source="codex"
    )

    session_dir = isolated_home / ".codex" / "sessions" / "2026" / "05" / "14"
    session_dir.mkdir(parents=True)
    (session_dir / "rollout-eval-session.jsonl").write_text(
        json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"{evaluation_module.EVALUATION_PROMPT}\n\n<session_transcript>...</session_transcript>",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    classified = evaluation_worker_module.classify_local_evaluator_sessions(
        limit=10,
        db_path=db_path,
    )

    saved = database_module.get_session_evaluation("eval-session", db_path=db_path)
    assert classified == 1
    assert saved is not None
    assert saved["outcome"] == "no_op"
    assert database_module.list_active_evaluation_jobs(db_path=db_path) == []


def test_classify_local_evaluator_sessions_marks_transcriptless_codex_job_telemetry_no_op(
    evaluation_worker_module,
    database_module,
    isolated_home,
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(
        database_module,
        db_path,
        "evaluated-session",
        request_count=3,
        started="2026-05-14T09:00:00+00:00",
        ended="2026-05-14T09:05:00+00:00",
    )
    _insert_session_record(
        database_module,
        db_path,
        "evaluator-telemetry",
        request_count=1,
        started="2026-05-14T10:00:10+00:00",
        ended="2026-05-14T10:00:10+00:00",
        updated_at="2026-05-14T10:00:11+00:00",
    )
    _insert_session_record(
        database_module,
        db_path,
        "outside-job-window",
        request_count=1,
        started="2026-05-14T10:10:00+00:00",
        ended="2026-05-14T10:10:00+00:00",
        updated_at="2026-05-14T10:10:00+00:00",
    )
    _insert_session_record(
        database_module,
        db_path,
        "manual-evaluator-telemetry",
        request_count=1,
        source="manual",
        outcome="solved",
        started="2026-05-14T10:00:12+00:00",
        ended="2026-05-14T10:00:12+00:00",
        updated_at="2026-05-14T10:00:13+00:00",
    )
    with database_module.Session(database_module.get_engine(db_path)) as session:
        session.add(
            database_module.EvaluationJob(
                job_id="job-1",
                kind="session_evaluation",
                session_id="evaluated-session",
                client_source="codex",
                trigger="auto",
                status="succeeded",
                created_at="2026-05-14T09:59:59+00:00",
                started_at="2026-05-14T10:00:00+00:00",
                finished_at="2026-05-14T10:00:20+00:00",
            )
        )
        session.commit()

    classified = evaluation_worker_module.classify_local_evaluator_sessions(
        limit=10,
        db_path=db_path,
    )

    saved = database_module.get_session_evaluation(
        "evaluator-telemetry", db_path=db_path
    )
    outside = database_module.get_session_evaluation(
        "outside-job-window", db_path=db_path
    )
    manual = database_module.get_session_evaluation(
        "manual-evaluator-telemetry", db_path=db_path
    )
    assert classified == 1
    assert saved is not None
    assert saved["outcome"] == "no_op"
    assert outside is None
    assert manual is not None
    assert manual["outcome"] == "solved"


def test_run_evaluation_worker_once_respects_max_concurrent_jobs(
    evaluation_worker_module,
    database_module,
    isolated_home,
    monkeypatch,
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    _insert_session_record(database_module, db_path, "s1", client_source="codex")
    _insert_session_record(database_module, db_path, "s2", client_source="codex")
    database_module.create_session_evaluation_job(
        session_id="s1", client_source="codex", trigger="manual", db_path=db_path
    )
    database_module.create_session_evaluation_job(
        session_id="s2", client_source="codex", trigger="manual", db_path=db_path
    )
    created = []
    to_thread_calls = []

    async def fake_to_thread(fn, *args, **kwargs):
        to_thread_calls.append(fn.__name__)
        if fn.__name__ == "_claim_evaluation_jobs":
            return fn(*args, **kwargs)
        raise AssertionError("Evaluator coroutine should not run in this test")

    def fake_create_task(coro):
        created.append(coro)
        coro.close()
        return None

    monkeypatch.setattr(evaluation_worker_module.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(
        evaluation_worker_module.asyncio, "create_task", fake_create_task
    )

    started = asyncio.run(
        evaluation_worker_module.run_evaluation_worker_once(
            config=evaluation_worker_module.EvaluationWorkerConfig(
                auto_enabled=False,
                max_concurrent_jobs=1,
            ),
            db_path=db_path,
        )
    )

    assert started == 1
    assert len(created) == 1
    assert to_thread_calls == ["_claim_evaluation_jobs"]
    assert database_module.count_running_evaluation_jobs(db_path=db_path) == 1


def test_run_evaluation_worker_continues_after_failed_tick(
    evaluation_worker_module,
    monkeypatch,
    caplog,
):
    calls = []
    stop_event = asyncio.Event()

    async def fake_run_once(**kwargs):
        calls.append(kwargs["config"])
        if len(calls) == 1:
            raise RuntimeError("database temporarily unavailable")
        stop_event.set()
        return 0

    monkeypatch.setattr(
        evaluation_worker_module,
        "run_evaluation_worker_once",
        fake_run_once,
    )

    asyncio.run(
        evaluation_worker_module.run_evaluation_worker(
            stop_event=stop_event,
            config=evaluation_worker_module.EvaluationWorkerConfig(
                idle_sleep_cap_seconds=1
            ),
        )
    )

    assert len(calls) == 2
    assert "Evaluation worker tick failed" in caplog.text


def test_run_evaluation_worker_continues_after_timed_out_tick(
    evaluation_worker_module,
    monkeypatch,
    caplog,
):
    calls = []
    release_first_tick = asyncio.Event()
    stop_event = asyncio.Event()

    async def fake_run_once(**kwargs):
        calls.append(kwargs["config"])
        if len(calls) == 1:
            await release_first_tick.wait()
            return 0
        stop_event.set()
        return 0

    monkeypatch.setattr(
        evaluation_worker_module,
        "run_evaluation_worker_once",
        fake_run_once,
    )

    async def exercise_worker():
        async def release_after_timeout():
            await asyncio.sleep(1.2)
            release_first_tick.set()

        asyncio.create_task(release_after_timeout())
        await evaluation_worker_module.run_evaluation_worker(
            stop_event=stop_event,
            config=evaluation_worker_module.EvaluationWorkerConfig(
                idle_sleep_cap_seconds=1,
                worker_tick_timeout_seconds=1,
            ),
        )

    asyncio.run(exercise_worker())

    assert len(calls) == 2
    assert "Evaluation worker tick timed out" in caplog.text
