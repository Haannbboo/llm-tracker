# llm-tracker CLI Reference

Reference for the CLI as it exists now. `llm-tracker summary` and the isolated
tracking mode are gone; this document describes what remains. Per-command
behavior — including exit codes, the banner and the removed commands — is in
[cli-refactor.md](cli-refactor.md).

## Overview

`llm-tracker` is one command with two components. The client is always
installed; the server component is optional.

- **Client** — the tracking wrapper, agent configuration, sign-in, the component
  report. Reports to whichever collector it is pointed at.
- **Server** — the API, the OTLP collector, the proxy, the dashboard, the
  evaluation worker. Reached through `llm-tracker server ...`.

Anything that is not one of the subcommands below is run as a child command with
usage tracking: the wrapper records the usage high-watermark, runs the child,
then fetches the summary of everything recorded after that watermark. It uses
the collector that is already running — there is no temporary database,
collector or proxy per run, and nothing is started or stopped on your behalf. If
the API is not reachable the child still runs, untracked, and the exit code is
still the child's.

## Usage

```bash
llm-tracker [options] <command> [args...]
llm-tracker [options] -- <command> [args...]
llm-tracker <subcommand> [subcommand options]
llm-tracker server <command> [args...]
```

The `--` separator is optional for common agent commands. Use it after
llm-tracker flags when the child command or its first argument could be parsed
as a wrapper option.

## Commands

| Command | Component | Effect |
|---|---|---|
| `llm-tracker login [--server URL] [--device-name NAME] [--no-browser]` | client | Sign in and wire detected agents. Stores the server's `otlp_logs_endpoint`. |
| `llm-tracker logout [--keep-agents]` | client | Delete this machine's credentials, then un-wire the agents. |
| `llm-tracker setup [--disable]` | client | Point detected agents at a collector, or take llm-tracker's telemetry keys back off. |
| `llm-tracker status [--json]` | either | Report installed components, whether they run, and where agents point. |
| `llm-tracker update [--check\|--dry-run] [--scope all\|client\|server]` | either | Update installed components; `--check` checks server availability, while client availability is not published. |
| `llm-tracker check-server --server URL` | client | Internal: verify reachability and wire protocol. Writes nothing. |
| `llm-tracker <command> [args...]` | client | Run any command with usage tracking. |
| `llm-tracker server bootstrap` | server | Install, build the dashboard, start, verify, restart the API. |
| `llm-tracker server start` | server | Turn the services on. |
| `llm-tracker server stop [program...]` | server | Stop all services, or the named ones. |
| `llm-tracker server restart [--otlp-port N]` | server | Migrate, then reload the running services. |
| `llm-tracker server status [program...]` | server | Supervisord table, ports, port check. |
| `llm-tracker server token create --email EMAIL [--kind cli\|ingest\|web] [--name NAME]` | server | Mint an operator token on the server box. |
| `llm-tracker --version` | either | Client version, plus the server release when it is installed. |
| `llm-tracker --help`, `llm-tracker server --help` | either | Usage for the client and the service commands. |

`llm-tracker start`, `stop`, `restart`, `bootstrap` and `token` still work and
forward to the matching `llm-tracker server` command, printing a one-line note
on stderr. `status` is not one of them: it is the component report, and the
service view is `llm-tracker server status`.

## Examples

```bash
# Track an interactive Codex session
llm-tracker codex

# Track Claude Code
llm-tracker claude

# Track a single-shot Codex command
llm-tracker codex exec "say hello in one sentence"

# JSON summary
llm-tracker --json -- codex

# Machine-readable summary only (suppress child stdout/stderr)
llm-tracker --usage-only --json -- codex exec "hello"

# Write summary to a file
llm-tracker --summary-dest file --summary-file /tmp/llm-summary.json -- claude

# Route through the long-running local proxy
llm-tracker --proxy-env -- some-openai-compatible-cli

# Longer wait for late-arriving telemetry
llm-tracker --wait-ms 5000 -- codex exec "hello"

# No summary at all
llm-tracker --no-summary -- codex exec "say hello"

# What is installed, is it running, where do agents point
llm-tracker status
llm-tracker status --json

# Wire the agents this machine has on PATH
llm-tracker setup
llm-tracker setup --disable
```

Status redacts credentials and private paths from displayed endpoints. When the
running API cannot provide collector bind metadata, the OTLP service has state
`unknown` and a null port in JSON; the text view shows `:? unknown` and asks you
to check the collector configuration.
An unknown address alone does not mark the service as down.

## Tracking Flags

All tracking flags go before the child command; use `--` when they do.

