import { useEffect, useState } from 'react'
import { getToolColor } from '../utils'
import { HorizontalBarChart } from './HorizontalBarChart'
import type { BarItem } from './HorizontalBarChart'
import { t } from '../i18n/index.ts'

type ToolCallRow = {
  tool_name: string
  count: number
}

export function ToolCallsChart({
  filterParams = {},
}: {
  filterParams?: {
    provider?: string
    model?: string | null
    client_source?: string | null
    since?: string | null
    until?: string | null
    only_failed?: boolean
    status_429?: boolean
    status_4xx?: boolean
    status_5xx?: boolean
  }
}) {
  const [rows, setRows] = useState<ToolCallRow[]>([])

  useEffect(() => {
    const controller = new AbortController()
    async function fetchToolCalls() {
      try {
        const url = new URL('/usage/by-tool', window.location.origin)
        if (filterParams.provider) url.searchParams.set('provider', filterParams.provider)
        if (filterParams.model) url.searchParams.set('model', filterParams.model)
        if (filterParams.client_source) url.searchParams.set('client_source', filterParams.client_source)
        if (filterParams.since) url.searchParams.set('since', filterParams.since)
        if (filterParams.until) url.searchParams.set('until', filterParams.until)
        if (filterParams.only_failed) url.searchParams.set('only_failed', 'true')
        if (filterParams.status_429) url.searchParams.set('status_429', 'true')
        if (filterParams.status_4xx) url.searchParams.set('status_4xx', 'true')
        if (filterParams.status_5xx) url.searchParams.set('status_5xx', 'true')

        const res = await fetch(url.toString(), { signal: controller.signal })
        if (res.ok) {
          setRows(await res.json())
        }
      } catch {
        // Ignore abort errors
      }
    }
    fetchToolCalls()
    return () => controller.abort()
  }, [filterParams])

  const items: BarItem[] = rows.map(row => {
    const c = getToolColor(row.tool_name)
    return {
      name: row.tool_name,
      icon: null,
      tokens: row.count,
      cost: 0,
      color: c.bg,
      badgeBg: c.bg,
      badgeText: c.text,
    }
  })

  return (
    <HorizontalBarChart
      title={t('Tool Calls')}
      icon="🔧"
      items={items}
      metric="count"
    />
  )
}
