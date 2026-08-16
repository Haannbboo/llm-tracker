from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from config.app import CONFIG

from . import evaluation as evaluation_module
from .auth import mint_token
from .database import (
    get_usage_high_watermark_ts,
    init_db,
    merge_usage_database,
    summarize_usage_window,
)

evaluation_subprocess = evaluation_module.subprocess


class ApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunOptions:
    json_output: bool = False
    summary_dest: str = "stderr"
    summary_file: str | None = None
    wait_ms: int = 3000
    poll_ms: int = 250
    proxy_env: bool = False
    no_summary: bool = False
    quiet_child_output: bool = False


@dataclass(frozen=True)
class TempService:
    name: str
    port: int
    process: subprocess.Popen[bytes]


class UsageApiClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        credentials = load_credentials() or {}
        if base_url is None:
            base_url = credentials.get("server_url") or None
        self.base_url = base_url or build_api_base_url()
        self.token = token if token is not None else credentials.get("cli_token")

    def get_high_watermark(self) -> int:
        try:
            data = self._get_json("/usage/high-watermark")
            return int(data["ts"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError(str(exc)) from exc

    def get_run_summary(
        self,
        *,
        after_ts: int,
        until_ts: int | None = None,
        client_source: str | None = None,
        session_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"after_ts": after_ts}
        if until_ts is not None:
            params["until_ts"] = until_ts
        if client_source is not None:
            params["client_source"] = client_source
        if session_id is not None:
            params["session_id"] = session_id
        if provider is not None:
            params["provider"] = provider
        if model is not None:
            params["model"] = model
        return self._get_json("/usage/run-summary", params=params)

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = httpx.get(
                f"{self.base_url.rstrip('/')}{path}",
                params=params,
                headers=headers,
                timeout=5,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise ApiError("session rejected — run llm-tracker login") from exc
            raise ApiError(str(exc)) from exc
        except Exception as exc:
            raise ApiError(str(exc)) from exc


class DatabaseUsageClient:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def get_high_watermark(self) -> int:
        return get_usage_high_watermark_ts(db_path=self.db_url)

    def get_run_summary(
        self,
        *,
        after_ts: int,
        until_ts: int | None = None,
        client_source: str | None = None,
        session_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        return summarize_usage_window(
            after_ts=after_ts,
            until_ts=until_ts,
            client_source=client_source,
            session_id=session_id,
            provider=provider,
            model=model,
            db_path=self.db_url,
        )


def build_api_base_url() -> str:
    from config.server_config import resolve_server_urls

    return resolve_server_urls(CONFIG)["api_url"]


def build_proxy_base_urls() -> tuple[str, str]:
    from config.server_config import resolve_server_urls

    proxy_url = resolve_server_urls(CONFIG)["proxy_url"]
    return f"{proxy_url}/v1", proxy_url


class CliHelpFormatter(argparse.RawDescriptionHelpFormatter):
    def __init__(self, prog: str):
        super().__init__(prog, max_help_position=30)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="llm-tracker",
        description=("Track an agent command or inspect a tracked session summary."),
        epilog=(
            "available commands:\n"
            "  bootstrap                install deps, configure agents, and start services\n"
            "  start                    start llm-tracker services\n"
            "  stop [program...]        stop all services or named services: llm-tracker-proxy, llm-tracker-api, llm-tracker-otlp\n"
            "  restart [program...]     restart all services or named services: llm-tracker-proxy, llm-tracker-api, llm-tracker-otlp\n"
            "  status                   show service status\n"
            "  update [--check|--dry-run]  fetch, pull, bootstrap, and restart\n"
            "  summary <session_id>     show the saved LLM summary for a tracked session\n"
            "  login [--server URL]     log in to a hosted server and wire agents\n"
            "  token create --email <email> [--kind cli|ingest|web] [--name <device>]\n"
            "                           mint an auth token (operator-only, runs on the server box)\n"
            "  codex ...                run Codex with tracking\n"
            "  claude ...               run Claude Code with tracking\n"
            "  <any-command> ...        run any command with tracking\n\n"
            "Use '--' only when passing llm-tracker flags before the child command."
        ),
        formatter_class=CliHelpFormatter,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="write the final usage summary as compact JSON",
    )
    parser.add_argument(
        "--usage-only",
        action="store_true",
        help="write only the usage summary to stdout and suppress child output",
    )
    parser.add_argument(
        "--summary-dest",
        choices=("stdout", "stderr", "file"),
        default="stderr",
        help="choose where the final usage summary is written",
    )
    parser.add_argument(
        "--summary-file",
        help="path to write the summary when --summary-dest=file",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=3000,
        help="max time in milliseconds to wait for tracked usage after the command exits",
    )
    parser.add_argument(
        "--poll-ms",
        type=int,
        default=250,
        help="poll interval in milliseconds while waiting for the final summary",
    )
    parser.add_argument(
        "--proxy-env",
        action="store_true",
        help="set OPENAI_BASE_URL and ANTHROPIC_BASE_URL for the child command",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="run tracking but skip printing the final usage summary",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args


def parse_update_args(command: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="llm-tracker update",
        description="Fetch, pull (fast-forward), bootstrap, and restart.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="show status without pulling or bootstrapping",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show planned commands without executing them",
    )
    return parser.parse_args(command[1:])


def run_update_command(command: list[str]) -> int:
    """Delegate to scripts/update.sh for the actual update logic."""
    update_args = parse_update_args(command)
    scripts_dir = project_root() / "scripts"
    update_script = scripts_dir / "update.sh"
    if not update_script.exists():
        print(f"Update script not found: {update_script}", file=sys.stderr)
        return 1

    cmd: list[str] = ["bash", str(update_script)]
    if update_args.check:
        cmd.append("--check")
    elif update_args.dry_run:
        cmd.append("--dry-run")

    return subprocess.run(cmd).returncode


def parse_token_args(command: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="llm-tracker token",
        description="Manage auth tokens (operator-only; talks to the configured DB).",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    create = subparsers.add_parser(
        "create", help="mint a token for a user, creating the user if needed"
    )
    create.add_argument("--email", required=True, help="user email")
    create.add_argument(
        "--kind", choices=("cli", "ingest", "web"), default="cli", help="token kind"
    )
    create.add_argument("--name", help="device name to label the token with")
    return parser.parse_args(command[1:])


def run_token_command(command: list[str]) -> int:
    token_args = parse_token_args(command)

    init_db()
    try:
        token, user = mint_token(
            token_args.email, kind=token_args.kind, device_name=token_args.name
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Minted {token_args.kind} token for {user.email} (shown once):")
    print(token)
    return 0


# ------------------------------------------------------- hosted credentials


def credentials_path() -> Path:
    from config.models import get_tracker_home

    return Path(get_tracker_home()) / "credentials.json"


def load_credentials() -> dict[str, Any] | None:
    path = credentials_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = None
    if not isinstance(data, dict):
        if path.exists():
            print(
                f"warning: could not read {path}; ignoring saved credentials",
                file=sys.stderr,
            )
        return None
    return data


def save_credentials(data: dict[str, Any]) -> None:
    """Write credentials.json atomically, 0600 from the moment it exists."""
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    os.chmod(tmp, 0o600)  # in case a stale tmp pre-existed with wider mode
    tmp.replace(path)


# --------------------------------------------------------------- CLI login


def parse_login_args(command: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="llm-tracker login",
        description="Log in to a hosted llm-tracker server and wire agents.",
    )
    parser.add_argument(
        "--server", help="server base URL (e.g. https://app.example.com)"
    )
    parser.add_argument(
        "--device-name", dest="device_name", help="device label for tokens"
    )
    parser.add_argument(
        "--no-browser",
        dest="no_browser",
        action="store_true",
        help="don't attempt to open a browser (the login URL is always printed)",
    )
    return parser.parse_args(command[1:])


def _sanitize_device_name(raw: str | None) -> str:
    cleaned = "".join(c for c in (raw or "").strip() if c.isprintable())
    return cleaned[:64] or "cli-device"


def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) per RFC 7636 S256."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _normalize_cli_code(raw: str) -> str:
    """Uppercase, strip whitespace and hyphens (what a human may retype)."""
    return "".join(raw.split()).upper().replace("-", "")


def run_login_command(command: list[str]) -> int:
    args = parse_login_args(command)
    server = (
        args.server
        or os.environ.get("LLMTRACKER_SERVER")
        or (load_credentials() or {}).get("server_url")
        or ""
    ).rstrip("/")
    if not server:
        print(
            "no server configured: pass --server URL, set LLMTRACKER_SERVER, "
            "or point LLM_TRACKER_HOME at an existing credentials.json",
            file=sys.stderr,
        )
        return 2
    if server.startswith("http://") and not server.startswith(
        ("http://localhost", "http://127.0.0.1")
    ):
        print(
            "warning: --server uses http://; login tokens will travel unencrypted",
            file=sys.stderr,
        )

    try:
        httpx.get(f"{server}/version", timeout=5).raise_for_status()
    except Exception as exc:
        print(f"llm-tracker server unreachable at {server}: {exc}", file=sys.stderr)
        return 1

    verifier, challenge = _pkce_pair()
    device_name = _sanitize_device_name(
        args.device_name or socket.gethostname() or "cli-device"
    )
    login_url = f"{server}/auth/cli/start?" + urlencode(
        {"code_challenge": challenge, "device_name": device_name}
    )

    print(f"Open this URL in your browser to continue login:\n  {login_url}")
    over_ssh = bool(os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"))
    if not args.no_browser and not over_ssh:
        webbrowser.open(login_url)

    response: httpx.Response | None = None
    for attempt in range(3):
        try:
            raw = input("Paste the code shown in your browser: ")
        except EOFError:
            print("no code entered; no credentials written", file=sys.stderr)
            return 1
        if not raw.strip():
            print("no code entered; no credentials written", file=sys.stderr)
            return 1
        try:
            response = httpx.post(
                f"{server}/auth/cli/exchange",
                json={"code": _normalize_cli_code(raw), "code_verifier": verifier},
                timeout=10,
            )
        except Exception as exc:
            print(f"login exchange failed: {exc}", file=sys.stderr)
            return 1
        if response.status_code == 200:
            break
        detail = ""
        try:
            detail = str(response.json().get("detail", ""))
        except Exception:
            pass
        if response.status_code == 400 and attempt < 2:
            print("invalid or expired code — paste it again", file=sys.stderr)
            continue
        print(
            f"login failed: HTTP {response.status_code}"
            f"{f' ({detail})' if detail else ''}",
            file=sys.stderr,
        )
        return 1
    if response is None:
        return 1
    try:
        payload = response.json()
    except Exception:
        print("login failed: server returned an invalid response", file=sys.stderr)
        return 1
    user = payload.get("user") or {}

    save_credentials(
        {
            "server_url": server,
            "user_id": user.get("id"),
            "email": user.get("email"),
            "device_name": payload.get("device_name"),
            "cli_token": payload.get("cli_token"),
            "ingest_token": payload.get("ingest_token"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    print(f"Logged in as {user.get('email')} (device: {payload.get('device_name')})")
    print(f"Credentials saved to {credentials_path()}")
    print(f"Dashboard: {server}")

    wired = wire_agents_for_hosted(
        logs_endpoint=(payload.get("otlp") or {}).get("logs_endpoint"),
    )
    if wired:
        print("Wired agents: " + ", ".join(wired))
    else:
        print("No tracked agents detected; nothing to wire.")
    return 0


def wire_agents_for_hosted(*, logs_endpoint: str | None) -> list[str]:
    """Point detected agents' telemetry at the hosted server (idempotent)."""
    if not logs_endpoint:
        return []
    scripts_dir = project_root() / "scripts"
    home = Path.home()
    jobs: list[tuple[str, str, list[str], str]] = []
    if shutil.which("codex"):
        jobs.append(
            (
                "codex",
                "configure-codex-settings.py",
                [str(home / ".codex" / "config.toml")],
                logs_endpoint,
            )
        )
    if shutil.which("claude"):
        jobs.append(
            (
                "claude",
                "configure-claude-settings.py",
                [str(home / ".claude" / "settings.json")],
                logs_endpoint,
            )
        )
    if shutil.which("opencode"):
        jobs.append(
            (
                "opencode",
                "configure-opencode-plugin.py",
                [str(project_root())],
                logs_endpoint,
            )
        )
    if shutil.which("kilo"):
        jobs.append(
            ("kilo", "configure-kilo-plugin.py", [str(project_root())], logs_endpoint)
        )

    wired: list[str] = []
    # The configure scripts honor OTEL_EXPORTER_OTLP_LOGS_ENDPOINT over the
    # endpoint argument; strip it so a pre-existing local OTLP env config
    # can't silently override the hosted endpoint just logged in to.
    env = {
        k: v for k, v in os.environ.items() if k != "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"
    }
    for name, script, prefix_args, endpoint in jobs:
        result = subprocess.run(
            # Trailing shape matches the scripts' documented argv:
            # [PREFIX...] PORT HOST ENDPOINT — the endpoint overrides the
            # placeholder port/host.
            [
                sys.executable,
                str(scripts_dir / script),
                *prefix_args,
                "0",
                "localhost",
                endpoint,
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode == 0:
            wired.append(name)
        else:
            print(
                f"warning: wiring {name} failed: {result.stderr.strip()}",
                file=sys.stderr,
            )
    return wired


def parse_session_summary_args(command: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="llm-tracker summary")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="print the LLM summary without updating the sessions database row",
    )
    parser.add_argument("session_id")
    return parser.parse_args(command[1:])


def options_from_args(args: argparse.Namespace) -> RunOptions:
    usage_only = bool(args.usage_only)
    return RunOptions(
        json_output=args.json,
        summary_dest="stdout" if usage_only else args.summary_dest,
        summary_file=args.summary_file,
        wait_ms=args.wait_ms,
        poll_ms=args.poll_ms,
        proxy_env=args.proxy_env,
        no_summary=args.no_summary,
        quiet_child_output=usage_only,
    )


def child_output_kwargs(options: RunOptions) -> dict[str, Any]:
    if not options.quiet_child_output:
        return {}
    return {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }


def build_child_env(
    options: RunOptions,
    *,
    proxy_base_urls: tuple[str, str] | None = None,
    otlp_logs_endpoint: str | None = None,
) -> dict[str, str] | None:
    if not options.proxy_env and otlp_logs_endpoint is None:
        return None

    env = os.environ.copy()
    env.pop("LLM_TRACKER_DB_URL", None)

    if options.proxy_env:
        openai_base_url, anthropic_base_url = proxy_base_urls or build_proxy_base_urls()
        if proxy_base_urls is None:
            env.setdefault("OPENAI_BASE_URL", openai_base_url)
            env.setdefault("ANTHROPIC_BASE_URL", anthropic_base_url)
        else:
            env["OPENAI_BASE_URL"] = openai_base_url
            env["ANTHROPIC_BASE_URL"] = anthropic_base_url

    if otlp_logs_endpoint is not None:
        env["CLAUDE_CODE_ENABLE_TELEMETRY"] = "1"
        env["OTEL_LOGS_EXPORTER"] = "otlp"
        env["OTEL_EXPORTER_OTLP_LOGS_PROTOCOL"] = "http/json"
        env["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] = otlp_logs_endpoint

    return env


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_service_env(db_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env["LLM_TRACKER_DB_URL"] = db_url
    root = str(project_root())
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        root if not existing_pythonpath else f"{root}{os.pathsep}{existing_pythonpath}"
    )
    return env


def find_free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_port(port: int, *, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.05)
    raise RuntimeError(f"temporary service did not listen on port {port}: {last_error}")


def start_temp_service(*, name: str, module: str, db_url: str) -> TempService:
    port = find_free_loopback_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            f"{module}:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=project_root(),
        env=build_service_env(db_url),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_port(port)
    except Exception:
        stop_temp_service(TempService(name=name, port=port, process=process))
        raise
    return TempService(name=name, port=port, process=process)


def stop_temp_service(service: TempService) -> None:
    if service.process.poll() is not None:
        return
    service.process.terminate()
    try:
        service.process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        service.process.kill()
        service.process.wait(timeout=5)


def _codex_exec_subcommand_index(command: list[str]) -> int | None:
    if not command:
        return None
    if Path(command[0]).name != "codex":
        return None
    for index, part in enumerate(command[1:], start=1):
        if part in {"exec", "e"}:
            return index
    return None


def build_child_command(
    command: list[str],
    *,
    otlp_logs_endpoint: str | None = None,
) -> list[str]:
    if otlp_logs_endpoint is None:
        return command

    exec_index = _codex_exec_subcommand_index(command)
    if exec_index is None:
        return command

    return [
        command[0],
        "-c",
        f'otel.exporter.otlp-http.endpoint="{otlp_logs_endpoint}"',
        "-c",
        'otel.exporter.otlp-http.protocol="json"',
        *command[1:],
    ]


def run_with_watermark_tracking(
    *,
    command: list[str],
    client: UsageApiClient,
    options: RunOptions,
) -> int:
    try:
        before_ts = client.get_high_watermark()
    except ApiError as exc:
        print(
            f"llm-tracker API unavailable before command start: {exc}",
            file=sys.stderr,
        )
        before_ts = None

    completed = subprocess.run(
        command,
        env=build_child_env(options),
        **child_output_kwargs(options),
    )
    child_code = _normalize_return_code(int(completed.returncode))

    if options.no_summary:
        return child_code

    if before_ts is None:
        print("No summary could be produced.", file=sys.stderr)
        return child_code

    summary = poll_summary(
        client,
        after_ts=before_ts,
        options=options,
    )
    if summary is None:
        print(
            "Command completed, but llm-tracker summary retrieval failed.",
            file=sys.stderr,
        )
        return child_code

    try:
        write_summary(summary, options)
    except Exception as exc:
        print(f"llm-tracker summary output failed: {exc}", file=sys.stderr)
    return child_code


def configured_main_db_url() -> str:
    return str(CONFIG["db"]["url"])


def temp_proxy_base_urls(proxy_port: int) -> tuple[str, str]:
    return f"http://127.0.0.1:{proxy_port}/v1", f"http://127.0.0.1:{proxy_port}"


def run_with_isolated_tracking(
    *,
    command: list[str],
    options: RunOptions,
) -> int:
    main_db_url = configured_main_db_url()
    run_dir = Path(tempfile.mkdtemp(prefix="llm-tracker-run-"))
    run_db_path = run_dir / "usage.db"
    run_db_url = f"sqlite:///{run_db_path}"
    init_db(run_db_url)
    run_client = DatabaseUsageClient(run_db_url)
    services: list[TempService] = []
    cleanup_run_dir = True

    try:
        try:
            # Start the temp OTLP collector in every isolated run so the child's
            # own OTLP telemetry (its global settings point at the main collector)
            # is redirected into this run DB instead of leaking into the main DB.
            # With proxy_env the proxy also records the same requests; the two
            # paths converge on the run DB where record_usage dedups them.
            otlp_service = start_temp_service(
                name="otlp",
                module="src.otlp",
                db_url=run_db_url,
            )
            services.append(otlp_service)
            otlp_logs_endpoint = f"http://127.0.0.1:{otlp_service.port}/v1/logs"

            proxy_base_urls = None
            if options.proxy_env:
                proxy_service = start_temp_service(
                    name="proxy",
                    module="src.proxy",
                    db_url=run_db_url,
                )
                services.append(proxy_service)
                proxy_base_urls = temp_proxy_base_urls(proxy_service.port)
        except Exception as exc:
            cleanup_run_dir = False
            print(
                "llm-tracker isolated services failed; "
                f"run DB retained at {run_db_path}: {exc}",
                file=sys.stderr,
            )
            return 1

        completed = subprocess.run(
            build_child_command(
                command,
                otlp_logs_endpoint=otlp_logs_endpoint,
            ),
            env=build_child_env(
                options,
                proxy_base_urls=proxy_base_urls,
                otlp_logs_endpoint=otlp_logs_endpoint,
            ),
            **child_output_kwargs(options),
        )
        child_code = _normalize_return_code(int(completed.returncode))

        wait_for_usage_flush(run_client, options)  # type: ignore[arg-type]
        for service in reversed(services):
            stop_temp_service(service)
        services.clear()
        summary = summarize_usage_window(after_ts=0, db_path=run_db_url)

        try:
            init_db(main_db_url)
            merge_usage_database(
                source_db_path=run_db_url,
                target_db_path=main_db_url,
            )
        except Exception as exc:
            cleanup_run_dir = False
            print(
                f"llm-tracker merge failed; run DB retained at {run_db_path}: {exc}",
                file=sys.stderr,
            )

        if not options.no_summary:
            try:
                write_summary(summary, options)
            except Exception as exc:
                print(f"llm-tracker summary output failed: {exc}", file=sys.stderr)
        return child_code
    finally:
        for service in reversed(services):
            stop_temp_service(service)
        if cleanup_run_dir:
            shutil.rmtree(run_dir, ignore_errors=True)


def run_with_tracking(
    *,
    command: list[str],
    options: RunOptions,
    client: UsageApiClient | None = None,
) -> int:
    if client is not None:
        return run_with_watermark_tracking(
            command=command,
            client=client,
            options=options,
        )
    return run_with_isolated_tracking(
        command=command,
        options=options,
    )


def _normalize_return_code(returncode: int) -> int:
    if returncode < 0:
        return 128 + abs(returncode)
    return returncode


def poll_summary(
    client: UsageApiClient,
    *,
    after_ts: int,
    options: RunOptions,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + max(options.wait_ms, 0) / 1000
    latest_summary: dict[str, Any] | None = None

    while True:
        try:
            summary = client.get_run_summary(after_ts=after_ts)
        except ApiError as exc:
            print(f"llm-tracker API error: {exc}", file=sys.stderr)
            return latest_summary

        latest_summary = summary
        if time.monotonic() >= deadline:
            break
        time.sleep(max(options.poll_ms, 1) / 1000)

    if latest_summary and latest_summary.get("summary", {}).get("requests", 0) > 0:
        return latest_summary

    try:
        until_ts = client.get_high_watermark()
    except ApiError as exc:
        print(f"llm-tracker API error: {exc}", file=sys.stderr)
        return latest_summary

    try:
        return client.get_run_summary(
            after_ts=after_ts,
            until_ts=until_ts,
        )
    except ApiError as exc:
        print(f"llm-tracker API error: {exc}", file=sys.stderr)
        return None


def wait_for_usage_flush(client: UsageApiClient, options: RunOptions) -> None:
    """Give OTLP exporters a bounded window to write final usage rows."""
    poll_summary(client, after_ts=0, options=options)


def run_session_summary_command(
    command: list[str],
    *,
    json_output: bool = False,
) -> int:
    summary_args = parse_session_summary_args(command)
    use_json = json_output or bool(summary_args.json)
    try:
        evaluation = evaluation_module.summarize_session_with_llm(
            summary_args.session_id,
            db_path=configured_main_db_url(),
            update=not summary_args.no_update,
        )
    except Exception as exc:
        print(f"llm-tracker summary failed: {exc}", file=sys.stderr)
        return 1

    if use_json:
        print(json.dumps(evaluation, separators=(",", ":")))
    else:
        print(format_session_evaluation_summary(summary_args.session_id, evaluation))
    return 0


def format_session_evaluation_summary(
    session_id: str,
    evaluation: dict[str, Any],
) -> str:
    lines = [
        "llm-tracker session summary",
        f"session: {session_id}",
        f"outcome: {evaluation.get('outcome') or 'unknown'}",
    ]
    confidence = evaluation.get("confidence")
    if confidence is not None:
        lines.append(f"confidence: {float(confidence):.2f}")
    task_title = evaluation.get("task_title")
    if task_title:
        lines.append(f"title: {task_title}")
    summary = evaluation.get("summary")
    if summary:
        lines.extend(["", str(summary)])
    evidence = evaluation.get("evidence")
    if evidence:
        lines.append("")
        lines.append("evidence:")
        for item in evidence:
            lines.append(f"  - {item}")
    failure_reason = evaluation.get("failure_reason")
    if failure_reason:
        lines.extend(["", f"failure reason: {failure_reason}"])
    return "\n".join(lines) + "\n"


def write_summary(summary: dict[str, Any], options: RunOptions) -> None:
    if options.json_output:
        content = json.dumps(summary, separators=(",", ":")) + "\n"
    else:
        content = format_human_summary(summary)

    if options.summary_dest == "file":
        if not options.summary_file:
            raise ApiError("--summary-file is required when --summary-dest=file")
        Path(options.summary_file).write_text(content, encoding="utf-8")
    elif options.summary_dest == "stdout":
        print(content, end="")
    else:
        print(content, end="", file=sys.stderr)


def format_human_summary(summary: dict[str, Any]) -> str:
    totals = summary.get("summary", {})
    requests = int(totals.get("requests", 0) or 0)
    if requests == 0:
        return "No llm-tracker usage recorded for this command.\n"

    total_tokens = int(totals.get("total_tokens", 0) or 0)
    cached_tokens = int(totals.get("cached_tokens", 0) or 0)
    cache_hit_rate = float(totals.get("cache_hit_rate", 0) or 0)
    total_cost = float(totals.get("total_cost_usd", 0) or 0)
    avg_latency = totals.get("avg_latency_ms")
    avg_ttft = totals.get("avg_ttft_ms")

    lines = [
        "llm-tracker usage summary",
        (
            f"requests: {requests}, total tokens: {total_tokens:,}, "
            f"cached: {cached_tokens:,} ({cache_hit_rate:.0%})"
        ),
        (
            f"latency avg: {_format_ms(avg_latency)}, "
            f"ttft avg: {_format_ms(avg_ttft)}, cost: ${total_cost:.4f}"
        ),
    ]

    sessions = summary.get("sessions", [])
    if sessions:
        lines.append("")
        lines.append("sessions:")
        for session in sessions:
            session_id = session.get("session_id") or "unattributed"
            lines.append(
                "  "
                f"{session_id}  "
                f"{int(session.get('requests', 0) or 0)} req  "
                f"{int(session.get('total_tokens', 0) or 0):,} tok  "
                f"{float(session.get('cache_hit_rate', 0) or 0):.0%} cached  "
                f"${float(session.get('total_cost_usd', 0) or 0):.4f}"
            )

    return "\n".join(lines) + "\n"


def _format_ms(value: Any) -> str:
    if value is None:
        return "n/a"
    ms = float(value)
    if ms >= 1000:
        return f"{ms / 1000:.2f}s"
    return f"{ms:.0f}ms"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    if not args.command:
        print("usage: llm-tracker [options] -- <command> [args...]", file=sys.stderr)
        return 2
    if args.command[0] == "summary":
        return run_session_summary_command(args.command, json_output=args.json)
    if args.command[0] == "update":
        return run_update_command(args.command)
    if args.command[0] == "token":
        return run_token_command(args.command)
    if args.command[0] == "login":
        return run_login_command(args.command)

    options = options_from_args(args)
    if options.summary_dest == "file" and not options.summary_file:
        print("--summary-file is required when --summary-dest=file", file=sys.stderr)
        return 2
    if args.usage_only and options.no_summary:
        print("--usage-only cannot be combined with --no-summary", file=sys.stderr)
        return 2

    try:
        # Hosted credentials present → API (watermark) path with the bearer
        # token; otherwise the isolated local-tracking path, as before.
        client: UsageApiClient | None = UsageApiClient() if load_credentials() else None
        return run_with_tracking(
            command=args.command,
            options=options,
            client=client,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 127
    except PermissionError as exc:
        print(str(exc), file=sys.stderr)
        return 126


if __name__ == "__main__":
    raise SystemExit(main())
