import { useEffect, useMemo, useState, useRef, useCallback } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import yaml from 'js-yaml'
import './App.css'
import { toggleTheme, getTheme } from './theme'
import { getModelBadgeBackgroundColor, getModelTextColor } from './model-badge'
import type { ActiveFilter, DailyUsage, DateRangeOption, UsageRow, UsageSummary } from './types'
import { formatCompact, formatCost, formatLatency, formatNumber, formatRate, formatTime, FIXED_PROVIDER_COLORS, getProviderColor, getSinceDate, getTimezoneOffset, getModelIcon, PALETTE, value } from './utils'
import { Sparkline } from './Sparkline'
import { ModelSelector } from './ModelSelector'
import { TrendChart } from './charts/TrendChart'
import { CacheHitRateChart } from './charts/CacheHitRateChart'
import { TopUsageChart } from './charts/TopUsageChart'
import { DailyHeatmap } from './charts/DailyHeatmap'
import { t, useLang } from './i18n/index.ts'
import { useCountUp } from './useCountUp'
import { getVerifyTimeoutGuidance } from './setup-guidance'

type SetupAgentHealth = {
  configured: boolean
  endpoint_matches: boolean
  configured_endpoint: string | null
  expected_endpoint: string
  status: 'ready' | 'missing_config' | 'wrong_endpoint'
}

type SetupDiagnostics = {
  expected: {
    otlp_endpoint: string
    otlp_logs_endpoint: string
  }
  summary: {
    total_agents: number
    configured_agents: number
    matching_agents: number
  }
  agents: Record<string, SetupAgentHealth>
}

type OnboardingCopiedCommand = {
  source: string
  command: string
}

function CopyButton({
  text,
  className = 'btn-ghost',
  style,
  idleLabel,
  copiedLabel,
  onCopied,
  timeoutMs = 1500,
}: {
  text: string
  className?: string
  style?: CSSProperties
  idleLabel: ReactNode
  copiedLabel: ReactNode
  onCopied?: () => void
  timeoutMs?: number
}) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    void navigator.clipboard.writeText(text)
      .then(() => {
        setCopied(true)
        onCopied?.()
        setTimeout(() => setCopied(false), timeoutMs)
      })
  }

  return (
    <button
      className={`${className}${copied ? ' btn-copy-clicked' : ''}`}
      onClick={handleCopy}
      style={style}
    >
      {copied ? copiedLabel : idleLabel}
    </button>
  )
}

