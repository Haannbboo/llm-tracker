# llm-tracker Agent Guide

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

1. Before commit, run an independent code review using a fresh subagent.
2. Fix must-fix review findings.
3. Commit only after approval.
4. Push the current branch only after approval.
5. Open a PR using `.agents/commands/pr-template.md`.
6. Do not merge without approval.

Workflow details: `.agents/commands/feature-pr.md`.
Verification workflow: `.agents/commands/verify.md`.
Independent review: `.agents/commands/review.md`.
Open PR workflow: `.agents/commands/open-pr.md`.
Pre-PR checklist: `.agents/commands/pre-pr.md`.
Project rules: `.agents/commands/llm-tracker.md`.

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

Three-script chain, all internal except `bootstrap.sh`:

```txt
bootstrap.sh → install.sh → start.sh → post-checks
```

- `bootstrap.sh` — public entrypoint. One command for full setup.
- `install.sh` — Python venv, deps, CLI symlink, frontend build with Node.js detection.
- `start.sh` — supervisord, port checks, API restart, serves `frontend/dist`.

Quick backend iteration:

```bash
~/.venv/bin/supervisorctl -c ~/.llm-tracker/supervisord.conf restart llm-tracker-api
```

Frontend dev:

```bash
cd frontend && npm run dev
```

Vite dev uses port `5173`. Bootstrap serves built frontend through FastAPI.

## Durable repo notes

- Runtime API port is config-driven. Do not assume `4001`; read `~/.llm-tracker/config.yaml`. This repo has recently run the API on `4004`.
- Service control uses `~/.llm-tracker/supervisord.conf`.
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

More details: `.agents/commands/llm-tracker.md`.

## Agent skills

### Issue tracker

This repo currently uses GitHub for source control. If issues are needed, prefer GitHub Issues unless local markdown is explicitly requested. Future detailed config can live in `docs/agents/issue-tracker.md`.

### Triage labels

Default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Future detailed config can live in `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo. Use root README plus `.agents/commands/llm-tracker.md`; ADRs may live under `docs/adr/` only for durable architecture decisions.
