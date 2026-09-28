"""Run any command with usage tracking and report what it cost.

One path: read the usage high-watermark, run the child against the collector
that is already running, then ask for the summary of everything recorded after
that watermark. Nothing is started and nothing is stopped, so a run never
leaves a process behind and never has to merge a scratch database.

The API is the local one unless this machine is signed in, in which case it is
the signed-in server and the summary comes back over the network.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from client.paths import local_server_info


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


class UsageApiClient:
    """Reads run summaries from whichever server this machine reports to."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        from client.auth import load_credentials

        credentials = load_credentials() or {}
        if base_url is None:
            base_url = credentials.get("server_url") or local_server_info()["api_url"]
        self.base_url = str(base_url)
        if token is None:
            candidate = credentials.get("cli_token")
            token = candidate if isinstance(candidate, str) else None
        self.token = token

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
        self, path: str, *, params: dict[str, Any] | None = None
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


def options_from_args(args) -> RunOptions:
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
    return {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


def build_child_env(options: RunOptions) -> dict[str, str] | None:
    """Point the child at the running collector, and at the proxy with --proxy-env.

    Both use the long-running services. There is no per-run proxy.
    """
    if not options.proxy_env:
        return None
    info = local_server_info()
    env = os.environ.copy()
    env.pop("LLM_TRACKER_DB_URL", None)
    env.setdefault("OPENAI_BASE_URL", f"{info['proxy_url']}/v1")
    env.setdefault("ANTHROPIC_BASE_URL", info["proxy_url"])
    return env


def _normalize_return_code(returncode: int) -> int:
    if returncode < 0:
        return 128 + abs(returncode)
    return returncode


def poll_summary(
    client: UsageApiClient, *, after_ts: int, options: RunOptions
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

    # Nothing arrived within the wait window. Re-anchor on the current
    # watermark so a run that recorded usage just after the deadline is not
    # reported as empty.
    try:
        until_ts = client.get_high_watermark()
    except ApiError as exc:
        print(f"llm-tracker API error: {exc}", file=sys.stderr)
        return latest_summary

    try:
        return client.get_run_summary(after_ts=after_ts, until_ts=until_ts)
    except ApiError as exc:
        print(f"llm-tracker API error: {exc}", file=sys.stderr)
        return None


def run_with_tracking(*, command: list[str], options: RunOptions) -> int:
    client = UsageApiClient()
    before_ts: int | None
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

    summary = poll_summary(client, after_ts=before_ts, options=options)
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


def write_summary(summary: dict[str, Any], options: RunOptions) -> None:
    content = (
        json.dumps(summary, separators=(",", ":"))
        if options.json_output
        else format_human_summary(summary)
    )
    content += "\n"

    if options.summary_dest == "file":
        if not options.summary_file:
            raise ApiError("--summary-file is required when --summary-dest=file")
        Path(options.summary_file).write_text(content, encoding="utf-8")
    elif options.summary_dest == "stdout":
        print(content, end="")
    else:
        print(content, end="", file=sys.stderr)


def _format_ms(value: Any) -> str:
    if value is None:
        return "n/a"
    ms = float(value)
    if ms >= 1000:
        return f"{ms / 1000:.2f}s"
    return f"{ms:.0f}ms"


def format_human_summary(summary: dict[str, Any]) -> str:
    totals = summary.get("summary", {})
    requests = int(totals.get("requests", 0) or 0)
    if requests == 0:
        return "No llm-tracker usage recorded for this command.\n"

    total_tokens = int(totals.get("total_tokens", 0) or 0)
    cached_tokens = int(totals.get("cached_tokens", 0) or 0)
    cache_hit_rate = float(totals.get("cache_hit_rate", 0) or 0)
    total_cost = float(totals.get("total_cost_usd", 0) or 0)

    lines = [
        "llm-tracker usage summary",
        (
            f"requests: {requests}, total tokens: {total_tokens:,}, "
            f"cached: {cached_tokens:,} ({cache_hit_rate:.0%})"
        ),
        (
            f"latency avg: {_format_ms(totals.get('avg_latency_ms'))}, "
            f"ttft avg: {_format_ms(totals.get('avg_ttft_ms'))}, "
            f"cost: ${total_cost:.4f}"
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
