import { useEffect, useMemo, useState } from 'react'
import yaml from 'js-yaml'
import './App.css'
import { toggleTheme, getTheme } from './theme'
import { getModelBadgeBackgroundColor, getModelTextColor } from './model-badge'
import type { ActiveFilter, DailyUsage, DateRangeOption, ProviderUsage, SourceUsage, UsageRow, UsageSummary } from './types'
import { formatCompact, formatCost, formatLatency, formatNumber, formatRate, formatTime, FIXED_PROVIDER_COLORS, getProviderColor, getSinceDate, getTimezoneOffset, getModelIcon, PALETTE, value } from './utils'
import { Sparkline } from './Sparkline'
import { ModelSelector } from './ModelSelector'
import { TrendChart } from './charts/TrendChart'
import { CacheHitRateChart } from './charts/CacheHitRateChart'
import { ModelTokenChart } from './charts/ModelTokenChart'
import { ProviderTokenChart } from './charts/ProviderTokenChart'
import { SourceTokenChart } from './charts/SourceTokenChart'
import { DailyHeatmap } from './charts/DailyHeatmap'

function App() {
  const [view, setView] = useState<'dashboard' | 'logs' | 'settings'>('dashboard')
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [summary, setSummary] = useState<UsageSummary[]>([])
  const [usageRows, setUsageRows] = useState<UsageRow[]>([])
  const [dailyUsage, setDailyUsage] = useState<DailyUsage[]>([])
  const [totalLogs, setTotalLogs] = useState(0)
  const [limit, setLimit] = useState(10)
  const [page, setPage] = useState(1)
  const [jumpPage, setJumpPage] = useState('')

  const [activeFilter, setActiveFilter] = useState<ActiveFilter>(null)
  const [activeSource, setActiveSource] = useState<string | null>(null)
  const [sources, setSources] = useState<string[]>([])
  const [sourceUsage, setSourceUsage] = useState<SourceUsage[]>([])
  const [providerUsage, setProviderUsage] = useState<ProviderUsage[]>([])
  const [dateRange, setDateRange] = useState<DateRangeOption>('24h')
  const [customSince, setCustomSince] = useState('')
  const [customUntil, setCustomUntil] = useState('')

  const [configContent, setConfigContent] = useState('')
  const [configParsed, setConfigParsed] = useState<any>(null)
  const [selectedPricingProvider, setSelectedPricingProvider] = useState('global')
  const [configStatus, setConfigStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  const [error, setError] = useState<string | null>(null)
  const [theme, setTheme] = useState<'light' | 'dark'>(getTheme)

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
    void fetchInitialConfig()
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const controller = new AbortController()

    async function loadData() {
      if (view === 'settings') {
        try {
          const response = await fetch('/config', { signal: controller.signal })
          if (response.ok) {
            const data = await response.json()
            setConfigContent(data.content)
            setConfigParsed(data.parsed)
          }
        } catch (err) {
          console.error('Failed to load config:', err)
        }
        return
      }

      setError(null)

      try {
        const since = dateRange === 'custom' ? customSince : getSinceDate(dateRange)
        const until = dateRange === 'custom' ? customUntil : null

        const offset = (page - 1) * limit
        const usageUrl = new URL('/usage', window.location.origin)
        usageUrl.searchParams.set('limit', String(limit))
        usageUrl.searchParams.set('offset', String(offset))

        if (activeFilter) {
          usageUrl.searchParams.set('provider', activeFilter.provider)
          if (activeFilter.model) usageUrl.searchParams.set('model', activeFilter.model)
        }
        if (activeSource) usageUrl.searchParams.set('client_source', activeSource)
        if (since) usageUrl.searchParams.set('since', since)
        if (until) usageUrl.searchParams.set('until', until)

        const summaryUrl = new URL('/usage/summary', window.location.origin)
        if (activeFilter) {
          summaryUrl.searchParams.set('provider', activeFilter.provider)
          if (activeFilter.model) summaryUrl.searchParams.set('model', activeFilter.model)
        }
        if (since) summaryUrl.searchParams.set('since', since)
        if (until) summaryUrl.searchParams.set('until', until)
        if (activeSource) summaryUrl.searchParams.set('client_source', activeSource)

        const bySourceUrl = new URL('/usage/by-source', window.location.origin)
        if (activeFilter) {
          bySourceUrl.searchParams.set('provider', activeFilter.provider)
          if (activeFilter.model) bySourceUrl.searchParams.set('model', activeFilter.model)
        }
        if (since) bySourceUrl.searchParams.set('since', since)
        if (until) bySourceUrl.searchParams.set('until', until)
        if (activeSource) bySourceUrl.searchParams.set('client_source', activeSource)

        const byProviderUrl = new URL('/usage/by-provider', window.location.origin)
        if (activeFilter) {
          byProviderUrl.searchParams.set('provider', activeFilter.provider)
          if (activeFilter.model) byProviderUrl.searchParams.set('model', activeFilter.model)
        }
        if (since) byProviderUrl.searchParams.set('since', since)
        if (until) byProviderUrl.searchParams.set('until', until)
        if (activeSource) byProviderUrl.searchParams.set('client_source', activeSource)

        const countUrl = new URL('/usage/count', window.location.origin)
        if (activeFilter) {
          countUrl.searchParams.set('provider', activeFilter.provider)
          if (activeFilter.model) countUrl.searchParams.set('model', activeFilter.model)
        }
        if (activeSource) countUrl.searchParams.set('client_source', activeSource)
        if (since) countUrl.searchParams.set('since', since)
        if (until) countUrl.searchParams.set('until', until)

        const dailyUrl = new URL('/usage/daily', window.location.origin)
        if (activeFilter) {
          dailyUrl.searchParams.set('provider', activeFilter.provider)
          if (activeFilter.model) dailyUrl.searchParams.set('model', activeFilter.model)
        }
        if (activeSource) dailyUrl.searchParams.set('client_source', activeSource)
        if (since) dailyUrl.searchParams.set('since', since)
        if (until) dailyUrl.searchParams.set('until', until)
        dailyUrl.searchParams.set('tz_offset', getTimezoneOffset())
        if (dateRange === '5h' || dateRange === '24h') {
          dailyUrl.searchParams.set('granularity', 'hour')
        }

        const [summaryResponse, usageResponse, countResponse, dailyResponse, bySourceResponse, byProviderResponse] = await Promise.all([
          fetch(summaryUrl.toString(), { signal: controller.signal }),
          fetch(usageUrl.toString(), { signal: controller.signal }),
          fetch(countUrl.toString(), { signal: controller.signal }),
          fetch(dailyUrl.toString(), { signal: controller.signal }),
          fetch(bySourceUrl.toString(), { signal: controller.signal }),
          fetch(byProviderUrl.toString(), { signal: controller.signal }),
        ])

        if (!summaryResponse.ok || !usageResponse.ok || !countResponse.ok || !dailyResponse.ok || !bySourceResponse.ok || !byProviderResponse.ok) {
          throw new Error('Failed to fetch usage data')
        }

        const [summaryData, usageData, countData, dailyData, bySourceData, byProviderData] = (await Promise.all([
          summaryResponse.json(),
          usageResponse.json(),
          countResponse.json(),
          dailyResponse.json(),
          bySourceResponse.json(),
          byProviderResponse.json(),
        ])) as [UsageSummary[], UsageRow[], { total: number }, DailyUsage[], SourceUsage[], ProviderUsage[]]

        setSummary(summaryData)
        setUsageRows(usageData)
        setTotalLogs(countData.total)
        setDailyUsage(dailyData)
        setSourceUsage(bySourceData)
        setProviderUsage(byProviderData)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(err instanceof Error ? err.message : 'Unknown error')
      }
    }

    void loadData()
    return () => controller.abort()
  }, [view, activeFilter, activeSource, limit, page, dateRange, customSince, customUntil, refreshTrigger])

  useEffect(() => {
    if (view === 'settings') return
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

  useEffect(() => {
    setPage(1)
  }, [activeFilter, activeSource, dateRange, customSince, customUntil, limit])

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
    if (dateRange === '5h') minutes = 300;
    else if (dateRange === '7d') minutes = 10080;
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
      rpm: requests / minutes,
      tpm: totalTokens / minutes,
      avgTokensPerRequest: requests === 0 ? 0 : totalTokens / requests,
      successRate
    }
  }, [activeFilter, summary, dateRange])

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
        setError(error.detail || 'Failed to save config')
        setConfigStatus('error')
      }
    } catch (err) {
      setError('Connection error while saving config')
      setConfigStatus('error')
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

  return (
    <div className="app">
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
            📊 Dashboard
          </button>
          <button className={`nav-item ${view === 'logs' ? 'active' : ''}`} onClick={() => setView('logs')}>
            📜 Request Logs
          </button>
          <button className={`nav-item ${view === 'settings' ? 'active' : ''}`} onClick={() => setView('settings')}>
            ⚙️ Settings
          </button>
        </nav>
        <button
          className="nav-item"
          style={{ marginLeft: 'auto', fontSize: '18px' }}
          onClick={() => setTheme(toggleTheme())}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>
      </header>

      <main className="main">

        <div className="content-body">
          {view === 'dashboard' && (
            <>
              <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '8px' }}>
                  <select
                    className="input-plain"
                    value={dateRange}
                    onChange={(e) => setDateRange(e.target.value as DateRangeOption)}
                  >
                    <option value="5h">Last 5 Hours</option>
                    <option value="24h">Last 24 Hours</option>
                    <option value="7d">Last 7 Days</option>
                    <option value="30d">Last 30 Days</option>
                    <option value="all">All Time</option>
                    <option value="custom">Custom Range</option>
                  </select>
                  <ModelSelector
                    activeFilter={activeFilter}
                    summary={summary}
                    providerColors={providerColors}
                    onChange={setActiveFilter}
                  />
                  <select
                    className="input-plain"
                    value={activeSource || ''}
                    onChange={(e) => setActiveSource(e.target.value || null)}
                  >
                    <option value="">All Sources</option>
                    {sources.map(source => (
                      <option key={source} value={source}>{source}</option>
                    ))}
                  </select>
                </div>

              <div className="widgets-grid">
                <div className="widget">
                  <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div className="icon-box icon-yellow">#</div>
                        <div>
                          <div className="stat-label">Token Usage</div>
                          <div className="stat-value">{formatCompact(totals.totalTokens)}</div>
                        </div>
                      </div>
                      <div style={{ width: '100px' }}>
                        <Sparkline data={dailyUsage.map(d => value(d.prompt_tokens) > 0 ? (value(d.cached_tokens) / value(d.prompt_tokens)) * 100 : 0)} color="var(--color-green)" />
                      </div>
                    </div>
                    <div className="stat-label" style={{ marginBottom: 0 }}>
                      In: {formatCompact(totals.promptTokens)} / Out: {formatCompact(totals.completionTokens)}
                    </div>
                    <div className="stat-label" style={{ fontSize: '11px', marginBottom: 0 }}>
                      Cached: {formatCompact(totals.cachedTokens)}
                      <span style={{ marginLeft: '6px', color: 'var(--color-green)', fontWeight: 600 }}>
                        ({totals.totalTokens > 0 ? ((value(totals.cachedTokens) / totals.totalTokens) * 100).toFixed(1) : 0}% Hit)
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
                          <div className="stat-label">Requests</div>
                          <div className="stat-value">{formatNumber(totals.requests)}</div>
                        </div>
                      </div>
                      <div style={{ width: '100px' }}>
                        <Sparkline data={dailyUsage.map(d => d.requests)} color="var(--color-pink)" />
                      </div>
                    </div>
                    <div className="stat-label" style={{ marginTop: '-2px' }}>
                      Avg: <span style={{ color: 'var(--color-purple)', fontWeight: 600 }}>{formatCompact(totals.avgTokensPerRequest)} tokens/req</span>
                    </div>
                  </div>
                </div>

                <div className="widget">
                  <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div className="icon-box icon-green">$</div>
                        <div>
                          <div className="stat-label">Estimated Cost</div>
                          <div className="stat-value">{formatCost(totals.totalCost)}</div>
                        </div>
                      </div>
                      <div style={{ width: '100px' }}>
                        <Sparkline data={dailyUsage.map(d => d.requests > 0 ? value(d.total_cost_usd) / d.requests : 0)} color="var(--color-blue)" />
                      </div>
                    </div>
                    <div className="stat-label" style={{ marginTop: '-2px' }}>
                      Avg: <span style={{ color: 'var(--color-blue)', fontWeight: 600 }}>{formatCost(totals.requests > 0 ? totals.totalCost / totals.requests : 0)} / req</span>
                    </div>
                  </div>
                </div>

                <div className="widget">
                  <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div className="icon-box icon-blue">⚡</div>
                        <div>
                          <div className="stat-label">Performance</div>
                          <div className="stat-value">{totals.rpm.toFixed(3)} <span style={{ fontSize: '12px', fontWeight: 500 }}>RPM</span></div>
                        </div>
                      </div>
                      <div style={{ width: '100px' }}>
                        <Sparkline data={dailyUsage.map(d => value(d.total_tokens))} color="var(--color-purple)" />
                      </div>
                    </div>
                    <div className="stat-label" style={{ marginTop: '-2px' }}>
                      Avg Throughput: <span style={{ color: 'var(--color-purple)', fontWeight: 600 }}>{formatCompact(totals.tpm)} TPM</span>
                    </div>
                  </div>
                </div>

                <div className="widget">
                  <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div className="icon-box icon-pink">~</div>
                        <div>
                          <div className="stat-label">Average Response</div>
                          <div className="stat-value">{formatLatency(totals.avgLatency)}</div>
                        </div>
                      </div>
                      <div style={{ width: '100px' }}>
                        <Sparkline data={dailyUsage.map(d => value(d.avg_latency_ms))} color="var(--color-pink)" />
                      </div>
                    </div>
                    <div className="stat-label" style={{ marginTop: '-2px' }}>
                      Success Rate: <span style={{ color: 'var(--color-green)', fontWeight: 600 }}>{totals.successRate.toFixed(1)}%</span>
                    </div>
                  </div>
                </div>

              </div>

              <div style={{ display: 'flex', gap: '24px', height: '400px' }}>
                <div style={{ flex: '1 1 0', minWidth: 0 }}>
                  <TrendChart
                    data={dailyUsage}
                    title={`${(dateRange === '5h' || dateRange === '24h') ? 'Hourly' : 'Daily'} Usage Trend`}
                  />
                </div>
                <div style={{ flex: '1 1 0', minWidth: 0, display: 'flex', gap: '24px' }}>
                  <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                    <CacheHitRateChart
                      data={dailyUsage}
                      title="Cache Hit Rate"
                    />
                  </div>
                  <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <DailyHeatmap mode="activity" activeFilter={activeFilter} activeSource={activeSource} />
                    <DailyHeatmap mode="success-rate" activeFilter={activeFilter} activeSource={activeSource} />
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '24px', alignItems: 'stretch' }}>
                <div style={{ flex: 1 }}>
                  <ModelTokenChart
                    summary={summary}
                    title="Usage by Model"
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <ProviderTokenChart
                    data={providerUsage}
                    title="Usage by Provider"
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <SourceTokenChart
                    data={sourceUsage}
                    title="Usage by Source"
                  />
                </div>
              </div>

              <div className="content-grid">

              </div>
            </>
          )}

          {view === 'logs' && (
            <div className="logs-page">
              <div className="filter-bar">
                <div className="filter-group">
                  <div className="filter-label">Model</div>
                  <ModelSelector
                    activeFilter={activeFilter}
                    summary={summary}
                    providerColors={providerColors}
                    onChange={setActiveFilter}
                  />
                </div>

                <div className="filter-group">
                  <div className="filter-label">Source</div>
                  <select
                    className="input-plain"
                    value={activeSource || ''}
                    onChange={(e) => setActiveSource(e.target.value || null)}
                  >
                    <option value="">All Sources</option>
                    {sources.map(source => (
                      <option key={source} value={source}>{source}</option>
                    ))}
                  </select>
                </div>

                <div className="filter-group">
                  <div className="filter-label">Date Range</div>
                  <select
                    className="input-plain"
                    value={dateRange}
                    onChange={(e) => setDateRange(e.target.value as DateRangeOption)}
                  >
                    <option value="5h">Last 5 Hours</option>
                    <option value="24h">Last 24 Hours</option>
                    <option value="7d">Last 7 Days</option>
                    <option value="30d">Last 30 Days</option>
                    <option value="all">All Time</option>
                    <option value="custom">Custom Range</option>
                  </select>
                </div>

                {dateRange === 'custom' && (
                  <>
                    <div className="filter-group">
                      <div className="filter-label">Since</div>
                      <input
                        type="datetime-local"
                        className="input-plain"
                        value={customSince.split('.')[0]}
                        onChange={(e) => setCustomSince(new Date(e.target.value).toISOString())}
                      />
                    </div>
                    <div className="filter-group">
                      <div className="filter-label">Until</div>
                      <input
                        type="datetime-local"
                        className="input-plain"
                        value={customUntil.split('.')[0]}
                        onChange={(e) => setCustomUntil(new Date(e.target.value).toISOString())}
                      />
                    </div>
                  </>
                )}

                <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px', alignItems: 'center', alignSelf: 'flex-end' }}>
                   <button
                    className="btn-ghost"
                    onClick={() => setRefreshTrigger(t => t + 1)}
                   >
                     <span>🔄</span> Refresh
                   </button>
                   <button
                    style={{ padding: '8px 16px', background: 'var(--color-blue)', color: 'white', borderRadius: '8px', fontSize: '12px', fontWeight: 700 }}
                    onClick={() => {
                      setDateRange('24h')
                      setPage(1)
                    }}
                   >
                     Today
                   </button>
                </div>
              </div>

              <div className="panel">
                <div className="panel-body" style={{ padding: 0 }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th style={{ width: '120px' }}>Time</th>
                        <th style={{ width: '150px', padding: '12px 8px' }}>Model</th>
                        <th style={{ width: '120px', padding: '12px 8px' }}>Provider</th>
                        <th style={{ width: '110px', padding: '12px 8px' }}>Source</th>
                        <th style={{ minWidth: '140px' }}>Input (Prompt)</th>
                        <th style={{ minWidth: '120px' }}>Output</th>
                        <th style={{ minWidth: '100px' }}>Cost</th>
                        <th style={{ padding: '12px 8px' }}>
                          <div className="has-tooltip">
                            TTFT / Latency
                            <div className="tooltip-text">
                              <b>Claude Code:</b> No TTFT<br/>
                              <b>Gemini CLI:</b> Time to first chunk<br/>
                              <b>Codex:</b> Actual TTFT<br/>
                              <b>Proxy:</b> Time to first chunk
                            </div>
                          </div>
                        </th>
                        <th style={{ width: '80px' }}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {usageRows.map(row => (
                        <tr key={row.id}>
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
                              maxWidth: '140px',
                              fontWeight: 600
                            }}>
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
                                <span style={{ fontSize: '10px', fontWeight: 400, marginLeft: '4px', color: 'var(--text-secondary)' }}>tokens</span>
                                {value(row.prompt_length) > 0 && (
                                  <span style={{ fontSize: '10px', fontWeight: 400, marginLeft: '6px', color: 'var(--text-muted)' }}>
                                    (Prompt: {formatNumber(row.prompt_length)} chars)
                                  </span>
                                )}
                              </div>
                              {value(row.cached_tokens) > 0 && (
                                <div style={{ fontSize: '9px', color: 'var(--color-green)', fontWeight: 700 }}>
                                  Cache read {formatNumber(row.cached_tokens)} ({Math.round((value(row.cached_tokens) / (value(row.prompt_tokens) || 1)) * 100)}%)
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
                                  Reasoning {formatNumber(row.reasoning_tokens)} ({Math.round((value(row.reasoning_tokens) / (value(row.completion_tokens) || 1)) * 100)}%)
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
                                        <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>Input:</span>
                                        <div style={{ textAlign: 'right' }}>
                                          <div>{formatCost(actualInputCost)}</div>
                                          {modelConfig?.input !== undefined && (
                                            <div style={{ fontSize: '9px', color: 'rgba(255, 255, 255, 0.4)' }}>{formatNumber(uncachedTokens)} tokens x {formatRate(modelConfig.input)}</div>
                                          )}
                                        </div>
                                      </div>
                                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                                        <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>Output:</span>
                                        <div style={{ textAlign: 'right' }}>
                                          <div>{formatCost(outputCost)}</div>
                                          {modelConfig?.output !== undefined && (
                                            <div style={{ fontSize: '9px', color: 'rgba(255, 255, 255, 0.4)' }}>{formatNumber(completionTokens)} tokens x {formatRate(modelConfig.output)}</div>
                                          )}
                                        </div>
                                      </div>
                                      {cacheCost > 0 && (
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                                          <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>Cache:</span>
                                          <div style={{ textAlign: 'right' }}>
                                            <div style={{ color: 'var(--color-green)' }}>{formatCost(cacheCost)}</div>
                                            {modelConfig?.cacheRead !== undefined && (
                                              <div style={{ fontSize: '9px', color: 'rgba(255, 255, 255, 0.4)' }}>{formatNumber(cached)} tokens x {formatRate(modelConfig.cacheRead)}</div>
                                            )}
                                          </div>
                                        </div>
                                      )}
                                      <div style={{ marginTop: '4px', paddingTop: '4px', borderTop: '1px solid #334155', display: 'flex', justifyContent: 'space-between', color: 'white' }}>
                                        <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>Total:</span>
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
                                }} title="Time To First Token">
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
                              }} title="Total Latency">
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
                      ))}
                      {usageRows.length === 0 && (
                        <tr>
                          <td colSpan={7} style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                            No requests found for the selected filters.
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
                    Showing <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{Math.min(totalLogs, (page - 1) * limit + 1)}-{Math.min(totalLogs, page * limit)}</span> of <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{totalLogs}</span> logs
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
                      ◀ Prev
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
                      Next ▶
                    </button>

                    <div style={{ marginLeft: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Jump:</span>
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
                      onChange={(e) => setLimit(Number(e.target.value))}
                      style={{
                        border: 'none',
                        background: 'transparent',
                        fontWeight: 700,
                        fontSize: '13px',
                        color: 'var(--text-primary)',
                        outline: 'none',
                        cursor: 'pointer'
                      }}
                    >
                      <option value={10}>10 / page</option>
                      <option value={25}>25 / page</option>
                      <option value={50}>50 / page</option>
                      <option value={100}>100 / page</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          )}

          {view === 'settings' && (
            <div className="settings-page" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <div className="panel">
                <div className="panel-tabs">
                  <div className="tab active"><span>🔌</span> Active Providers</div>
                </div>
                <div className="panel-body" style={{ padding: '0' }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Provider</th>
                        <th>Base URL</th>
                        <th>Models</th>
                      </tr>
                    </thead>
                    <tbody>
                      {configParsed?.providers ? Object.entries(configParsed.providers).map(([name, conf]: [string, any]) => {
                        const models = Array.isArray(conf.models)
                          ? conf.models
                          : (conf.models ? Object.keys(conf.models) : []);
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
                            <td style={{ fontSize: '12px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{conf.base_url}</td>
                            <td>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                                {models.map((m: string) => {
                                  const hasOverride = conf.models?.[m]?.cost !== undefined;
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
                                      {hasOverride && <span title="Cost Override" style={{ fontSize: '10px' }}>💰</span>}
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
                            No providers configured in config.yaml.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="panel">
                <div className="panel-tabs" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div className="tab active"><span>💎</span> Model Pricing</div>
                  <div style={{ paddingRight: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Scope:</span>
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
                      <option value="global">Global Default</option>
                      {configParsed?.providers && Object.keys(configParsed.providers).map(p => (
                        <option key={p} value={p}>Provider: {p}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="panel-body" style={{ padding: '0' }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th style={{ width: '220px' }}>Model</th>
                        <th>Input (per 1M)</th>
                        <th>Output (per 1M)</th>
                        <th>Cache Read (per 1M)</th>
                        <th>Cache Write (per 1M)</th>
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
                                {isOverridden && <span title="Provider Override" style={{ fontSize: '10px' }}>💰</span>}
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
                            No global models configured in config.yaml.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="panel">
                <div className="panel-tabs">
                  <div className="tab active"><span>📝</span> Configuration (YAML)</div>
                </div>
                <div className="panel-body">
                  <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
                    Directly edit your <code>config.yaml</code>. Providers and routing are defined here.
                  </p>

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
                        ✓ Configuration saved successfully
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
                      {configStatus === 'saving' ? 'Saving...' : 'Save Configuration'}
                    </button>
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
