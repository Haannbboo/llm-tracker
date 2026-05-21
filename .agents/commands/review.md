# Review Workflow

Run an independent code review on the current branch before commit or PR. Be harsh. Catch the bullshit before users do.

## Inputs

```bash
git status --short
git branch --show-current
git diff --stat main...HEAD
git diff main...HEAD
```

If not on a feature branch, say so. If the diff contains unrelated changes, flag them.

## How to run

Use a fresh subagent with only:

- repo guidance files: `AGENTS.md`, `.agents/commands/llm-tracker.md`, `.agents/commands/pre-pr.md`
- current branch name
- `git diff --stat main...HEAD`
- `git diff main...HEAD`
- test commands/results already run from `.agents/commands/verify.md`; if missing or clearly insufficient, run focused read-only-safe checks yourself before verdict

The reviewer must not share the implementer's context. No rubber-stamping. No vibes.

## Review focus

Before judging implementation details, build a standards checklist from `AGENTS.md` and `.agents/commands/llm-tracker.md`. If the diff violates those rules, flag it as must-fix unless the PR body explicitly documents an approved exception.

### Correctness

- Does the code actually implement the approved spec?
- Are edge cases handled, or did someone slap happy-path duct tape on it?
- Are errors explicit and recoverable?
- Are timeouts/retries/idempotency considered where needed?

### Privacy and security

- No API keys, tokens, auth headers, cookies, connection strings, or secrets in code/docs/tests.
- No raw prompt/raw response/request body logging unless explicitly configured and tested.
- Trace payloads must avoid leaking private user data by default.
- Error messages should not dump secrets or full sensitive payloads.

### Cost and pricing

- Token accounting uses the right input/output/reasoning/cache fields.
- Cache read/write pricing is handled separately when providers expose it.
- Missing pricing has safe fallback behavior.
- Provider/model normalization does not silently merge incompatible models.
- Historical/backfill behavior is explicit if cost logic changes.

### Provider adapters

- Provider-specific behavior is isolated.
- OpenAI/Anthropic/Gemini/OpenRouter/LiteLLM naming differences are handled intentionally.
- Streaming and non-streaming behavior are consistent where expected.
- Tool-call handling covers partial chunks and malformed chunks.

### Database and migrations

- Schema changes include migration path and backward compatibility.
- Remote Postgres/Supabase latency or hung calls are considered.
- Worker loops do not block forever on DB calls.
- Indexes are considered for new query patterns.

### Frontend/backend integration

- Frontend API calls have backend routes.
- Vite dev proxy includes frontend-used routes by updating `frontend/vite-api-proxy.js` `shouldProxyApiRequest()` explicit `pathname === ...` / prefix checks.
- Loading/error/empty states are handled.
- Dashboard numbers match backend semantics.

### Tests

- Tests cover the changed behavior, not just snapshots of the happy path.
- Regression tests exist for bugs.
- Provider/cost/schema/streaming changes have focused tests.
- Frontend changes run `npm test` and `npm run build` where relevant.
- If verification was skipped or weak, run targeted checks from `.agents/commands/verify.md` before approving; at minimum explain exactly why a check was not run.

## Output format

```md
## Verdict

APPROVE | REQUEST CHANGES | BLOCKED

## Must fix

- [file:line] issue, why it matters, suggested fix

## Should fix

- ...

## Nice to have

- ...

## Tests missing

- ...

## Risk assessment

Low/Medium/High. Explain briefly.

## Commands reviewed/run

- `git diff main...HEAD`
- `...`
```

## Rules

- Do not rewrite code during review unless explicitly asked for fixes.
- Do not approve if secrets/privacy/cost/schema risks are unresolved.
- Do not nitpick formatting that tools handle.
- Prefer concrete file/function feedback over vague vibes.
