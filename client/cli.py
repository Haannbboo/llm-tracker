"""The client half of ``llm-tracker``.

One command, two components. This module is the client: the tracking wrapper,
agent configuration, sign-in, and the component report. It never imports the
server, so it runs on a machine that has only a client — a dependency on
``src`` would break that, and ``tests/client/test_no_server_imports.py``
enforces it.

The server component is reached through the launcher, which routes
``llm-tracker server ...`` to the shell scripts in the server checkout.
"""

from __future__ import annotations

import argparse
import sys

from client import auth, setup, status, track, update
from client.paths import client_version

PROG = "llm-tracker"

SUBCOMMANDS = ("login", "logout", "setup", "status", "update", "check-server")

EPILOG = """\
commands:
  login [--server URL]      sign in to a server and wire detected agents
  logout [--keep-agents]    remove this machine's credentials
  setup [--disable]         point detected agents at a collector
  status [--json]           report installed components and whether they run
  update [--check]          update whichever components are installed
  server <command>          start, stop, restart, bootstrap, status, token
                            (requires the server component)

anything else is run with usage tracking, e.g. `llm-tracker codex exec "hi"`
tracking options go before the command; use -- when they do:
  llm-tracker --json -- codex exec "hi"
"""

REMOVED = {
    "summary": (
        "llm-tracker: 'summary' is no longer a command. Evaluations now run in "
        "the background; see the dashboard."
    ),
    "server": (
        "llm-tracker: 'server' commands are handled by the launcher script, "
        "which resolves the server component."
    ),
}


def _add_banner_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-banner", action="store_true", help="do not print the llm-tracker banner"
    )


def _build_wrapper_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Run a command with usage tracking.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"{PROG} {client_version()}"
    )
    parser.add_argument(
        "--json", action="store_true", help="write the usage summary as compact JSON"
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
        help="where the usage summary is written",
    )
    parser.add_argument(
        "--summary-file", help="path to write the summary when --summary-dest=file"
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=3000,
        help="max milliseconds to wait for tracked usage after the command exits",
    )
    parser.add_argument(
        "--poll-ms",
        type=int,
        default=250,
        help="poll interval in milliseconds while waiting for the summary",
    )
    parser.add_argument(
        "--proxy-env",
        action="store_true",
        help="set OPENAI_BASE_URL and ANTHROPIC_BASE_URL for the child command",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="run tracking but skip printing the usage summary",
    )
    _add_banner_flag(parser)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def _build_subcommand(name: str) -> argparse.ArgumentParser:
    if name == "login":
        parser = argparse.ArgumentParser(
            prog=f"{PROG} login",
            description="Sign in to a server and wire detected agents.",
        )
        parser.add_argument("--server", help="server base URL")
        parser.add_argument("--device-name", help="device label for tokens")
        parser.add_argument(
            "--no-browser",
            action="store_true",
            help="print the login URL without opening a browser",
        )
        _add_banner_flag(parser)
        return parser
    if name == "logout":
        parser = argparse.ArgumentParser(
            prog=f"{PROG} logout",
            description="Remove this machine's credentials.",
        )
        parser.add_argument(
            "--keep-agents",
            action="store_true",
            help="leave agent configuration in place (it will be rejected)",
        )
        _add_banner_flag(parser)
        return parser
    if name == "setup":
        parser = argparse.ArgumentParser(
            prog=f"{PROG} setup",
            description="Point detected agents at a collector.",
        )
        parser.add_argument(
            "--disable",
            action="store_true",
            help="remove llm-tracker's telemetry settings instead of writing them",
        )
        _add_banner_flag(parser)
        return parser
    if name == "status":
        parser = argparse.ArgumentParser(
            prog=f"{PROG} status",
            description="Report installed components and whether they run.",
        )
        parser.add_argument(
            "--json", action="store_true", help="print one compact JSON line"
        )
        _add_banner_flag(parser)
        return parser
    if name == "update":
        parser = argparse.ArgumentParser(
            prog=f"{PROG} update",
            description="Update whichever components are installed.",
        )
        parser.add_argument(
            "--check", action="store_true", help="report without changing anything"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="print the planned commands"
        )
        parser.add_argument(
            "--scope", choices=("all", "client", "server"), default="all"
        )
        parser.add_argument(
            "--rebuild-plugins",
            action="store_true",
            help="rebuild agent plugins after updating",
        )
        _add_banner_flag(parser)
        return parser
    # check-server is internal: the installer uses it to refuse an incompatible box.
    parser = argparse.ArgumentParser(prog=f"{PROG} check-server")
    parser.add_argument("--server", required=True)
    _add_banner_flag(parser)
    return parser


def _run_tracking(argv: list[str]) -> int:
    parser = _build_wrapper_parser()
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.print_help()
        return 0

    options = track.options_from_args(args)
    if options.summary_dest == "file" and not options.summary_file:
        print("--summary-file is required when --summary-dest=file", file=sys.stderr)
        return 2
    if args.usage_only and args.no_summary:
        print("--usage-only cannot be combined with --no-summary", file=sys.stderr)
        return 2

    try:
        return track.run_with_tracking(command=command, options=options)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 127
    except PermissionError as exc:
        print(str(exc), file=sys.stderr)
        return 126


def _run_subcommand(name: str, argv: list[str]) -> int:
    parser = _build_subcommand(name)
    args = parser.parse_args(argv[1:])
    if name == "login":
        return auth.login(
            args.server, device_name_arg=args.device_name, no_browser=args.no_browser
        )
    if name == "logout":
        return auth.logout(keep_agents=args.keep_agents)
    if name == "setup":
        return setup.run_setup(disable=args.disable)
    if name == "status":
        return status.run_status(as_json=args.json)
    if name == "update":
        return update.run_update(
            check=args.check,
            dry_run=args.dry_run,
            scope=args.scope,
            rebuild_plugins=args.rebuild_plugins,
        )
    try:
        server = auth.normalize_server_url(args.server)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return auth.check_server(server)


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    first = raw[0] if raw else ""

    if first in REMOVED:
        print(REMOVED[first], file=sys.stderr)
        return 2
    if first in SUBCOMMANDS:
        return _run_subcommand(first, raw)
    return _run_tracking(raw)


if __name__ == "__main__":
    raise SystemExit(main())
