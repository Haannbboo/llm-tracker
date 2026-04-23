# OTLP Expansion Todo

Follow-up task list for OTLP field capture expansion. See [docs/otlp-shared-fields.md](docs/otlp-shared-fields.md) for the field analysis and implementation notes.

## Done
- [x] `prompt_length`: Store raw prompt-length metadata from OTLP prompt events.

## P0: Core Tracking
- [ ] `duration_ms`: Keep validating end-to-end request latency coverage.
- [ ] `model`: Keep validating model-name coverage across all OTLP integrations.

## P1: Essential Observability
- [ ] `proxy_pass_through`: Support transparent forwarding for arbitrary endpoints to ensure compatibility with new provider features.
- [ ] `service.version`: Add CLI version correlation.
- [ ] `event.name`: Persist event class for request/response/tool filtering.
- [ ] `event.timestamp`: Persist client-side event time for ordering.
- [x] `base_url`: Normalize exact base URLs into `base_urls` and persist `usage.base_url_id` when local config exposes the upstream URL.

## P2: Cleanup & Simplification
- [ ] Remove `endpoint` if OTLP-first tracking makes it redundant.
- [ ] Revisit `tool_tokens` if provider coverage stays inconsistent.
- [ ] `success`: Add a normalized success/failure signal.
- [ ] Split schema migration responsibility out of `src/database.py`.
  Keep `database.py` focused on runtime access/helpers, and move shape-changing schema work into an explicit migration path so proxy/API/OTLP startup does not own destructive DB changes.

## P3: Deep Debugging
- [ ] `observed_time_ns`: Add OTLP receive-order fallback metadata.
- [ ] `prompt`: Capture raw prompt content only behind an explicit privacy gate.
