# tokenage Agent Guide

LLM usage tracker: transparent proxy + OTLP collector. See [README.md](README.md) for architecture, setup, and commands.

This file is public repo guidance. Keep personal memory, local paths, private planning, account details, and machine-specific secrets out of it.

## Local private instructions

If `AGENTS.local.md` exists, read it before starting work.

`AGENTS.local.md` is private, gitignored, and must never be committed, quoted, summarized into public files, or included in PRs.

If `CLAUDE.local.md` or `.claude/*.local.md` exists, treat it the same way: private local context only.

## Default workflow

Assume the worktree/branch has already been created for you. Do not create branches or worktrees unless explicitly asked.

Normal feature work is handled by the agent's planning/testing skills:

```txt
request → design/spec → approval → implementation → testing
```

This repo adds only the final landing gate:

1. Before commit, run an independent code review using a fresh opposite-tool CLI process.
2. Fix must-fix review findings.
3. Commit only after approval.
4. Push the current branch only after approval.
5. Open a PR using `.agents/commands/pr-template.md`.
6. Do not merge without approval.

Workflow details: `.agents/commands/feature-pr.md`.
Verification workflow: `.agents/commands/verify.md`.
Independent review: `.agents/commands/review/SKILL.md`.
Open PR workflow: `.agents/commands/open-pr.md`.
Pre-PR checklist: `.agents/commands/pre-pr.md`.
Project rules: `.agents/commands/tokenage.md`.

When handling PR comments, CI failures, or CodeRabbit feedback, read `.agents/commands/pr-follow-up.md` before acting. For review comments only, read `.agents/commands/respond-to-pr-comments.md`. These are not optional — they cover reply style, fix scoping, verification, and resolving GitHub conversations.

## Git and PR rules

- `main` must stay runnable.
- Do not work directly on `main` unless explicitly asked.
- Do not create branches/worktrees unless explicitly asked.
- Do not commit until explicitly approved.
- Do not push, open PRs, or merge until explicitly approved.
- Prefer squash merge for feature branches.
- Ask whether to squash when merging.
- Never add merge commits when asked to merge.
- Commit messages: one-line conventional style, no co-authorship.

Example commit style:

```txt
feat: add OpenCode plugin usage tracking
fix: handle missing cache_read token pricing
docs: add provider adapter workflow
```

## Version management

Version format: `MAJOR.MINOR.PATCH` (e.g. `0.1.180`).

- `VERSION` at repo root is the server release.
- `client/VERSION` is the client release, tracked separately so a hosted client
  snapshot can move without a server release.

- `MAJOR`: bumped manually for breaking changes — edit first field in the file.
- `MINOR`: bumped manually for feature releases — edit second field in the file.
- `PATCH`: auto-incremented on PR branches targeting `main` by `.github/workflows/bump-version.yml`; the bump commit becomes part of the PR before squash merge, so `main` gets a single squashed commit. The workflow raises only the files the diff touched: `client/`, `plugins/` and `scripts/hosted-install.sh` bump the client, `src/`, `frontend/`, `scripts/`, `VERSION` and friends bump the server, and `protocol/` bumps both.

`tokenage --version` prints the client version and commit, and appends `· server <VERSION>` when the server component is installed.

The version is exposed via `GET /version` (both API and proxy apps) and displayed in Settings → Services in the frontend.

Any new API route consumed by the frontend must be added to `frontend/vite-api-proxy.js` and its proxy route tests.

## Code style

- Python: use ruff formatting. Pre-commit enforces ruff-format.
- TypeScript: use `Record<string, any>` for dynamic objects such as config and API results. `Record<string, unknown>` causes excessive casting in JSX here.
- Avoid unrelated refactors. If you see unrelated crap, note it separately instead of mixing it into the current diff.

## Test and verification commands

Backend:

```bash
uv run python -m pytest -q
```

If `uv` is unavailable but the bootstrap-created virtualenv exists, use `./.venv/bin/python -m pytest -q` as a fallback.

