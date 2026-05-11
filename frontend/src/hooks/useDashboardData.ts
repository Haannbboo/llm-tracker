import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import type { ActiveFilter, DailyUsage, DateRangeOption, UsageSummary } from '../types'
import { getSinceDate, getTimezoneOffset, FIXED_PROVIDER_COLORS, PALETTE } from '../utils'
import { t } from '../i18n/index.ts'
import { useApp } from '../contexts/AppContext'

export function useDashboardData() {
  const { refreshTrigger, setError } = useApp()

  const [summary, setSummary] = useState<UsageSummary[]>([])
  const [dailyUsage, setDailyUsage] = useState<DailyUsage[]>([])
  const [heatmapData, setHeatmapData] = useState<DailyUsage[]>([])
  const [totalTrackedEvents, setTotalTrackedEvents] = useState<number | null>(null)
  const [sources, setSources] = useState<string[]>([])
  const [dashboardInitialLoading, setDashboardInitialLoading] = useState(true)
  const [dashboardRefreshing, setDashboardRefreshing] = useState(false)

  const [activeFilter, setActiveFilter] = useState<ActiveFilter>(null)
  const [activeSource, setActiveSource] = useState<string | null>(null)
  const [dateRange, setDateRange] = useState<DateRangeOption>('24h')
  const [customSince, setCustomSince] = useState('')
  const [customUntil, setCustomUntil] = useState('')

  const dashboardRequestRef = useRef(0)
  const dashboardHasLoadedRef = useRef(false)

  const providerColors = useMemo(() => {
    const allProviders = Array.from(new Set(summary.map(s => s.provider))).sort();
    const map: Record<string, string> = {};
    allProviders.forEach(p => {
      const lowP = p.toLowerCase();
      if (FIXED_PROVIDER_COLORS[lowP]) {
        map[p] = FIXED_PROVIDER_COLORS[lowP];
      }
    });
    let paletteIdx = 0;
    allProviders.forEach(p => {
      if (!map[p]) {
        map[p] = PALETTE[paletteIdx % PALETTE.length];
        paletteIdx++;
      }
    });
    return map;
  }, [summary]);

  const applyFilterParams = useCallback((url: URL, opts: { withPagination?: boolean; limit?: number; page?: number } = {}) => {
    const since = dateRange === 'custom' ? customSince : getSinceDate(dateRange)
    const until = dateRange === 'custom' ? customUntil : null

    if (opts.withPagination && opts.limit !== undefined && opts.page !== undefined) {
      url.searchParams.set('limit', String(opts.limit))
      url.searchParams.set('offset', String((opts.page - 1) * opts.limit))
    }
    if (activeFilter) {
      if (activeFilter.provider) url.searchParams.set('provider', activeFilter.provider)
      if (activeFilter.model) url.searchParams.set('model', activeFilter.model)
      if (activeFilter.only_failed) url.searchParams.set('only_failed', 'true')
      if (activeFilter.status_429) url.searchParams.set('status_429', 'true')
      if (activeFilter.status_4xx) url.searchParams.set('status_4xx', 'true')
      if (activeFilter.status_5xx) url.searchParams.set('status_5xx', 'true')
    }
    if (activeSource) url.searchParams.set('client_source', activeSource)
    if (since) url.searchParams.set('since', since)
    if (until) url.searchParams.set('until', until)
    return url
  }, [dateRange, customSince, customUntil, activeFilter, activeSource])

  const dashboardFilterParams = useMemo(() => ({
    provider: activeFilter?.provider,
    model: activeFilter?.model,
    client_source: activeSource,
    since: dateRange === 'custom' ? customSince : getSinceDate(dateRange),
    until: dateRange === 'custom' ? customUntil : null,
    only_failed: activeFilter?.only_failed,
    status_429: activeFilter?.status_429,
    status_4xx: activeFilter?.status_4xx,
    status_5xx: activeFilter?.status_5xx
  }), [activeFilter, activeSource, dateRange, customSince, customUntil])

  // Dashboard fetch
  useEffect(() => {
    const controller = new AbortController()
    const requestId = ++dashboardRequestRef.current
    const isCurrentRequest = () => !controller.signal.aborted && dashboardRequestRef.current === requestId
    const sig = { signal: controller.signal }

    async function fetchDashboard() {
      const isInitialDashboardLoad = !dashboardHasLoadedRef.current
      setError(null)
      setDashboardInitialLoading(isInitialDashboardLoad)
      setDashboardRefreshing(!isInitialDashboardLoad)
      try {
        const summaryUrl = applyFilterParams(new URL('/usage/summary', window.location.origin))
        const dailyUrl = applyFilterParams(new URL('/usage/daily', window.location.origin))
        dailyUrl.searchParams.set('tz_offset', getTimezoneOffset())
        if (dateRange === '24h') dailyUrl.searchParams.set('granularity', 'hour')

        const heatmapUrl = new URL('/usage/daily', window.location.origin)
        heatmapUrl.searchParams.set('since', new Date(Date.now() - 730 * 24 * 60 * 60 * 1000).toISOString())
        heatmapUrl.searchParams.set('until', new Date().toISOString())
        heatmapUrl.searchParams.set('granularity', 'day')
        heatmapUrl.searchParams.set('tz_offset', getTimezoneOffset())
        if (activeFilter) {
          heatmapUrl.searchParams.set('provider', activeFilter.provider)
          if (activeFilter.model) heatmapUrl.searchParams.set('model', activeFilter.model)
        }
        if (activeSource) heatmapUrl.searchParams.set('client_source', activeSource)

        const totalCountUrl = new URL('/usage/count', window.location.origin)

        const responses = await Promise.all([
          fetch(summaryUrl.toString(), sig),
          fetch(dailyUrl.toString(), sig),
          fetch(heatmapUrl.toString(), sig),
          fetch(totalCountUrl.toString(), sig),
        ])

        if (responses.some(r => !r.ok)) throw new Error(t('Failed to fetch dashboard data'))
        const [summaryData, dailyData, heatmapRaw, totalCountData] =
          await Promise.all(responses.map(r => r.json())) as [UsageSummary[], DailyUsage[], DailyUsage[], { total: number }]

        if (!isCurrentRequest()) return

        setSummary(summaryData)
        setDailyUsage(dailyData)
        setHeatmapData(heatmapRaw)
        setTotalTrackedEvents(totalCountData.total)
        dashboardHasLoadedRef.current = true
      } catch (err) {
        if (!isCurrentRequest()) return
        setError(err instanceof Error ? err.message : t('Unknown error'))
      } finally {
        if (isCurrentRequest()) {
          setDashboardInitialLoading(false)
          setDashboardRefreshing(false)
        }
      }
    }

    void fetchDashboard()
    return () => controller.abort()
  }, [activeFilter, activeSource, dateRange, customSince, customUntil, refreshTrigger, applyFilterParams, setError])

  // Sources fetch
  useEffect(() => {
    const controller = new AbortController()
    const since = dateRange === 'custom' ? customSince : getSinceDate(dateRange)
    const until = dateRange === 'custom' ? customUntil : null
    const url = new URL('/usage/sources', window.location.origin)
    if (since) url.searchParams.set('since', since)
    if (until) url.searchParams.set('until', until)
    fetch(url.toString(), { signal: controller.signal })
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then((data: string[]) => setSources(data))
      .catch(() => {})
    return () => controller.abort()
  }, [dateRange, customSince, customUntil, refreshTrigger])

  const totals = useMemo(() => {
    const data = activeFilter
      ? summary.filter(s => s.provider === activeFilter.provider && (activeFilter.model === null || s.model === activeFilter.model))
      : summary

    const requests = data.reduce((sum, row) => sum + (row.requests || 0), 0)
    const promptTokens = data.reduce((sum, row) => sum + (row.prompt_tokens || 0), 0)
    const completionTokens = data.reduce((sum, row) => sum + (row.completion_tokens || 0), 0)
    const reasoningTokens = data.reduce((sum, row) => sum + (row.reasoning_tokens || 0), 0)
    const cachedTokens = data.reduce((sum, row) => sum + (row.cached_tokens || 0), 0)
    const totalTokens = data.reduce((sum, row) => sum + (row.total_tokens || 0), 0)
    const totalCost = data.reduce((sum, row) => sum + (row.total_cost_usd || 0), 0)
    const latencyWeight = data.reduce((sum, row) => sum + (row.avg_latency_ms || 0) * (row.requests || 0), 0)

    const successfulRequests = data.reduce((sum, row) => sum + (row.successful_requests || 0), 0)
    const successRate = requests > 0 ? (successfulRequests / requests) * 100 : 100

    const s429 = data.reduce((sum, row) => sum + (row.status_429 || 0), 0)
    const s4xx = data.reduce((sum, row) => sum + (row.status_4xx || 0), 0)
    const s5xx = data.reduce((sum, row) => sum + (row.status_5xx || 0), 0)
    const sUnknown = data.reduce((sum, row) => sum + (row.status_unknown || 0), 0)

    let minutes = 1440;
    if (dateRange === '7d') minutes = 10080;
    else if (dateRange === '30d') minutes = 43200;

    return {
      requests,
      promptTokens,
      completionTokens,
      reasoningTokens,
      cachedTokens,
      totalTokens,
      totalCost,
      avgLatency: requests === 0 ? 0 : latencyWeight / requests,
      avgEffectivePrice: requests === 0 ? 0 : totalCost / requests,
      avgEffectivePricePerMillion: totalTokens === 0 ? 0 : (totalCost / totalTokens) * 1_000_000,
      rpm: requests / minutes,
      tpm: totalTokens / minutes,
      avgTokensPerRequest: requests === 0 ? 0 : totalTokens / requests,
      successRate,
      statusBreakdown: { s429, s4xx, s5xx, sUnknown }
    }
  }, [activeFilter, summary, dateRange])

  return {
    summary, dailyUsage, heatmapData, totalTrackedEvents, sources,
    dashboardInitialLoading, dashboardRefreshing,
    activeFilter, setActiveFilter, activeSource, setActiveSource,
    dateRange, setDateRange, customSince, setCustomSince, customUntil, setCustomUntil,
    providerColors, applyFilterParams, dashboardFilterParams, totals,
  }
}
