from __future__ import annotations

import subprocess

import pytest


def test_build_agent_command_uses_codex_ephemeral_resume(evaluation_module):
    invocation = evaluation_module.build_agent_invocation(
        client_source="codex",
        session_id="sess-1",
        prompt="Evaluate this",
    )

    assert invocation.command == [
        "codex",
        "exec",
        "resume",
        "sess-1",
        "--ephemeral",
        "-",
    ]
    assert invocation.stdin == "Evaluate this"


def test_build_agent_command_claude_uses_model(evaluation_module):
    invocation = evaluation_module.build_agent_invocation(
        client_source="claude",
        session_id="sess-1",
        prompt="Evaluate this",
        model="claude-3-opus",
    )

    assert invocation.command == [
        "claude",
        "--resume",
        "sess-1",
        "--fork-session",
        "--print",
        "--no-session-persistence",
        "--model",
        "claude-3-opus",
        "Evaluate this",
    ]


def test_build_agent_command_gemini_uses_model(evaluation_module):
    invocation = evaluation_module.build_agent_invocation(
        client_source="gemini",
        session_id="sess-1",
        prompt="Evaluate this",
        model="gemini-1.5-pro",
    )

    assert invocation.command == [
        "gemini",
        "--resume",
        "sess-1",
        "--model",
        "gemini-1.5-pro",
        "--prompt",
        "Evaluate this",
    ]


def test_build_agent_command_rejects_unsupported_source(evaluation_module):
    with pytest.raises(ValueError, match="Unsupported session source"):
        evaluation_module.build_agent_invocation(
            client_source="unknown",
            session_id="sess-1",
            prompt="Evaluate this",
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

    def fake_run(**kwargs):
        assert kwargs["args"] == [
            "codex",
            "exec",
            "resume",
            "sess-llm",
            "--ephemeral",
            "-",
        ]
        assert "Return ONLY valid JSON" in kwargs["input"]
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
