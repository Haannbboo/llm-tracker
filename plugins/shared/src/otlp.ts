export type OtlpPayloadParams = {
  sessionId: string
  messageId: string
  model: string
  provider: string
  promptLength: number | null
  inputTokens: number | null
  outputTokens: number | null
  reasoningTokens: number | null
  cachedTokens: number | null
  cacheCreationTokens: number | null
  totalTokens: number | null
  durationMs: number | null
  ttftMs: number | null
  statusCode: number | null
  errorName: string | null
  timestampMs: number
}

export function buildOtlpPayload(
  params: OtlpPayloadParams,
  serviceName: string,
): Record<string, any> {
  const eventName = `${serviceName}.message_completed`
  const scopeName = `${serviceName}-llm-tracker`
  const timeUnixNano = String(params.timestampMs * 1_000_000)

  const attrs: Record<string, any>[] = [
    { key: "event.name", value: { stringValue: eventName } },
    { key: "session.id", value: { stringValue: params.sessionId } },
    { key: "message.id", value: { stringValue: params.messageId } },
    { key: "model", value: { stringValue: params.model } },
    { key: "provider", value: { stringValue: params.provider } },
  ]

  if (params.inputTokens != null) {
    attrs.push({ key: "input_token_count", value: { intValue: params.inputTokens } })
  }
  if (params.outputTokens != null) {
    attrs.push({ key: "output_token_count", value: { intValue: params.outputTokens } })
  }
  if (params.totalTokens != null) {
    attrs.push({ key: "total_token_count", value: { intValue: params.totalTokens } })
  }
  if (params.durationMs != null) {
    attrs.push({ key: "duration_ms", value: { intValue: params.durationMs } })
  }
  if (params.reasoningTokens != null) {
    attrs.push({ key: "reasoning_token_count", value: { intValue: params.reasoningTokens } })
  }
  if (params.statusCode != null) {
    attrs.push({ key: "http.response.status_code", value: { intValue: params.statusCode } })
    attrs.push({ key: "status_code", value: { intValue: params.statusCode } })
  }
  if (params.errorName != null) {
    attrs.push({ key: "error.type", value: { stringValue: params.errorName } })
  }
  if (params.ttftMs != null) {
    attrs.push({ key: "ttft_ms", value: { intValue: params.ttftMs } })
  }
  if (params.promptLength != null) {
    attrs.push({ key: "prompt_length", value: { intValue: params.promptLength } })
  }
  if (params.cachedTokens != null) {
    attrs.push({ key: "cached_token_count", value: { intValue: params.cachedTokens } })
  }
  if (params.cacheCreationTokens != null) {
    attrs.push({ key: "cache_creation_token_count", value: { intValue: params.cacheCreationTokens } })
  }

  return {
    resourceLogs: [
      {
        resource: {
          attributes: [
            { key: "service.name", value: { stringValue: serviceName } },
            { key: "session.id", value: { stringValue: params.sessionId } },
          ],
        },
        scopeLogs: [
          {
            scope: { name: scopeName },
            logRecords: [{ timeUnixNano, severityNumber: 9, attributes: attrs }],
          },
        ],
      },
    ],
  }
}

export async function emitOtlp(payload: Record<string, any>, endpoint: string): Promise<boolean> {
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      console.error(`[llm-tracker] OTLP emission failed: collector returned ${response.status}`)
      return false
    }
    return true
  } catch (err) {
    console.error("[llm-tracker] OTLP emission failed:", err)
    return false
  }
}
