# llm-tracker CLI: user-facing behavior

Status: implemented. One `llm-tracker` command is the entry point on every
machine; what it can do depends on which components are installed.

Every human-facing command prints the llm-tracker banner first — see
[Banner](#banner). The sample output below omits it.

| Command | Component | Effect |
| --- | --- | --- |
| `llm-tracker login` | client | Sign in to a server and wire detected agents. |
| `llm-tracker logout` | client | Remove this machine's credentials. |
| `llm-tracker setup` | client | Point detected agents at a collector. No auth, no service control. |
| `llm-tracker status` | either | Report installed components and whether they run. |
| `llm-tracker update` | either | Update whichever components are installed. |
| `llm-tracker <command> ...` | client | Run any command with usage tracking and print the run summary. |
| `llm-tracker server start` | server | Turn the services on. Nothing else. |
| `llm-tracker server stop` | server | Stop services. |
| `llm-tracker server restart` | server | Reload running services so new backend code takes effect. |
| `llm-tracker server bootstrap` | server | Install, build the dashboard, start, verify. |
| `llm-tracker server status` | server | Supervisord table, ports, port check. |
| `llm-tracker server token create` | server | Mint an operator token. |

`llm-tracker check-server --server URL` also exists and is internal: the
installer uses it to refuse a box whose wire protocol this client cannot speak.
It writes nothing.

Two components, one command:

- **Client** (`client/`) — the tracking wrapper, agent configuration, sign-in and
  the component report. Owns `$LLM_TRACKER_HOME/credentials.json` and
  `installation.json`, both mode `0600`. Depends only on `httpx` and `pyyaml`,
  and never imports `src`.
- **Server** (`src/`, `scripts/`) — the API, the OTLP collector, the proxy, the
  dashboard, pricing, storage and the evaluation worker. Owns
  `~/.llm-tracker/config.yaml`, `supervisord.conf` and the database.

An all-in-one install has both. A remote machine installs only the client, and
every `llm-tracker server ...` command reports that the server component is not
installed instead of failing obscurely.

The launcher `scripts/llm-tracker` is the single entry point both installers
write. It resolves the two components separately: the client from
`$LLM_TRACKER_HOME/current` (a source snapshot with its own virtualenv) and the
server from `$LLM_TRACKER_ROOT` or `$LLM_TRACKER_HOME/src` (a git clone). When
the snapshot has no virtualenv of its own, the client runs under the server's.

Server startup no longer edits user agent settings. The client owns agent
configuration in both installation modes, via `setup` and `login`.

---

## Banner

Every command starts by printing the banner, so a user always knows which tool is
talking to them — including on a client-only machine that has no server at all.
It is decoration, so it goes to stderr and disappears whenever the output is for
a machine.

```
$ llm-tracker status
  ██╗      ██╗      ███╗   ███╗    ████████╗██████╗  █████╗  ██████╗██╗  ██╗███████╗██████╗
  ██║      ██║      ████╗ ████║    ╚══██╔══╝██╔══██╗██╔══██╗██╔════╝██║ ██╔╝██╔════╝██╔══██╗
  ██║      ██║      ██╔████╔██║       ██║   ██████╔╝███████║██║     █████╔╝ █████╗  ██████╔╝
  ██║      ██║      ██║╚██╔╝██║       ██║   ██╔══██╗██╔══██║██║     ██╔═██╗ ██╔══╝  ██╔══██╗
  ███████╗ ███████╗ ██║ ╚═╝ ██║       ██║   ██║  ██║██║  ██║╚██████╗██║  ██╗███████╗██║  ██║
  ╚══════╝ ╚══════╝ ╚═╝     ╚═╝       ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝

  llm-tracker 0.1.0 (client 89075ce) · server 0.2.19 (self-hosted)
  ...
```

Rules:

- **Full art on a terminal 95 columns or wider, compact art below that.** Same
  rule `banner()` uses in `scripts/lib/terminal.sh`, so no new widths to remember.
- **Always on stderr, never stdout.** A tracked child command's stdout stays
  exactly what the child wrote, and the TTY test is on stderr because that is
  the stream the banner goes to. (The color test in `terminal.sh` is still on
  stdout.)
- **The launcher prints it, and the scripts it calls are told not to.**
  `LLM_TRACKER_SKIP_BANNER=1` is exported, and `bootstrap.sh` and `start.sh`
  honor it, so `llm-tracker server bootstrap` prints one banner rather than
  three. `restart.sh`, `status.sh` and `update.sh` print their own banner
  unconditionally, so those three commands show it twice.
- **Suppressed when the output is for a machine**: stderr is not a TTY, or the
  arguments contain `--json`, `--usage-only`, `--no-banner`, or
  `--summary-dest` with the value `file` or `stdout`. Structured output stays
  parseable.
- **`--no-banner` turns it off for one command.** It is accepted by every
  subcommand as well as the tracking wrapper. Without it, `llm-tracker claude`
  pushes an interactive TUI down by eight lines on every launch.
- **Colors follow the existing rule**: colored on a TTY, plain when piped,
  plain under `NO_COLOR`. The banner itself still prints under `NO_COLOR` —
  that flag has always meant "no color", not "no banner".
- **`banner()` lives in `scripts/lib/terminal.sh`.** The client has no banner of
  its own. The launcher sources that file from the server clone, or from the
  client snapshot when there is no server component, and prints nothing when
  neither has it.

---

## `llm-tracker status`

Answers three questions in one screen: what is installed, is it running, and
where are my agents pointed. It never fails because something is *absent* — only
because something installed is broken. It is not an alias for anything; the old
service view is `llm-tracker server status`.

### Layout

Line 1 is versions. Every other line is `label` + value, label padded to 12
columns, in this order, each printed only when it applies:

1. versions
2. `services` — server component installed
3. `account` — always; either the signed-in identity or `not signed in`
4. `device` — signed in, and no server component on this machine
5. `agents` — always
6. `dashboard` — server component installed
7. `fix` — only when something is wrong, naming the command that repairs it

### All-in-one install, everything up

```
$ llm-tracker status
llm-tracker 0.1.0 (client 89075ce) · server 0.2.19 (self-hosted)
  services    proxy :4000 up · api :4001 up · otlp :4002 up
  account     signed in as you@example.com → http://localhost:4001
  agents      codex, claude, opencode → http://localhost:4002/v1/logs
  dashboard   http://localhost:4001
```

The `agents` line lists only the detected agents that point where this install
intends, and the first one's endpoint stands for all of them. It reads
`none detected` when no tracked agent is on `PATH`, and `none wired` when
agents are detected but none points at the intended collector.

### All-in-one install, services stopped

```
$ llm-tracker status
llm-tracker 0.1.0 (client 89075ce) · server 0.2.19 (self-hosted)
  services    proxy :4000 down · api :4001 down · otlp :4002 down
  account     signed in as you@example.com → http://localhost:4001
  agents      codex, claude, opencode → http://localhost:4002/v1/logs (not reachable)
  dashboard   http://localhost:4001
  fix         run llm-tracker server start
```

Exit code 1. `(not reachable)` appears when a service is down and there is
still something wired to show.

### Client-only install, signed in

```
$ llm-tracker status
llm-tracker 0.1.0 (client 89075ce)
  account     signed in as you@example.com → https://app.example.com
  device      hanbo-macbook
  agents      codex, claude → https://app.example.com/v1/logs
```

No `services` and no `dashboard` line: there is no server on this machine. The
`device` line is the mirror image of that — it is shown only on a client-only
install, where the machine identity is the useful fact.

### Client-only install, not signed in

```
$ llm-tracker status
llm-tracker 0.1.0 (client 89075ce)
  account     not signed in
  agents      none wired
  fix         run llm-tracker login --server <url>
```

Exit code 0. Not being signed in is a fact, not a fault.

### `fix` precedence

Only one `fix` line is printed, and the first of these that applies wins:

1. a detected agent is not wired → `run llm-tracker setup`
2. the server component is installed and a service is not up →
   `run llm-tracker server start`
3. no server component and not signed in →
   `run llm-tracker login --server <url>`

### `--json`

One compact line, same fields, for scripts:

```
$ llm-tracker status --json
{"client":{"version":"0.1.0","commit":"89075ce1f4b7d2e6a9c0b3d8e5f2a7c1b4d90e33"},"server":{"installed":true,"version":"0.2.19","mode":"self-hosted","services":[{"name":"proxy","port":4000,"state":"up","supervised":true},{"name":"api","port":4001,"state":"up","supervised":true},{"name":"otlp","port":4002,"state":"up","supervised":true}]},"account":{"signed_in":true,"email":"you@example.com","server_url":"http://localhost:4001","device_name":"hanbo-macbook"},"agents":[{"name":"codex","installed":true,"detected":true,"configured":true,"endpoint_matches":true,"endpoint":"http://localhost:4002/v1/logs"},{"name":"claude","installed":true,"detected":true,"configured":true,"endpoint_matches":true,"endpoint":"http://localhost:4002/v1/logs"},{"name":"opencode","installed":true,"detected":true,"configured":true,"endpoint_matches":true,"endpoint":"http://localhost:4002/v1/logs"},{"name":"kilo","installed":true,"detected":false,"configured":false,"endpoint_matches":false,"endpoint":null}],"dashboard":"http://localhost:4001"}
```

Field notes:

- `client.commit` is a 40-character git SHA or `null`; it is `null` for a
  snapshot with no `COMMIT` file and no `LLM_TRACKER_CLIENT_COMMIT`.
- `server` is `{"installed": false}` and nothing else when the server component
  is absent, and carries `version`, `mode` and `services` when it is present.
- `service.supervised` is `true`/`false` from `supervisorctl`, or `null` when
  supervisord cannot be asked at all (no `supervisord.conf`, no `supervisorctl`).
- `account.device_name` is present only when the credentials carry one; an
  absent account is `{"signed_in": false, "email": null, "server_url": null}`.
- `agents` is always all four agents — `codex`, `claude`, `opencode`, `kilo` —
  in that order, with `installed` (llm-tracker ships a configure script for it),
  `detected` (found on `PATH`), `configured` (its config file has the keys),
  `endpoint_matches` and `endpoint` (what it actually points at, `null` when
  unconfigured). `dashboard` is the local API URL, or `null` with no server
  component.

### Rules

- Reads state only. Creates no files, starts no services.
- Works with no `config.yaml`, no `supervisord.conf`, no `credentials.json` — the
  normal case on a fresh client-only machine.
- "up" for a service means supervisord reports `RUNNING` **and** the port
  accepts a connection. Supervisord alone is not enough.
- "wired" for an agent means the endpoint in the agent's own config file equals
  the endpoint this install intends — the same comparison
  `GET /local/setup-health` already makes, so `status` and the dashboard cannot
  disagree.

---

## Start, restart, bootstrap

The three service commands are separated by *what you changed*, not by which
script grew where. Each does one job, and running the wrong one is cheap.

| After you… | Run | Cost |
| --- | --- | --- |
| reboot the machine | `llm-tracker server start` | seconds |
| edit backend Python | `llm-tracker server restart` | instant |
| change `requirements.txt`, pull new code, edit the frontend | `llm-tracker server bootstrap` | minutes |
| install a new agent, or point agents at a different collector | `llm-tracker setup` | seconds |

`start` is what runs at boot, so it is deliberately the dullest: it turns
services on and nothing else. `restart` is the hammer for code edits, so it does
nothing but reload processes — no installs, no builds, no config writes. You can
run it fifty times an hour without thinking about it. `bootstrap` is the heavy
one: install, build, start, verify.

## `llm-tracker server start`

Turns the services on. Idempotent — safe to run when they are already up.

It creates `config.yaml` from `config.example.yaml` if absent, syncs missing
defaults into it, checks the configured ports (auto-assigning on a first run
only), applies schema migrations, and starts supervisord and the three
programs. If supervisord is already running it reloads rather than starting a
second one.

```
$ llm-tracker server start
  ✓ Dependencies up to date
  ✓ Config exists: /home/you/.llm-tracker/config.yaml
  ✓ Port check passed
  Applying schema migrations...
  ✓ Migrations applied
  ✓ Supervisord started
  ✓ llm-tracker-proxy: running
  ✓ llm-tracker-api: running
  ✓ llm-tracker-otlp: running

  ───────────────────────────────────────────
  🚀 llm-tracker is LIVE → http://localhost:4001
```

What it deliberately does **not** do:

- **No dependency install.** If `requirements.txt` changed since the last
  install, it refuses with the command to run:

  ```
  ✗ Dependencies are out of date (requirements.txt changed)
    run llm-tracker server bootstrap
  ```

  The check is the `requirements.txt` hash stamp already written to
  `.venv/.requirements.sha256`, so it costs one `sha256sum`.
- **No frontend build.** That is `bootstrap`.
- **No agent configuration.** That is `setup`, in both installation modes. Agent
  wiring is never edited by the server.
- **No API restart because `frontend/dist` exists.** Restarting the API to pick
  up a new dashboard build belongs to `bootstrap`, which is the only command
  that builds.

Flags: none. It takes no program names; it manages all three services as a set,
and reloading a single program is not something this command can express.

Fails with `Port check failed` and a table of conflicting ports when a configured
port is held by a process supervisord does not own.

## `llm-tracker server stop`

```
$ llm-tracker server stop
  Stopping all programs...
  ✓ All services stopped
```

With program names, stops only those:

```
$ llm-tracker server stop llm-tracker-proxy
  Stopping llm-tracker-proxy...
  ✓ llm-tracker-proxy: stopped
```

Valid names: `llm-tracker-proxy`, `llm-tracker-api`, `llm-tracker-otlp`.
Prints `Not running.` and exits 0 when `supervisord.conf` is absent.

## `llm-tracker server restart`

Reloads the running services so new backend code takes effect. Nothing else.

It refuses when nothing is running, applies pending schema migrations, sends
`SIGHUP` to each *running* service, and leaves stopped services stopped, naming
them and pointing at `llm-tracker server start`. Migrations stay in here on
purpose: they are idempotent and take milliseconds, and dropping them would mean
`git pull` followed by `restart` serves code against an old schema.

```
$ llm-tracker server restart
  ▶ Pre-flight checks
  ...

  ▶ Applying schema migrations
  ✓ Migrations applied

  ▶ Reloading services
  Sending SIGHUP to llm-tracker-proxy...
  ✓ llm-tracker-proxy: reloaded
  Sending SIGHUP to llm-tracker-api...
  ✓ llm-tracker-api: reloaded
  Sending SIGHUP to llm-tracker-otlp...
  ✓ llm-tracker-otlp: reloaded

  ───────────────────────────────────────────
  🚀 llm-tracker is LIVE → http://localhost:4001
```

What it deliberately does **not** do — all of this is `start` or `bootstrap`
and does not belong in a code reload:

- No dependency install, no frontend build.
- No config sync and no port check.
- No agent configuration.
- It never turns a stopped service on.

`--otlp-port N` persists the new port in `config.yaml` and fully restarts the
collector instead of reloading it, because the port is baked into the process.
This is the only flag `restart` takes, and the only one that writes config, since
the value has to be persisted before the collector can be reloaded with it.

## `llm-tracker server status`

The old `llm-tracker status`: the supervisord table, the configured ports, and
the port check. For operators who want only the service view.

```
$ llm-tracker server status
llm-tracker-proxy    RUNNING   pid 21455, uptime 3:11:02
llm-tracker-api      RUNNING   pid 21456, uptime 3:11:02
llm-tracker-otlp     RUNNING   pid 21457, uptime 3:11:02

  ▶ Port Information
    Proxy: 127.0.0.1:4000
    API:   127.0.0.1:4001
    OTLP:  127.0.0.1:4002

  ▶ Port Check
```

Accepts optional program names. Exit code 1 when no `supervisord.conf` exists.

## `llm-tracker server bootstrap`

Installs, builds, starts, verifies. The command for "I changed dependencies, the
frontend, or pulled new code".

It installs uv and the virtualenv, runs `uv pip install -r requirements.txt`,
builds the dashboard with npm, (re)creates the CLI symlink, then runs
`server start` and verifies the result. Exit code 0 when every check passes, 1
otherwise.

```
$ llm-tracker server bootstrap
  ▶ Installing dependencies & CLI
  Setting up llm-tracker environment...
  Creating venv...
  Installing dependencies...
  Building frontend (Node v22.14.0)...
  Frontend built: /home/you/.llm-tracker/src/frontend/dist
  Setting up CLI symlink...
  Installation complete! You can now use 'llm-tracker' (if in PATH) or 'scripts/start.sh'.

  ▶ Starting services
  ...

  ▶ Running post-start checks
  ✓ Config: /home/you/.llm-tracker/config.yaml
  ✓ CLI wrapper: scripts/llm-tracker
  ✓ CLI symlink: /home/you/.local/bin/llm-tracker
  ✓ API running: http://localhost:4001
  ✓ Proxy listening: http://localhost:4001
  ✓ OTLP listening: http://localhost:4001
  ✓ Dashboard: http://localhost:4001

  ▶ Verifying agent tracking
  ✓ Claude: skipped
  ✓ Codex: ready
  ✓ OpenCode: ready
  ✓ Kilo: skipped
  ✓ Agents: 2 ready, 2 skipped, 0 failed

  ───────────────────────────────────────────
  🚀 llm-tracker is LIVE → http://localhost:4001
```

It ends with a restart of the API when `frontend/dist` exists, because a freshly
built bundle is not served by an already-running process: the mount happens at
import time in `src/api.py`, so a process that started before the first build has
no dashboard at all. `start` and `restart` never do this; only the command that
builds needs to.

The port lines above are literal. `bootstrap.sh` reads three ports into three
variables and then interpolates the API port into the proxy, OTLP and dashboard
messages, so all four lines show the same URL.

An agent that is installed but not wired fails the check:

```
  ✗ Codex: OTLP not configured
  ✗ Agents: 0 ready, 3 skipped, 1 failed

  ⚠  llm-tracker started with 1 issue(s) → http://localhost:4001
```

`llm-tracker status` on the same machine names the repair:

```
  fix         run llm-tracker setup
```

Skipped with a warning, never failed, when the tool is missing: no `uv`
(downloaded), no Node ≥ 18 (frontend not built, no dashboard), no npm.

## `llm-tracker server token create`

Operator command, runs on the server box, talks directly to the database. Not
available to clients, and never over the network API.

```
$ llm-tracker server token create --email ops@example.com --kind ingest --name nas-01
Minted ingest token for ops@example.com (shown once):
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

`--email` is required, `--kind` is `cli` (default), `ingest` or `web`, and
`--name` labels the token with a device name. Exit 2 with the validation message
when the email is missing or the user cannot be created. This is the only
operator command left in `src/cli.py`.

## `llm-tracker login`

Authenticates this machine and wires detected agents at the server's OTLP
collector. Credentials are written to `~/.llm-tracker/credentials.json` with mode
`0600`, and the device receives its own CLI and ingestion tokens plus the
server's `otlp.logs_endpoint`, stored as `otlp_logs_endpoint`. That stored
endpoint is what later `setup` and `status` calls use as the intended collector,
so a client-only machine needs no local config at all.

```
$ llm-tracker login --server https://app.example.com
Open this URL in your browser to continue login:
  https://app.example.com/auth/cli/start?code_challenge=Ab3...&device_name=hanbo-macbook
Paste the code shown in your browser: A1B2-C3D4
Logged in as you@example.com (device: hanbo-macbook)
Credentials saved to /home/you/.llm-tracker/credentials.json
Dashboard: https://app.example.com
Wired agents: codex, claude, opencode
```

- Refuses non-HTTPS servers, except `http://localhost` and `http://127.0.0.1`,
  and reduces the URL to a bare origin. Without `--server` and without
  `$LLMTRACKER_SERVER` or a previous sign-in, it exits 2 with
  `server URL required: use login --server URL`.
- Checks `GET /version` and the protocol generation first, and prints nothing
  when that succeeds; a client the server cannot talk to exits 1 before any
  credential is touched.
- Re-logs in to the same server safely: the previous tokens are presented so the
  server can keep the same device identity across rotation, and a failed
  exchange leaves the old credentials in place.
- No browser is opened under `SSH_CONNECTION`/`SSH_TTY`, or with
  `--no-browser`. The URL is always printed.
- Agent wiring failures are warnings, not failures, and the exit code stays 0:

  ```
  warning: wiring kilo failed: npm install exited 1
  Logged in as you@example.com (device: hanbo-macbook)
  Wired agents: codex, claude
  ```

- With no tracked agent installed: `No tracked agents detected; nothing to wire.`

Flags: `--server URL`, `--device-name NAME`, `--no-browser`, `--no-banner`.

## `llm-tracker setup`

Points detected agents at a collector. Idempotent, no auth, no service control,
no dependency install. This is what replaced agent configuration inside
`server start` and `server restart`.

```
$ llm-tracker setup
  collector   https://app.example.com/v1/logs
  wired       codex, claude, opencode
```

Where the collector comes from, in order:

1. What `llm-tracker login` recorded in `credentials.json`.
2. A signed-in server that signed this machine in before it recorded one: `setup`
   reads `GET /version` once, takes its `otlp_logs_endpoint`, and stores it. The
   OTLP port is usually not the API port, so a remote server's collector cannot
   be derived locally.
3. The local collector, when this machine has the server component and is not
   signed in to anything else.

A machine signed in to a remote server never falls back to the local collector.
`llm-tracker status` reads only what is stored, so it stays offline and fast.

When the collector is unknown — a machine that signed in before its server
published one — `status` says `(target unknown)` and exits 0. Not knowing where
an agent points is not the same as it pointing somewhere wrong, and the
distinction shows in the exit code:

```
  agents      claude → https://app.example.com/v1/logs (target unknown)
  fix         run llm-tracker setup
```

`setup --disable` and `llm-tracker logout` use the recorded value, so a
hand-written collector is reported and left alone.

Re-run after moving the collector, changing its port, or installing a new agent.

There is no `--server` flag — the collector is discovered, never typed, because
the OTLP port is not the API port and typing it is how agents end up aimed at the
wrong server. With no collector to be found, the command prints one line and
exits 1:

```
No collector to wire agents to. Sign in with llm-tracker login, or install the server component.
```

With no tracked agent on `PATH` it prints
`No tracked agents detected; nothing to wire.` and exits 0. When agents are found
but none could be wired, it prints `no agents could be wired` and exits 1.

Flags: `--disable`, `--no-banner`.

`--disable` takes llm-tracker's telemetry settings back off the agents it
manages:

```
$ llm-tracker setup --disable
  un-wired  codex, claude
```

or `Nothing to un-wire.` when there was nothing to remove. Only the keys
llm-tracker writes are touched. Plugin entries and tool-call hooks are
identified by path, so they are removed unconditionally; the OTLP endpoint keys
are removed only while they still point where this install expects. Otherwise
the agent is reported and nothing is changed:

```
  claude     points at another collector, left alone
```

## `llm-tracker logout`

Removes this machine's credentials and un-wires the agents. The previous server
URL is read out of the credentials *before* they are deleted, so the
`--keep-agents` warning can still name what this machine was pointed at.

```
$ llm-tracker logout
  removed   /home/you/.llm-tracker/credentials.json
  un-wired  codex, claude, opencode
Signed out. The device stays listed in Settings → Devices until you remove it.
```

Nothing is sent to the server: `logout` only removes the local credentials file
and the agent configuration.

With `--keep-agents`, credentials are removed and the agent configs are left
alone; a warning on stderr says telemetry will be rejected, naming the server it
was pointed at:

```
  removed   /home/you/.llm-tracker/credentials.json
  warning   agents still point at the last configured collector (https://app.example.com) and will be rejected
```

With nothing to remove it prints `Not signed in; nothing to remove.` and exits
1. Flags: `--keep-agents`, `--no-banner`.

## `llm-tracker update`

Updates whichever components are installed, client first, stopping at the first
failure.

- **Server** — `scripts/update.sh`: fetch, fast-forward pull, then `bootstrap`,
  which installs, builds and restarts the services as its last steps. Refuses to
  run with a dirty worktree, detached HEAD, or no upstream.
- **Client** — the client is a source snapshot, so it updates by downloading the
  installer from the signed-in server's `GET /install.sh` and running it with
  `LLM_TRACKER_SERVER` and `LLM_TRACKER_BIN_DIR` set. That is the only way to
  install a new snapshot, so there is no separate release resolution here.
  Credentials are not touched. Without a signed-in server there is nothing to
  fetch the installer from and the command exits 1:
  `llm-tracker: cannot update the client without a server; run llm-tracker login --server <url> first.`

```
$ llm-tracker update
  ▶ Checking updates
  ✓ server  0.2.19  (/home/you/.llm-tracker/src)
  ✓ client  0.1.0  (commit 89075ce1f4b7d2e6a9c0b3d8e5f2a7c1b4d90e33)

  ▶ Updating client
  ✓ client  0.1.0
  ✓ credentials preserved

  ▶ Updating server
  ...

  ✓ llm-tracker is up to date
```

Client-only install:

```
$ llm-tracker update
  ▶ Checking updates
  ✓ client  0.1.0  (commit 89075ce1f4b7d2e6a9c0b3d8e5f2a7c1b4d90e33)

  ▶ Updating client
  ...
```

With neither component installed it prints
`llm-tracker: nothing to update on this machine.` and exits 0.

Flags: `--check` reports the installed versions and changes nothing, `--dry-run`
additionally prints the planned commands, `--scope all|client|server` limits the
work (default `all`), `--rebuild-plugins` re-runs `llm-tracker setup` at the end
to rebuild the OpenCode and Kilo plugins.

```
$ llm-tracker update --dry-run
  ▶ Checking updates
  ✓ server  0.2.19  (/home/you/.llm-tracker/src)
  ✓ client  0.1.0  (commit 89075ce1f4b7d2e6a9c0b3d8e5f2a7c1b4d90e33)

  Planned commands:
  bash /home/you/.llm-tracker/src/scripts/update.sh
  sh </install.sh from the signed-in server>
```

## `llm-tracker <command> ...`

Runs any command with usage tracking and prints the run summary to stderr, so
piping the child's stdout stays clean.

Tracking uses the services that are already running. The wrapper reads the usage
high-watermark from the API, runs the child, then fetches the summary for
everything recorded after that watermark. It starts nothing and stops nothing,
and it uses the long-running proxy when `--proxy-env` is given rather than a
private one for the run. The API is the signed-in server when there is one, and
the local server otherwise.

```
$ llm-tracker codex exec "say hello in one sentence"
...child output...
llm-tracker usage summary
requests: 1, total tokens: 12,431, cached: 11,904 (96%)
latency avg: 1.42s, ttft avg: 380ms, cost: $0.0187

sessions:
  01JQ8F2K9W3N  1 req  12,431 tok  96% cached  $0.0187
```

A run that recorded nothing:

```
No llm-tracker usage recorded for this command.
```

**If the API is not reachable, the command still runs, untracked.** It never
starts a service on your behalf, and the child is not held up waiting:

```
$ llm-tracker codex exec "say hello"
...child output...
llm-tracker API unavailable before command start: [Errno 111] Connection refused
No summary could be produced.
```

The exit code is still the child's, so a wrapper script behaves the same either
way. Only the summary is missing. With `--no-summary` the same situation prints
just the first line.

Flags: `--json`, `--usage-only`, `--summary-dest stdout|stderr|file`,
`--summary-file`, `--wait-ms`, `--poll-ms`, `--proxy-env`, `--no-summary`,
`--no-banner`. Use `--` before the child command when llm-tracker flags come
first. `--summary-dest file` without `--summary-file`, and `--usage-only`
together with `--no-summary`, are argument errors and exit 2.

`--proxy-env` points at the long-running proxy from `~/.llm-tracker/config.yaml`.
A client-only machine has no local proxy, so there is nothing there to point at.

## `llm-tracker --version` / `--help`

```
$ llm-tracker --version
llm-tracker 0.1.0 (client 89075ce)
```

With the server component installed, `--version` adds the server release:

```
$ llm-tracker --version
llm-tracker 0.1.0 (client 89075ce) · server 0.2.19
```

The two versions are independent. `client/VERSION` is the client snapshot's
version and root `VERSION` is the server release; the bump workflow raises the
patch of whichever of them the changed files belong to. The commit shown is the
client snapshot's `COMMIT`, or the server clone's `HEAD` on an all-in-one
install.

---

## Legacy aliases

Kept during migration, forwarding to the server commands. Each prints one notice
on stderr:

```
$ llm-tracker start
note: "llm-tracker start" is now "llm-tracker server start"
...
```

| Old | New |
| --- | --- |
| `llm-tracker bootstrap` | `llm-tracker server bootstrap` |
| `llm-tracker start` | `llm-tracker server start` |
| `llm-tracker stop` | `llm-tracker server stop` |
| `llm-tracker restart` | `llm-tracker server restart` |
| `llm-tracker token create` | `llm-tracker server token create` |

`status` is not an alias — it means the component report. The old service view is
`llm-tracker server status`, and it prints the same text as before.

The aliases are removed in the next major version of the server release.

## Removed commands

`llm-tracker summary` is gone. Evaluations run in the background through the
server's job API, and the result is on the dashboard. The spelling is refused
with exit 2 so a script that still calls it fails loudly instead of being run as
a tracked child command named `summary`:

```
$ llm-tracker summary 01JQ8F2K9W3N
llm-tracker: 'summary' is no longer a command. Evaluations now run in the background; see the dashboard.
$ echo $?
2
```

Isolated tracking is gone with it. There is no temporary database, no temporary
collector, no temporary proxy and no merge step: every run reports to the
collector that is already installed, in both installation modes.

## When a component is missing

```
$ llm-tracker server start
llm-tracker: the server component is not installed on this machine.
This machine has the client only, which reports to a remote server.
To run a local server, install the all-in-one release:
  curl -fsSL https://raw.githubusercontent.com/Haannbboo/llm-tracker/main/install.sh | bash
```

Exit code 1. Every `llm-tracker server ...` command behaves this way, so the
failure names the missing component instead of surfacing a missing file or a
missing virtualenv.

The mirror image, for a launcher with no client to run:

```
$ llm-tracker status
llm-tracker: the client component is not installed on this machine.
Install it with:
  curl -fsSL https://Haannbboo/llm-tracker/raw/main/scripts/hosted-install.sh | sh
```

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success, or the command ran and reported what it found. `llm-tracker status` exits 0 when nothing installed is broken — not being signed in is not a fault. |
| 1 | Something installed is broken or a check failed: a stopped service, a detected agent pointing at another collector, an unwired-or-unwireable `setup`, a failed sign-in or update, or `logout` with no credentials. |
| 2 | Argument validation error, including a removed command and an unknown `server` subcommand. |
| 126 | The tracked child command is not executable. |
| 127 | The tracked child command was not found. |
| 128+N | The tracked child command was killed by signal N. |
| other | The tracked child command's own exit code. |
