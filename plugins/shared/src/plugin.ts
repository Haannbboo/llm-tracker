import { finiteNumber, statusCodeFromError, errorName } from "./helpers.js"
import { makePromptState } from "./prompt.js"
import { buildOtlpPayload, buildToolEventPayload, emitOtlp } from "./otlp.js"

const DEFAULT_ENDPOINT = "http://localhost:4005/v1/logs"

function getEndpoint(options?: Record<string, any>): string {
  if (options?.endpoint && typeof options.endpoint === "string") return options.endpoint
  return DEFAULT_ENDPOINT
}

function normalizedProvider(value: unknown): string {
  if (typeof value !== "string") return "unknown"
  const normalized = value.trim().toLowerCase()
  return normalized || "unknown"
}

function nonNegativeNumber(value: unknown): number | null {
  const parsed = finiteNumber(value)
  return parsed != null && parsed >= 0 ? parsed : null
}

function getCompletedInfo(info: any): { completedAt: number | null; statusCode: number | null } {
  const knownStatus = statusCodeFromError(info.error)
  const statusCode = knownStatus ?? (info.error ? 500 : null)
  const completedAt = finiteNumber(info.time?.completed)
  if (completedAt == null && statusCode == null) return { completedAt: null, statusCode: null }
  if (!info.tokens && statusCode == null) return { completedAt: null, statusCode: null }
  return { completedAt, statusCode }
}

async function handleMessageUpdated(
  input: any,
  endpoint: string,
  info: any,
  clientSource: string,
  processed: Set<string>,
  pending: Set<string>,
  promptState: ReturnType<typeof makePromptState>,
): Promise<void> {
  if (info.role === "user") {
    promptState.rememberUserMessage(info.id)
    return
  }

  if (info.role !== "assistant") return
  if (processed.has(info.id) || pending.has(info.id)) return

  const { completedAt, statusCode } = getCompletedInfo(info)
  if (completedAt == null && statusCode == null) return

  pending.add(info.id)

  try {
    const provider = normalizedProvider(info.providerID)
    const model = info.modelID || "unknown"
    const createdAt: number = finiteNumber(info.time?.created) ?? Date.now()
    const timestampMs = completedAt ?? Date.now()
    const durationMs = completedAt != null ? completedAt - createdAt : null
    const firstPartStart = promptState.firstAssistantPartStart.get(info.id)
    const ttftMs =
      firstPartStart != null ? Math.max(0, Math.round(firstPartStart - createdAt)) : null

    const inputTokens = nonNegativeNumber(info.tokens?.input)
    const outputTokens = nonNegativeNumber(info.tokens?.output)
    const reasoningTokens = nonNegativeNumber(info.tokens?.reasoning)
    const cachedTokens = nonNegativeNumber(info.tokens?.cache?.read)
    const cacheCreationTokens = nonNegativeNumber(info.tokens?.cache?.write)
    const tokenValues = [inputTokens, outputTokens, reasoningTokens]
    const totalTokens: number | null = tokenValues.some((value) => value != null)
      ? tokenValues.reduce<number>((sum, value) => sum + (value ?? 0), 0)
      : null
    const promptLength =
      (promptState.userMessages.has(info.parentID) ? promptState.promptLengthForMessage(info.parentID) : null) ??
      (await promptState.fetchPromptLength(input.client, info.sessionID, info.parentID))

    const payload = buildOtlpPayload(
      {
        sessionId: info.sessionID,
        messageId: info.id,
        model,
        provider,
        promptLength,
        inputTokens,
        outputTokens,
        reasoningTokens,
        cachedTokens,
        cacheCreationTokens,
        totalTokens,
        durationMs,
        ttftMs,
        statusCode,
        errorName: errorName(info.error),
        timestampMs,
      },
      clientSource,
    )

    const emitted = await emitOtlp(payload, endpoint)
    if (!emitted) return

    processed.add(info.id)
    if (processed.size > 10_000) {
      const entries = Array.from(processed)
      for (let i = 0; i < entries.length / 2; i++) {
        processed.delete(entries[i])
      }
    }
    promptState.firstAssistantPartStart.delete(info.id)
  } finally {
    pending.delete(info.id)
  }
}

export function createPlugin(clientSource: string) {
  const processed = new Set<string>()
  const pending = new Set<string>()
  const promptState = makePromptState()
  const emittedTools = new Set<string>()

  return async (input: any, options?: Record<string, any>) => {
    const endpoint = getEndpoint(options) ?? DEFAULT_ENDPOINT

    return {
      event: async ({ event }: { event: { type: string; properties?: Record<string, any> } }) => {
        if (event.type === "message.part.updated") {
          const part = event.properties?.part
          if (!part) return
          promptState.rememberPromptPart(part)
          promptState.rememberFirstAssistantPart(part, Date.now())

          // Emit tool_decision event when a ToolPart completes.
          if (
            part.type === "tool" &&
            part.state?.status === "completed" &&
            part.tool &&
            part.callID &&
            !emittedTools.has(part.callID)
          ) {
            emittedTools.add(part.callID)
            if (emittedTools.size > 10_000) {
              const entries = Array.from(emittedTools)
              for (let i = 0; i < entries.length / 2; i++) emittedTools.delete(entries[i])
            }
            const toolPayload = buildToolEventPayload(
              {
                sessionId: part.sessionID,
                messageId: part.messageID,
                callId: part.callID,
                toolName: part.tool,
                timestampMs: Date.now(),
              },
              clientSource,
            )
            await emitOtlp(toolPayload, endpoint)
          }
          return
        }

        if (event.type !== "message.updated") return

        const info = event.properties?.info
        if (!info) return

        await handleMessageUpdated(input, endpoint, info, clientSource, processed, pending, promptState)
      },
    }
  }
}
