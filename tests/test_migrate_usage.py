from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import sqlite3


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrate_usage.py"


def _seed(
    db_path: Path,
    ts: str,
    prompt_tokens: int,
    *,
    base_url: str | None = None,
    provider_name: str = "test-provider",
    source: str = "proxy_config",
) -> None:
    base_url_line = ""
    base_url_id_arg = "None"
    if base_url is not None:
        base_url_line = f"""
base_url_id = get_or_create_base_url(
    "{base_url}",
    db_path=db_path,
    provider_name="{provider_name}",
    source="{source}",
)
"""
        base_url_id_arg = "base_url_id"

    script = f"""
from src.database import get_or_create_base_url, init_db, log_usage

db_path = r"{db_path}"
init_db(db_path)
{base_url_line}
log_usage(
    db_path,
    ts="{ts}",
    provider="test-provider",
    model="test-model",
    endpoint="/v1/responses",
    prompt_tokens={prompt_tokens},
    completion_tokens=5,
    reasoning_tokens=1,
    cached_tokens=2,
    total_tokens={prompt_tokens + 5},
    latency_ms=123,
    ttft_ms=None,
    tool_tokens=None,
    cache_creation_tokens=None,
    status=200,
    base_url_id={base_url_id_arg},
)
"""
    subprocess.run([sys.executable, "-c", script], check=True, cwd=SCRIPT.parents[1])


def test_migrate_usage_copies_rows_between_sqlite_databases(tmp_path: Path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"
    _seed(source_db, "2026-04-19T00:00:00+00:00", 10)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-url",
            f"sqlite:///{source_db}",
            "--target-url",
            f"sqlite:///{target_db}",
        ],
        cwd=SCRIPT.parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Migrated 1 rows" in result.stdout


def test_migrate_usage_rejects_nonempty_target_without_skip(tmp_path: Path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"
    _seed(source_db, "2026-04-19T00:00:00+00:00", 10)
    _seed(target_db, "2026-04-19T01:00:00+00:00", 20)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-url",
            f"sqlite:///{source_db}",
            "--target-url",
            f"sqlite:///{target_db}",
            "--allow-nonempty-target",
        ],
        cwd=SCRIPT.parents[1],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Re-run with --skip-existing" in result.stderr


def test_migrate_usage_skips_existing_rows_in_nonempty_target(tmp_path: Path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"

    _seed(source_db, "2026-04-19T00:00:00+00:00", 10)
    _seed(source_db, "2026-04-19T02:00:00+00:00", 30)
    _seed(target_db, "2026-04-19T01:00:00+00:00", 20)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-url",
            f"sqlite:///{source_db}",
            "--target-url",
            f"sqlite:///{target_db}",
            "--allow-nonempty-target",
            "--skip-existing",
        ],
        cwd=SCRIPT.parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Migrated 1 rows" in result.stdout
    assert "Skipped 1 rows already present in the target." in result.stdout


def test_migrate_usage_remaps_base_url_ids_for_nonempty_target(tmp_path: Path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"

    _seed(
        source_db,
        "2026-04-19T00:00:00+00:00",
        10,
        base_url="https://source.example/v1",
    )
    _seed(
        source_db,
        "2026-04-19T02:00:00+00:00",
        30,
        base_url="https://source.example/v1",
    )
    _seed(
        target_db,
        "2026-04-19T01:00:00+00:00",
        20,
        base_url="https://existing.example/v1",
    )

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-url",
            f"sqlite:///{source_db}",
            "--target-url",
            f"sqlite:///{target_db}",
            "--allow-nonempty-target",
            "--skip-existing",
        ],
        cwd=SCRIPT.parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    connection = sqlite3.connect(target_db)
    usage_row = connection.execute(
        "SELECT id, base_url_id FROM usage WHERE id = 2"
    ).fetchone()
    base_url_row = connection.execute(
        "SELECT id, base_url FROM base_urls WHERE id = ?",
        (usage_row[1],),
    ).fetchone()
    base_url_rows = connection.execute(
        "SELECT id, base_url FROM base_urls ORDER BY id"
    ).fetchall()
    connection.close()

    assert usage_row == (2, 2)
    assert base_url_row == (2, "https://source.example/v1")
    assert base_url_rows == [
        (1, "https://existing.example/v1"),
        (2, "https://source.example/v1"),
    ]
