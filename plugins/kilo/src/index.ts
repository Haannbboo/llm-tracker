import type { Plugin } from "@kilocode/plugin"
import { createPlugin } from "./shared/src/plugin.js"

const plugin: Plugin = createPlugin("kilo") as unknown as Plugin
export default plugin
