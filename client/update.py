"""``llm-tracker update`` — update whichever components are installed.

The server component is a git clone, so it updates with a fast-forward pull and a
bootstrap. The client component is a source snapshot under
``$LLM_TRACKER_HOME/versions``, so it updates by asking its server for the
installer and letting that install a new snapshot. Both paths reuse the code
that is already tested rather than reimplementing it here.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from client.paths import client_commit, client_root, client_version, server_root

INSTALLER_PATH = "/install.sh"


def _server_version(root: Path) -> str | None:
    try:
        return (root / "VERSION").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _bin_dir() -> Path:
    return Path(os.environ.get("LLM_TRACKER_BIN_DIR", "~/.local/bin")).expanduser()


def _run(command: list[str], env: dict[str, str] | None = None) -> int:
    return subprocess.run(command, env=env).returncode


def update_server(*, check: bool, dry_run: bool) -> int:
    root = server_root()
    if root is None:
        print("llm-tracker: the server component is not installed on this machine.")
        return 0
    script = root / "scripts" / "update.sh"
    if not script.is_file():
        print(f"llm-tracker: update script not found: {script}", file=sys.stderr)
        return 1
    command = ["bash", str(script)]
    if check:
        command.append("--check")
    elif dry_run:
        command.append("--dry-run")
    return _run(command)


def update_client() -> int:
    """Install the newest client snapshot without starting a new login."""
    from client.auth import load_credentials, normalize_server_url

    raw = (load_credentials() or {}).get("server_url")
    try:
        server_url = normalize_server_url(raw) if isinstance(raw, str) and raw else None
    except ValueError:
        server_url = None
    if not server_url:
        print(
            "llm-tracker: cannot update the client without a server; run "
            "llm-tracker login --server <url> first.",
            file=sys.stderr,
        )
        return 1
    with tempfile.TemporaryDirectory(prefix="llm-tracker-update-") as work:
        installer = Path(work) / "install.sh"
        curl = shutil.which("curl")
        if curl is None:
            print(
                "llm-tracker: curl is required to update the client.", file=sys.stderr
            )
            return 1
        if _run([curl, "-fsSL", f"{server_url}{INSTALLER_PATH}", "-o", str(installer)]):
            print(
                f"llm-tracker: could not download the installer from {server_url}.",
                file=sys.stderr,
            )
            return 1
        installer.chmod(0o700)
        env = os.environ.copy()
        env["LLM_TRACKER_SERVER"] = str(server_url)
        env["LLM_TRACKER_BIN_DIR"] = str(_bin_dir())
        env["LLM_TRACKER_SKIP_LOGIN"] = "1"
        if _run(["sh", str(installer)], env=env):
            print("llm-tracker: client update failed.", file=sys.stderr)
            return 1
    return 0


def run_update(*, check: bool, dry_run: bool, scope: str) -> int:
    if scope not in ("all", "client", "server"):
        print("llm-tracker: --scope must be all, client or server.", file=sys.stderr)
        return 2

    root = server_root()
    snapshot = client_root()
    has_server = root is not None and scope in ("all", "server")
    has_client = snapshot is not None and scope in ("all", "client")

    print("  ▶ Installed components")
    if has_server and root is not None:
        print(f"  Installed server  {_server_version(root) or 'unknown'}  ({root})")
    if has_client:
        print(
            f"  Installed client  {client_version()}  "
            f"(commit {client_commit() or 'unknown'})"
        )
    if not has_server and not has_client:
        print("llm-tracker: nothing to update on this machine.")
        return 0

    if check:
        print("")
        result = 0
        if has_server:
            result = update_server(check=True, dry_run=False)
        if has_client:
            print(
                "  Client update availability cannot be checked: the hosted "
                "installer does not publish a client version."
            )
        return result

    if dry_run:
        print("\n  Planned commands:")
        if has_server and root is not None:
            print(f"  bash {root / 'scripts' / 'update.sh'}")
        if has_client:
            print(f"  sh <{INSTALLER_PATH} from the signed-in server>")
        return 0

    print("")
    if has_client:
        print("  ▶ Updating client")
        if update_client():
            return 1
        print("  ✓ client updated")
        print("  ✓ credentials preserved")
    if has_server and root is not None:
        print("  ▶ Updating server")
        if update_server(check=False, dry_run=False):
            return 1

    print("")
    print("  ✓ llm-tracker is up to date")
    return 0
