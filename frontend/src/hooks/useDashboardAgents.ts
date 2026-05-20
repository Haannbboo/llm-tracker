import { useEffect, useState } from 'react'
import type { SetupDiagnostics } from '../types'

export type LocalAgentInfo = {
  found: boolean
  path: string | null
}

export type AgentsData = {
  localAgents: Record<string, LocalAgentInfo> | null
  setupDiagnostics: SetupDiagnostics | null
}

export function useDashboardAgents(): AgentsData {
  const [localAgents, setLocalAgents] = useState<Record<string, LocalAgentInfo> | null>(null)
  const [setupDiagnostics, setSetupDiagnostics] = useState<SetupDiagnostics | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    async function fetchLocalAgents() {
      try {
        const response = await fetch('/local/agents', { signal: controller.signal })
        if (response.ok) setLocalAgents(await response.json())
      } catch {}
    }

    async function fetchSetupDiagnostics() {
      try {
        const response = await fetch('/local/setup-health', { signal: controller.signal })
        if (response.ok) setSetupDiagnostics(await response.json())
      } catch {}
    }

    void fetchLocalAgents()
    void fetchSetupDiagnostics()

    return () => controller.abort()
  }, [])

  return { localAgents, setupDiagnostics }
}
