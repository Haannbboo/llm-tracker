import { useEffect, useState } from 'react'

type VersionData = {
  name: string
  version: string
}

export function useVersion() {
  const [versionData, setVersionData] = useState<VersionData | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    async function fetchVersion() {
      try {
        const response = await fetch('/version', { signal: controller.signal })
        if (response.ok) setVersionData(await response.json())
      } catch {}
    }

    void fetchVersion()
    return () => controller.abort()
  }, [])

  return versionData
}
