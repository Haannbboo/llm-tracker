# OTLP Expansion Todo

Follow-up task list for OTLP field capture expansion. See [docs/otlp-shared-fields.md](docs/otlp-shared-fields.md) for the field analysis and implementation notes.

## Done
- [x] `prompt_length`: Store raw prompt-length metadata from OTLP prompt events.

## P0: Core Tracking
- [ ] `duration_ms`: Keep validating end-to-end request latency coverage.
- [ ] `model`: Keep validating model-name coverage across all OTLP integrations.

## P1: Essential Observability
- [ ] `service.version`: Add CLI version correlation.
- [ ] `event.name`: Persist event class for request/response/tool filtering.
- [ ] `event.timestamp`: Persist client-side event time for ordering.

## P2: Cleanup & Simplification
- [ ] Remove `endpoint` if OTLP-first tracking makes it redundant.
- [ ] Revisit `tool_tokens` if provider coverage stays inconsistent.
- [ ] `success`: Add a normalized success/failure signal.

## P3: Deep Debugging
- [ ] `observed_time_ns`: Add OTLP receive-order fallback metadata.
- [ ] `prompt`: Capture raw prompt content only behind an explicit privacy gate.
