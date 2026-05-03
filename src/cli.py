from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from config.app import CONFIG
from .provider_parser import parse_provider_metadata


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


@dataclass(frozen=True)
class SessionFileState:
    mtime_ns: int
    size: int


CODEX_EXEC_ENDPOINT = "generate-codex-session"


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

    def record_usage(self, usage: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/usage", json_body=usage)

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

    def _post_json(
        self,
        path: str,
        *,
        json_body: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}{path}",
                json=json_body,
                timeout=5,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise ApiError(str(exc)) from exc


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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="llm-tracker")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--summary-dest",
        choices=("stdout", "stderr", "file"),
        default="stderr",
    )
    parser.add_argument("--summary-file")
    parser.add_argument("--wait-ms", type=int, default=3000)
    parser.add_argument("--poll-ms", type=int, default=250)
    parser.add_argument("--proxy-env", action="store_true")
    parser.add_argument("--no-summary", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args


def options_from_args(args: argparse.Namespace) -> RunOptions:
    return RunOptions(
        json_output=args.json,
        summary_dest=args.summary_dest,
        summary_file=args.summary_file,
        wait_ms=args.wait_ms,
        poll_ms=args.poll_ms,
        proxy_env=args.proxy_env,
        no_summary=args.no_summary,
    )


def build_child_env(options: RunOptions) -> dict[str, str] | None:
    if not options.proxy_env:
        return None

    env = os.environ.copy()
    openai_base_url, anthropic_base_url = build_proxy_base_urls()
    env.setdefault("OPENAI_BASE_URL", openai_base_url)
    env.setdefault("ANTHROPIC_BASE_URL", anthropic_base_url)
    return env


def _is_codex_exec_command(command: list[str]) -> bool:
    if not command:
        return False
    if Path(command[0]).name != "codex":
        return False
    return "exec" in command[1:]


def _codex_sessions_root() -> Path:
    return Path.home() / ".codex" / "sessions"


def _snapshot_codex_session_files(
    sessions_root: Path | None = None,
) -> dict[Path, SessionFileState]:
    root = sessions_root or _codex_sessions_root()
    if not root.exists():
        return {}

    snapshot: dict[Path, SessionFileState] = {}
    for path in root.glob("**/*.jsonl"):
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshot[path] = SessionFileState(mtime_ns=stat.st_mtime_ns, size=stat.st_size)
    return snapshot


def _changed_codex_session_files(
    snapshot: dict[Path, SessionFileState],
    sessions_root: Path | None = None,
) -> list[Path]:
    root = sessions_root or _codex_sessions_root()
    if not root.exists():
        return []

    changed: list[tuple[int, Path]] = []
    for path in root.glob("**/*.jsonl"):
        try:
            stat = path.stat()
        except OSError:
            continue
        previous = snapshot.get(path)
        if previous is None or (
            previous.mtime_ns != stat.st_mtime_ns or previous.size != stat.st_size
        ):
            changed.append((stat.st_mtime_ns, path))
    return [path for _, path in sorted(changed, reverse=True)]


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _codex_timestamp_to_iso(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.now(timezone.utc).isoformat()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _same_cwd(left: str, right: str) -> bool:
    return os.path.abspath(left) == os.path.abspath(right)


def extract_codex_exec_usage_from_session(
    path: Path,
    *,
    command_cwd: str | None = None,
) -> dict[str, Any] | None:
    session_meta: dict[str, Any] = {}
    turn_context: dict[str, Any] = {}
    last_token_usage: dict[str, Any] | None = None
    task_complete: dict[str, Any] | None = None
    task_complete_ts: str | None = None

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        entry_type = entry.get("type")
        payload = entry.get("payload") or {}
        if entry_type == "session_meta":
            session_meta = payload
        elif entry_type == "turn_context":
            turn_context = payload
        elif entry_type == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info") or {}
            usage = info.get("last_token_usage")
            if isinstance(usage, dict):
                last_token_usage = usage
        elif entry_type == "event_msg" and payload.get("type") == "task_complete":
            task_complete = payload
            task_complete_ts = entry.get("timestamp")

    if session_meta.get("originator") != "codex_exec":
        return None
    if session_meta.get("source") != "exec":
        return None

    cwd = session_meta.get("cwd") or turn_context.get("cwd")
    if command_cwd and cwd and not _same_cwd(str(cwd), command_cwd):
        return None

    session_id = session_meta.get("id")
    if not session_id or not last_token_usage:
        return None

    prompt_tokens = _to_int(last_token_usage.get("input_tokens")) or 0
    completion_tokens = _to_int(last_token_usage.get("output_tokens")) or 0
    cached_tokens = _to_int(last_token_usage.get("cached_input_tokens"))
    reasoning_tokens = _to_int(last_token_usage.get("reasoning_output_tokens"))
    total_tokens = _to_int(last_token_usage.get("total_tokens"))
    if total_tokens is None:
        total_tokens = prompt_tokens + completion_tokens

    task_complete = task_complete or {}
    metadata = parse_provider_metadata("codex")

    return {
        "ts": _codex_timestamp_to_iso(
            task_complete_ts or session_meta.get("timestamp")
        ),
        "provider": metadata.provider,
        "model": turn_context.get("model")
        or session_meta.get("model")
        or "codex-unknown",
        "client_source": "codex",
        "session_id": str(session_id),
        "endpoint": CODEX_EXEC_ENDPOINT,
        "prompt_tokens": prompt_tokens,
        "prompt_length": 0,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens,
        "reasoning_tokens": reasoning_tokens,
        "tool_tokens": None,
        "cache_creation_tokens": None,
        "total_tokens": total_tokens,
        "latency_ms": _to_int(task_complete.get("duration_ms")),
        "ttft_ms": _to_int(task_complete.get("time_to_first_token_ms")),
        "status": None,
        "base_url": metadata.base_url,
        "base_url_source": metadata.source,
    }


def record_codex_exec_usage_fallback(
    *,
    command: list[str],
    client: UsageApiClient,
    after_id: int,
    session_snapshot: dict[Path, SessionFileState],
    command_cwd: str,
) -> dict[str, Any] | None:
    if not _is_codex_exec_command(command):
        return None

    for session_file in _changed_codex_session_files(session_snapshot):
        usage = extract_codex_exec_usage_from_session(
            session_file,
            command_cwd=command_cwd,
        )
        if usage is None:
            continue

        try:
            existing = client.get_run_summary(
                after_id=after_id,
                client_source="codex",
                session_id=usage["session_id"],
            )
        except ApiError as exc:
            print(
                f"Codex exec usage fallback skipped: {exc}",
                file=sys.stderr,
            )
            return None

        if int(existing.get("summary", {}).get("requests", 0) or 0) > 0:
            return None

        try:
            client.record_usage(usage)
        except ApiError as exc:
            print(
                f"Codex exec usage fallback failed: {exc}",
                file=sys.stderr,
            )
            return None
        return usage

    return None


def run_with_tracking(
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

    codex_session_snapshot = (
        _snapshot_codex_session_files() if _is_codex_exec_command(command) else None
    )
    command_cwd = os.getcwd()
    completed = subprocess.run(command, env=build_child_env(options))
    child_code = _normalize_return_code(int(completed.returncode))

    if before_id is not None and codex_session_snapshot is not None:
        record_codex_exec_usage_fallback(
            command=command,
            client=client,
            after_id=before_id,
            session_snapshot=codex_session_snapshot,
            command_cwd=command_cwd,
        )

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
    options = options_from_args(args)
    if options.summary_dest == "file" and not options.summary_file:
        print("--summary-file is required when --summary-dest=file", file=sys.stderr)
        return 2

    try:
        return run_with_tracking(
            command=args.command,
            client=UsageApiClient(),
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
