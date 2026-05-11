import { useState, useEffect, useCallback, useMemo } from 'react'
import type { SessionSummary, SessionsSummary, DateRangeOption } from '../types'
import { getSinceDate, buildSessionInsights } from '../utils'
import { t } from '../i18n/index.ts'
import { useApp } from '../contexts/AppContext'

export function useSessionsData(opts: {
  activeSource: string | null
  dateRange: DateRangeOption
  customSince: string
  customUntil: string
}) {
  const { refreshTrigger, setError } = useApp()

  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [sessionsSummary, setSessionsSummary] = useState<SessionsSummary | null>(null)
  const [sessionCount, setSessionCount] = useState(0)
  const [sessionsLoading, setSessionsLoading] = useState(true)
  const [sessionSortBy, setSessionSortBy] = useState<string>('ended')
  const [sessionSortOrder, setSessionSortOrder] = useState<'asc' | 'desc'>('desc')
  const [sessionPage, setSessionPage] = useState(1)
  const [hasMoreSessions, setHasMoreSessions] = useState(true)
  const [selectedSession, setSelectedSession] = useState<SessionSummary | null>(null)

  const handleSessionSort = useCallback((column: string) => {
    if (sessionSortBy === column) {
      setSessionSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSessionSortBy(column)
      setSessionSortOrder('desc')
    }
    setSessionPage(1)
  }, [sessionSortBy])

  const sessionInsights = useMemo(() => {
    return buildSessionInsights(sessions)
  }, [sessions])

  // Sessions fetch
  useEffect(() => {
    const controller = new AbortController()
    const sig = { signal: controller.signal }

    async function fetchSessionsData() {
      setError(null)
      setSessionsLoading(true)
      try {
        const since = opts.dateRange === 'custom' ? opts.customSince : getSinceDate(opts.dateRange)
        const until = opts.dateRange === 'custom' ? opts.customUntil : null

        const sessionsUrl = new URL('/sessions', window.location.origin)
        if (opts.activeSource) sessionsUrl.searchParams.set('client_source', opts.activeSource)
        if (since) sessionsUrl.searchParams.set('since', since)
        if (until) sessionsUrl.searchParams.set('until', until)
        sessionsUrl.searchParams.set('sort_by', sessionSortBy)
        sessionsUrl.searchParams.set('sort_order', sessionSortOrder)
        sessionsUrl.searchParams.set('limit', '50')
        sessionsUrl.searchParams.set('offset', String((sessionPage - 1) * 50))

        const summaryUrl = new URL('/sessions/summary', window.location.origin)
        if (opts.activeSource) summaryUrl.searchParams.set('client_source', opts.activeSource)
        if (since) summaryUrl.searchParams.set('since', since)
        if (until) summaryUrl.searchParams.set('until', until)

        const responses = await Promise.all([
          fetch(sessionsUrl.toString(), sig),
          fetch(summaryUrl.toString(), sig),
        ])

        if (responses.some(r => !r.ok)) throw new Error(t('Failed to fetch session data'))
        const [sessionsData, summaryData] =
          await Promise.all(responses.map(r => r.json())) as [{ sessions: SessionSummary[]; total: number }, SessionsSummary]

        if (sessionPage === 1) {
          setSessions(sessionsData.sessions)
        } else {
          setSessions(prev => [...prev, ...sessionsData.sessions])
        }
        setSessionCount(sessionsData.total)
        setSessionsSummary(summaryData)
        setHasMoreSessions(sessionsData.sessions.length === 50)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(err instanceof Error ? err.message : t('Unknown error'))
      } finally {
        setSessionsLoading(false)
      }
    }

    void fetchSessionsData()
    return () => controller.abort()
  }, [opts.activeSource, opts.dateRange, opts.customSince, opts.customUntil, refreshTrigger, sessionSortBy, sessionSortOrder, sessionPage, setError])

  return {
    sessions, sessionsSummary, sessionCount, sessionsLoading, hasMoreSessions,
    sessionSortBy, sessionSortOrder, sessionPage,
    selectedSession, setSelectedSession,
    handleSessionSort, sessionInsights,
    setSessionPage,
  }
}
