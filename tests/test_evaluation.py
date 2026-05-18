from __future__ import annotations

import json
import subprocess

import pytest


def test_build_evaluator_command_uses_central_codex_ephemeral(evaluation_module):
    invocation = evaluation_module.build_evaluator_invocation("Transcript text")

    assert invocation.command == [
        "codex",
        "-c",
        "otel.enabled=false",
        "exec",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--ignore-rules",
        "-",
    ]
    assert "Transcript text" in invocation.stdin
    assert invocation.env["OTEL_SDK_DISABLED"] == "true"
    assert invocation.env["OTEL_LOGS_EXPORTER"] == "none"


def test_load_codex_transcript_reads_user_assistant_text_only(
    evaluation_module, isolated_home
):
    session_dir = isolated_home / ".codex" / "sessions" / "2026" / "05" / "14"
    session_dir.mkdir(parents=True)
    session_path = session_dir / "rollout-2026-05-14T00-00-00-sess-codex.jsonl"
    records = [
        {"type": "session_meta", "payload": {"id": "sess-codex"}},
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "Developer rules"}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Fix the chart"}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "shell",
                "arguments": "secret tool input",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Chart fixed"}],
            },
        },
    ]
    session_path.write_text(
        "\n".join(json.dumps(record) for record in records), encoding="utf-8"
    )

    transcript = evaluation_module.load_session_transcript("codex", "sess-codex")

    assert "USER:\nFix the chart" in transcript
    assert "ASSISTANT:\nChart fixed" in transcript
    assert "Developer rules" not in transcript
    assert "secret tool input" not in transcript


def test_load_claude_transcript_skips_tool_results(evaluation_module, isolated_home):
    session_dir = isolated_home / ".claude" / "projects" / "-project"
    session_dir.mkdir(parents=True)
    session_path = session_dir / "sess-claude.jsonl"
    records = [
        {
            "type": "user",
            "uuid": "u1",
            "message": {"role": "user", "content": "Fix the backend"},
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "message": {
                "id": "msg-1",
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I updated the backend"},
                    {"type": "tool_use", "name": "Bash", "input": "secret"},
                ],
            },
        },
        {
            "type": "user",
            "uuid": "u2",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "content": "large command output",
                    }
                ],
            },
        },
    ]
    session_path.write_text(
        "\n".join(json.dumps(record) for record in records), encoding="utf-8"
    )

    transcript = evaluation_module.load_session_transcript("claude-code", "sess-claude")

    assert "USER:\nFix the backend" in transcript
    assert "ASSISTANT:\nI updated the backend" in transcript
    assert "large command output" not in transcript
    assert "secret" not in transcript


def test_load_gemini_transcript_reads_logs_for_session(
    evaluation_module, isolated_home
):
    gemini_dir = isolated_home / ".gemini" / "tmp" / "llm-tracker"
    gemini_dir.mkdir(parents=True)
    logs = [
        {
            "sessionId": "other-session",
            "messageId": 0,
            "type": "user",
            "message": "Ignore me",
        },
        {
            "sessionId": "sess-gemini",
            "messageId": 0,
            "type": "user",
            "message": "Diagnose dashboard",
        },
        {
            "sessionId": "sess-gemini",
            "messageId": 1,
            "type": "assistant",
            "message": "Dashboard diagnosis complete",
        },
    ]
    (gemini_dir / "logs.json").write_text(json.dumps(logs), encoding="utf-8")

    transcript = evaluation_module.load_session_transcript("gemini-cli", "sess-gemini")

    assert "USER:\nDiagnose dashboard" in transcript
    assert "ASSISTANT:\nDashboard diagnosis complete" in transcript
    assert "Ignore me" not in transcript