function App() {
  const [view, setView] = useState<'dashboard' | 'logs' | 'settings' | 'test'>('dashboard')
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [summary, setSummary] = useState<UsageSummary[]>([])
  const [usageRows, setUsageRows] = useState<UsageRow[]>([])
  const [dailyUsage, setDailyUsage] = useState<DailyUsage[]>([])
  const [totalLogs, setTotalLogs] = useState(0)
  const [totalTrackedEvents, setTotalTrackedEvents] = useState<number | null>(null)

  // Connectivity Test State
  const [testBaseUrl, setTestBaseUrl] = useState('')
  const [testApiKey, setTestApiKey] = useState('')
  const [testFormat, setTestFormat] = useState('openai')
  const [testModel, setTestModel] = useState('')
  const [testMessage, setTestMessage] = useState('What is 2 + 3?')
  const [testResult, setTestResult] = useState<Record<string, any> | null>(null)
  const [isTesting, setIsTesting] = useState(false)

  const [limit, setLimit] = useState(10)
  const [page, setPage] = useState(1)
  const [jumpPage, setJumpPage] = useState('')
  const resetPage = useCallback(() => setPage(1), [])
  const requestUsageRefresh = useCallback(() => {
    setRefreshTrigger(trigger => trigger + 1)
  }, [])

  const [activeFilter, setActiveFilter] = useState<ActiveFilter>(null)
  const [activeSource, setActiveSource] = useState<string | null>(null)
  const [sources, setSources] = useState<string[]>([])
  const [heatmapData, setHeatmapData] = useState<DailyUsage[]>([])
  const [dateRange, setDateRange] = useState<DateRangeOption>('24h')
  const [customSince, setCustomSince] = useState('')
  const [customUntil, setCustomUntil] = useState('')

  const [configContent, setConfigContent] = useState('')
  const [configParsed, setConfigParsed] = useState<Record<string, any> | null>(null)
  const [selectedPricingProvider, setSelectedPricingProvider] = useState('global')
  const [configStatus, setConfigStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  const [error, setError] = useState<string | null>(null)
  const [theme, setTheme] = useState<'light' | 'dark'>(getTheme)
  const { lang, setLang } = useLang()
  const [dashboardInitialLoading, setDashboardInitialLoading] = useState(true)
  const [dashboardRefreshing, setDashboardRefreshing] = useState(false)
  const [logsLoading, setLogsLoading] = useState(true)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)

  // Empty-state verification polling state machine
  const [verifyPhase, setVerifyPhase] = useState<'idle' | 'polling' | 'success' | 'timeout'>('idle')
  const [verificationResult, setVerificationResult] = useState<UsageRow | null>(null)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollingStartRef = useRef<number>(0)
  const autoVerifyStartedRef = useRef(false)
  const [copiedOnboardingCommand, setCopiedOnboardingCommand] = useState<OnboardingCopiedCommand | null>(null)
  const [localAgents, setLocalAgents] = useState<Record<string, { found: boolean; path: string | null }> | null>(null)
  const [setupDiagnostics, setSetupDiagnostics] = useState<SetupDiagnostics | null>(null)

  const [modelColWidth, setModelColWidth] = useState(180)
  const resizeRef = useRef<{ startX: number; startWidth: number } | null>(null)
  const dashboardRequestRef = useRef(0)
  const dashboardHasLoadedRef = useRef(false)

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

  useEffect(() => {
    const controller = new AbortController()
    async function fetchInitialConfig() {
      try {
        const response = await fetch('/config', { signal: controller.signal })
        if (response.ok) {
          const data = await response.json()
          setConfigContent(data.content)
          setConfigParsed(data.parsed)
        }
      } catch (err) {
        console.error('Failed to load initial config:', err)
      }
    }
    async function fetchLocalAgents() {
      try {
        const response = await fetch('/local/agents', { signal: controller.signal })
        if (response.ok) setLocalAgents(await response.json())
      } catch {}
    }
    async function fetchSetupDiagnostics() {
      try {
        const response = await fetch('/local/setup-health')
        if (response.ok) setSetupDiagnostics(await response.json())
      } catch {}
    }
    void fetchInitialConfig()
    void fetchLocalAgents()
    void fetchSetupDiagnostics()
    return () => controller.abort()
  }, [])

  // Shared helper: apply filter/source/date params to a URL
  const applyFilterParams = useCallback((url: URL, opts: { withPagination?: boolean } = {}) => {
    const since = dateRange === 'custom' ? customSince : getSinceDate(dateRange)
    const until = dateRange === 'custom' ? customUntil : null

    if (opts.withPagination) {
      url.searchParams.set('limit', String(limit))
      url.searchParams.set('offset', String((page - 1) * limit))
    }
    if (activeFilter) {
      url.searchParams.set('provider', activeFilter.provider)
      if (activeFilter.model) url.searchParams.set('model', activeFilter.model)
    }
    if (activeSource) url.searchParams.set('client_source', activeSource)
    if (since) url.searchParams.set('since', since)
    if (until) url.searchParams.set('until', until)
    return url
  }, [dateRange, customSince, customUntil, limit, page, activeFilter, activeSource])

  // Dashboard: summary, daily, heatmap, by-source, by-provider (no paginated logs)
  useEffect(() => {
    if (view !== 'dashboard') return
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
  }, [view, activeFilter, activeSource, dateRange, customSince, customUntil, refreshTrigger, applyFilterParams])

  // Logs: paginated rows, count
  useEffect(() => {
    if (view !== 'logs') return
    const controller = new AbortController()
    const sig = { signal: controller.signal }

    async function fetchLogs() {
      setError(null)
      setLogsLoading(true)
      try {
        const usageUrl = applyFilterParams(new URL('/usage', window.location.origin), { withPagination: true })
        const countUrl = applyFilterParams(new URL('/usage/count', window.location.origin))

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
  }, [view, activeFilter, activeSource, limit, page, dateRange, customSince, customUntil, refreshTrigger, applyFilterParams])

  useEffect(() => {
    if (view !== 'dashboard' && view !== 'logs') return
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
  }, [view, dateRange, customSince, customUntil, refreshTrigger])

  const totals = useMemo(() => {
    const data = activeFilter
      ? summary.filter(s => s.provider === activeFilter.provider && (activeFilter.model === null || s.model === activeFilter.model))
      : summary

    const requests = data.reduce((sum, row) => sum + value(row.requests), 0)
    const promptTokens = data.reduce((sum, row) => sum + value(row.prompt_tokens), 0)
    const completionTokens = data.reduce((sum, row) => sum + value(row.completion_tokens), 0)
    const reasoningTokens = data.reduce((sum, row) => sum + value(row.reasoning_tokens), 0)
    const cachedTokens = data.reduce((sum, row) => sum + value(row.cached_tokens), 0)
    const totalTokens = data.reduce((sum, row) => sum + value(row.total_tokens), 0)
    const totalCost = data.reduce((sum, row) => sum + value(row.total_cost_usd), 0)
    const latencyWeight = data.reduce((sum, row) => sum + value(row.avg_latency_ms) * value(row.requests), 0)

    const successfulRequests = data.reduce((sum, row) => sum + value(row.successful_requests), 0)
    const successRate = requests > 0 ? (successfulRequests / requests) * 100 : 100

    let minutes = 1440;
    if (dateRange === '7d') minutes = 10080;
    else if (dateRange === '30d') minutes = 43200;
    else if (dateRange === 'all') {
      minutes = 1440;
    }

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
      successRate
    }
  }, [activeFilter, summary, dateRange])

  const animatedTotalTokens = useCountUp(dashboardInitialLoading ? 0 : totals.totalTokens)
  const animatedRequests = useCountUp(dashboardInitialLoading ? 0 : totals.requests)
  const animatedCost = useCountUp(dashboardInitialLoading ? 0 : totals.totalCost)
  const animatedRpm = useCountUp(dashboardInitialLoading ? 0 : totals.rpm)
  const animatedLatency = useCountUp(dashboardInitialLoading ? 0 : totals.avgLatency)

  const totalPages = Math.ceil(totalLogs / limit)

  const handleSaveConfig = async () => {
    setConfigStatus('saving')
    try {
      const response = await fetch('/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: configContent })
      })
      if (response.ok) {
        setConfigStatus('saved')
        setTimeout(() => setConfigStatus('idle'), 3000)
      } else {
        const error = await response.json()
        setError(error.detail || t('Failed to save config'))
        setConfigStatus('error')
      }
    } catch {
      setError(t('Connection error while saving config'))
      setConfigStatus('error')
    }
  }

  const handleRunTest = async () => {
    setIsTesting(true)
    setTestResult(null)
    try {
      const response = await fetch('/test-connectivity', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: testBaseUrl,
          api_key: testApiKey,
          format: testFormat,
          model: testModel || null,
          message: testMessage || null
        })
      })
      const text = await response.text()
      try {
        setTestResult(JSON.parse(text))
      } catch {
        setTestResult({ status_code: response.status, body: text, url: '' })
      }
    } catch (err) {
      setTestResult({ error: err instanceof Error ? err.message : t('Test failed') })
    } finally {
      setIsTesting(false)
    }
  }

  const handleCostChange = (model: string, field: string, value: string) => {
    const numValue = value === '' ? undefined : parseFloat(value);
    const newParsed = { ...configParsed };

    if (selectedPricingProvider === 'global') {
      if (!newParsed.models) newParsed.models = {};
      if (!newParsed.models[model]) newParsed.models[model] = {};
      if (!newParsed.models[model].cost) newParsed.models[model].cost = {};

      if (numValue === undefined) {
        delete newParsed.models[model].cost[field];
      } else {
        newParsed.models[model].cost[field] = numValue;
      }
    } else {
      if (!newParsed.providers) newParsed.providers = {};
      if (!newParsed.providers[selectedPricingProvider]) newParsed.providers[selectedPricingProvider] = {};
      if (!newParsed.providers[selectedPricingProvider].models) newParsed.providers[selectedPricingProvider].models = {};
      if (!newParsed.providers[selectedPricingProvider].models[model]) newParsed.providers[selectedPricingProvider].models[model] = {};
      if (!newParsed.providers[selectedPricingProvider].models[model].cost) newParsed.providers[selectedPricingProvider].models[model].cost = {};

      if (numValue === undefined) {
        delete newParsed.providers[selectedPricingProvider].models[model].cost[field];
      } else {
        newParsed.providers[selectedPricingProvider].models[model].cost[field] = numValue;
      }
    }

    setConfigParsed(newParsed);
    setConfigContent(yaml.dump(newParsed, { indent: 2, noRefs: true }));
  }

  const stopVerificationPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }

  useEffect(() => stopVerificationPolling, [])

  const handleVerifyEvent = () => {
    stopVerificationPolling()
    setVerifyPhase('polling')
    setVerificationResult(null)
    pollingStartRef.current = Date.now()

    const checkForEvent = async () => {
      try {
        const countRes = await fetch('/usage/count')
        if (!countRes.ok) throw new Error('Failed to check')
        const { total } = await countRes.json()
        setTotalTrackedEvents(total)

        if (total > 0) {
          stopVerificationPolling()
          setVerifyPhase('success')
          const usageRes = await fetch('/usage?limit=1')
          if (usageRes.ok) {
            const rows = await usageRes.json() as UsageRow[]
            if (rows.length > 0) {
              setVerificationResult(rows[0])
              setRefreshTrigger(t => t + 1)
            }
          }
          return
        }

        if (Date.now() - pollingStartRef.current >= 45000) {
          stopVerificationPolling()
          setVerifyPhase('timeout')
        }
      } catch {
        if (Date.now() - pollingStartRef.current >= 45000) {
          stopVerificationPolling()
          setVerifyPhase('timeout')
        }
      }
    }

    void checkForEvent()
    pollingRef.current = setInterval(checkForEvent, 2000)
  }

  const armOnboardingVerification = (command: OnboardingCopiedCommand) => {
    setCopiedOnboardingCommand(command)
    handleVerifyEvent()
  }

  const getAgentDisplayName = (name: string) => {
    const normalized = name.toLowerCase()
    if (normalized.includes('vectorengine') || normalized.includes('claude')) return 'Claude Code'
    if (normalized.includes('codesonline') || normalized.includes('codex')) return 'Codex'
    if (normalized.includes('gemini')) return 'Gemini CLI'
    return name
  }

  const getSetupAgentKey = (name: string) => {
    const normalized = name.toLowerCase()
    if (normalized.includes('vectorengine') || normalized.includes('claude')) return 'claude'
    if (normalized.includes('codesonline') || normalized.includes('codex')) return 'codex'
    if (normalized.includes('gemini')) return 'gemini'
    return normalized
  }

  const manualCurlEquivalent = (() => {
    let base = testBaseUrl.replace(/\/$/, '')
    if (!base.includes('/v1')) base = base + '/v1'
    const endpoint = testFormat === 'openai' ? '/chat/completions' : testFormat === 'anthropic' ? '/messages' : '/responses'
    const fullUrl = base.endsWith(endpoint) ? base : base + endpoint
    return `curl ${fullUrl} \\\
  -H "${testFormat === 'anthropic' ? 'x-api-key' : 'Authorization: Bearer'}: ${testApiKey || 'YOUR_KEY'}" \\\
  -H "Content-Type: application/json" \\\
  -d '{"model": "${testModel || 'gpt-5.4'}", "messages": [{"role": "user", "content": "${(testMessage || 'What is 2 + 3?').replace(/"/g, '\\"')}"}], "max_tokens": 10}'`
  })()

  const showFirstRunOnboarding = !dashboardInitialLoading && totalTrackedEvents === 0

  useEffect(() => {
    if (!showFirstRunOnboarding || autoVerifyStartedRef.current) return
    autoVerifyStartedRef.current = true
    handleVerifyEvent()
  }, [showFirstRunOnboarding])
  const foundLocalAgents = localAgents
    ? Object.entries(localAgents).filter(([, info]) => info.found)
    : []
  const foundLocalAgentCount = foundLocalAgents.length
  const setupLocalAgentTotal = setupDiagnostics
    ? foundLocalAgents.filter(([name]) => setupDiagnostics.agents[getSetupAgentKey(name)]).length
    : foundLocalAgentCount
  const setupMatchingAgents = setupDiagnostics
    ? foundLocalAgents.filter(([name]) => setupDiagnostics.agents[getSetupAgentKey(name)]?.endpoint_matches).length
    : 0
  const setupConfiguredAgents = setupDiagnostics
    ? foundLocalAgents.filter(([name]) => setupDiagnostics.agents[getSetupAgentKey(name)]?.configured).length
    : 0
  const setupSummaryText = setupDiagnostics
    ? setupLocalAgentTotal > 0
      ? `${setupMatchingAgents}/${setupLocalAgentTotal}`
      : t('No local Agent')
    : t('Unknown')
  const setupSummaryColor = setupDiagnostics && setupMatchingAgents > 0 ? 'var(--color-green)' : 'var(--text-muted)'
  const verifyTimeoutGuidance = getVerifyTimeoutGuidance({
    setupHealthAvailable: setupDiagnostics !== null,
    localAgentDetectionAvailable: localAgents !== null,
    localAgentCount: foundLocalAgentCount,
    setupLocalAgentTotal,
    configuredAgents: setupConfiguredAgents,
    matchingAgents: setupMatchingAgents,
  })

  return (
    <div className="app">
      <main className="main">
        <header className="top-navbar">
          <pre className="navbar-ascii" style={{ fontFamily: 'monospace', fontSize: 'clamp(2px, 0.275vw, 5px)', lineHeight: '1.1', margin: 0, whiteSpace: 'pre', letterSpacing: '0.5px' }}>
{" ___       ___       _____ ______           _________  ________  ________  ________  ___  __    _______   ________     \n"}
{"|\\  \\     |\\  \\     |\\   _ \\  _   \\        |\\___   ___\\\\   __  \\|\\   __  \\|\\   ____\\|\\  \\|\\  \\ |\\  ___ \\ |\\   __  \\    \n"}
{"\\ \\  \\    \\ \\  \\    \\ \\  \\\\\\__\\ \\  \\       |\\___ \\  \\_\\ \\  \\|\\  \\ \\  \\|\\  \\ \\  \\___|\\ \\  \\/  /|\\ \\   __/|\\ \\  \\|\\  \\   \n"}
{" \\ \\  \\    \\ \\  \\    \\ \\  \\\\|__| \\  \\           \\ \\  \\ \\ \\   _  _\\ \\   __  \\ \\  \\    \\ \\   ___  \\ \\  \\_|/_\\ \\   _  _\\  \n"}
{"  \\ \\  \\____\\ \\  \\____\\ \\  \\    \\ \\  \\           \\ \\  \\ \\ \\  \\\\  \\\\ \\  \\ \\  \\ \\  \\____\\ \\  \\\\ \\  \\ \\  \\_|\\ \\ \\  \\\\  \\| \n"}
{"   \\ \\_______\\ \\_______\\ \\__\\    \\ \\__\\           \\ \\__\\ \\ \\__\\\\ _\\\\ \\__\\ \\__\\ \\_______\\ \\__\\\\ \\__\\ \\_______\\ \\__\\\\ _\\ \n"}
{"    \\|_______|\\|_______|\\|__|     \\|__|            \\|__|  \\|__|\\|__|\\|__|\\|__|\\|_______|\\|__| \\|__|\\|_______|\\|__|\\|__|"}
</pre>
          <nav className="navbar-nav">
            <button className={`nav-item ${view === 'dashboard' ? 'active' : ''}`} onClick={() => setView('dashboard')}>
              📊 {t('Dashboard')}
            </button>
            <button className={`nav-item ${view === 'logs' ? 'active' : ''}`} onClick={() => setView('logs')}>
              📜 {t('Request Logs')}
            </button>
            <button className={`nav-item ${view === 'settings' ? 'active' : ''}`} onClick={() => setView('settings')}>
              ⚙️ {t('Settings')}
            </button>
            <button className={`nav-item ${view === 'test' ? 'active' : ''}`} onClick={() => setView('test')}>
              🔌 {t('Connectivity Test')}
            </button>
          </nav>
          <button
            className="nav-item"
            style={{ marginLeft: 'auto', fontSize: '18px' }}
            onClick={() => setTheme(toggleTheme())}
            title={theme === 'dark' ? t('Switch to light mode') : t('Switch to dark mode')}
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
          <button
            className="nav-item"
            style={{ fontSize: '13px', fontWeight: 700, minWidth: '36px', textAlign: 'center' }}
            onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
            title={lang === 'zh' ? '切换到中文' : 'Switch to English'}
          >
            {lang === 'zh' ? '中' : 'EN'}
          </button>
        </header>

        <div className="content-body">
          {view === 'dashboard' && (
            <>
              {totalTrackedEvents !== 0 && (
              <div className="dashboard-filter-row" style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '8px' }}>
                  <select
                    className="input-plain"
                    value={dateRange}
                    onChange={(e) => { setDateRange(e.target.value as DateRangeOption); resetPage(); }}
                  >
                    <option value="24h">{t('Last 24 Hours')}</option>
                    <option value="7d">{t('Last 7 Days')}</option>
                    <option value="30d">{t('Last 30 Days')}</option>
                    <option value="all">{t('All Time')}</option>
                    <option value="custom">{t('Custom Range')}</option>
                  </select>
                  <ModelSelector
                    activeFilter={activeFilter}
                    summary={summary}
                    providerColors={providerColors}
                    onChange={(f) => { setActiveFilter(f); resetPage(); }}
                  />
                  <select
                    className="input-plain"
                    value={activeSource || ''}
                    onChange={(e) => { setActiveSource(e.target.value || null); resetPage(); }}
                  >
                    <option value="">{t('All Sources')}</option>
                    {sources.map(source => (
                      <option key={source} value={source}>{source}</option>
                    ))}
                  </select>
                  <button
                    className={`btn-ghost btn-refresh ${dashboardRefreshing ? 'is-refreshing' : ''}`}
                    onClick={requestUsageRefresh}
                    disabled={dashboardRefreshing}
                    aria-label={t('Refresh')}
                    title={t('Refresh')}
                  >
                    <span className="refresh-icon">↻</span>
                  </button>
                </div>
              )}

              {dashboardInitialLoading ? (
                <div />
              ) : showFirstRunOnboarding ? (
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '40px 24px',
                  textAlign: 'center',
                  gap: '24px',
                }}>
                  <div style={{ maxWidth: '560px' }}>
                    <div style={{ fontSize: '28px', marginBottom: '8px' }}>
                      {t('No traffic tracked yet')}
                    </div>
                    <div style={{ fontSize: '15px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                      {t('Run one test command below. When llm-tracker sees the request, usage, cost, and latency will appear here.')}
                    </div>
                  </div>

                  {/* Step 1: Bootstrap */}
                  <div style={{ width: '100%', maxWidth: '680px', textAlign: 'left' }}>
                    <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '12px', textTransform: 'uppercase' }}>
                      {t('Step 1: Bootstrap')}
                    </div>
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 16px',
                      borderRadius: '8px',
                      background: 'var(--surface-hover)',
                      border: '1px solid var(--border-color)',
                    }}>
                      <code style={{ fontSize: '13px', fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>llm-tracker bootstrap</code>
                      <CopyButton
                        text="llm-tracker bootstrap"
                        style={{ fontSize: '11px', padding: '4px 10px', whiteSpace: 'nowrap' }}
                        idleLabel={`📋 ${t('Copy')}`}
                        copiedLabel={`✓ ${t('Copied!')}`}
                      />
                    </div>
                  </div>

                  {/* Step 2: Run a test command */}
                  <div style={{ width: '100%', maxWidth: '680px', textAlign: 'left' }}>
                    <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '12px', textTransform: 'uppercase' }}>
                      {t('Step 2: Run a test command')}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {[
                        { cmd: 'llm-tracker claude', source: 'Claude Code' },
                        { cmd: 'llm-tracker codex exec "hello"', source: 'Codex' },
                        { cmd: 'llm-tracker gemini -p "hello"', source: 'Gemini CLI' },
                      ].map(({ cmd, source }) => (
                        <div key={cmd} style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '10px 16px',
                          borderRadius: '8px',
                          background: 'var(--surface-hover)',
                          border: '1px solid var(--border-color)',
                        }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', minWidth: '80px' }}>{source}</span>
                            <code style={{ fontSize: '13px', fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{cmd}</code>
                          </div>
                          <CopyButton
                            text={cmd}
                            style={{ fontSize: '11px', padding: '4px 10px', whiteSpace: 'nowrap' }}
                            idleLabel={`📋 ${t('Copy')}`}
                            copiedLabel={`✓ ${t('Copied!')}`}
                            onCopied={() => armOnboardingVerification({ source, command: cmd })}
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Step 3: Wait for event */}
                  <div style={{ width: '100%', maxWidth: '680px', textAlign: 'left' }}>
                    <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '12px', textTransform: 'uppercase' }}>
                      {t('Step 3: Wait for event')}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {verificationResult ? (
                        <>
                          <div style={{
                            padding: '8px 12px',
                            borderRadius: '6px',
                            background: 'var(--icon-green-bg)',
                            color: 'var(--color-green)',
                            fontWeight: 600,
                            fontSize: '13px',
                          }}>
                            {t('Tracking works. Your first request is recorded.')}
                          </div>
                          <div style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                            <div><span style={{ color: 'var(--text-muted)' }}>{t('Source:')}</span> {verificationResult.client_source || '—'}</div>
                            <div><span style={{ color: 'var(--text-muted)' }}>{t('Model:')}</span> {verificationResult.model || '—'}</div>
                            <div><span style={{ color: 'var(--text-muted)' }}>{t('Tokens:')}</span> {formatNumber(verificationResult.prompt_tokens)} {t('In:')} / {formatNumber(verificationResult.completion_tokens)} {t('Out:')}</div>
                            <div><span style={{ color: 'var(--text-muted)' }}>{t('Cost:')}</span> {formatCost(value(verificationResult.total_cost_usd))}</div>
                            <div><span style={{ color: 'var(--text-muted)' }}>{t('Latency:')}</span> {formatLatency(verificationResult.latency_ms)}</div>
                          </div>
                          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                            <button className="btn-primary" onClick={() => setView('logs')} style={{ fontSize: '12px', alignSelf: 'flex-start' }}>
                              {t('View request logs')}
                            </button>
                            <button className="btn-ghost" onClick={() => { setVerifyPhase('idle'); setVerificationResult(null); }} style={{ fontSize: '12px', alignSelf: 'flex-start' }}>
                              {t('Reset')}
                            </button>
                          </div>
                        </>
                      ) : (
                        <>
                          <div
                            aria-live="polite"
                            title={copiedOnboardingCommand?.command}
                            style={{
                              fontSize: '12px',
                              color: verifyPhase === 'timeout'
                                ? 'var(--color-red)'
                                : copiedOnboardingCommand && verifyPhase === 'idle'
                                  ? 'var(--color-green)'
                                  : 'var(--text-muted)',
                              padding: copiedOnboardingCommand && verifyPhase === 'idle' ? '8px 10px' : undefined,
                              borderRadius: copiedOnboardingCommand && verifyPhase === 'idle' ? '6px' : undefined,
                              background: copiedOnboardingCommand && verifyPhase === 'idle' ? 'var(--icon-green-bg)' : undefined,
                            }}
                          >
                            {verifyPhase === 'polling'
                              ? t('Waiting for your first event...')
                              : verifyPhase === 'timeout'
                                ? t(verifyTimeoutGuidance)
                                : copiedOnboardingCommand
                                  ? <><span style={{ fontWeight: 700 }}>{copiedOnboardingCommand.source}</span>: {t('Agent command copied. Run it in your terminal — checking automatically.')}</>
                                  : t('This page is checking automatically. Run a command above to generate your first event.')}
                          </div>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Setup health + Detected agents */}
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                    gap: '16px',
                    width: '100%',
                    maxWidth: '680px',
                  }}>
                    {/* Setup health */}
                    <div className="panel" style={{ textAlign: 'left' }}>
                      <div className="panel-tabs">
                        <div className="tab active"><span>🏥</span> {t('Setup health')}</div>
                      </div>
                      <div className="panel-body" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        <div style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                          gap: '8px',
                        }}>
                          <div style={{
                            padding: '10px 12px',
                            borderRadius: '8px',
                            background: 'var(--bg-secondary)',
                          }}>
                            <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 700, marginBottom: '4px' }}>{t('API server')}</div>
                            <div style={{ fontSize: '13px', color: error ? 'var(--color-red)' : 'var(--color-green)', fontWeight: 700 }}>
                              {error ? t('Broken') : t('Reachable')}
                            </div>
                          </div>
                          <div style={{
                            padding: '10px 12px',
                            borderRadius: '8px',
                            background: 'var(--bg-secondary)',
                          }}>
                            <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 700, marginBottom: '4px' }}>{t('OTLP configured')}</div>
                            <div style={{ fontSize: '13px', color: setupSummaryColor, fontWeight: 700 }}>
                              {setupSummaryText}
                            </div>
                          </div>
                        </div>
                        {setupDiagnostics && setupConfiguredAgents === 0 && (
                          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                            {t('No local OTLP config found yet. Run bootstrap, then run a test command above. This page checks automatically.')}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Detected agents */}
                    <div className="panel" style={{ textAlign: 'left' }}>
                      <div className="panel-tabs">
                        <div className="tab active"><span>🤖</span> {t('Detected Agents')}</div>
                      </div>
                      <div className="panel-body" style={{ padding: '16px' }}>
                        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '12px' }}>
                          {t('Detected from your local config and available commands.')}
                        </div>
                        {localAgents ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                            {Object.entries(localAgents).map(([name, info]) => (
                              <div key={name} style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                gap: '12px',
                                padding: '10px 12px',
                                borderRadius: '8px',
                                background: 'var(--bg-secondary)',
                              }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                                  <span style={{
                                    width: '8px', height: '8px', borderRadius: '50%',
                                    background: info.found ? 'var(--color-green)' : 'var(--text-muted)',
                                    flexShrink: 0,
                                  }} />
                                  <div style={{ minWidth: 0 }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                      <span style={{ fontWeight: 700, fontSize: '13px' }}>{getAgentDisplayName(name)}</span>
                                      <span style={{ fontSize: '11px', color: info.found ? 'var(--color-green)' : 'var(--text-muted)', fontWeight: 700 }}>
                                        {info.found ? t('Ready') : t('Not found')}
                                      </span>
                                    </div>
                                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '3px', wordBreak: 'break-all' }}>
                                      {t('Detected:')} {info.path || t('Unknown')}
                                    </div>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : sources.length > 0 ? (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                            {sources.map(src => (
                              <span key={src} style={{
                                padding: '4px 12px',
                                borderRadius: '6px',
                                background: 'var(--icon-green-bg)',
                                color: 'var(--color-green)',
                                fontWeight: 600,
                                fontSize: '13px',
                              }}>{src}</span>
                            ))}
                          </div>
                        ) : (
                          <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                            {t('No local Agent')}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
              <div className={`dashboard-refresh-surface ${dashboardRefreshing ? 'is-refreshing' : ''}`}>
              <div className="widgets-grid">
                {dashboardInitialLoading ? (
                  Array.from({ length: 5 }, (_, i) => (
                    <div key={i} className="widget">
                      <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center', gap: '10px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <div className="skeleton" style={{ width: 40, height: 40, borderRadius: 12 }} />
                            <div>
                              <div className="skeleton skeleton-text" style={{ width: 80 }} />
                              <div className="skeleton skeleton-value" />
                            </div>
                          </div>
                          <div className="skeleton" style={{ width: 100, height: 32, borderRadius: 6 }} />
                        </div>
                        <div className="skeleton skeleton-text-sm" style={{ width: '60%' }} />
                        <div className="skeleton skeleton-text-sm" style={{ width: '40%' }} />
                      </div>
                    </div>
                  ))
                ) : (
                  <>
                <div className="widget">
                  <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div className="icon-box icon-yellow">#</div>
                        <div>
                          <div className="stat-label">{t('Token Usage')}</div>
                          <div className="stat-value">{formatCompact(animatedTotalTokens)}</div>
                        </div>
                      </div>
                      <div style={{ width: '100px' }}>
                        <Sparkline data={dailyUsage.map(d => value(d.prompt_tokens) > 0 ? (value(d.cached_tokens) / value(d.prompt_tokens)) * 100 : 0)} color="var(--color-green)" />
                      </div>
                    </div>
                    <div className="stat-label" style={{ marginBottom: 0 }}>
                      {t('In:')} {formatCompact(totals.promptTokens)} / {t('Out:')} {formatCompact(totals.completionTokens)}
                    </div>
                    <div className="stat-label" style={{ fontSize: '11px', marginBottom: 0 }}>
                      {t('Cached:')} {formatCompact(totals.cachedTokens)}
                      <span style={{ marginLeft: '6px', color: 'var(--color-green)', fontWeight: 600 }}>
                        ({totals.totalTokens > 0 ? ((value(totals.cachedTokens) / totals.totalTokens) * 100).toFixed(1) : 0}% {t('Hit)')}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="widget">
                  <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div className="icon-box icon-green">↑</div>
                        <div>
                          <div className="stat-label">{t('Requests')}</div>
                          <div className="stat-value">{formatNumber(animatedRequests)}</div>
                        </div>
                      </div>
                      <div style={{ width: '100px' }}>
                        <Sparkline data={dailyUsage.map(d => d.requests)} color="var(--color-pink)" />
                      </div>
                    </div>
                    <div className="stat-label" style={{ marginTop: '-2px' }}>
                      {t('Avg:')} <span style={{ color: 'var(--color-purple)', fontWeight: 600 }}>{formatCompact(totals.avgTokensPerRequest)} {t('tokens/req')}</span>
                    </div>
                  </div>
                </div>

                <div className="widget">
                  <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div className="icon-box icon-green">$</div>
                        <div>
                          <div className="stat-label">{t('Estimated Cost')}</div>
                          <div className="stat-value">{formatCost(animatedCost, 2)}</div>
                        </div>
                      </div>
                      <div style={{ width: '100px' }}>
                        <Sparkline data={dailyUsage.map(d => d.requests > 0 ? value(d.total_cost_usd) / d.requests : 0)} color="var(--color-blue)" />
                      </div>
                    </div>
                    <div className="stat-label" style={{ marginTop: '-2px' }}>
                      {t('Avg:')} <span style={{ color: 'var(--color-blue)', fontWeight: 600 }}>{formatCost(totals.avgEffectivePrice, 3)} {t('/ req')}</span>
                    </div>
                    <div className="stat-label" style={{ fontSize: '11px', marginBottom: 0 }}>
                      {t('Avg $/M tokens:')} <span style={{ color: 'var(--color-green)', fontWeight: 600 }}>{formatRate(totals.avgEffectivePricePerMillion)}</span>
                    </div>
                  </div>
                </div>

                <div className="widget">
                  <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div className="icon-box icon-blue">⚡</div>
                        <div>
                          <div className="stat-label">{t('Performance')}</div>
                          <div className="stat-value">{animatedRpm.toFixed(3)} <span style={{ fontSize: '12px', fontWeight: 500 }}>{t('RPM')}</span></div>
                        </div>
                      </div>
                      <div style={{ width: '100px' }}>
                        <Sparkline data={dailyUsage.map(d => value(d.total_tokens))} color="var(--color-purple)" />
                      </div>
                    </div>
                    <div className="stat-label" style={{ marginTop: '-2px' }}>
                      {t('Avg Throughput:')} <span style={{ color: 'var(--color-purple)', fontWeight: 600 }}>{formatCompact(totals.tpm)} {t('TPM')}</span>
                    </div>
                  </div>
                </div>

                <div className="widget">
                  <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div className="icon-box icon-pink">~</div>
                        <div>
                          <div className="stat-label">{t('Average Response')}</div>
                          <div className="stat-value">{formatLatency(animatedLatency)}</div>
                        </div>
                      </div>
                      <div style={{ width: '100px' }}>
                        <Sparkline data={dailyUsage.map(d => value(d.avg_latency_ms))} color="var(--color-pink)" />
                      </div>
                    </div>
                    <div className="stat-label" style={{ marginTop: '-2px' }}>
                      {t('Success Rate:')} <span style={{ color: 'var(--color-green)', fontWeight: 600 }}>{totals.successRate.toFixed(1)}%</span>
                    </div>
                  </div>
                </div>
                  </>
                )}
              </div>

              <div style={{ display: 'flex', gap: '24px', height: '400px' }}>
                <div style={{ flex: '1 1 0', minWidth: 0 }}>
                  <TrendChart
                    data={dailyUsage}
                    title={`${dateRange === '24h' ? t('Hourly Usage Trend') : t('Daily Usage Trend')}`}
                    granularity={dateRange === '24h' ? 'hour' : 'day'}
                    periodCount={dateRange === '24h' ? 24 : dateRange === '7d' ? 7 : dateRange === '30d' ? 30 : 365}
                    showDots={dateRange !== 'all'}
                  />
                </div>
                <div style={{ flex: '1 1 0', minWidth: 0, display: 'flex', gap: '24px' }}>
                  <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                    <CacheHitRateChart
                      data={dailyUsage}
                      title={t('Cache Hit Rate')}
                    />
                  </div>
                  <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <DailyHeatmap mode="activity" data={heatmapData} />
                    <DailyHeatmap mode="success-rate" data={heatmapData} />
                  </div>
                </div>
              </div>

              <TopUsageChart summary={summary} theme={theme} />

              <div className="content-grid">

              </div>
              </div>
              )}
            </>
          )}

          {view === 'logs' && (
            <div className="logs-page">
              <div className="filter-bar">
                <div className="filter-group">
                  <div className="filter-label">{t('Model')}</div>
                  <ModelSelector
                    activeFilter={activeFilter}
                    summary={summary}
                    providerColors={providerColors}
                    onChange={(f) => { setActiveFilter(f); resetPage(); }}
                  />
                  </div>

                <div className="filter-group">
                  <div className="filter-label">{t('Source')}</div>
                  <select
                    className="input-plain"
                    value={activeSource || ''}
                    onChange={(e) => { setActiveSource(e.target.value || null); resetPage(); }}
                  >
                    <option value="">{t('All Sources')}</option>
                    {sources.map(source => (
                      <option key={source} value={source}>{source}</option>
                    ))}
                  </select>
                </div>

                <div className="filter-group">
                  <div className="filter-label">{t('Date Range')}</div>
                  <select
                    className="input-plain"
                    value={dateRange}
                    onChange={(e) => setDateRange(e.target.value as DateRangeOption)}
                  >
                    <option value="24h">{t('Last 24 Hours')}</option>
                    <option value="7d">{t('Last 7 Days')}</option>
                    <option value="30d">{t('Last 30 Days')}</option>
                    <option value="all">{t('All Time')}</option>
                    <option value="custom">{t('Custom Range')}</option>
                  </select>
                </div>

                {dateRange === 'custom' && (
                  <>
                    <div className="filter-group">
                      <div className="filter-label">{t('Since')}</div>
                      <input
                        type="datetime-local"
                        className="input-plain"
                        value={customSince.split('.')[0]}
                        onChange={(e) => { setCustomSince(new Date(e.target.value).toISOString()); resetPage(); }}
                        />                    </div>
                    <div className="filter-group">
                      <div className="filter-label">{t('Until')}</div>
                      <input
                        type="datetime-local"
                        className="input-plain"
                        value={customUntil.split('.')[0]}
                        onChange={(e) => { setCustomUntil(new Date(e.target.value).toISOString()); resetPage(); }}
                        />                    </div>
                  </>
                )}

                <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px', alignItems: 'center', alignSelf: 'flex-end' }}>
                   <button
                    className="btn-ghost btn-refresh"
                    onClick={requestUsageRefresh}
                    aria-label={t('Refresh')}
                    title={t('Refresh')}
                   >
                     <span className="refresh-icon">↻</span>
                   </button>
                   <button
                    style={{ padding: '8px 16px', background: 'var(--color-blue)', color: 'white', borderRadius: '8px', fontSize: '12px', fontWeight: 700 }}
                    onClick={() => {
                      setDateRange('24h')
                      setPage(1)
                    }}
                   >
                     {t('Last 24h')}
                   </button>
                </div>
              </div>

              <div className="panel">
                <div className="panel-body" style={{ padding: 0 }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th style={{ width: '120px' }}>{t('Time')}</th>
                        <th style={{ width: modelColWidth, padding: '12px 8px', position: 'relative' }}>
                          {t('Model')}
                          <div
                            onMouseDown={handleResizeStart}
                            style={{
                              position: 'absolute',
                              right: 0,
                              top: 0,
                              bottom: 0,
                              width: '3px',
                              cursor: 'col-resize',
                              userSelect: 'none',
                              backgroundColor: 'rgba(128,128,128,0.2)',
                            }}
                            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(128,128,128,0.5)'}
                            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'rgba(128,128,128,0.2)'}
                          />
                        </th>
                        <th style={{ width: '120px', padding: '12px 8px' }}>{t('Provider')}</th>
                        <th style={{ width: '110px', padding: '12px 8px' }}>{t('Source')}</th>
                        <th style={{ minWidth: '140px' }}>{t('Input (Prompt)')}</th>
                        <th style={{ minWidth: '120px' }}>{t('Output')}</th>
                        <th style={{ minWidth: '100px' }}>{t('Cost')}</th>
                        <th style={{ padding: '12px 8px' }}>
                          <div className="has-tooltip">
                            TTFT / Latency
                            <div className="tooltip-text">
                              <b>Claude Code:</b> {t('Claude Code: No TTFT')}<br/>
                              <b>Gemini CLI:</b> {t('Gemini CLI: Time to first chunk')}<br/>
                              <b>Codex:</b> {t('Codex: Actual TTFT')}<br/>
                              <b>Proxy:</b> {t('Proxy: Time to first chunk')}
                            </div>
                          </div>
                        </th>
                        <th style={{ width: '80px' }}>{t('Status')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {logsLoading ? (
                        Array.from({ length: 5 }, (_, i) => (
                          <tr key={`skeleton-${i}`}>
                            <td><div className="skeleton" style={{ width: 90, height: 14 }} /></td>
                            <td><div className="skeleton" style={{ width: 120, height: 24, borderRadius: 6 }} /></td>
                            <td><div className="skeleton" style={{ width: 70, height: 20, borderRadius: 4 }} /></td>
                            <td><div className="skeleton" style={{ width: 60, height: 20, borderRadius: 4 }} /></td>
                            <td><div className="skeleton" style={{ width: 80, height: 14 }} /></td>
                            <td><div className="skeleton" style={{ width: 60, height: 14 }} /></td>
                            <td><div className="skeleton" style={{ width: 50, height: 14 }} /></td>
                            <td><div className="skeleton" style={{ width: 100, height: 20, borderRadius: 999 }} /></td>
                            <td><div className="skeleton" style={{ width: 40, height: 20, borderRadius: 6 }} /></td>
                          </tr>
                        ))
                      ) : usageRows.map(row => (
                        <>
                        <tr
                          key={row.id}
                          className={`expandable-row${expandedRow === row.id ? ' expanded' : ''}`}
                          onClick={() => setExpandedRow(expandedRow === row.id ? null : row.id)}
                        >
                          <td style={{ color: 'var(--text-secondary)' }}>{formatTime(row.ts)}</td>
                          <td style={{ padding: '8px' }}>
                            <div style={{
                              padding: '4px 6px',
                              borderRadius: '6px',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                              fontSize: '11px',
                              backgroundColor: getModelBadgeBackgroundColor(row.model),
                              color: getModelTextColor(row.model),
                              maxWidth: modelColWidth - 10,
                              fontWeight: 600,
                              cursor: 'pointer'
                            }} title={row.model}>
                              {getModelIcon(row.model)}
                              <span style={{
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap'
                              }}>
                                {row.model}
                              </span>
                            </div>
                          </td>
                          <td style={{ padding: '8px' }}>
                            <div style={{
                              padding: '2px 8px',
                              borderRadius: '4px',
                              display: 'inline-flex',
                              fontSize: '10px',
                              backgroundColor: getProviderColor(row.provider, providerColors) + '22',
                              color: getProviderColor(row.provider, providerColors),
                              width: 'fit-content',
                              border: `1px solid ${getProviderColor(row.provider, providerColors)}44`,
                              fontWeight: 600
                            }}>
                              {row.provider}
                            </div>
                          </td>
                          <td style={{ padding: '8px' }}>
                            <div style={{
                              padding: '2px 8px',
                              borderRadius: '4px',
                              display: 'inline-flex',
                              fontSize: '10px',
                              backgroundColor: 'var(--tab-toggle-bg)',
                              color: 'var(--text-secondary)',
                              width: 'fit-content',
                              border: '1px solid var(--border-color)',
                              fontWeight: 600
                            }}>
                              {row.client_source || '—'}
                            </div>
                          </td>
                          <td style={{ verticalAlign: 'top' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                              <div style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>
                                {formatNumber(row.prompt_tokens)}
                                <span style={{ fontSize: '10px', fontWeight: 400, marginLeft: '4px', color: 'var(--text-secondary)' }}>{t('tokens')}</span>
                                {value(row.prompt_length) > 0 && (
                                  <span style={{ fontSize: '10px', fontWeight: 400, marginLeft: '6px', color: 'var(--text-muted)' }}>
                                    {t('(Prompt:')} {formatNumber(row.prompt_length)}{t(' chars)')}
                                  </span>
                                )}
                              </div>
                              {value(row.cached_tokens) > 0 && (
                                <div style={{ fontSize: '9px', color: 'var(--color-green)', fontWeight: 700 }}>
                                  {t('Cache read')} {formatNumber(row.cached_tokens)} ({Math.round((value(row.cached_tokens) / (value(row.prompt_tokens) || 1)) * 100)}%)
                                </div>
                              )}
                            </div>
                            {value(row.cached_tokens) > 0 && (
                              <div
                                title={`Cache read: ${formatNumber(row.cached_tokens)} tokens`}
                                style={{
                                  width: '100%',
                                  height: '3px',
                                  background: 'var(--progress-bg)',
                                  borderRadius: '2px',
                                  marginTop: '4px',
                                  overflow: 'hidden',
                                  border: '1px solid var(--border-color)'
                                }}
                              >
                                <div style={{
                                  width: `${(value(row.cached_tokens) / (value(row.prompt_tokens) || 1)) * 100}%`,
                                  height: '100%',
                                  background: 'var(--color-green)'
                                }} />
                              </div>
                            )}
                          </td>
                          <td style={{ fontWeight: 600, color: 'var(--color-blue)', verticalAlign: 'top' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                              <div>{formatNumber(row.completion_tokens)}</div>
                              {value(row.reasoning_tokens) > 0 && (
                                <div style={{ fontSize: '9px', color: 'var(--text-secondary)', fontWeight: 700 }}>
                                  {t('Reasoning')} {formatNumber(row.reasoning_tokens)} ({Math.round((value(row.reasoning_tokens) / (value(row.completion_tokens) || 1)) * 100)}%)
                                </div>
                              )}
                            </div>
                            {value(row.reasoning_tokens) > 0 && (
                              <div
                                style={{
                                  width: '100%',
                                  height: '3px',
                                  background: 'var(--progress-bg)',
                                  borderRadius: '2px',
                                  marginTop: '4px',
                                  overflow: 'hidden',
                                  border: '1px solid var(--border-color)',
                                  display: 'flex'
                                }}
                              >
                                {value(row.reasoning_tokens) > 0 && (
                                  <div
                                    title={`Reasoning: ${formatNumber(row.reasoning_tokens)} tokens`}
                                    style={{
                                      width: `${(value(row.reasoning_tokens) / (value(row.completion_tokens) || 1)) * 100}%`,
                                      height: '100%',
                                      background: '#64748b'
                                    }}
                                  />
                                )}
                              </div>
                            )}
                          </td>
                          <td style={{ verticalAlign: 'top' }}>
                            {(() => {
                              const total = value(row.total_cost_usd);
                              if (total === 0) return <div style={{ color: 'var(--color-green)', fontWeight: 500 }}>$0.00</div>;

                              const prompt = value(row.prompt_tokens);
                              const cached = value(row.cached_tokens);
                              const inputCost = value(row.input_cost_usd);
                              const outputCost = value(row.output_cost_usd);

                              const cacheRatio = prompt > 0 ? (cached / prompt) : 0;
                              const cacheCost = inputCost * cacheRatio;
                              const actualInputCost = inputCost - cacheCost;

                              const uncachedTokens = Math.max(0, prompt - cached);
                              const completionTokens = value(row.completion_tokens);

                              const modelConfig = configParsed?.providers?.[row.provider]?.models?.[row.model]?.cost || configParsed?.models?.[row.model]?.cost;

                              return (
                                <div className="has-tooltip" style={{ borderBottom: 'none' }}>
                                  <div style={{ color: 'var(--color-green)', fontWeight: 500, cursor: 'pointer' }}>
                                    {formatCost(total)}
                                  </div>
                                  <div className="tooltip-text" style={{ width: '200px', marginLeft: '-100px' }}>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                                        <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>{t('Input:')}</span>
                                        <div style={{ textAlign: 'right' }}>
                                          <div>{formatCost(actualInputCost)}</div>
                                          {modelConfig?.input !== undefined && (
                                            <div style={{ fontSize: '9px', color: 'rgba(255, 255, 255, 0.4)' }}>{formatNumber(uncachedTokens)} tokens x {formatRate(modelConfig.input)}</div>
                                          )}
                                        </div>
                                      </div>
                                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                                        <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>{t('Output:')}</span>
                                        <div style={{ textAlign: 'right' }}>
                                          <div>{formatCost(outputCost)}</div>
                                          {modelConfig?.output !== undefined && (
                                            <div style={{ fontSize: '9px', color: 'rgba(255, 255, 255, 0.4)' }}>{formatNumber(completionTokens)} tokens x {formatRate(modelConfig.output)}</div>
                                          )}
                                        </div>
                                      </div>
                                      {cacheCost > 0 && (
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                                          <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>{t('Cache:')}</span>
                                          <div style={{ textAlign: 'right' }}>
                                            <div style={{ color: 'var(--color-green)' }}>{formatCost(cacheCost)}</div>
                                            {modelConfig?.cacheRead !== undefined && (
                                              <div style={{ fontSize: '9px', color: 'rgba(255, 255, 255, 0.4)' }}>{formatNumber(cached)} tokens x {formatRate(modelConfig.cacheRead)}</div>
                                            )}
                                          </div>
                                        </div>
                                      )}
                                      <div style={{ marginTop: '4px', paddingTop: '4px', borderTop: '1px solid #334155', display: 'flex', justifyContent: 'space-between', color: 'white' }}>
                                        <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>{t('Total:')}</span>
                                        <span>{formatCost(total)}</span>
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              );
                            })()}
                          </td>
                          <td style={{ padding: '8px' }}>
                            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                              {value(row.ttft_ms) > 0 && (
                                <div style={{
                                  backgroundColor: 'var(--badge-success-bg)',
                                  color: 'var(--badge-success-text)',
                                  padding: '2px 12px',
                                  borderRadius: '999px',
                                  fontSize: '12px',
                                  whiteSpace: 'nowrap'
                                }} title={t('Time To First Token')}>
                                  {formatLatency(row.ttft_ms)}
                                </div>
                              )}
                              <div style={{
                                backgroundColor: 'var(--badge-error-bg)',
                                color: 'var(--badge-error-text)',
                                padding: '2px 12px',
                                borderRadius: '999px',
                                fontSize: '12px',
                                whiteSpace: 'nowrap'
                              }} title={t('Total Latency')}>
                                {formatLatency(row.latency_ms)}
                              </div>
                            </div>
                          </td>
                          <td>
                            <span className={`badge ${value(row.status) >= 400 ? 'badge-error' : 'badge-success'}`}>
                              {row.status ?? '200'}
                            </span>
                          </td>
                        </tr>
                        {expandedRow === row.id && (
                          <tr className="expanded-row">
                            <td colSpan={9}>
                              <div className="expanded-detail">
                                <div className="detail-group">
                                  <span className="detail-label">{t('Request ID')}</span>
                                  <span className="detail-value">#{row.id}</span>
                                </div>
                                <div className="detail-group">
                                  <span className="detail-label">{t('Full Timestamp')}</span>
                                  <span className="detail-value">{row.ts}</span>
                                </div>
                                <div className="detail-group">
                                  <span className="detail-label">{t('Endpoint')}</span>
                                  <span className="detail-value">{row.endpoint}</span>
                                </div>
                                <div className="detail-group">
                                  <span className="detail-label">{t('Total Tokens')}</span>
                                  <span className="detail-value">{formatNumber(row.total_tokens ?? (value(row.prompt_tokens) + value(row.completion_tokens)))}</span>
                                </div>
                                {value(row.tool_tokens) > 0 && (
                                  <div className="detail-group">
                                    <span className="detail-label">{t('Tool Tokens')}</span>
                                    <span className="detail-value">{formatNumber(row.tool_tokens)}</span>
                                  </div>
                                )}
                                {value(row.prompt_length) > 0 && (
                                  <div className="detail-group">
                                    <span className="detail-label">{t('Prompt Length')}</span>
                                    <span className="detail-value">{formatNumber(row.prompt_length)} {t('chars')}</span>
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                        </>
                      ))}
                      {usageRows.length === 0 && !logsLoading && (
                        <tr>
                          <td colSpan={7} style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                            {t('No requests found for the selected filters.')}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                <div style={{
                  padding: '16px 24px',
                  borderTop: '1px solid var(--border-color)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  background: 'var(--surface-hover)'
                }}>
                  <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                    {t('Showing')} <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{Math.min(totalLogs, (page - 1) * limit + 1)}-{Math.min(totalLogs, page * limit)}</span> {t('of')} <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{totalLogs}</span> {t('logs')}
                  </div>

                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <button
                      disabled={page === 1}
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                      className="pagination-btn"
                      style={{
                        cursor: page === 1 ? 'not-allowed' : 'pointer',
                        opacity: page === 1 ? 0.5 : 1
                      }}
                    >
                      ◀ {t('Prev')}
                    </button>

                    <div style={{ display: 'flex', gap: '4px' }}>
                      {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                        let pageNum = i + 1;
                        if (totalPages > 5 && page > 3) {
                          pageNum = page - 3 + i + 1;
                          if (pageNum > totalPages) pageNum = totalPages - (4 - i);
                        }
                        return (
                          <button
                            key={pageNum}
                            onClick={() => setPage(pageNum)}
                            style={{
                              width: '32px',
                              height: '32px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              borderRadius: '6px',
                              fontSize: '12px',
                              fontWeight: 700,
                              background: page === pageNum ? 'var(--color-blue)' : 'var(--input-bg)',
                              color: page === pageNum ? '#fff' : 'var(--text-primary)',
                              border: '1px solid var(--border-color)',
                              cursor: 'pointer'
                            }}
                          >
                            {pageNum}
                          </button>
                        );
                      })}
                    </div>

                    <button
                      disabled={page === totalPages || totalPages === 0}
                      onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                      className="pagination-btn"
                      style={{
                        cursor: (page === totalPages || totalPages === 0) ? 'not-allowed' : 'pointer',
                        opacity: (page === totalPages || totalPages === 0) ? 0.5 : 1
                      }}
                    >
                      {t('Next')} ▶
                    </button>

                    <div style={{ marginLeft: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{t('Jump:')}</span>
                      <input
                        type="text"
                        value={jumpPage}
                        onChange={(e) => {
                          const val = e.target.value;
                          if (val === '' || /^\d+$/.test(val)) {
                            setJumpPage(val);
                          }
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            const p = parseInt(jumpPage);
                            if (!isNaN(p) && p >= 1 && p <= totalPages) {
                              setPage(p);
                              setJumpPage('');
                            }
                          }
                        }}
                        placeholder={String(page)}
                        style={{
                          width: '40px',
                          height: '28px',
                          padding: '0 4px',
                          borderRadius: '4px',
                          border: '1px solid var(--border-color)',
                          fontSize: '12px',
                          textAlign: 'center',
                          outline: 'none'
                        }}
                      />
                    </div>

                    <div style={{ marginLeft: '12px', height: '16px', width: '1px', background: 'var(--border-color)' }} />

                    <select
                      value={limit}
                      onChange={(e) => { setLimit(Number(e.target.value)); resetPage(); }}                      style={{
                        border: 'none',
                        background: 'transparent',
                        fontWeight: 700,
                        fontSize: '13px',
                        color: 'var(--text-primary)',
                        outline: 'none',
                        cursor: 'pointer'
                      }}
                    >
                      <option value={10}>10 {t('/ page')}</option>
                      <option value={25}>25 {t('/ page')}</option>
                      <option value={50}>50 {t('/ page')}</option>
                      <option value={100}>100 {t('/ page')}</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          )}

          {view === 'settings' && (
            <div className="settings-page" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              {/* Settings detected local agents */}
              <div className="panel">
                <div className="panel-tabs">
                  <div className="tab active"><span>🧭</span> {t('Detected Agents')}</div>
                </div>
                <div className="panel-body" style={{ padding: '0' }}>
                  <div style={{ padding: '16px', borderBottom: '1px solid var(--border-color)', fontSize: '13px', color: 'var(--text-secondary)' }}>
                    {t('Detected from your local config and available commands.')}
                  </div>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{t('Agent')}</th>
                        <th>{t('Status')}</th>
                        <th>{t('Detected:')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {localAgents && Object.keys(localAgents).length > 0 ? Object.entries(localAgents).map(([name, info]) => (
                        <tr key={name}>
                          <td style={{ fontWeight: 700 }}>{getAgentDisplayName(name)}</td>
                          <td>
                            <span className={`badge ${info.found ? 'badge-success' : 'badge-error'}`}>
                              {info.found ? t('Ready') : t('Not found')}
                            </span>
                          </td>
                          <td style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: info.path ? 'var(--text-secondary)' : 'var(--text-muted)' }}>
                            {info.path || t('Unknown')}
                          </td>
                        </tr>
                      )) : (
                        <tr>
                          <td colSpan={3} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                            {localAgents ? t('No local Agent') : t('Unknown')}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="panel">
                <div className="panel-tabs">
                  <div className="tab active"><span>📡</span> {t('OTLP Tracking Setup')}</div>
                </div>
                <div className="panel-body" style={{ padding: '0' }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{t('Agent')}</th>
                        <th>{t('Status')}</th>
                        <th>{t('Expected endpoint')}</th>
                        <th>{t('Configured endpoint')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {setupDiagnostics ? Object.entries(setupDiagnostics.agents).map(([name, agent]) => (
                        <tr key={name}>
                          <td style={{ fontWeight: 700 }}>{getAgentDisplayName(name)}</td>
                          <td>
                            <span className={`badge ${agent.endpoint_matches ? 'badge-success' : 'badge-error'}`}>
                              {agent.status === 'ready' ? t('Ready') : agent.status === 'wrong_endpoint' ? t('Wrong endpoint') : t('Missing config')}
                            </span>
                          </td>
                          <td style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{agent.expected_endpoint}</td>
                          <td style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: agent.endpoint_matches ? 'var(--color-green)' : 'var(--color-red)' }}>
                            {agent.configured_endpoint ?? '—'}
                          </td>
                        </tr>
                      )) : (
                        <tr>
                          <td colSpan={4} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                            {t('Unknown')}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                  <div style={{ padding: '16px', borderTop: '1px solid var(--border-color)', fontSize: '13px', color: 'var(--text-secondary)' }}>
                    {t('OTLP configured')}: <strong>{setupSummaryText}</strong> · {t('Configured')}: <strong>{setupConfiguredAgents}/{setupLocalAgentTotal}</strong>
                  </div>
                </div>
              </div>

              <div className="panel">
                <div className="panel-tabs">
                  <div className="tab active"><span>🔌</span> {t('Active Providers')}</div>
                </div>
                <div className="panel-body" style={{ padding: '0' }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{t('Provider')}</th>
                        <th>{t('Base URL')}</th>
                        <th>{t('Models')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {configParsed?.providers ? Object.entries(configParsed.providers as Record<string, unknown>).map(([name, conf]) => {
                        const c = conf as { models?: unknown[] | Record<string, unknown>, base_url?: string };
                        const models = Array.isArray(c.models)
                          ? c.models
                          : (c.models ? Object.keys(c.models) : []);
                        const color = getProviderColor(name, providerColors);
                        return (
                          <tr key={name}>
                            <td style={{ padding: '8px' }}>
                              <div style={{
                                padding: '4px 10px',
                                borderRadius: '6px',
                                backgroundColor: color + '22',
                                color: color,
                                fontWeight: 500,
                                border: `1px solid ${color}44`,
                                display: 'inline-block',
                                fontSize: '12px'
                              }}>
                                {name}
                              </div>
                            </td>
                            <td style={{ fontSize: '12px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{c.base_url}</td>
                            <td>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                                {(models as string[]).map((m: string) => {
                                  const mConf = !Array.isArray(c.models) ? (c.models?.[m] as { cost?: unknown }) : undefined;
                                  const hasOverride = mConf?.cost !== undefined;
                                  return (
                                    <span key={m} style={{
                                      fontSize: '10px',
                                      padding: '2px 6px',
                                      background: hasOverride ? 'var(--icon-yellow-bg)' : 'var(--tab-toggle-bg)',
                                      borderRadius: '4px',
                                      color: hasOverride ? 'var(--color-yellow)' : 'var(--text-secondary)',
                                      border: hasOverride ? `1px solid var(--color-yellow)` : '1px solid var(--border-color)',
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      gap: '4px'
                                    }}>
                                      {m}
                                      {hasOverride && <span title={t('Cost Override')} style={{ fontSize: '10px' }}>💰</span>}
                                    </span>
                                  );
                                })}
                              </div>
                            </td>
                          </tr>
                        );
                      }) : (
                        <tr>
                          <td colSpan={3} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                            {t('No providers configured in config.yaml.')}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="panel">
                <div className="panel-tabs" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div className="tab active"><span>💎</span> {t('Model Pricing')}</div>
                  <div style={{ paddingRight: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-muted)', textTransform: 'uppercase' }}>{t('Scope:')}</span>
                    <select
                      value={selectedPricingProvider}
                      onChange={(e) => setSelectedPricingProvider(e.target.value)}
                      style={{
                        padding: '4px 12px',
                        borderRadius: '6px',
                        border: '1px solid var(--border-color)',
                        fontSize: '13px',
                        fontWeight: 600,
                        background: 'var(--surface-hover)',
                        outline: 'none'
                      }}
                    >
                      <option value="global">{t('Global Default')}</option>
                      {configParsed?.providers && Object.keys(configParsed.providers).map(p => (
                        <option key={p} value={p}>{t('Provider:')} {p}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="panel-body" style={{ padding: '0' }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th style={{ width: '220px' }}>{t('Model')}</th>
                        <th>{t('Input (per 1M)')}</th>
                        <th>{t('Output (per 1M)')}</th>
                        <th>{t('Cache Read (per 1M)')}</th>
                        <th>{t('Cache Write (per 1M)')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {configParsed?.models ? Object.keys(configParsed.models).map((name) => {
                        const globalCost = configParsed.models[name]?.cost || {};
                        const providerCost = selectedPricingProvider !== 'global'
                          ? (configParsed.providers?.[selectedPricingProvider]?.models?.[name]?.cost || {})
                          : null;

                        const isOverridden = providerCost !== null && Object.keys(providerCost).length > 0;
                        const activeCost = providerCost !== null ? providerCost : globalCost;

                        const inputProps = (field: string) => ({
                          type: "number",
                          step: "0.001",
                          value: activeCost[field] !== undefined ? activeCost[field] : "",
                          placeholder: selectedPricingProvider !== 'global' ? (globalCost[field] ?? "—") : "0.000",
                          onChange: (e: React.ChangeEvent<HTMLInputElement>) => handleCostChange(name, field, e.target.value),
                          style: {
                            width: '100%',
                            padding: '6px 8px',
                            borderRadius: '4px',
                            border: '1px solid transparent',
                            background: activeCost[field] === undefined && selectedPricingProvider !== 'global' ? 'transparent' : 'var(--input-bg)',
                            borderBottom: '1px solid var(--border-color)',
                            fontSize: '13px',
                            color: activeCost[field] === undefined && selectedPricingProvider !== 'global' ? 'var(--text-muted)' : 'var(--text-primary)',
                            outline: 'none',
                            textAlign: 'left' as const
                          }
                        });

                        return (
                          <tr key={name} style={{ background: isOverridden ? 'var(--icon-yellow-bg)' : 'transparent' }}>
                            <td style={{ fontWeight: 700 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                {getModelIcon(name)}
                                {name}
                                {isOverridden && <span title={t('Provider Override')} style={{ fontSize: '10px' }}>💰</span>}
                              </div>
                            </td>
                            <td><input {...inputProps('input')} /></td>
                            <td><input {...inputProps('output')} /></td>
                            <td><input {...inputProps('cacheRead')} /></td>
                            <td><input {...inputProps('cacheWrite')} /></td>
                          </tr>
                        );
                      }) : (
                        <tr>
                          <td colSpan={5} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                            {t('No global models configured in config.yaml.')}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="panel">
                <div className="panel-tabs">
                  <div className="tab active"><span>📝</span> {t('Configuration (YAML)')}</div>
                </div>
                <div className="panel-body">
                  <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }} dangerouslySetInnerHTML={{ __html: t('Directly edit your <code>config.yaml</code>. Providers and routing are defined here.') }} />

                  <div style={{ position: 'relative', background: '#1e293b', borderRadius: '8px', overflow: 'hidden', border: '1px solid #334155' }}>
                    <div style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '40px',
                      bottom: 0,
                      background: '#0f172a',
                      borderRight: '1px solid #334155',
                      display: 'flex',
                      flexDirection: 'column',
                      paddingTop: '16px',
                      alignItems: 'center',
                      color: '#475569',
                      fontSize: '11px',
                      fontFamily: 'var(--font-mono)',
                      userSelect: 'none'
                    }}>
                      {Array.from({ length: 20 }, (_, i) => <div key={i} style={{ height: '20.8px' }}>{i + 1}</div>)}
                    </div>
                    <textarea
                      value={configContent}
                      onChange={(e) => setConfigContent(e.target.value)}
                      style={{
                        width: '100%',
                        height: '420px',
                        padding: '16px 16px 16px 56px',
                        fontFamily: 'var(--font-mono)',
                        fontSize: '13px',
                        border: 'none',
                        outline: 'none',
                        lineHeight: '1.6',
                        background: 'transparent',
                        color: '#e2e8f0',
                        resize: 'vertical',
                        whiteSpace: 'pre',
                        overflowX: 'auto'
                      }}
                      spellCheck={false}
                    />
                  </div>

                  {error && view === 'settings' && (
                    <div style={{
                      marginTop: '16px',
                      padding: '12px',
                      background: 'var(--badge-error-bg)',
                      color: 'var(--badge-error-text)',
                      borderRadius: '8px',
                      fontSize: '13px',
                      fontWeight: 500
                    }}>
                      ⚠️ {error}
                    </div>
                  )}

                  <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end', gap: '12px', alignItems: 'center' }}>
                    {configStatus === 'saved' && (
                      <span style={{ color: 'var(--color-green)', fontSize: '13px', fontWeight: 600 }}>
                        ✓ {t('Configuration saved successfully')}
                      </span>
                    )}
                    <button
                      disabled={configStatus === 'saving'}
                      onClick={handleSaveConfig}
                      style={{
                        padding: '10px 24px',
                        background: 'var(--color-blue)',
                        color: 'white',
                        borderRadius: '8px',
                        fontSize: '14px',
                        fontWeight: 700,
                        opacity: configStatus === 'saving' ? 0.7 : 1,
                        cursor: configStatus === 'saving' ? 'not-allowed' : 'pointer',
                        boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                      }}
                    >
                      {configStatus === 'saving' ? t('Saving...') : t('Save Configuration')}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {view === 'test' && (
            <div className="test-page" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <div className="panel">
                <div className="panel-tabs">
                  <div className="tab active"><span>🧪</span> {t('Upstream Connectivity Test')}</div>
                </div>
                <div className="panel-content" style={{ padding: '24px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      <div className="filter-group">
                        <div className="filter-label">{t('Base URL')}</div>
                        <input
                          type="text"
                          className="input-plain"
                          placeholder="https://api.openai.com/v1"
                          value={testBaseUrl}
                          onChange={(e) => setTestBaseUrl(e.target.value)}
                          style={{ width: '100%' }}
                        />
                        <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '4px' }}>
                          {t('The upstream API root URL, e.g. https://api.openai.com/v1')}
                        </div>
                      </div>

                      <div className="filter-group">
                        <div className="filter-label">{t('API Key')}</div>
                        <input 
                          type="password" 
                          className="input-plain" 
                          placeholder="sk-..."
                          value={testApiKey}
                          onChange={(e) => setTestApiKey(e.target.value)}
                          style={{ width: '100%' }}
                        />
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                        <div className="filter-group">
                          <div className="filter-label">{t('Format')}</div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            {[
                              { id: 'openai', label: t('OpenAI'), sub: t('Chat Completion') },
                              { id: 'anthropic', label: t('Anthropic'), sub: t('Claude') },
                              { id: 'responses', label: t('Codex'), sub: t('Responses') },
                            ].map((f) => (
                              <button
                                key={f.id}
                                type="button"
                                className={`format-chip${testFormat === f.id ? ' format-chip-active' : ''}`}
                                onClick={() => setTestFormat(f.id)}
                              >
                                <span style={{ fontWeight: 700, fontSize: '12px' }}>{f.label}</span>
                                <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{f.sub}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                        <div className="filter-group">
                          <div className="filter-label">{t('Model')}</div>
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
                            {[
                              { id: 'gpt-5.5', label: 'GPT-5.5', sub: 'OpenAI' },
                              { id: 'gpt-5.4', label: 'GPT-5.4', sub: 'OpenAI' },
                              { id: 'claude-opus-4-7', label: 'Claude Opus 4.7', sub: 'Anthropic' },
                              { id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6', sub: 'Anthropic' },
                            ].map((m) => (
                              <button
                                key={m.id}
                                type="button"
                                className={`model-chip${testModel === m.id ? ' model-chip-active' : ''}`}
                                onClick={() => setTestModel(testModel === m.id ? '' : m.id)}
                              >
                                <span style={{ fontWeight: 700, fontSize: '12px' }}>{m.label}</span>
                                <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{m.sub}</span>
                              </button>
                            ))}
                          </div>
                          <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontSize: '11px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{t('Custom:')}</span>
                            <input
                              type="text"
                              className="input-plain"
                              placeholder="model-id"
                              value={!['gpt-5.5','gpt-5.4','claude-opus-4-7','claude-sonnet-4-6'].includes(testModel) ? testModel : ''}
                              onChange={(e) => setTestModel(e.target.value)}
                              style={{ flex: 1 }}
                            />
                          </div>
                        </div>
                        <div className="filter-group" style={{ marginTop: '12px', gridColumn: '1 / -1' }}>
                          <div className="filter-label">{t('Message')}</div>
                          <textarea
                            className="input-plain"
                            rows={2}
                            value={testMessage}
                            onChange={(e) => setTestMessage(e.target.value)}
                            style={{ width: '100%', resize: 'vertical', fontFamily: 'var(--font-mono)', fontSize: '12px' }}
                          />
                        </div>
                      </div>

                      <button
                        className="btn-primary"
                        onClick={handleRunTest}
                        disabled={isTesting || !testBaseUrl || !testApiKey}
                        style={{ marginTop: '8px' }}
                      >
                        {isTesting ? `⌛ ${t('Testing...')}` : `🚀 ${t('Run Connectivity Test')}`}
                      </button>

                      <div style={{ marginTop: '16px', padding: '16px', background: 'var(--surface-hover)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                          <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>{t('Manual curl equivalent')}</div>
                          <CopyButton
                            className="btn-copy"
                            text={manualCurlEquivalent}
                            idleLabel={`📋 ${t('Copy')}`}
                            copiedLabel={`✓ ${t('Copied')}`}
                            timeoutMs={800}
                          />
                        </div>
                        <pre style={{ margin: 0, fontSize: '11px', whiteSpace: 'pre-wrap', wordBreak: 'break-all', color: 'var(--text-secondary)' }}>
                          {manualCurlEquivalent}
                        </pre>
                      </div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      <div className="filter-label">{t('Test Result')}</div>
                      {!testResult ? (
                        <div style={{ 
                          flex: 1, 
                          display: 'flex', 
                          flexDirection: 'column',
                          alignItems: 'center', 
                          justifyContent: 'center', 
                          color: 'var(--text-muted)',
                          border: '2px dashed var(--border-color)',
                          borderRadius: '12px',
                          minHeight: '300px'
                        }}>
                          <span style={{ fontSize: '32px', marginBottom: '12px' }}>⚡</span>
                          <span>{t('Results will appear here after testing')}</span>
                        </div>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                            <div className="widget" style={{ padding: '16px', background: testResult.error || testResult.status_code >= 400 ? 'var(--icon-pink-bg)' : 'var(--icon-green-bg)' }}>
                              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{t('Status Code')}</div>
                              <div style={{ fontSize: '24px', fontWeight: 800, color: testResult.error || testResult.status_code >= 400 ? '#e11d48' : '#16a34a' }}>
                                {testResult.error ? t('Error') : testResult.status_code}
                              </div>
                            </div>
                            <div className="widget" style={{ padding: '16px' }}>
                              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{t('Latency')}</div>
                              <div style={{ fontSize: '24px', fontWeight: 800 }}>{testResult.latency_ms}ms</div>
                            </div>
                          </div>
                          
                          {typeof testResult.body === 'string' && testResult.body.trim().startsWith('<') ? (
                            <div className="widget" style={{ padding: '16px', background: 'var(--icon-yellow-bg)' }}>
                              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>{t('Response')}</div>
                              <div style={{ fontSize: '12px', color: '#b45309', fontWeight: 600, marginBottom: '8px' }}>
                                {t('Upstream returned HTML -- check that base_url points to an API endpoint')}
                              </div>
                              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: '200px', overflow: 'auto' }}>
                                {testResult.body.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 1000)}
                              </div>
                            </div>
                          ) : (
                            <div className="widget" style={{ padding: '16px' }}>
                              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '8px' }}>{t('Response Body')}</div>
                              <pre style={{
                                margin: 0,
                                fontSize: '12px',
                                fontFamily: 'var(--font-mono)',
                                lineHeight: '1.5',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-all',
                                color: 'var(--text-primary)',
                                maxHeight: '400px',
                                overflow: 'auto'
                              }}>
                                {typeof testResult.body === 'object' ? JSON.stringify(testResult.body, null, 2) : testResult.body || testResult.error}
                              </pre>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

export default App
