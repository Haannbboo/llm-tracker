# CLI split review fixes

This follow-up hardens the hosted client/server split introduced in
`d62effb7703c886b166914305b64b880579e1415`. The component ownership design is in
`docs/client-server-split-handoff.md`.

## Behavior

- Publish supported protocol generations and the hosted installer from the
  existing server. The installer and version metadata are public; ingestion
  and account APIs retain their authentication requirements.
- Resolve one active client source, interpreter, version, and commit. A hosted
  launcher cannot mistake an unrelated virtualenv for a server checkout.
- Use the configured local ports and support IPv6 and scheme-less public
  origins. Service probes use bind addresses rather than the public origin.
  Status asks the running API for the collector address with a bounded timeout.
  The public collector hint honors safe runtime endpoint overrides, preserves
  custom paths, and omits hints that would expose secrets or advertise a
  different collector.
  Public endpoint hints are separate from host/port bind metadata, which shares
  the collector startup resolver. Missing bind metadata produces an unknown
  collector address in status instead of a guessed port. Wildcard overrides use the
  configured public origin; loopback-only overrides are not advertised to
  remote clients.
- Keep documented server command aliases. Consume `--no-banner` before
  forwarding server arguments, and persist `restart --otlp-port`.
- Delegate server update checks and report client update availability as unknown
  until release metadata exists. Client updates preserve credentials and refresh
  plugin paths without initiating another login.
- Configure agents from the client. Disable only settings for a known matching
  collector; unknown or foreign collectors are left unchanged. Helper failures
  produce a failing setup/cleanup result.
- Preserve unrelated agent settings. Malformed JSON files are refused without
  being rewritten. Codex edits validate both TOML syntax and unchanged unrelated
  values before writing, including nested headers, missing final newlines,
  commented tables, and implicit parent tables.
- Report invalid credential files through CLI diagnostics without a traceback
  or file contents. Sign-out captures the collector before removing credentials.
  Status redacts credential-bearing URLs and private URL paths; direct
  configure helpers report the modified file without echoing collector URLs.
  Login distinguishes absent agents from failed configuration, preserving the
  new credentials while reporting that setup still needs attention.
- State explicitly that tracking summaries cover an account watermark window.
  Concurrent activity is included, and delayed events outside the timestamp
  window can be omitted. Exclusive command attribution requires correlation
  that this CLI design does not provide.
  JSON summaries include explicit attribution metadata. `--proxy-env` checks
  connectivity before launch and replaces inherited provider base URL values.

## Deliberate limits

Stable device identity, version reporting per device, independent release
workflows, and machine-local proxy ownership remain future split work. Removed
client-only installation proofs and ignored identity fields are not restored.
A hosted client does not provide a local proxy; `--proxy-env` requires an
already-running proxy configured locally.

The historical Claude tool-call hook is a no-op, so setup does not register it.
Unsupported Codex layouts are refused without modification. Direct configure
helpers retain PORT/HOST inputs; the client uses TARGET/ENDPOINT inputs and
explicit configured/skipped/failed exit statuses.

## Verification

The independent review uses fresh opposite-tool CLI processes for the skeptic,
architect, and minimalist lenses. Earlier five-minute attempts were incomplete;
longer runs completed and identified additional configuration and CLI defects.
Those findings are covered by the fixes above. All three fresh landing reviewers
completed successfully and found no remaining must-fix issue.

- Full Python suite: **1197 passed, 6 skipped**, seven deprecation warnings.
  Green in CI after one fix: launcher contract tests ship their own client
  snapshot instead of requiring the checkout's bootstrap venv.
- Full pre-commit checks: passed, including formatting, lint, typing, OTLP
  readiness, and the test hook.
- Public endpoint and operational bind metadata have separate regression
  coverage, including IPv6, wildcard binds, unavailable APIs, and unsafe URLs.
- Helper timeout/start failures are covered for wiring and disabling, proving
  that exception command arguments do not escape into diagnostics.
- CI caught the launcher contract tests leaning on the developer checkout's
  bootstrap venv: they now ship their own client snapshot (client, protocol,
  scripts/lib, commit stamp) and scrub `HOME`, `TOKENAGE_ROOT`, and
  `TOKENAGE_SKIP_BANNER` from the inherited environment, so the same tests
  exercise identical launcher routing on every machine. The banner-suppression
  case that CI caught is also covered on a real tty now, not just under pipes.
