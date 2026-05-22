import type { Plugin } from "@opencode-ai/plugin"

const DEFAULT_ENDPOINT = "http://localhost:4002/v1/logs"
const MAX_TRACKED_MESSAGES = 10_000
const processed = new Set<string>()
const pending = new Set<string>()
const userMessages = new Set<string>()
const promptPartLengths = new Map<string, Map<string, number>>()
const firstAssistantPartStart = new Map<string, number>()

function getEndpoint(options?: Record<string, unknown>): string {
  if (options?.endpoint && typeof options.endpoint === "string") return options.endpoint
  return DEFAULT_ENDPOINT
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function statusCodeValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return Math.trunc(value)
  if (typeof value !== "string") return null

  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? parsed : null
}

function errorObject(error: unknown): Record<string, unknown> | null {
  if (!error || typeof error !== "object") return null
  return error as Record<string, unknown>
}

function errorName(error: unknown): string | null {
  const err = errorObject(error)
  return typeof err?.name === "string" ? err.name : null
}

function statusCodeFromError(error: unknown): number | null {
  const err = errorObject(error)
  if (!err) return null

  const directStatus = statusCodeValue(err.statusCode)
  if (directStatus != null) return directStatus

  const data = errorObject(err.data)
  return statusCodeValue(data?.statusCode)
}

type PromptPart = {
  id?: string
  messageID?: string
  type?: string
  text?: string
  synthetic?: boolean
  ignored?: boolean
  time?: {
    start?: number
    created?: number
  }
}

type PromptClient = {
  session?: {
    message?: (options: { path: { id: string; messageID: string } }) => Promise<{ data?: { info?: { role?: string }, parts?: PromptPart[] } } | undefined>
  }
}

function rememberUserMessage(messageId: string): void {
  userMessages.add(messageId)
  while (userMessages.size > MAX_TRACKED_MESSAGES) {
    const oldest = userMessages.keys().next().value
    if (!oldest) break
    userMessages.delete(oldest)
  }
}

function trimPromptPartLengths(): void {
  while (promptPartLengths.size > MAX_TRACKED_MESSAGES) {
    const oldest = promptPartLengths.keys().next().value
    if (!oldest) break
    promptPartLengths.delete(oldest)
  }
}

function trimFirstAssistantPartStart(): void {
  while (firstAssistantPartStart.size > MAX_TRACKED_MESSAGES) {
    const oldest = firstAssistantPartStart.keys().next().value
    if (!oldest) break
    firstAssistantPartStart.delete(oldest)
  }
}

function rememberPromptPart(part: PromptPart): void {
  if (part.type !== "text") return
  if (!part.messageID || !part.id || typeof part.text !== "string") return
  if (part.synthetic || part.ignored) return

  const parts = promptPartLengths.get(part.messageID) ?? new Map<string, number>()
  parts.set(part.id, part.text.length)
  promptPartLengths.set(part.messageID, parts)
  trimPromptPartLengths()
}

function rememberFirstAssistantPart(part: PromptPart, observedAt: number): void {
  if (part.type !== "text" && part.type !== "reasoning") return
  if (!part.messageID) return
  if (part.synthetic || part.ignored) return
  if (firstAssistantPartStart.has(part.messageID)) return
  const partStart = part.time?.start
  const hasStartTime = typeof partStart === "number" && Number.isFinite(partStart)
  const hasContent = typeof part.text === "string" && part.text.length > 0
  if (!hasStartTime && !hasContent) return

  firstAssistantPartStart.set(part.messageID, hasStartTime ? partStart : observedAt)
  trimFirstAssistantPartStart()
}

function promptLengthForMessage(messageId: string): number | null {
  const parts = promptPartLengths.get(messageId)
  if (!parts) return null
  return Array.from(parts.values()).reduce((sum, length) => sum + length, 0)
}

async function fetchPromptLength(
  client: PromptClient,
  sessionId: string,
  messageId: string,
): Promise<number | null> {
  try {
    const result = await client.session?.message?.({ path: { id: sessionId, messageID: messageId } })
    if (result?.data?.info?.role !== "user") return null
    const parts = result.data.parts
    if (!Array.isArray(parts)) return null

    rememberUserMessage(messageId)
    for (const part of parts) {
      rememberPromptPart(part)
    }
    return promptLengthForMessage(messageId)
  } catch {
    return null
  }
}

function buildOtlpPayload(params: {
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
}): Record<string, unknown> {
  const timeUnixNano = String(params.timestampMs * 1_000_000)

  const attrs: Record<string, unknown>[] = [
    { key: "event.name", value: { stringValue: "opencode.message_completed" } },
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

async function emitOtlp(payload: Record<string, unknown>, endpoint: string): Promise<boolean> {
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

const plugin: Plugin = async (input, options) => {
  const endpoint = getEndpoint(options)

  return {
    event: async ({ event }) => {
      if (event.type === "message.part.updated") {
        const part = event.properties?.part
        if (!part) return
        rememberPromptPart(part)
        rememberFirstAssistantPart(part, Date.now())
        return
      }

      if (event.type !== "message.updated") return

      const info = event.properties?.info
      if (!info) return

      if (info.role === "user") {
        rememberUserMessage(info.id)
        return
      }

      if (info.role !== "assistant") return

      if (processed.has(info.id) || pending.has(info.id)) return

      const provider = info.providerID || "unknown"
      const model = info.modelID || "unknown"
      const knownStatus = statusCodeFromError(info.error)
      const statusCode = knownStatus ?? (info.error ? 500 : null)
      const completedAt = finiteNumber(info.time?.completed)
      if (completedAt == null && statusCode == null) return
      if (!info.tokens && statusCode == null) return
      pending.add(info.id)

      try {
        const createdAt: number = finiteNumber(info.time?.created) ?? Date.now()
        const timestampMs = completedAt ?? Date.now()
        const durationMs = completedAt != null ? completedAt - createdAt : null
        const firstPartStart = firstAssistantPartStart.get(info.id)
        const ttftMs =
          firstPartStart != null ? Math.max(0, Math.round(firstPartStart - createdAt)) : null

        const inputTokens = finiteNumber(info.tokens?.input)
        const outputTokens = finiteNumber(info.tokens?.output)
        const reasoningTokens = finiteNumber(info.tokens?.reasoning)
        const tokenValues = [inputTokens, outputTokens, reasoningTokens]
        const totalTokens: number | null = tokenValues.some((value) => value != null)
          ? tokenValues.reduce<number>((sum, value) => sum + (value ?? 0), 0)
          : null
        const promptLength =
          (userMessages.has(info.parentID) ? promptLengthForMessage(info.parentID) : null) ??
          (await fetchPromptLength(input.client, info.sessionID, info.parentID))

        const payload = buildOtlpPayload({
          sessionId: info.sessionID,
          messageId: info.id,
          model,
          provider,
          promptLength,
          inputTokens,
          outputTokens,
          reasoningTokens,
          cachedTokens: finiteNumber(info.tokens?.cache?.read),
          cacheCreationTokens: finiteNumber(info.tokens?.cache?.write),
          totalTokens,
          durationMs,
          ttftMs,
          statusCode,
          errorName: errorName(info.error),
          timestampMs,
        })

        const emitted = await emitOtlp(payload, endpoint)
        if (!emitted) return

        processed.add(info.id)
        if (processed.size > 10_000) {
          const entries = Array.from(processed)
          for (let i = 0; i < entries.length / 2; i++) {
            processed.delete(entries[i])
          }
        }
        firstAssistantPartStart.delete(info.id)
      } finally {
        pending.delete(info.id)
      }
    },
  }
}

export default plugin
