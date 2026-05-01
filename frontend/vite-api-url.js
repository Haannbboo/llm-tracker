import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

import yaml from 'js-yaml'

const DEFAULT_API_URL = 'http://localhost:4001'

function buildApiUrlFromConfig(config) {
  const server = config?.server ?? {}
  const host = server.host || 'localhost'
  const port = server.port ?? 4000
  const apiPort = server.api_port ?? port + 1
  return `http://${host}:${apiPort}`
}

function readApiUrlFromTrackerConfig(trackerConfigPath) {
  try {
    const parsed = yaml.load(readFileSync(trackerConfigPath, 'utf-8')) ?? {}
    return buildApiUrlFromConfig(parsed)
  } catch {
    return null
  }
}

export function resolveApiUrl({
  env,
  trackerConfigPath = join(homedir(), '.llm-tracker', 'config.yaml'),
} = {}) {
  if (env?.LLM_TRACKER_API_URL) {
    return env.LLM_TRACKER_API_URL
  }

  if (env?.LLM_TRACKER_BACKEND_URL) {
    return env.LLM_TRACKER_BACKEND_URL
  }

  return readApiUrlFromTrackerConfig(trackerConfigPath) ?? DEFAULT_API_URL
}
