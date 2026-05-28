from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_CLEAN_GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "PRE_COMMIT_ALLOW_NO_CONFIG": "1",
}


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in the given repo."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=check,
        env=_CLEAN_GIT_ENV,
    )


def _make_update_repo(
    tmp_path: Path,
    *,
    stub_bootstrap: str = "exit 0",
    stub_restart: str = "exit 0",
) -> tuple[Path, Path]:
    """Create a bare remote and a cloned local repo with update.sh."""
    bare = tmp_path / "remote.git"
    local = tmp_path / "local"

    # Create bare remote
    subprocess.run(
        ["git", "init", "--bare", str(bare)],
        check=True,
        capture_output=True,
        text=True,
        env=_CLEAN_GIT_ENV,
    )

    # Clone to local
    subprocess.run(
        ["git", "clone", str(bare), str(local)],
        check=True,
        capture_output=True,
        text=True,
        env=_CLEAN_GIT_ENV,
    )

    # Copy scripts into local repo
    repo_root = Path(__file__).resolve().parents[2]
    scripts_dir = local / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    lib_dir = scripts_dir / "lib"
    lib_dir.mkdir(exist_ok=True)

    shutil.copy2(repo_root / "scripts" / "update.sh", scripts_dir / "update.sh")
    (scripts_dir / "update.sh").chmod(0o755)
    shutil.copy2(repo_root / "scripts" / "lib" / "terminal.sh", lib_dir / "terminal.sh")

    # Stub bootstrap.sh and restart.sh
    for name, body in [("bootstrap.sh", stub_bootstrap), ("restart.sh", stub_restart)]:
        (scripts_dir / name).write_text(
            f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8"
        )
        (scripts_dir / name).chmod(0o755)

    # Initial commit and push
    (local / "README.md").write_text("init\n", encoding="utf-8")
    _git(local, "add", ".")
    _git(local, "commit", "-m", "init")
    _git(local, "push", "origin", "main")

    return local, bare


def _add_remote_commit(bare: Path, local: Path, filename: str = "new.txt") -> str:
    """Add a commit to the remote via a second clone, return the commit hash."""
    helper = local.parent / "helper"
    subprocess.run(
        ["git", "clone", str(bare), str(helper)],
        check=True,
        capture_output=True,
        text=True,
        env=_CLEAN_GIT_ENV,
    )
    (helper / filename).write_text("upstream change\n", encoding="utf-8")
    _git(helper, "add", ".")
    _git(helper, "commit", "-m", f"add {filename}")
    _git(helper, "push", "origin", "main")
    commit = _git(helper, "rev-parse", "HEAD").stdout.strip()
    shutil.rmtree(helper)
    return commit


def _run_update(
    local: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    env = {**_CLEAN_GIT_ENV}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["/bin/bash", str(local / "scripts" / "update.sh"), *args],
        cwd=local,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )


# ── Tests ───────────────────────────────────────────────────────────


def test_update_pulls_ff_and_runs_bootstrap_and_restart(tmp_path):
    local, bare = _make_update_repo(tmp_path)
    _add_remote_commit(bare, local)

    _git(local, "fetch", "origin")
    result = _run_update(local)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Pulling updates" in output
    assert "Bootstrap complete" in output
    assert "Servers restarted" in output
    assert "Update complete" in output


def test_update_already_up_to_date(tmp_path):
    local, _ = _make_update_repo(tmp_path)

    result = _run_update(local)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Already up to date" in output
    assert "Bootstrap" not in output


