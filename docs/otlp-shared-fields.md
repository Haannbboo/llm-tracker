# OTLP Shared Field Analysis

Date: 2026-04-22

This note summarizes which OTLP fields are shared across all three coding-agent integrations currently captured by llm-tracker:

- Claude Code
- Codex
- Gemini CLI

Capture sources used for this analysis:

- `logs/otlp-captures/claude-code.fields.json`
- `logs/otlp-captures/claude-code.sample.json`
- `logs/otlp-captures/codex_cli_rs.fields.json`
- `logs/otlp-captures/codex_cli_rs.sample.json`
- `logs/otlp-captures/gemini-cli.fields.json`
- `logs/otlp-captures/gemini-cli.sample.json`

## Shared Fields

Shared OTLP log attributes across all three captures:

- `duration_ms`
- `event.name`
- `event.timestamp`
- `model`
- `prompt`
- `prompt_length`
- `success`

Shared OTLP resource attributes across all three captures:

- `service.name`
- `service.version`

Fields already materially used by `src/otlp.py`:

- `duration_ms`
- `model`
- `service.name` for routing
- `prompt_length` (persisted in DB)

Fields not currently persisted or meaningfully used for tracking:

- `service.version`
- `event.timestamp`
- `event.name`
- `success`
- `prompt`

One additional shared record-level field is worth noting even though it is not an OTLP attribute:

- `observedTimeUnixNano`

It is present in all three captured log-record shapes and is only partially used today as a Codex fallback.

## Prioritized Recommendation

### 1. `service.version`

Why:

- Highest debugging value for very low storage cost
- Lets llm-tracker correlate schema drift and behavior changes with specific CLI versions
- Useful for dashboards, incident analysis, and regression tracking

Recommended DB type:

- `TEXT` or `VARCHAR(32)`

Observed value size:

- 7 bytes in all captured samples

Estimated storage cost:

- Payload bytes: about 7 bytes per row
- Practical DB cost: about 8-16 bytes per row for a short text field

### 2. `event.timestamp`

Why:

- Better client-side event ordering than pure ingest time
- Useful when OTLP batches arrive late or out of order
- Helps compare upstream event time against server receive time

Recommended DB type:

- `TIMESTAMPTZ`

Observed value size:

- 24 bytes as ISO 8601 text in all captured samples

Estimated storage cost:

- If normalized to `TIMESTAMPTZ`: 8 bytes per row
- If stored as raw text: about 24 bytes per row

### 3. `event.name`

Why:

- High operational value for filtering and debugging OTLP rows
- Distinguishes `api_request`, `api_response`, `api_error`, `codex.sse_event`, `tool_result`, and similar event classes
- Currently used transiently for parsing, but not persisted

Recommended DB type:

- `TEXT` or `VARCHAR(64)`

Observed value size:

- Min 11 bytes
- Max 41 bytes
- Avg about 20.3 bytes across captured samples

Estimated storage cost:

- Payload bytes: about 11-41 bytes per row
- Practical DB cost: about 16-32 bytes per row for typical values

### 4. `success`

Why:

- Cheap, normalized success/failure signal across all three agents
- Complements HTTP status because not all agents expose status the same way
- Useful for failure-rate dashboards and alerting

Recommended DB type:

- `BOOLEAN`

Observed value size:

- 4 bytes in the captured value representations (`true`)

Estimated storage cost:

- If normalized to `BOOLEAN`: about 1 byte per row
- If stored as text: about 4-5 bytes per row

### 5. `prompt_length`

Why:

- Cheap workload-size proxy
- Helps detect prompt growth and unusually large requests without storing prompt content
- Good analytics value with low privacy risk

Recommended DB type:

- `INTEGER`

Observed value size:

- Min 2 bytes
- Max 5 bytes
- Avg about 3.6 bytes across captured samples

Estimated storage cost:

- If normalized to `INTEGER`: 4 bytes per row
- If stored as text: about 2-5 bytes per row

## Secondary Candidate

### `observedTimeUnixNano`

Why:

- Shared across all three record shapes
- Good fallback when `timeUnixNano` is zero or unreliable
- Useful if nanosecond-level OTLP receive ordering becomes important

Recommended DB type:

- `BIGINT`

Observed value size:

- 19 bytes as decimal text

Estimated storage cost:

- If normalized to `BIGINT`: 8 bytes per row
- If stored as text: about 19 bytes per row

Priority:

- Medium
- Useful, but lower ROI than `service.version`, `event.timestamp`, and `event.name`

## Not Recommended For Default Storage

### `prompt`

Why not:

- High privacy sensitivity
- Potentially very large and effectively unbounded
- Large impact on storage size, backups, and query performance

Observed sample size:

- 10-19 bytes in current captures

Important caveat:

- Those numbers are misleading because Claude and Codex currently emit redacted placeholder values in the captures
- Real prompts can easily be hundreds to hundreds of thousands of bytes

Estimated storage cost:

- Best case: small placeholder string
- Realistic case: highly variable, potentially dominating row size

Recommendation:

