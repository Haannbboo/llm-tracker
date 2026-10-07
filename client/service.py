"""The per-device client service.

A user-level background process that owns device-local work. It is a purely
outbound component: it never accepts connections, so it runs the same whether
the server is on this machine or in the cloud. It records this machine's
client/agent status on an interval and reports it to whichever server applies:
the one this machine signed in to, or the local server component.

Managed by ``tokenage client start|stop|restart|status|run``. ``login`` and the
installer start it, and it runs on every device, with or without a server
component on the same machine.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from client.auth import save_private_object
from client.paths import client_commit, client_version, tracker_home
from client.setup import AGENT_SCRIPTS, intended_endpoint, read_agent_states

CHECK_INTERVAL_SECONDS = 60.0
START_TIMEOUT_SECONDS = 10.0
STOP_TIMEOUT_SECONDS = 10.0
REPORT_TIMEOUT_SECONDS = 10.0

logger = logging.getLogger("tokenage.client.service")


def state_path() -> Path:
    """The daemon's pid and liveness record, read directly by the CLI.

    Structure: ``{"pid": int, "started_at": int, "last_check_at": int | null,
    "last_report_at": int | null, "last_report_status": str | null}``
    (`started_at`/`last_check_at`/`last_report_at` are unix seconds). The daemon
    writes it atomically at start and on every check, and removes it on clean
    exit; a missing file or a dead pid means the service is stopped.
    """
    return tracker_home() / "run" / "client.json"


def log_path() -> Path:
    return tracker_home() / "logs" / "client.log"


def _read_state() -> dict[str, Any] | None:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _write_state(state: dict[str, Any]) -> None:
    save_private_object(state_path(), state)


def _clear_state() -> None:
    state_path().unlink(missing_ok=True)


def running_state() -> dict[str, Any] | None:
    """The daemon state while its process is alive; None otherwise."""
    state = _read_state()
    if state is None or not _pid_alive(state.get("pid")):
        return None
    return state


def service_status() -> dict[str, Any]:
    state = running_state()
    status: dict[str, Any] = {
        "running": state is not None,
        "log": str(log_path()),
        "client_version": client_version(),
        "client_commit": client_commit(),
    }
    if state is not None:
        status["pid"] = state.get("pid")
        status["started_at"] = state.get("started_at")
        status["last_check_at"] = state.get("last_check_at")
        status["last_report_at"] = state.get("last_report_at")
        status["last_report_status"] = state.get("last_report_status")
    return status


def _detected_agents() -> dict[str, dict[str, Any]]:
    home = Path.home()
    detected: dict[str, dict[str, Any]] = {}
    for name in AGENT_SCRIPTS:
        path = shutil.which(name)
        if path is None and name == "kilo":
            fallback = home / ".kilo" / "bin" / "kilo"
            path = str(fallback) if fallback.exists() else None
        detected[name] = {"found": path is not None, "path": path}
    return detected


def health_payload() -> dict[str, Any]:
    """The device's status: build, detected agents and collector wiring.

    Local file paths are included because these consumers are on this machine;
    a report that leaves it is assembled from the same payload minus the paths.
    """
    endpoint = intended_endpoint()
    states = read_agent_states(endpoint)
    agents = {name: states[name] for name in AGENT_SCRIPTS}
    return {
        "device_name": socket.gethostname() or "device",
        "client_version": client_version(),
        "client_commit": client_commit(),
        "collected_at": int(time.time()),
        "expected": {
            "otlp_endpoint": endpoint[: -len("/v1/logs")] if endpoint else None,
            "otlp_logs_endpoint": endpoint,
        },
        "summary": {
            "total_agents": len(agents),
            "configured_agents": sum(
                1 for agent in agents.values() if agent["configured"]
            ),
            "matching_agents": sum(
                1 for agent in agents.values() if agent["endpoint_matches"] is True
            ),
        },
        "agents": agents,
        "detected": _detected_agents(),
    }


def report_payload(payload: dict[str, Any], *, include_paths: bool) -> dict[str, Any]:
    """The payload as a report body, without local file paths when hosted.

    A remote server has no use for this machine's file layout, and storing it
    would leak local paths; a local server gets the full payload.
    """
    if include_paths:
        return payload
    report = dict(payload)
    detected = payload.get("detected")
    if isinstance(detected, dict):
        report["detected"] = {
            name: {key: value for key, value in info.items() if key != "path"}
            for name, info in detected.items()
        }
    return report


def _report_once(state: dict[str, Any]) -> None:
    """Send this device's status to whichever server applies. Never raises.

    Signed in: report to that server with the CLI token, without local paths.
    Not signed in but a local server is installed: report to it with the
    installation key, paths included. Neither: stay idle until the next tick.
    """
    from client.auth import installation_key, load_credentials
    from client.paths import local_server_info, server_root

    try:
        credentials = load_credentials() or {}
    except ValueError:
        credentials = {}
    server_url = credentials.get("server_url")
    cli_token = credentials.get("cli_token")
    try:
        if (
            isinstance(server_url, str)
            and server_url
            and isinstance(cli_token, str)
            and cli_token
        ):
            response = httpx.post(
                f"{server_url}/devices/status",
                json=report_payload(health_payload(), include_paths=False),
                headers={"Authorization": f"Bearer {cli_token}"},
                timeout=REPORT_TIMEOUT_SECONDS,
            )
        elif server_root() is not None:
            body = report_payload(health_payload(), include_paths=True)
            body["installation_key"] = installation_key()
            response = httpx.post(
                f"{local_server_info()['api_url']}/devices/status",
                json=body,
                timeout=REPORT_TIMEOUT_SECONDS,
            )
        else:
            return
        response.raise_for_status()
    except Exception:
        state["last_report_status"] = "failed"
        logger.exception("device report failed")
        return
    state["last_report_at"] = int(time.time())
    state["last_report_status"] = "ok"


def _check_once(state: dict[str, Any]) -> None:
    payload = health_payload()
    state["last_check_at"] = payload["collected_at"]
    _report_once(state)
    _write_state(state)
    logger.info(
        "device check: %s/%s agents configured, %s matching",
        payload["summary"]["configured_agents"],
        payload["summary"]["total_agents"],
        payload["summary"]["matching_agents"],
    )


def run_foreground() -> int:
    existing = running_state()
    if existing is not None:
        print(
            f"tokenage client service is already running (pid {existing['pid']})",
            file=sys.stderr,
        )
        return 1

    log_path().parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path()),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # Signals only flip the flag; the loop below owns the actual shutdown, so
    # cleanup always runs on the way out.
    stop = False

    def _request_stop(signum, frame):  # noqa: ARG001
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    state: dict[str, Any] = {
        "pid": os.getpid(),
        "started_at": int(time.time()),
        "last_check_at": None,
        "last_report_at": None,
        "last_report_status": None,
    }
    _write_state(state)
    print(f"tokenage client service running (pid {os.getpid()})")
    logger.info("client service started (pid %s)", os.getpid())
    try:
        while not stop:
            try:
                _check_once(state)
            except Exception:
                # A broken agent config must fail the check, never the daemon.
                logger.exception("device check failed")
            # Sleep in slices so a stop signal is honored within half a second.
            deadline = time.monotonic() + CHECK_INTERVAL_SECONDS
            while not stop and time.monotonic() < deadline:
                time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
    finally:
        # A concurrent start may have replaced the state file; only clear ours.
        current = _read_state()
        if current is not None and current.get("pid") == os.getpid():
            _clear_state()
        logger.info("client service stopped (pid %s)", os.getpid())
    return 0


def start() -> int:
    existing = running_state()
    if existing is not None:
        print(f"tokenage client service is already running (pid {existing['pid']})")
        return 0

    log_path().parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TOKENAGE_SKIP_BANNER"] = "1"
    # The child appends its stdout/stderr here; this handle closes when the
    # parent exits, the child keeps its duplicates.
    with open(log_path(), "ab") as log:
        try:
            process = subprocess.Popen(
                [sys.executable, "-P", "-m", "client", "client", "run"],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
                env=env,
                close_fds=True,
            )
        except OSError as exc:
            print(
                f"tokenage: could not start the client service: {exc}", file=sys.stderr
            )
            return 1

    # The child writes its state file once running; an early exit means failure.
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        state = running_state()
        if state is not None:
            print(f"  started   client service (pid {state['pid']})")
            print(f"  log       {log_path()}")
            return 0
        if process.poll() is not None:
            print(
                f"tokenage: client service exited during startup; see {log_path()}",
                file=sys.stderr,
            )
            return 1
        time.sleep(0.1)
    print(
        f"tokenage: client service did not report ready; see {log_path()}",
        file=sys.stderr,
    )
    return 1


def stop() -> int:
    state = _read_state()
    pid = state.get("pid") if state is not None else None
    if not _pid_alive(pid):
        if state is not None:
            _clear_state()
        print("tokenage client service is not running")
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        print(f"tokenage: could not stop the client service: {exc}", file=sys.stderr)
        return 1
    # Graceful first: the daemon removes its own state on the way out.
    deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            _clear_state()
            print(f"  stopped   client service (pid {pid})")
            return 0
        time.sleep(0.1)
    # SIGKILL cannot clean up after itself, so the stale state file goes here.
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    _clear_state()
    print(f"  stopped   client service (pid {pid})")
    return 0


def restart() -> int:
    stop()
    return start()


def run_status(*, as_json: bool) -> int:
    data = service_status()
    if as_json:
        print(json.dumps(data, separators=(",", ":"), sort_keys=True))
    elif data["running"]:
        print(f"tokenage client service running (pid {data['pid']})")
        if data.get("last_check_at"):
            stamp = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(data["last_check_at"])
            )
            print(f"  last check  {stamp}")
        if data.get("last_report_at"):
            stamp = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(data["last_report_at"])
            )
            print(f"  last report {stamp} ({data.get('last_report_status')})")
        elif data.get("last_report_status"):
            print(f"  last report {data['last_report_status']}")
        print(f"  log         {data['log']}")
    else:
        print("tokenage client service is not running")
    return 0 if data["running"] else 1


def _render_health(payload: dict[str, Any]) -> str:
    lines = [
        f"tokenage {payload['client_version']}"
        + (
            f" (client {payload['client_commit'][:7]})"
            if payload["client_commit"]
            else ""
        )
    ]
    for name in AGENT_SCRIPTS:
        agent = payload["agents"][name]
        detected = payload["detected"][name]["found"]
        state = "not detected" if not detected else agent["status"]
        lines.append(f"  {name:<10}{state}")
    return "\n".join(lines) + "\n"


def run_health(*, as_json: bool) -> int:
    payload = health_payload()
    if as_json:
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    else:
        print(_render_health(payload), end="")
    return 0
