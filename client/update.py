"""``tokenage update`` — update the client.

The client is a source snapshot under ``$TOKENAGE_HOME/versions``, so it updates
by asking its server for the installer and letting that install a new snapshot.
Updating the server clone is ``tokenage server update``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from client.paths import client_commit, client_root, client_version

INSTALLER_PATH = "/install.sh"


def _bin_dir() -> Path:
    return Path(os.environ.get("TOKENAGE_BIN_DIR", "~/.local/bin")).expanduser()


def _run(command: list[str], env: dict[str, str] | None = None) -> int:
    return subprocess.run(command, env=env).returncode


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
            "tokenage: cannot update the client without a server; run "
            "tokenage login --server <url> first.",
            file=sys.stderr,
        )
        return 1
    with tempfile.TemporaryDirectory(prefix="tokenage-update-") as work:
        installer = Path(work) / "install.sh"
        curl = shutil.which("curl")
        if curl is None:
            print("tokenage: curl is required to update the client.", file=sys.stderr)
            return 1
        if _run([curl, "-fsSL", f"{server_url}{INSTALLER_PATH}", "-o", str(installer)]):
            print(
                f"tokenage: could not download the installer from {server_url}.",
                file=sys.stderr,
            )
            return 1
        installer.chmod(0o700)
        env = os.environ.copy()
        env["TOKENAGE_SERVER"] = str(server_url)
        env["TOKENAGE_BIN_DIR"] = str(_bin_dir())
        env["TOKENAGE_SKIP_LOGIN"] = "1"
        if _run(["sh", str(installer)], env=env):
            print("tokenage: client update failed.", file=sys.stderr)
            return 1
    return 0


def run_update(*, check: bool, dry_run: bool) -> int:
    if client_root() is None:
        print(
            "tokenage: no client snapshot to update on this machine "
            "(the server updates with tokenage server update)."
        )
        return 0

    print("  ▶ Installed client")
    print(
        f"  Installed client  {client_version()}  "
        f"(commit {client_commit() or 'unknown'})"
    )
    if check:
        print(
            "  Client update availability cannot be checked: the hosted "
            "installer does not publish a client version."
        )
        return 0
    if dry_run:
        print(f"  sh <{INSTALLER_PATH} from the signed-in server>")
        return 0

    print("  ▶ Updating client")
    if update_client():
        return 1
    print("  ✓ client updated")
    print("  ✓ credentials preserved")
    return 0