Script-specific changes:

```bash
uv run python -m pytest tests/scripts/ -q
```

Client changes:

```bash
uv run python -m pytest tests/client/ -q
```

Frontend:

```bash
cd frontend && npm test
cd frontend && npm run build
```

Pre-commit:

```bash
pre-commit run --all-files
```

Use targeted tests during iteration, but before commit/PR run the relevant full checks for touched areas.

## Bootstrap architecture

There is one installed command: `scripts/tokenage`. Both installers write it, and the `# tokenage launcher` marker line is how each recognises a launcher it previously wrote. The all-in-one installer symlinks it from the server clone into `~/.local/bin`; the hosted client installer copies it there. It resolves the two components out of `$TOKENAGE_HOME` — `current` for the client snapshot, `src` for the server clone — and routes to whichever one the arguments name.

- `client/` — the client: tracking wrapper, agent configuration, sign-in, component report. It must never import `src`.
- `src/`, `scripts/` — the server component: API, OTLP collector, proxy, dashboard, evaluation worker.

Command surface:

```bash
tokenage status            # this client: sign-in, agents, wiring
tokenage setup             # agent configuration, in both installation modes
tokenage client start      # install + start the OS-supervised client service (systemd --user / launchd)
tokenage client status     # whether the OS manager runs it, last report
tokenage server start      # turn the services on
tokenage server restart    # reload running code
tokenage server update     # update the server clone
tokenage server bootstrap  # install, build the dashboard, start, verify
tokenage server status     # the service view
```

`tokenage start`, `stop`, `restart`, `bootstrap` and `token` still forward to the matching `server` command with a one-line note on stderr. `tokenage status` is not an alias for the service view.

### Testing local changes: set `TOKENAGE_ROOT`

`tokenage server ...` runs the scripts from `$TOKENAGE_HOME/src` — the deployed clone — not the checkout you are editing. Older clones also configure agents from `start.sh`/`restart.sh`, rebuilding the endpoint as `http://localhost:<port>/v1/logs` and dropping the scheme from `server.base_url`, which silently repoints agent settings and fails the `otlp-ready` hook. So prefix server commands in a checkout:

```bash
TOKENAGE_ROOT="$PWD" tokenage server restart    # reload THIS checkout's code
TOKENAGE_ROOT="$PWD" tokenage server bootstrap  # build THIS checkout's dashboard
```

It also makes the client import this checkout instead of a snapshot. Repair agent settings with `TOKENAGE_ROOT="$PWD" tokenage setup`.

The all-in-one install is still a three-script chain:

```txt
install.sh (root) → scripts/bootstrap.sh → scripts/start.sh
```

- `install.sh` — curl-pipe-bash entrypoint at repo root. Checks prerequisites (git, bash, curl), clones/updates repo to `~/.tokenage/src`, delegates to `scripts/bootstrap.sh`.
- `bootstrap.sh` — installs deps (via embedded `_install_deps()`), builds the dashboard, starts services via `start.sh`, runs post-start verification, then restarts the API so the new `frontend/dist` is served. Only the command that builds restarts the API, because the mount happens at import time.
- `start.sh` — config, port check, schema migrations, supervisord. Refuses with "run tokenage server bootstrap" when `requirements.txt` changed. Never touches agent settings.
- `scripts/restart.sh` — migrations, then `SIGHUP` to the running services. Nothing else; `--otlp-port N` is its only flag and persists the port.
- The hosted client install is `scripts/hosted-install.sh`, served from `GET /install.sh`. It writes a client snapshot under `~/.tokenage/versions` and flips `~/.tokenage/current`.

Quick backend iteration: `TOKENAGE_ROOT="$PWD" tokenage server restart` (see `scripts/restart.sh`) reloads the supervisord-managed services to pick up backend changes locally.

The human views frontend changes through the built version, not Vite dev — after frontend edits, run `TOKENAGE_ROOT="$PWD" tokenage server bootstrap` to rebuild `frontend/dist` (`npm install && npm run build`) so the changes show up.

