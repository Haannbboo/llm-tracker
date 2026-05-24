import type { Plugin } from "@opencode-ai/plugin"
import { createPlugin } from "./shared/src/plugin.js"

const plugin: Plugin = createPlugin("opencode") as unknown as Plugin
export default plugin
