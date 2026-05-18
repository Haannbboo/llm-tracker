from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from config.app import CONFIG
from .database import (
    get_usage_high_watermark,
    init_db,
    merge_usage_database,
    summarize_usage_window,
)
from . import evaluation as evaluation_module

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
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or build_api_base_url()

    def get_high_watermark(self) -> int:
        try:
            data = self._get_json("/usage/high-watermark")
            return int(data["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError(str(exc)) from exc

    def get_run_summary(
        self,
        *,
        after_id: int,
        until_id: int | None = None,
        client_source: str | None = None,
        session_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"after_id": after_id}
        if until_id is not None:
            params["until_id"] = until_id
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
        try:
            response = httpx.get(
                f"{self.base_url.rstrip('/')}{path}",
                params=params,
                timeout=5,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise ApiError(str(exc)) from exc


class DatabaseUsageClient:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def get_high_watermark(self) -> int:
        return get_usage_high_watermark(db_path=self.db_url)

    def get_run_summary(
        self,
        *,
        after_id: int,
        until_id: int | None = None,
        client_source: str | None = None,
        session_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        return summarize_usage_window(
            after_id=after_id,
            until_id=until_id,
            client_source=client_source,
            session_id=session_id,
            provider=provider,
            model=model,
            db_path=self.db_url,
        )


def build_api_base_url() -> str:
    server = CONFIG["server"]
    host = server.get("host", "127.0.0.1")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    port = int(server.get("api_port", int(server.get("port", 4000)) + 1))
    return f"http://{host}:{port}"


def build_proxy_base_urls() -> tuple[str, str]:
    server = CONFIG["server"]
    host = server.get("host", "127.0.0.1")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    port = int(server.get("port", 4000))
    return f"http://{host}:{port}/v1", f"http://{host}:{port}"


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
            "  summary <session_id>     show the saved LLM summary for a tracked session\n"
            "  codex ...                run Codex with tracking\n"
            "  claude ...               run Claude Code with tracking\n"
            "  gemini ...               run Gemini CLI with tracking\n"
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
        before_id = client.get_high_watermark()
    except ApiError:
        print(
            "llm-tracker API unavailable before command start.",
            file=sys.stderr,
        )
        before_id = None

    completed = subprocess.run(
        command,
        env=build_child_env(options),
        **child_output_kwargs(options),
    )
    child_code = _normalize_return_code(int(completed.returncode))

    if options.no_summary:
        return child_code

    if before_id is None:
        print("No summary could be produced.", file=sys.stderr)
        return child_code

    summary = poll_summary(
        client,
        after_id=before_id,
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
            otlp_service = start_temp_service(
                name="otlp",
                module="src.otlp",
                db_url=run_db_url,
            )
            services.append(otlp_service)

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

        otlp_logs_endpoint = f"http://127.0.0.1:{otlp_service.port}/v1/logs"
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

        wait_for_usage_flush(run_client, options)
        for service in reversed(services):
            stop_temp_service(service)
        services.clear()
        summary = summarize_usage_window(after_id=0, db_path=run_db_url)

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
    after_id: int,
    options: RunOptions,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + max(options.wait_ms, 0) / 1000
    latest_summary: dict[str, Any] | None = None

    while True:
        try:
            summary = client.get_run_summary(after_id=after_id)
        except ApiError:
            return latest_summary

        latest_summary = summary
        if time.monotonic() >= deadline:
            break
        time.sleep(max(options.poll_ms, 1) / 1000)

    if latest_summary and latest_summary.get("summary", {}).get("requests", 0) > 0:
        return latest_summary

    try:
        until_id = client.get_high_watermark()
    except ApiError:
        return latest_summary

    try:
        return client.get_run_summary(
            after_id=after_id,
            until_id=until_id,
        )
    except ApiError:
        return None


def wait_for_usage_flush(client: UsageApiClient, options: RunOptions) -> None:
    """Give OTLP exporters a bounded window to write final usage rows."""
    poll_summary(client, after_id=0, options=options)


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

    options = options_from_args(args)
    if options.summary_dest == "file" and not options.summary_file:
        print("--summary-file is required when --summary-dest=file", file=sys.stderr)
        return 2
    if args.usage_only and options.no_summary:
        print("--usage-only cannot be combined with --no-summary", file=sys.stderr)
        return 2

    try:
        return run_with_tracking(
            command=args.command,
            options=options,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 127
    except PermissionError as exc:
        print(str(exc), file=sys.stderr)
        return 126


if __name__ == "__main__":
    raise SystemExit(main())