- Do not add `prompt` to the default `usage` table
- If prompt capture is ever needed, gate it behind an explicit debug mode or separate retention policy

## Suggested Implementation Order

Add first:

1. `service_version`
2. `event_name`
3. `event_ts`
4. `success`
5. `prompt_length` [DONE]

Add only if needed later:

1. `observed_time_ns`
2. `prompt`

## Storage Summary

Approximate normalized per-row storage cost if implemented with typed columns:

- `service_version`: about 8-16 bytes
- `event_name`: about 16-32 bytes
- `event_ts`: 8 bytes
- `success`: 1 byte
- `prompt_length`: 4 bytes
- `observed_time_ns`: 8 bytes

Recommended first-wave addition total:

- Roughly 37-61 bytes per OTLP row, excluding DB row overhead and indexes

Notes:

- These estimates are data-only and intentionally approximate
- Real PostgreSQL row cost will also include tuple/header overhead, alignment, and any index cost
- If indexes are added on these columns, index storage will usually exceed the field payload itself for the small scalar columns

## Per-Agent Field Locations

This section answers the practical question: where is each candidate field located in the OTLP payload for Codex, Claude Code, and Gemini CLI.

JSON-path conventions used below:

- Resource attribute: `resourceLogs[].resource.attributes[]`
- Log-record attribute: `resourceLogs[].scopeLogs[].logRecords[].attributes[]`

### `service.version`

- Codex:
  `resourceLogs[].resource.attributes[].key == "service.version"`
- Claude Code:
  `resourceLogs[].resource.attributes[].key == "service.version"`
- Gemini CLI:
  `resourceLogs[].resource.attributes[].key == "service.version"`

Observed examples:

- Codex: `"0.122.0"`
- Claude Code: `"2.1.114"`
- Gemini CLI: `"v25.9.0"`

### `event.timestamp`

- Codex:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "event.timestamp"`
  Observed in the raw sample on `event.name == "codex.tool_result"`
- Claude Code:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "event.timestamp"`
  Observed in the raw sample on `event.name == "user_prompt"`
- Gemini CLI:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "event.timestamp"`
  Observed in the raw sample on events including `gemini_cli.user_prompt`, `gemini_cli.api_request`, `gemini_cli.plan.approval_mode_duration`, `gemini_cli.plan.approval_mode_switch`, and `gen_ai.client.inference.operation.details`

### `event.name`

- Codex:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "event.name"`
  Observed values include `codex.api_request`, `codex.sse_event`, `codex.tool_decision`, `codex.tool_result`, `codex.user_prompt`
- Claude Code:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "event.name"`
  Observed values include `api_error`, `api_request`, `skill_activated`, `tool_decision`, `tool_result`, `user_prompt`
- Gemini CLI:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "event.name"`
  Observed values include `gemini_cli.api_request`, `gemini_cli.api_response`, `gemini_cli.hook_call`, `gemini_cli.model_routing`, `gemini_cli.user_prompt`, `gen_ai.client.inference.operation.details`

### `success`

- Codex:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "success"`
  Observed in the raw sample on `event.name == "codex.tool_result"`
- Claude Code:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "success"`
  Presence confirmed by aggregated field capture; the current single raw sample file does not preserve the exact event where it appeared
- Gemini CLI:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "success"`
  Presence confirmed by aggregated field capture; the current single raw sample file does not preserve the exact event where it appeared

Note:

- `success` is shared, but it does not appear on every event type for every agent

### `prompt_length`

- Codex:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "prompt_length"`
  Presence confirmed by aggregated field capture; the current single raw sample file does not preserve the exact event where it appeared
- Claude Code:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "prompt_length"`
  Observed in the raw sample on `event.name == "user_prompt"`
- Gemini CLI:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "prompt_length"`
  Observed in the raw sample on `event.name == "gemini_cli.user_prompt"`

Inference:

- For Codex, `prompt_length` most likely arrives on `codex.user_prompt` events, but that specific event was not preserved in the first raw sample file. The aggregated field capture confirms the key exists somewhere in Codex OTLP traffic.

### `prompt`

- Codex:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "prompt"`
  Presence confirmed by aggregated field capture; the current single raw sample file does not preserve the exact event where it appeared
- Claude Code:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "prompt"`
  Observed in the raw sample on `event.name == "user_prompt"`
- Gemini CLI:
  `resourceLogs[].scopeLogs[].logRecords[].attributes[].key == "prompt"`
  Observed in the raw sample on `event.name == "gemini_cli.user_prompt"`

Inference:

- For Codex, `prompt` most likely arrives on `codex.user_prompt` events, but the current saved raw sample did not include that specific record

### `observedTimeUnixNano`

- Codex:
  `resourceLogs[].scopeLogs[].logRecords[].observedTimeUnixNano`
- Claude Code:
  `resourceLogs[].scopeLogs[].logRecords[].observedTimeUnixNano`
- Gemini CLI:
  `resourceLogs[].scopeLogs[].logRecords[].observedTimeUnixNano`

This is not an OTLP attribute key. It is a log-record field on the OTLP envelope itself.