| Flag | Default | Description |
|---|---|---|
| `--json` | off | Write the usage summary as a single-line compact JSON object. |
| `--usage-only` | off | Write only the summary to stdout and suppress child stdout/stderr. Implies `--summary-dest stdout`. Cannot combine with `--no-summary`. |
| `--summary-dest` | `stderr` | Where to write the summary: `stdout`, `stderr`, or `file`. |
| `--summary-file` | (none) | Path for `--summary-dest file`. Required when using that mode. |
| `--wait-ms` | `3000` | Milliseconds to poll for usage data after the child exits. |
| `--poll-ms` | `250` | Milliseconds between poll attempts. |
| `--proxy-env` | off | Replace `OPENAI_BASE_URL` and `ANTHROPIC_BASE_URL` for the child with the configured proxy. Refuse to launch if the proxy port is unreachable. |
| `--no-summary` | off | Skip the summary; just run the command and return its exit code. |
| `--no-banner` | off | Do not print the llm-tracker banner. Accepted by every subcommand too. |
| `--version` | — | Print the client version, and the server release when the server component is installed. |

## Tracking Model

One path, in both installation modes:

1. Read the usage high-watermark from the API — the signed-in server when the
   machine is signed in, the local server otherwise (`GET /usage/high-watermark`).
2. Run the child command. Nothing is started, and `--proxy-env` only adds two
   environment variables.
3. Poll `GET /usage/run-summary?after_ts=…` until `--wait-ms` expires. If
   nothing arrived, re-anchor on the current watermark and ask once more, so a
   run that recorded usage just after the deadline is not reported as empty.
4. Print the summary, or the JSON, to `--summary-dest`.

The summary covers all usage visible to the account after the starting
watermark. Concurrent commands and devices are included, and delayed events
outside the timestamp window can be omitted. It does not attribute cost
exclusively to the child command; use dashboard session views for that.
JSON summaries include an `attribution` object with scope
`account_activity_window`, `exclusive_to_command: false`,
`concurrent_runs_included: true`, and `delayed_events_may_be_omitted: true`.

The API being unreachable is not an error: the child runs, the exit code is the
child's, and the wrapper says so on stderr before the child starts and once more
after it.

`--proxy-env` requires a running proxy configured locally. Installing the hosted
client alone does not provide a proxy.

## Service Management

```bash
llm-tracker server status                              # supervisord table, ports, port check
llm-tracker server status llm-tracker-api              # one program
llm-tracker server start                               # services on; refuses if requirements.txt changed
llm-tracker server stop                                # all services
llm-tracker server stop llm-tracker-proxy              # one program
llm-tracker server restart                             # migrate, then SIGHUP the running services
llm-tracker server restart --otlp-port 5002            # persist a new OTLP port, then restart the collector
llm-tracker server bootstrap                           # install, build, start, verify, restart the API
llm-tracker server token create --email ops@example.com
```

Valid program names: `llm-tracker-proxy`, `llm-tracker-api`, `llm-tracker-otlp`.
The same scripts are in the checkout as `scripts/start.sh`, `scripts/stop.sh`,
`scripts/restart.sh`, `scripts/status.sh`, `scripts/bootstrap.sh` and
`scripts/update.sh`; `llm-tracker server …` is the interface to use.

`llm-tracker start`, `stop`, `restart`, `bootstrap` and `token` are still
accepted as aliases, with a one-line note on stderr.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success, or the command ran and reported what it found. `llm-tracker status` exits 0 when nothing installed is broken; not being signed in is not a fault. |
| 1 | Something installed is broken, or a check failed: a stopped service, a detected agent pointing at another collector, `setup` with no collector or nothing wireable, a failed sign-in or update, `logout` with no credentials. |
| 2 | Argument validation error, a removed command (`summary`), or an unknown `server` subcommand. |
| 126 | Child command is not executable. |
| 127 | Child command not found. |
| 128+N | Child killed by signal N. |
| Other | The child command's own exit code. |

## Configuration

Server config lives at `~/.llm-tracker/config.yaml` (override the path with
`LLM_TRACKER_CONFIG`). A template is provided at `config.example.yaml`. The
client reads only the `server:` section, so a config written by a different
version cannot break it.

```yaml
models:
  gpt-5.4:
    cost:
      input: 2.5        # USD per million input tokens
      output: 15.0       # USD per million output tokens
      cacheRead: 0.25    # USD per million cached input tokens

providers:
  my-provider:
    base_url: https://api.example.com/v1
    models:
      gpt-5.4: {}

server:
  host: 127.0.0.1
  port: 4000        # Proxy port
  api_port: 4001    # API port
  otlp_port: 4002   # OTLP collector port

db:
  path: ~/.llm-tracker/usage.db   # SQLite (default)
  # url: postgresql+psycopg://user:pass@host:5432/db
```

`llm-tracker server start` merges missing defaults from `config.example.yaml`
into the user config without overwriting existing values. `llm-tracker server
restart` does not touch config at all, except to persist `--otlp-port`.

Client state, all under `$LLM_TRACKER_HOME` (default `~/.llm-tracker`):

