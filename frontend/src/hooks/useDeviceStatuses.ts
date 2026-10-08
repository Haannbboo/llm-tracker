import { useEffect, useState } from 'react'
import type { DeviceStatus } from '../types'

export function useDeviceStatuses(active: boolean) {
  const [statuses, setStatuses] = useState<DeviceStatus[] | null>(null)

  useEffect(() => {
    if (!active) return
    const controller = new AbortController()
    async function fetchStatuses() {
      try {
        const response = await fetch('/devices/status', { signal: controller.signal })
        if (response.ok) {
          const data = await response.json()
          setStatuses(Array.isArray(data.devices) ? data.devices : [])
        }
      } catch {}
    }
    void fetchStatuses()
    return () => controller.abort()
  }, [active])

  return { statuses }
}
