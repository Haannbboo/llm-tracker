"""bootstrap.sh: install deps, link the launcher, then hand off to Python."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "src" / "scripts" / "bootstrap.sh"


def _run(tmp_path: Path, home: Path):
    repo = tmp_path / "repo"
    (repo / "src" / "scripts").mkdir(parents=True)
    (repo / "client" / "bin").mkdir(parents=True)
    shutil.copy2(SCRIPT, repo / "src" / "scripts" / "bootstrap.sh")
    (repo / "src" / "pyproject.toml").write_text("[project]\n")
    (repo / "client" / "bin" / "tokenage").write_text("#!/bin/sh\n")

    log = tmp_path / "log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Fake uv: `uv venv ... <dir>` makes a python that logs how it was exec'd.
    uv = bin_dir / "uv"
    uv.write_text(
        '#!/bin/sh\necho "uv $*" >> "$LOG"\n'
        'if [ "$1" = venv ]; then\n'
        '  d="$(eval echo \\${$#})"; mkdir -p "$d/bin"\n'
        '  printf \'#!/bin/sh\\necho "python $*" >> "$LOG"\\n\' > "$d/bin/python"\n'
        '  chmod +x "$d/bin/python"\n'
        "fi\n"
    )
    uv.chmod(0o755)
    env = {
        **os.environ,
        "HOME": str(home),
        "LOG": str(log),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "PYTHONPATH": "",
    }
    env.pop("TOKENAGE_BIN_DIR", None)
    result = subprocess.run(
        ["bash", str(repo / "src" / "scripts" / "bootstrap.sh"), "--x"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    return result, log.read_text() if log.exists() else "", repo


def test_bootstrap_installs_links_the_launcher_and_execs_python(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    result, log, repo = _run(tmp_path, home)

    assert result.returncode == 0, result.stderr
    assert f"-r {repo}/src/pyproject.toml --extra dev" in log
    assert "python -m src.cli bootstrap --x" in log
    assert (home / ".local" / "bin" / "tokenage").resolve() == (
        repo / "client" / "bin" / "tokenage"
    )


def test_bootstrap_leaves_an_existing_launcher_alone(tmp_path):
    home = tmp_path / "home"
    launcher = home / ".local" / "bin" / "tokenage"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("# tokenage launcher\n")

    result, _, _ = _run(tmp_path, home)

    assert result.returncode == 0, result.stderr
    assert not launcher.is_symlink()
