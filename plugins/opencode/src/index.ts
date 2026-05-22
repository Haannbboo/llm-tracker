import type { Plugin } from "@opencode-ai/plugin"

const DEFAULT_ENDPOINT = "http://localhost:4002/v1/logs"
const processed = new Set<string>()

function getEndpoint(options?: Record<string, unknown>): string {
  if (options?.endpoint && typeof options.endpoint === "string") return options.endpoint
  return DEFAULT_ENDPOINT
}

function buildOtlpPayload(params: {
  sessionId: string
  messageId: string
  model: string
  provider: string
  inputTokens: number
  outputTokens: number
  reasoningTokens: number | null
  cachedTokens: number | null
  cacheCreationTokens: number | null
  totalTokens: number
  durationMs: number
  timestampMs: number
}): Record<string, unknown> {
  const timeUnixNano = String(params.timestampMs * 1_000_000)

  const attrs: Record<string, unknown>[] = [
    { key: "event.name", value: { stringValue: "opencode.message_completed" } },
    { key: "session.id", value: { stringValue: params.sessionId } },
    { key: "message.id", value: { stringValue: params.messageId } },
    { key: "model", value: { stringValue: params.model } },
    { key: "provider", value: { stringValue: params.provider } },
    { key: "input_token_count", value: { intValue: params.inputTokens } },
    { key: "output_token_count", value: { intValue: params.outputTokens } },
    { key: "total_token_count", value: { intValue: params.totalTokens } },
    { key: "duration_ms", value: { intValue: params.durationMs } },
  ]

  if (params.reasoningTokens != null) {
    attrs.push({ key: "reasoning_token_count", value: { intValue: params.reasoningTokens } })
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
            { key: "service.name", value: { stringValue: "opencode" } },
            { key: "session.id", value: { stringValue: params.sessionId } },
          ],
        },
        scopeLogs: [
          {
            scope: { name: "opencode-llm-tracker" },
            logRecords: [{ timeUnixNano, severityNumber: 9, attributes: attrs }],
          },
        ],
      },
    ],
  }
}

async function emitOtlp(payload: Record<string, unknown>, endpoint: string): Promise<void> {
  try {
    await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  } catch (err) {
    console.error("[llm-tracker] OTLP emission failed:", err)
  }
}

const plugin: Plugin = async (_input, options) => {
  const endpoint = getEndpoint(options)

  return {
    event: async ({ event }) => {
      if (event.type !== "message.updated") return

      const info = event.properties?.info
      if (!info) return

      if (info.role !== "assistant") return
      if (!info.time?.completed || !info.tokens) return

      if (processed.has(info.id)) return
      processed.add(info.id)

      if (processed.size > 10_000) {
        const entries = Array.from(processed)
        for (let i = 0; i < entries.length / 2; i++) {
          processed.delete(entries[i])
        }
      }

      const provider = info.providerID || "unknown"
      const model = info.modelID || "unknown"

      const createdAt: number = info.time.created ?? Date.now()
      const completedAt: number = info.time.completed
      const durationMs = completedAt - createdAt

      const totalTokens: number =
        (info.tokens.input ?? 0) + (info.tokens.output ?? 0) + (info.tokens.reasoning ?? 0)

      const payload = buildOtlpPayload({
        sessionId: info.sessionID,
        messageId: info.id,
        model,
        provider,
        inputTokens: info.tokens.input ?? 0,
        outputTokens: info.tokens.output ?? 0,
        reasoningTokens: info.tokens.reasoning ?? null,
        cachedTokens: info.tokens.cache?.read ?? null,
        cacheCreationTokens: info.tokens.cache?.write ?? null,
        totalTokens,
        durationMs,
        timestampMs: createdAt,
      })

      await emitOtlp(payload, endpoint)
    },
  }
}

export default plugin