def test_has_local_session_transcript_uses_path_or_metadata(
    evaluation_module, isolated_home
):
    codex_dir = isolated_home / ".codex" / "sessions" / "2026" / "05" / "14"
    codex_dir.mkdir(parents=True)
    (codex_dir / "rollout-2026-05-14T00-00-00-sess-codex.jsonl").write_text(
        "", encoding="utf-8"
    )

    claude_dir = isolated_home / ".claude" / "projects" / "-tmp-project"
    claude_dir.mkdir(parents=True)
    (claude_dir / "sess-claude.jsonl").write_text("", encoding="utf-8")

    gemini_dir = isolated_home / ".gemini" / "tmp" / "project" / "chats"
    gemini_dir.mkdir(parents=True)
    (gemini_dir / "session-2026-05-14T00-00-abcd.jsonl").write_text(
        '{"sessionId":"sess-gemini","kind":"main"}\n'
        '{"sessionId":"sess-gemini","type":"user","message":"Hello"}\n',
        encoding="utf-8",
    )
    (gemini_dir / "session-2026-05-14T00-00-other.jsonl").write_text(
        '{"sessionId":"other"}\n{"sessionId":"sess-hidden"}\n',
        encoding="utf-8",
    )

    assert evaluation_module.has_local_session_transcript("codex", "sess-codex")
    assert evaluation_module.has_local_session_transcript("claude-code", "sess-claude")
    assert evaluation_module.has_local_session_transcript("gemini-cli", "sess-gemini")
    assert not evaluation_module.has_local_session_transcript(
        "gemini-cli", "sess-hidden"
    )
    assert not evaluation_module.has_local_session_transcript(
        "proxy-client", "sess-any"
    )


def test_evaluation_prompt_treats_memory_tasks_as_no_op(evaluation_module):
    prompt = evaluation_module.EVALUATION_PROMPT

    assert "claude-mem-context" in prompt
    assert "background context, not the task being evaluated" in prompt
    assert 'return outcome "no_op"' in prompt


def test_detects_claude_mem_observer_session(evaluation_module, isolated_home):
    session_dir = (
        isolated_home
        / ".claude"
        / "projects"
        / "-Users-hanbo--claude-mem-observer-sessions"
    )
    session_dir.mkdir(parents=True)
    (session_dir / "sess-mem.jsonl").write_text("", encoding="utf-8")

    assert evaluation_module.is_claude_mem_observer_session("sess-mem") is True
    assert evaluation_module.is_claude_mem_observer_session("sess-normal") is False


def test_parse_evaluation_output_rejects_invalid_outcome(evaluation_module):
    with pytest.raises(ValueError, match="Invalid outcome"):
        evaluation_module.parse_evaluation_output(
            '{"outcome":"great","task_title":null,"summary":null,"confidence":0.8,"evidence":[],"failure_reason":null}'
        )


def test_parse_evaluation_output_accepts_json_with_cli_noise(evaluation_module):
    parsed = evaluation_module.parse_evaluation_output(
        """
The 'metricReader' option is deprecated. Please use 'metricReaders' instead.
{
  "task_title": "Update frontend regression tests",
  "summary": "Updated and committed frontend tests.",
  "outcome": "solved",
  "confidence": 1.0,
  "evidence": ["Verified tests passed"],
  "failure_reason": null
}
"""
    )

    assert parsed["outcome"] == "solved"
    assert parsed["task_title"] == "Update frontend regression tests"
    assert parsed["evidence"] == ["Verified tests passed"]


@pytest.mark.parametrize("confidence", [True, -0.1, 1.1, 82])
def test_parse_evaluation_output_rejects_invalid_confidence(
    evaluation_module, confidence
):
    with pytest.raises(ValueError, match="Evaluation confidence"):
        evaluation_module.parse_evaluation_output(
            f'{{"task_title":null,"summary":null,"outcome":"solved","confidence":{str(confidence).lower()},"evidence":[],"failure_reason":null}}'
        )


def test_run_session_evaluation_job_sanitizes_agent_failure_errors(
    evaluation_module,
    database_module,
    isolated_home,
    monkeypatch,
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    with database_module.Session(database_module.get_engine(db_path)) as session:
        session.add(
            database_module.SessionRecord(
                session_id="sess-secret",
                client_source="codex",
                started="2026-05-11T10:00:00+00:00",
                ended="2026-05-11T10:30:00+00:00",
                updated_at="2026-05-11T10:30:00+00:00",
            )
        )
        session.commit()

    session_dir = isolated_home / ".codex" / "sessions" / "2026" / "05" / "14"
    session_dir.mkdir(parents=True)
    (session_dir / "rollout-sess-secret.jsonl").write_text(
        json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Secret task"}],
                },
            }
        ),
        encoding="utf-8",
    )

    job = database_module.create_session_evaluation_job(
        session_id="sess-secret",
        client_source="codex",
        db_path=db_path,
    )

    def fake_run(**kwargs):
        return subprocess.CompletedProcess(
            args=kwargs["args"],
            returncode=1,
            stdout="",
            stderr="/Users/hanbo/private/token.txt failed with api_key=secret",
        )

    monkeypatch.setattr(evaluation_module.subprocess, "run", fake_run)

    evaluation_module.run_session_evaluation_job(job["job_id"], db_path=db_path)

    polled = database_module.get_evaluation_job(job["job_id"], db_path=db_path)
    assert polled is not None
    assert polled["status"] == "failed"
    assert polled["error"] == "Evaluation agent failed"