def test_update_refuses_dirty_worktree(tmp_path):
    local, bare = _make_update_repo(tmp_path)
    _add_remote_commit(bare, local)
    _git(local, "fetch", "origin")

    # Create dirty state
    (local / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")

    result = _run_update(local)

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "refused: local changes detected" in output


def test_update_refuses_detached_head(tmp_path):
    local, bare = _make_update_repo(tmp_path)
    _add_remote_commit(bare, local)
    _git(local, "fetch", "origin")

    # Detach HEAD
    _git(local, "checkout", "--detach")

    result = _run_update(local)

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "refused: detached HEAD" in output


def test_update_refuses_missing_upstream(tmp_path):
    local, bare = _make_update_repo(tmp_path)

    # Create a branch with no upstream
    _git(local, "checkout", "-b", "no-upstream")

    result = _run_update(local)

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "refused: branch 'no-upstream' has no upstream" in output


def test_update_refuses_missing_upstream_remote(tmp_path):
    local, bare = _make_update_repo(tmp_path)

    # Remove the upstream remote (origin in this case)
    _git(local, "remote", "remove", "origin", check=False)

    result = _run_update(local)

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "has no upstream" in output or "remote" in output


def test_update_refuses_non_fast_forward(tmp_path):
    local, bare = _make_update_repo(tmp_path)

    # Add a local commit (don't push)
    (local / "local.txt").write_text("local\n", encoding="utf-8")
    _git(local, "add", ".")
    _git(local, "commit", "-m", "local change")

    # Add a conflicting upstream commit
    _add_remote_commit(bare, local, "upstream.txt")

    # Fetch to see divergence
    _git(local, "fetch", "origin")

    result = _run_update(local)

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "refused: upstream cannot be fast-forwarded" in output


def test_update_reports_bootstrap_failure(tmp_path):
    local, bare = _make_update_repo(
        tmp_path,
        stub_bootstrap="echo 'bootstrap failed' >&2; exit 1",
    )
    _add_remote_commit(bare, local)
    _git(local, "fetch", "origin")

    result = _run_update(local)

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "bootstrap failed" in output
    assert "Source update succeeded, but bootstrap failed" in output


def test_update_reports_restart_failure(tmp_path):
    local, bare = _make_update_repo(
        tmp_path,
        stub_restart="echo 'restart failed' >&2; exit 1",
    )
    _add_remote_commit(bare, local)
    _git(local, "fetch", "origin")

    result = _run_update(local)

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "restart failed" in output
    assert "Bootstrap succeeded, but server restart failed" in output


def test_update_check_mode(tmp_path):
    local, bare = _make_update_repo(tmp_path)
    _add_remote_commit(bare, local)
    _git(local, "fetch", "origin")

    result = _run_update(local, "--check")

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Branch:" in output
    assert "Ahead:" in output
    assert "Behind:" in output
    # Should not have pulled or bootstrapped
    assert "Pulling" not in output
    assert "Bootstrap" not in output


def test_update_dry_run_mode(tmp_path):
    local, bare = _make_update_repo(tmp_path)
    _add_remote_commit(bare, local)
    _git(local, "fetch", "origin")

    result = _run_update(local, "--dry-run")

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Planned commands:" in output
    assert "pull --ff-only" in output
    assert "bootstrap.sh" in output
    assert "restart.sh" in output
    # Should not have pulled or bootstrapped
    assert "Pulling" not in output
    assert "Bootstrap" not in output


def test_update_fetches_from_correct_remote(tmp_path):
    """Regression: update should fetch the actual upstream remote, not hardcoded origin."""
    bare = tmp_path / "upstream.git"
    local = tmp_path / "local"

    subprocess.run(
        ["git", "init", "--bare", str(bare)],
        check=True,
        capture_output=True,
        text=True,
        env=_CLEAN_GIT_ENV,
    )

    # Clone with custom remote name "upstream" instead of "origin"
    subprocess.run(
        ["git", "clone", "--origin", "upstream", str(bare), str(local)],
        check=True,
        capture_output=True,
        text=True,
        env=_CLEAN_GIT_ENV,
    )

    # Copy scripts
    repo_root = Path(__file__).resolve().parents[2]
    scripts_dir = local / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    lib_dir = scripts_dir / "lib"
    lib_dir.mkdir(exist_ok=True)
    shutil.copy2(repo_root / "scripts" / "update.sh", scripts_dir / "update.sh")
    (scripts_dir / "update.sh").chmod(0o755)
    shutil.copy2(repo_root / "scripts" / "lib" / "terminal.sh", lib_dir / "terminal.sh")
    for name, body in [("bootstrap.sh", "exit 0"), ("restart.sh", "exit 0")]:
        (scripts_dir / name).write_text(
            f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8"
        )
        (scripts_dir / name).chmod(0o755)

    # Initial commit and push
    (local / "README.md").write_text("init\n", encoding="utf-8")
    _git(local, "add", ".")
    _git(local, "commit", "-m", "init")
    _git(local, "push", "upstream", "main")

    # Add upstream commit via helper clone
    helper = tmp_path / "helper"
    subprocess.run(
        ["git", "clone", "--origin", "upstream", str(bare), str(helper)],
        check=True,
        capture_output=True,
        text=True,
        env=_CLEAN_GIT_ENV,
    )
    (helper / "new.txt").write_text("upstream change\n", encoding="utf-8")
    _git(helper, "add", ".")
    _git(helper, "commit", "-m", "add new.txt")
    _git(helper, "push", "upstream", "main")
    shutil.rmtree(helper)

    result = _run_update(local)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Fetched from upstream" in output
    assert "Pulling updates" in output
    assert "Update complete" in output


def test_update_works_from_any_cwd(tmp_path):
    local, bare = _make_update_repo(tmp_path)
    _add_remote_commit(bare, local)
    _git(local, "fetch", "origin")

    # Run from a different directory
    other_dir = tmp_path / "other"
    other_dir.mkdir()

    result = subprocess.run(
        ["/bin/bash", str(local / "scripts" / "update.sh")],
        cwd=other_dir,
        env=_CLEAN_GIT_ENV,
        text=True,
        capture_output=True,
        timeout=30,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Update complete" in output