| Path | Owner | Contents |
|---|---|---|
| `current` | client | Symlink to the active client source snapshot. |
| `versions/` | client | Previous client snapshots. |
| `credentials.json` | client | Signed-in identity, CLI and ingest tokens, `otlp_logs_endpoint`. Mode `0600`. |
| `config.yaml` | server | Server config. |
| `supervisord.conf` | server | Written by `server start`. |
| `run/` | server | supervisord pid and socket. |

## Environment Variables

| Variable | Description |
|---|---|
| `LLM_TRACKER_HOME` | Override the tracker home directory (default `~/.llm-tracker`). |
| `LLM_TRACKER_ROOT` | Path to the server checkout. Overrides `$LLM_TRACKER_HOME/src`; used by worktrees and tests. |
| `LLM_TRACKER_CONFIG` | Override the config file path. |
| `LLM_TRACKER_BIN_DIR` | Where the launcher is installed (default `~/.local/bin`). |
| `LLM_TRACKER_CLIENT_COMMIT` | Commit to report for the client, when the snapshot has no `COMMIT` file. |
| `LLM_TRACKER_SKIP_BANNER` | Set by the launcher so a script it calls does not print a second banner. `bootstrap.sh` and `start.sh` honor it; `restart.sh`, `status.sh` and `update.sh` do not. |
| `LLM_TRACKER_SKIP_INSTALL` | `1` makes `bootstrap` skip dependency installation and record the requirements stamp anyway. |
| `LLM_TRACKER_SERVER` | Server URL `llm-tracker update` passes to the hosted installer, and the default the hosted installer reads instead of its baked-in server URL. |
| `LLMTRACKER_SERVER` | Fallback server URL for `llm-tracker login` when `--server` is absent. |
| `LLM_TRACKER_INGEST_TOKEN` | Set by `llm-tracker setup` on the agent configure scripts when signed in, so agents send the device ingest token. |
| `LLM_TRACKER_DB_URL` | Override the database URL at runtime (server side; removed from the child's env by `--proxy-env`). |
| `LLM_TRACKER_API_URL` | Frontend-only: override the API base URL used by the Vite dev server. |
| `OPENAI_BASE_URL` | Set by `--proxy-env` to route OpenAI-compatible clients through the proxy. |
| `ANTHROPIC_BASE_URL` | Set by `--proxy-env` to route Anthropic-compatible clients through the proxy. |
| `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` | The agent telemetry endpoint. `llm-tracker setup` strips any pre-existing value before writing its own. |
| `NO_COLOR` | No color. The banner still prints. |

## API Endpoints

The API service runs at `http://127.0.0.1:4001` by default, and at the
signed-in server's origin on a client-only machine.

```bash
curl http://127.0.0.1:4001/usage?limit=20
curl http://127.0.0.1:4001/usage/summary
curl http://127.0.0.1:4001/usage/daily
curl http://127.0.0.1:4001/usage/high-watermark
curl http://127.0.0.1:4001/usage/run-summary?after_ts=0
curl http://127.0.0.1:4001/config
curl http://127.0.0.1:4001/local/setup-health
curl http://127.0.0.1:4001/version
```

`/version` is public when auth is enabled, and carries the wire protocol range,
the server release, and `otlp_logs_endpoint` — the collector clients point agents
at. Its `collector_bind` host/port fields describe server-local listener
addresses for status diagnostics; they are not hosted client wiring targets.
No URL credentials or paths are included in those bind fields. Authenticated
ingestion still requires its token. A client that signed in before the endpoint
was published reads it once from here and stores it in `credentials.json` for
later agent endpoint checks. Status also queries the local API for bind metadata
when the server component is installed.

Query params for `/usage`: `limit`, `offset`, `provider`, `model`, `since`, `until`.

Query params for `/usage/daily`: `since`, `until`, `provider`, `model`, `granularity`, `tz_offset`.

Query params for `/usage/run-summary`: `after_ts`, `until_ts`, `since`, `until`,
`client_source`, `session_id`, `provider`, `model`, `include_rows`. The wrapper
sends only `after_ts`, plus `until_ts` on the re-anchor pass.

## Helper Scripts

| Script | Purpose |
|---|---|
| `scripts/sync-config.py` | Merge missing defaults into the user config. Run by `server start`. |
| `scripts/migrate_schema.py` | Apply database schema migrations. Run by `server start` and `server restart`. |
| `scripts/check-service-ports.py` | Detect port conflicts before starting services. |
| `scripts/auto-assign-ports.py` | Pick free ports on a first run. |
| `scripts/configure-claude-settings.py` | Configure Claude Code OTLP telemetry. |
| `scripts/configure-codex-settings.py` | Configure Codex OTLP telemetry. |
| `scripts/configure-opencode-plugin.py` | Configure the OpenCode plugin OTLP telemetry. |
| `scripts/configure-kilo-plugin.py` | Configure the Kilo Code plugin OTLP telemetry. |

The four `configure-*.py` scripts are the ones `llm-tracker setup` shells out to;
they own the agent file formats. The server never calls them.
