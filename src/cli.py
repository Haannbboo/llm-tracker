"""The server component's CLI: operator commands that need the database.

Everything a per-user client does — the tracking wrapper, sign-in, agent
configuration, status — lives in ``client/`` and never imports this module.
``tokenage server <command>`` routes the service commands to the shell
scripts; the launcher routes ``tokenage server token`` here.
"""

from __future__ import annotations

import argparse
import secrets
import sys

from src.auth import mint_token
from src.database import init_db

PROG = "tokenage server"


def parse_token_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=f"{PROG} token",
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
    return parser.parse_args(argv)


def run_token_command(argv: list[str]) -> int:
    token_args = parse_token_args(argv)

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


def run_login_link_command() -> int:
    from src.auth.google import store_login_code
    from src.auth.routes import auth_provider
    from src.config.app import CONFIG
    from src.config.server_config import resolve_server_urls

    if auth_provider() != "local":
        print("login-link only applies to auth.provider: local", file=sys.stderr)
        return 2
    code = secrets.token_urlsafe(24)
    store_login_code(code)
    api_url = resolve_server_urls(CONFIG)["api_url"]
    print(f"{api_url}/auth/local/login?code={code}")
    print("Single use; expires in 5 minutes.", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "token":
        return run_token_command(args[1:])
    if args and args[0] == "login-link":
        return run_login_link_command()
    print(f"usage: {PROG} token create --email <email> | login-link", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
