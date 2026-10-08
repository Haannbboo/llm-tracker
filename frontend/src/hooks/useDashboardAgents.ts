import { useEffect, useState } from 'react'
import type { DeviceStatus, SetupDiagnostics } from '../types'

export type LocalAgentInfo = {
  found: boolean
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

    async function fetchDeviceStatus() {
      try {
        const response = await fetch('/devices/status', { signal: controller.signal })
        if (!response.ok) return
        const data = await response.json()
        const devices: DeviceStatus[] = Array.isArray(data?.devices) ? data.devices : []
        const latest = devices.reduce<DeviceStatus | null>(
          (best, device) => (best === null || device.reported_at > best.reported_at ? device : best),
          null,
        )
        const status = latest?.status
        if (!status) return

        const detected = status.detected as Record<string, any> | undefined
        if (detected) {
          const agents: Record<string, LocalAgentInfo> = {}
          for (const [name, info] of Object.entries(detected)) {
            agents[name] = { found: Boolean(info?.found) }
          }
          setLocalAgents(agents)
        }
        if (status.agents) setSetupDiagnostics({ agents: status.agents })
      } catch {}
    }

    void fetchDeviceStatus()

    return () => controller.abort()
  }, [])

  return { localAgents, setupDiagnostics }
}
