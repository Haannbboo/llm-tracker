import type { PromptPart, PromptClient } from "./types.js"

export const MAX_TRACKED_MESSAGES = 10_000

export function makePromptState() {
  const userMessages = new Set<string>()
  const promptPartLengths = new Map<string, Map<string, number>>()
  const firstAssistantPartStart = new Map<string, number>()

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

  return {
    userMessages,
    firstAssistantPartStart,
    rememberUserMessage,
    rememberPromptPart,
    rememberFirstAssistantPart,
    promptLengthForMessage,
    fetchPromptLength,
  }
}

export type PromptState = ReturnType<typeof makePromptState>
