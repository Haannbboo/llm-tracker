import { useState, useEffect, useCallback, useRef } from 'react'
import type { UsageRow, DateRangeOption, ActiveFilter } from '../types'
import { getSinceDate } from '../utils'
import { t } from '../i18n/index.ts'
import { useApp } from '../contexts/AppContext'

export function useLogsData(opts: {
  activeFilter: ActiveFilter
  activeSource: string | null
  sessionFilter: string | null
  dateRange: DateRangeOption
  customSince: string
  customUntil: string
}) {
  const { refreshTrigger, setError } = useApp()

  const [usageRows, setUsageRows] = useState<UsageRow[]>([])
  const [totalLogs, setTotalLogs] = useState(0)
  const [limit, setLimit] = useState(10)
  const [page, setPage] = useState(1)
  const [jumpPage, setJumpPage] = useState('')
  const [logsLoading, setLogsLoading] = useState(true)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  const [modelColWidth, setModelColWidth] = useState(150)
  const resizeRef = useRef<{ startX: number; startWidth: number } | null>(null)

  const resetPage = useCallback(() => setPage(1), [])

  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault()
    resizeRef.current = { startX: e.clientX, startWidth: modelColWidth }
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
    const handleMouseMove = (e: MouseEvent) => {
      if (!resizeRef.current) return
      const delta = e.clientX - resizeRef.current.startX
      const newWidth = Math.max(100, resizeRef.current.startWidth + delta)
      setModelColWidth(newWidth)
    }
    const handleMouseUp = () => {
      resizeRef.current = null
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }

  // Logs fetch
  useEffect(() => {
    const controller = new AbortController()
    const sig = { signal: controller.signal }

    async function fetchLogs() {
      setError(null)
      setLogsLoading(true)
      try {
        const since = opts.dateRange === 'custom' ? opts.customSince : getSinceDate(opts.dateRange)
        const until = opts.dateRange === 'custom' ? opts.customUntil : null

        const usageUrl = new URL('/usage', window.location.origin)
        usageUrl.searchParams.set('limit', String(limit))
        usageUrl.searchParams.set('offset', String((page - 1) * limit))
        if (opts.activeFilter) {
          if (opts.activeFilter.provider) usageUrl.searchParams.set('provider', opts.activeFilter.provider)
          if (opts.activeFilter.model) usageUrl.searchParams.set('model', opts.activeFilter.model)
          if (opts.activeFilter.only_failed) usageUrl.searchParams.set('only_failed', 'true')
          if (opts.activeFilter.status_429) usageUrl.searchParams.set('status_429', 'true')
          if (opts.activeFilter.status_4xx) usageUrl.searchParams.set('status_4xx', 'true')
          if (opts.activeFilter.status_5xx) usageUrl.searchParams.set('status_5xx', 'true')
        }
        if (opts.activeSource) usageUrl.searchParams.set('client_source', opts.activeSource)
        if (opts.sessionFilter) usageUrl.searchParams.set('session_id', opts.sessionFilter)
        if (since) usageUrl.searchParams.set('since', since)
        if (until) usageUrl.searchParams.set('until', until)

        const countUrl = new URL('/usage/count', window.location.origin)
        if (opts.activeFilter) {
          if (opts.activeFilter.provider) countUrl.searchParams.set('provider', opts.activeFilter.provider)
          if (opts.activeFilter.model) countUrl.searchParams.set('model', opts.activeFilter.model)
          if (opts.activeFilter.only_failed) countUrl.searchParams.set('only_failed', 'true')
          if (opts.activeFilter.status_429) countUrl.searchParams.set('status_429', 'true')
          if (opts.activeFilter.status_4xx) countUrl.searchParams.set('status_4xx', 'true')
          if (opts.activeFilter.status_5xx) countUrl.searchParams.set('status_5xx', 'true')
        }
        if (opts.activeSource) countUrl.searchParams.set('client_source', opts.activeSource)
        if (opts.sessionFilter) countUrl.searchParams.set('session_id', opts.sessionFilter)
        if (since) countUrl.searchParams.set('since', since)
        if (until) countUrl.searchParams.set('until', until)

        const responses = await Promise.all([
          fetch(usageUrl.toString(), sig),
          fetch(countUrl.toString(), sig),
        ])

        if (responses.some(r => !r.ok)) throw new Error(t('Failed to fetch log data'))
        const [usageData, countData] =
          await Promise.all(responses.map(r => r.json())) as [UsageRow[], { total: number }]

        setUsageRows(usageData)
        setTotalLogs(countData.total)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(err instanceof Error ? err.message : t('Unknown error'))
      } finally {
        setLogsLoading(false)
      }
    }

    void fetchLogs()
    return () => controller.abort()
  }, [opts.activeFilter, opts.activeSource, opts.sessionFilter, opts.dateRange, opts.customSince, opts.customUntil, limit, page, refreshTrigger, setError])

  const totalPages = Math.ceil(totalLogs / limit)

  return {
    usageRows, totalLogs, totalPages,
    limit, setLimit, page, setPage, jumpPage, setJumpPage, resetPage,
    logsLoading, expandedRow, setExpandedRow,
    modelColWidth, handleResizeStart,
  }
}