def test_start_session_evaluation_job_rejects_manual_evaluation(
    evaluation_module,
    database_module,
    isolated_home,
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    with database_module.Session(database_module.get_engine(db_path)) as session:
        session.add(
            database_module.SessionRecord(
                session_id="manual-protected",
                client_source="codex",
                started="2026-05-11T10:00:00+00:00",
                ended="2026-05-11T10:30:00+00:00",
                updated_at="2026-05-11T10:30:00+00:00",
                source="manual",
                outcome="solved",
                evaluated_at="2026-05-11T10:35:00+00:00",
            )
        )
        session.commit()

    with pytest.raises(ValueError, match="Manual evaluation exists"):
        evaluation_module.start_session_evaluation_job(
            "manual-protected",
            db_path=db_path,
        )


def test_start_session_evaluation_job_queues_without_running(
    evaluation_module,
    database_module,
    isolated_home,
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    with database_module.Session(database_module.get_engine(db_path)) as session:
        session.add(
            database_module.SessionRecord(
                session_id="sess-queued",
                client_source="codex",
                started="2026-05-11T10:00:00+00:00",
                ended="2026-05-11T10:30:00+00:00",
                updated_at="2026-05-11T10:30:00+00:00",
            )
        )
        session.commit()

    job = evaluation_module.start_session_evaluation_job(
        "sess-queued",
        db_path=db_path,
    )

    assert job["status"] == "queued"
    assert job["trigger"] == "manual"
    assert database_module.count_running_evaluation_jobs(db_path=db_path) == 0


def test_start_session_evaluation_job_promotes_queued_auto_job(
    evaluation_module,
    database_module,
    isolated_home,
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    with database_module.Session(database_module.get_engine(db_path)) as session:
        session.add(
            database_module.SessionRecord(
                session_id="sess-promote",
                client_source="codex",
                started="2026-05-11T10:00:00+00:00",
                ended="2026-05-11T10:30:00+00:00",
                updated_at="2026-05-11T10:30:00+00:00",
            )
        )
        session.commit()

    auto_job = database_module.create_session_evaluation_job(
        session_id="sess-promote",
        client_source="codex",
        trigger="auto",
        db_path=db_path,
    )

    manual_job = evaluation_module.start_session_evaluation_job(
        "sess-promote",
        db_path=db_path,
    )

    assert manual_job["job_id"] == auto_job["job_id"]
    assert manual_job["trigger"] == "manual"
    assert (
        database_module.get_evaluation_job(
            auto_job["job_id"],
            db_path=db_path,
        )["trigger"]
        == "manual"
    )


def test_run_session_evaluation_job_saves_llm_evaluation_before_success(
    evaluation_module,
    database_module,
    isolated_home,
    monkeypatch,
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    with database_module.Session(database_module.get_engine(db_path)) as session:
        session.add(
            database_module.SessionRecord(
                session_id="sess-llm",
                client_source="codex",
                started="2026-05-11T10:00:00+00:00",
                ended="2026-05-11T10:30:00+00:00",
                updated_at="2026-05-11T10:30:00+00:00",
            )
        )
        session.commit()

    job = database_module.create_session_evaluation_job(
        session_id="sess-llm",
        client_source="codex",
        db_path=db_path,
    )

    session_dir = isolated_home / ".codex" / "sessions" / "2026" / "05" / "14"
    session_dir.mkdir(parents=True)
    (session_dir / "rollout-sess-llm.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": "Fix dashboard"}
                            ],
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Completed the requested dashboard fix.",
                                }
                            ],
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    def fake_run(**kwargs):
        assert kwargs["args"] == [
            "codex",
            "-c",
            "otel.enabled=false",
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ignore-rules",
            "-",
        ]
        assert "Return ONLY valid JSON" in kwargs["input"]
        assert "USER:\nFix dashboard" in kwargs["input"]
        assert "ASSISTANT:\nCompleted the requested dashboard fix." in kwargs["input"]
        assert kwargs["env"]["OTEL_SDK_DISABLED"] == "true"
        return subprocess.CompletedProcess(
            args=kwargs["args"],
            returncode=0,
            stdout='{"task_title":"Fix dashboard","summary":"Completed the requested dashboard fix.","outcome":"solved","confidence":0.82,"evidence":["Final response said tests passed"],"failure_reason":null}',
            stderr="",
        )

    monkeypatch.setattr(evaluation_module.subprocess, "run", fake_run)

    evaluation_module.run_session_evaluation_job(job["job_id"], db_path=db_path)

    saved = database_module.get_session_evaluation("sess-llm", db_path=db_path)
    assert saved is not None
    assert saved["outcome"] == "solved"
    assert saved["source"] == "llm"
    assert saved["confidence"] == pytest.approx(0.82)
    assert saved["task_title"] == "Fix dashboard"

    polled = database_module.get_evaluation_job(job["job_id"], db_path=db_path)
    assert polled is not None
    assert polled["status"] == "succeeded"
    assert polled["error"] is None


def test_summarize_session_with_llm_marks_evaluator_session_no_op(
    evaluation_module,
    database_module,
    isolated_home,
    monkeypatch,
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    with database_module.Session(database_module.get_engine(db_path)) as session:
        session.add(
            database_module.SessionRecord(
                session_id="sess-evaluator",
                client_source="codex",
                started="2026-05-11T10:00:00+00:00",
                ended="2026-05-11T10:30:00+00:00",
                updated_at="2026-05-11T10:30:00+00:00",
            )
        )
        session.commit()

    session_dir = isolated_home / ".codex" / "sessions" / "2026" / "05" / "14"
    session_dir.mkdir(parents=True)
    (session_dir / "rollout-sess-evaluator.jsonl").write_text(
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

    def fail_if_called(**kwargs):
        raise AssertionError("Evaluator sessions should not invoke another evaluator")

    monkeypatch.setattr(evaluation_module.subprocess, "run", fail_if_called)

    result = evaluation_module.summarize_session_with_llm(
        "sess-evaluator",
        db_path=db_path,
    )

    saved = database_module.get_session_evaluation("sess-evaluator", db_path=db_path)
    assert result["outcome"] == "no_op"
    assert result["task_title"] == "LLM evaluation session"
    assert saved is not None
    assert saved["outcome"] == "no_op"
    assert saved["source"] == "llm"


def test_execute_session_evaluation_job_does_not_overwrite_later_manual_evaluation(
    evaluation_module,
    database_module,
    isolated_home,
    monkeypatch,
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    with database_module.Session(database_module.get_engine(db_path)) as session:
        session.add(
            database_module.SessionRecord(
                session_id="sess-manual-race",
                client_source="codex",
                started="2026-05-11T10:00:00+00:00",
                ended="2026-05-11T10:30:00+00:00",
                updated_at="2026-05-11T10:30:00+00:00",
            )
        )
        session.commit()

    session_dir = isolated_home / ".codex" / "sessions" / "2026" / "05" / "14"
    session_dir.mkdir(parents=True)
    (session_dir / "rollout-sess-manual-race.jsonl").write_text(
        json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Fix dashboard"}],
                },
            }
        ),
        encoding="utf-8",
    )
    job = database_module.create_session_evaluation_job(
        session_id="sess-manual-race",
        client_source="codex",
        trigger="auto",
        db_path=db_path,
    )
    database_module.claim_next_evaluation_job(db_path=db_path)
    database_module.upsert_session_evaluation(
        session_id="sess-manual-race",
        outcome="failed",
        source="manual",
        evidence=["User marked outcome manually"],
        db_path=db_path,
    )

    def fake_run(**kwargs):
        return subprocess.CompletedProcess(
            args=kwargs["args"],
            returncode=0,
            stdout='{"task_title":"Fix dashboard","summary":"Done","outcome":"solved","confidence":0.9,"evidence":["LLM result"],"failure_reason":null}',
            stderr="",
        )

    monkeypatch.setattr(evaluation_module.subprocess, "run", fake_run)

    evaluation_module.execute_session_evaluation_job(job["job_id"], db_path=db_path)

    saved = database_module.get_session_evaluation(
        "sess-manual-race",
        db_path=db_path,
    )
    polled = database_module.get_evaluation_job(job["job_id"], db_path=db_path)
    assert saved is not None
    assert saved["source"] == "manual"
    assert saved["outcome"] == "failed"
    assert saved["evidence"] == ["User marked outcome manually"]
    assert polled is not None
    assert polled["status"] == "succeeded"


def test_run_session_evaluation_job_returns_when_job_cannot_start(
    evaluation_module,
    database_module,
    isolated_home,
    monkeypatch,
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    with database_module.Session(database_module.get_engine(db_path)) as session:
        session.add(
            database_module.SessionRecord(
                session_id="sess-stale-job",
                client_source="codex",
                started="2026-05-11T10:00:00+00:00",
                ended="2026-05-11T10:30:00+00:00",
                updated_at="2026-05-11T10:30:00+00:00",
            )
        )
        session.commit()

    job = database_module.create_session_evaluation_job(
        session_id="sess-stale-job",
        client_source="codex",
        db_path=db_path,
    )
    database_module.claim_next_evaluation_job(db_path=db_path)
    database_module.mark_evaluation_job_failed(
        job["job_id"],
        "Evaluation job timed out",
        db_path=db_path,
    )

    evaluator_called = False

    def fail_if_called(*args, **kwargs):
        nonlocal evaluator_called
        evaluator_called = True
        raise AssertionError("Evaluator should not run for a non-startable job")

    monkeypatch.setattr(evaluation_module, "summarize_session_with_llm", fail_if_called)

    evaluation_module.run_session_evaluation_job(job["job_id"], db_path=db_path)

    polled = database_module.get_evaluation_job(job["job_id"], db_path=db_path)
    saved = database_module.get_session_evaluation(
        "sess-stale-job",
        db_path=db_path,
    )
    assert polled is not None
    assert polled["status"] == "failed"
    assert polled["error"] == "Evaluation job timed out"
    assert saved is None
    assert evaluator_called is False


def test_run_session_evaluation_job_saves_unknown_when_transcript_missing(
    evaluation_module,
    database_module,
    isolated_home,
    monkeypatch,
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)

    with database_module.Session(database_module.get_engine(db_path)) as session:
        session.add(
            database_module.SessionRecord(
                session_id="sess-missing",
                client_source="codex",
                started="2026-05-11T10:00:00+00:00",
                ended="2026-05-11T10:30:00+00:00",
                updated_at="2026-05-11T10:30:00+00:00",
            )
        )
        session.commit()

    job = database_module.create_session_evaluation_job(
        session_id="sess-missing",
        client_source="codex",
        db_path=db_path,
    )

    def fail_if_called(**kwargs):
        raise AssertionError("Evaluator should not run without a transcript")

    monkeypatch.setattr(evaluation_module.subprocess, "run", fail_if_called)

    evaluation_module.run_session_evaluation_job(job["job_id"], db_path=db_path)

    saved = database_module.get_session_evaluation("sess-missing", db_path=db_path)
    assert saved is not None
    assert saved["outcome"] == "unknown"
    assert saved["source"] == "llm"
    assert saved["confidence"] == pytest.approx(0.0)
    assert saved["task_title"] == "Transcript unavailable"

    polled = database_module.get_evaluation_job(job["job_id"], db_path=db_path)
    assert polled is not None
    assert polled["status"] == "succeeded"
    assert polled["error"] is None


def test_run_session_evaluation_job_marks_claude_mem_sessions_no_op(
    evaluation_module,
    database_module,
    isolated_home,
    monkeypatch,
):
    db_path = str(isolated_home / "usage.db")
    database_module.init_db(db_path)
    session_dir = (
        isolated_home
        / ".claude"
        / "projects"
        / "-Users-hanbo--claude-mem-observer-sessions"
    )
    session_dir.mkdir(parents=True)
    (session_dir / "sess-mem.jsonl").write_text("", encoding="utf-8")

    with database_module.Session(database_module.get_engine(db_path)) as session:
        session.add(
            database_module.SessionRecord(
                session_id="sess-mem",
                client_source="claude-code",
                started="2026-05-11T10:00:00+00:00",
                ended="2026-05-11T10:30:00+00:00",
                updated_at="2026-05-11T10:30:00+00:00",
            )
        )
        session.commit()

    job = database_module.create_session_evaluation_job(
        session_id="sess-mem",
        client_source="claude-code",
        db_path=db_path,
    )

    def fail_if_called(**kwargs):
        raise AssertionError("Claude should not be invoked for Claude-Mem sessions")

    monkeypatch.setattr(evaluation_module.subprocess, "run", fail_if_called)

    evaluation_module.run_session_evaluation_job(job["job_id"], db_path=db_path)

    saved = database_module.get_session_evaluation("sess-mem", db_path=db_path)
    assert saved is not None
    assert saved["outcome"] == "no_op"
    assert saved["source"] == "llm"
    assert saved["confidence"] == pytest.approx(1.0)
    assert saved["task_title"] == "Claude-Mem observer session"

    polled = database_module.get_evaluation_job(job["job_id"], db_path=db_path)
    assert polled is not None
    assert polled["status"] == "succeeded"
    assert polled["error"] is None