Frontend dev:

```bash
cd frontend && npm run dev
```

Vite dev uses port `5173`. `tokenage server bootstrap` builds and serves the frontend through FastAPI.

## Worktree dev environment

Create feature worktrees in `../tokenage-worktrees/`, next to the main `tokenage` clone. After creating one, symlink the main clone's virtualenv into it (`ln -s /path/to/main/clone/.venv .venv`) — `scripts/tokenage` and tests need it; without it they fall back to system `python3` and fail on missing deps.

`scripts/dev/dev-start.sh` launches an isolated dev environment for worktree work. It is fully independent from the main production server:

| | Main API server | Dev API server |
|---|---|---|
| **Manager** | supervisord (`~/.tokenage/supervisord.conf`) | standalone uvicorn |
| **Working dir** | `~/Documents/tokenage/` | worktree dir |
| **Port** | from `~/.tokenage/config.yaml` | random free port |
| **DB** | `~/.tokenage/usage.db` | ephemeral copy in `/tmp/` |
| **Auto-reload** | no | yes (`--reload`) |

Key behaviors:

- **Ephemeral DB**: copies `~/.tokenage/usage.db` into a temp dir; the main DB is never modified. Temp dir is deleted on stop.
- **Free ports**: API and Vite ports are allocated dynamically; no conflicts with main server.
- **Auto-reload**: the dev uvicorn server runs with `--reload`, so Python file changes restart it automatically.
- **Safe restart**: `scripts/dev/dev-stop.sh` + `scripts/dev/dev-start.sh` restarts only the dev server. The main supervisord-managed server is unaffected.

```bash
# Start isolated dev environment
./scripts/dev/dev-start.sh

# Stop it
./scripts/dev/dev-stop.sh
```

## Durable repo notes

- `client/` must never import `src`. A client-only install has no server clone, so the dependency would break the whole client; `tests/client/test_no_server_imports.py` enforces it.
- One auth model: every request resolves to a user. `auth.provider` is `local` (default; direct loopback requests are the built-in owner, others need a token or `tokenage server login-link`) or `google`. There is no auth-off mode; don't add `user is None` branches.
- Runtime API port is config-driven. Do not assume `4001`; read `~/.tokenage/config.yaml`. This repo has recently run the API on `4004`.
- Service control uses `~/.tokenage/supervisord.conf`.
- The configured DB may be remote Postgres/Supabase, not local SQLite. Worker and session-selector changes must tolerate slow or hung DB calls.
- For stuck evaluations, inspect `evaluation_jobs` plus `/evaluation-jobs/active`. A queued auto job can be normal buffer behavior; if no running job exists and it survives a worker interval, suspect the worker loop.
- Frontend-used API routes must be added to `frontend/vite-api-proxy.js` and its proxy route tests, or Vite dev mode may fail while production works.

## High-risk areas

Treat these as review-sensitive:

- API key, token, auth header, and secret handling.
- Raw prompt, raw response, request body, trace payload, and privacy-sensitive logs.
- Cost calculation, token accounting, cache read/write pricing, provider multipliers.
- Provider adapters and model-name normalization.
- Streaming/tool-call partial chunks and retry/timeout/idempotency behavior.
- Schema migrations and backward compatibility.
- Worker loops, background jobs, and DB calls that can hang.
- Frontend/backend route parity, especially Vite proxy behavior.

More details: `.agents/commands/tokenage.md`.

## Agent skills

### Issue tracker

This repo currently uses GitHub for source control. If issues are needed, prefer GitHub Issues unless local markdown is explicitly requested. Future detailed config can live in `docs/agents/issue-tracker.md`.

### Triage labels

Default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Future detailed config can live in `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo. Use root README plus `.agents/commands/tokenage.md`; ADRs may live under `docs/adr/` only for durable architecture decisions.
For the hosted client/server split design, read `docs/client-server-split-handoff.md`.
