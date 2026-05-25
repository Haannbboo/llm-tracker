export type PromptPart = {
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

export type PromptClient = {
  session?: {
    message?: (options: { path: { id: string; messageID: string } }) => Promise<
      { data?: { info?: { role?: string }; parts?: PromptPart[] } } | undefined
    >
  }
}
