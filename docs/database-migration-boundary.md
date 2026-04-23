# Database Migration Boundary

Date: 2026-04-23

## Context

`src/database.py` currently does three different jobs:

- define the SQLAlchemy tables used by the app
- provide runtime read/write helpers
- mutate schema on process startup through `init_db()`

That startup mutation now includes both:

- additive changes
  - create missing tables
  - add missing columns such as `usage.base_url_id`
- destructive cleanup
  - drop removed columns from `base_urls`

Today, proxy, API, and OTLP all call `init_db()` on startup, so every service process is also acting as a schema migration runner.

## Problem

This worked when schema changes were small and additive, but it is starting to create the wrong coupling:

- runtime access code and schema migration code now live in the same module
- every service startup can change shared database state
- destructive schema changes happen implicitly, not via an explicit migration step
- branch switching gets riskier because startup behavior depends on whichever code version runs first
- future refactors will have to preserve startup-safe migration behavior in code paths that should really only care about logging and reads

In short: `database.py` is no longer just a data-access layer.

## Why Now

This is a good time to refactor because the codebase has crossed a real boundary:

- a second normalized table now exists: `base_urls`
- `usage` now has a foreign key relationship via `base_url_id`
- we already needed custom migration behavior beyond `metadata.create_all()`
- we already introduced destructive cleanup logic for removed columns
- migration logic has started leaking into neighboring tooling such as `scripts/migrate_usage.py`

That is usually the point where “just keep schema logic in the database helper” stops being cheap.

If this is left alone, the next schema change will likely add more conditional startup behavior to `database.py` instead of making the boundary clearer.

## Goals

- keep service startup simple
- keep runtime DB access predictable
- make schema changes easier to reason about
- reduce the chance that startup code mutates production data unexpectedly
- create a clearer path for future schema evolution

## Non-Goals

- introducing a heavy migration framework immediately
- rewriting the whole database layer
- changing the current table design for `usage` or `base_urls`

## Design Options

### Option 1: Keep the current startup-migration model

Keep `init_db()` responsible for:

- `metadata.create_all()`
- additive column creation
- destructive cleanup
- future schema reshaping

Benefits:

- lowest short-term implementation cost
- no separate migration command required
- easy local developer experience

Costs:

- `database.py` keeps accumulating migration-specific logic
- every app process remains a schema migrator
- destructive changes continue to happen implicitly
- harder to reason about rollout order and compatibility
- encourages one-off schema conditionals instead of explicit migration planning

Assessment:

- acceptable only if schema changes remain rare and simple
- the codebase is already moving beyond this comfort zone

### Option 2: Keep additive bootstrap in `database.py`, move destructive changes out

Keep `init_db()` responsible only for safe bootstrap work:

- create missing tables
- add clearly safe missing columns

Move these into an explicit migration path:

- drop column
- rename column
- data backfill
- table rewrite
- foreign key remapping or normalization jobs

Benefits:

- small change from today
- preserves easy startup for fresh environments
- removes the most dangerous implicit behavior
- gives a cleaner boundary without requiring a full migration system yet

Costs:

- two mechanisms now exist temporarily
- someone still has to decide what counts as “safe additive bootstrap”
- the boundary needs to be enforced consistently

Assessment:

- best near-term option
- matches the current size and maturity of this repo

### Option 3: Move fully to explicit migrations

Make `database.py` runtime-only:

- table definitions
- runtime read/write helpers
- no schema mutation beyond perhaps initial DB existence checks

Use an explicit migration path for all schema changes:

- versioned SQL or Python migrations
- manual migration command or startup gate

Benefits:

- cleanest responsibility split
- safest production behavior
- clearer deploy and rollback semantics
- easier to reason about schema history

Costs:

- highest implementation overhead
- requires migration workflow discipline
- more setup for local development and CI

Assessment:

- strongest long-term architecture
- may be more process than this repo needs right now

## Recommendation

Adopt Option 2 now.

Specifically:

- keep `metadata.create_all()` in `init_db()`
- keep additive missing-column creation in `init_db()` only when the change is startup-safe
- stop doing destructive cleanup in `init_db()`
- move destructive changes and data-shape changes into explicit migration scripts

This gets most of the architectural benefit without forcing the project into a full migration framework immediately.

## Suggested Boundary

`src/database.py` should own:

- table definitions
- engine creation
- runtime insert/query helpers
- startup-safe additive bootstrap only

Explicit migration code should own:

- drop/rename column
- backfill existing data
- normalize historical rows
- data moves between tables
- compatibility transitions between schema versions

Scripts like `scripts/migrate_usage.py` should consume the public database helpers where practical, but they should be treated as migration tooling, not runtime access patterns.

## Practical Next Steps

1. Stop adding new destructive migration logic to `src/database.py`.
2. Extract the current `DROP COLUMN` behavior for removed `base_urls` columns into an explicit migration script.
3. Decide whether additive column creation should remain in `init_db()` permanently or also move later.
4. If schema churn continues, introduce a lightweight versioned migration mechanism.

## Decision Trigger For Moving To Option 3

Move from Option 2 to Option 3 if any of these happen:

- another normalized table is added
- schema changes require data backfill more than once
- multiple rollout-compatible schema versions need to coexist
- production deployment order starts to matter
- `database.py` gains another round of migration-specific branching

## Summary

The refactor is worth doing now because the project has already crossed from “simple bootstrap” into “real schema evolution”.

The main issue is not code style. The issue is responsibility drift:

- runtime database access
- startup bootstrap
- destructive migration behavior

are now mixed together.

The best next step is to keep startup-safe additive bootstrap in `database.py` for now, while moving destructive and historical-shape changes into explicit migration code.
