# Base URL Schema Design

Date: 2026-04-23

## Goal

Store exact historical `base_url` without repeating long URL text on every `usage` row.

## Proposed Schema

### New table

`base_urls`

Columns:

- `id`
- `base_url` unique not null
- `provider_name` nullable
- `source` nullable

Suggested meanings:

- `provider_name`: current best-known provider label for this URL
- `source`: where the URL came from

### Usage table

Add:

- `base_url_id` nullable

Keep:

- `provider`

Recommended types:

- `base_urls.id`: integer primary key
- `base_urls.base_url`: text unique
- `base_urls.provider_name`: text
- `base_urls.source`: text
- `usage.base_url_id`: nullable integer foreign key

## Write Path

### Proxy

- use `provider.base_url`
- upsert into `base_urls`
- write both:
  - `provider`
  - `base_url_id`

### OTLP

- parse raw `base_url` from local agent config
- upsert into `base_urls`
- write both:
  - `provider`
  - `base_url_id`

## Write Timing

- do the `base_urls` upsert inline, immediately before writing each `usage` row
- do not use a background sync job
- if `base_url` cannot be determined, leave `base_url_id = NULL`

## Upsert Behavior

Use a helper like:

- `get_or_create_base_url(base_url, provider_name=None, source=None) -> id`

Behavior:

- lookup by exact `base_url`
- if found, reuse existing `id`
- if missing, insert and return new `id`
- if `provider_name` is newly known, it may update the existing row
- if `source` is newly known, it may update the existing row

Do not create multiple rows for the same exact `base_url`.

## Existing Rows

- do not force full backfill
- leave old `base_url_id` as `NULL`
- keep existing `provider`
- optional later script:
  - backfill only unambiguous rows
  - skip ambiguous rows
  - mark inferred source

Do not infer historical `base_url` from today’s config unless the mapping is unambiguous.

## Read Path

- short term:
  - keep reading `usage.provider`
- medium term:
  - prefer joined `base_urls.provider_name` / `base_url`
  - fallback to `usage.provider`

Recommended API behavior:

- return `provider` exactly as today for compatibility
- optionally add joined `base_url`
- optionally add `base_url_id`

## Migration Rules

- create `base_urls` if missing
- add `usage.base_url_id` idempotently
- keep startup-safe migration logic because proxy/API/OTLP all call init

Migration notes:

- `usage.base_url_id` should be nullable
- do not drop or rewrite `usage.provider`
- migration must be safe if multiple processes start together
- avoid breaking existing rows or existing UI queries

## Invalid URLs

- store attempted invalid URLs too
- do not collapse failed URLs into the later working URL
- treat them as real historical records

Example:

- `https://api.vectorengine.ai`
- `https://api.vectorengine.com`

These should be separate `base_urls` rows if both were actually used.

Why:

- failed attempts are useful for debugging
- preserves historical truth
- request success/failure stays on `usage`

## Why Keep `provider`

- no breaking UI/API change
- easy fallback for old rows
- still useful as a cached display field

## Source Examples

Good `source` values:

- `proxy_config`
- `claude_settings`
- `codex_config`
- `gemini_settings`
- `backfilled_inferred`

## Implementation Areas

Likely code touch points:

- `src/database.py`
  - define `base_urls`
  - add `usage.base_url_id`
  - add migration helpers
  - add get-or-create helper
- `src/provider_parser.py`
  - expose raw base URL getters for Claude/Codex/Gemini
- `src/proxy.py`
  - resolve/create `base_urls` row before `log_usage(...)`
- `src/otlp.py`
  - parse config-derived `base_url`
  - resolve/create `base_urls` row before `log_usage(...)`
- `src/api.py`
  - optional joined `base_url` exposure
- frontend
  - optional display/filter support

## Naming Options

Good candidates:

- `base_urls`
- `provider_base_urls`
- `upstream_base_urls`

Recommended:

- `base_urls`

Reason:

- directly matches what is being normalized
- works well with `usage.base_url_id`
- still leaves room for provider mapping metadata
