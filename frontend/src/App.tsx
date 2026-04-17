import { useEffect, useMemo, useState } from 'react'
import './App.css'

type UsageSummary = {
  provider: string
  model: string
  requests: number
  prompt_tokens: number | null
  completion_tokens: number | null
  reasoning_tokens: number | null
  cached_tokens: number | null
  total_tokens: number | null
  avg_latency_ms: number | null
}

type UsageRow = {
  id: number
  ts: string
  provider: string
  model: string
  endpoint: string
  prompt_tokens: number | null
  completion_tokens: number | null
  reasoning_tokens: number | null
  cached_tokens: number | null
  total_tokens: number | null
  latency_ms: number | null
  status: number | null
}

type LoadState = 'idle' | 'loading' | 'ready' | 'error'
type ActiveFilter = { provider: string; model: string } | null

const numberFormatter = new Intl.NumberFormat()
const compactFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 1,
  notation: 'compact',
})

function value(input: number | null | undefined) {
  return input ?? 0
}

function formatNumber(input: number | null | undefined) {
  return numberFormatter.format(value(input))
}

function formatCompact(input: number | null | undefined) {
  return compactFormatter.format(value(input))
}

function formatLatency(input: number | null | undefined) {
  const latency = value(input)
  return latency >= 1000 ? `${(latency / 1000).toFixed(1)}s` : `${Math.round(latency)}ms`
}

function formatTime(input: string) {
  const date = new Date(input)

  if (Number.isNaN(date.valueOf())) {
    return input
  }

  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function tokenPercent(part: number, total: number) {
  if (total === 0) {
    return '0%'
  }

  return `${Math.max(4, Math.round((part / total) * 100))}%`
}

function App() {
  const [summary, setSummary] = useState<UsageSummary[]>([])
  const [usageRows, setUsageRows] = useState<UsageRow[]>([])
  const [limit, setLimit] = useState(50)
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>(null)
  const [loadState, setLoadState] = useState<LoadState>('idle')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    async function loadUsage() {
      setLoadState('loading')
      setError(null)

      try {
        const usageUrl = new URL('/usage', window.location.origin)
        usageUrl.searchParams.set('limit', String(limit))

        if (activeFilter) {
          usageUrl.searchParams.set('provider', activeFilter.provider)
          usageUrl.searchParams.set('model', activeFilter.model)
        }

        const [summaryResponse, usageResponse] = await Promise.all([
          fetch('/usage/summary', { signal: controller.signal }),
          fetch(`${usageUrl.pathname}${usageUrl.search}`, { signal: controller.signal }),
        ])

        if (!summaryResponse.ok || !usageResponse.ok) {
          throw new Error('Usage API returned an unsuccessful response.')
        }

        const [summaryData, usageData] = (await Promise.all([
          summaryResponse.json(),
          usageResponse.json(),
        ])) as [UsageSummary[], UsageRow[]]

        setSummary(summaryData)
        setUsageRows(usageData)
        setLoadState('ready')
      } catch (requestError) {
        if (controller.signal.aborted) {
          return
        }

        setLoadState('error')
        setError(
          requestError instanceof Error
            ? requestError.message
            : 'Unable to load usage data.',
        )
      }
    }

    void loadUsage()

    return () => controller.abort()
  }, [activeFilter, limit])

  const filteredSummary = useMemo(() => {
    if (!activeFilter) {
      return summary
    }

    return summary.filter(
      (row) =>
        row.provider === activeFilter.provider && row.model === activeFilter.model,
    )
  }, [activeFilter, summary])

  const totals = useMemo(() => {
    const requests = filteredSummary.reduce((sum, row) => sum + value(row.requests), 0)
    const promptTokens = filteredSummary.reduce(
      (sum, row) => sum + value(row.prompt_tokens),
      0,
    )
    const completionTokens = filteredSummary.reduce(
      (sum, row) => sum + value(row.completion_tokens),
      0,
    )
    const reasoningTokens = filteredSummary.reduce(
      (sum, row) => sum + value(row.reasoning_tokens),
      0,
    )
    const cachedTokens = filteredSummary.reduce(
      (sum, row) => sum + value(row.cached_tokens),
      0,
    )
    const totalTokens = filteredSummary.reduce((sum, row) => sum + value(row.total_tokens), 0)
    const latencyWeight = filteredSummary.reduce(
      (sum, row) => sum + value(row.avg_latency_ms) * value(row.requests),
      0,
    )
    const providers = new Set(filteredSummary.map((row) => row.provider))

      return {
        avgLatency: requests === 0 ? 0 : latencyWeight / requests,
        cachedTokens,
        completionTokens,
        modelCount: filteredSummary.length,
        promptTokens,
        providerCount: providers.size,
        reasoningTokens,
        requests,
        totalTokens,
    }
  }, [filteredSummary])

  const topModels = summary.slice(0, 6)
  const activeFilterLabel = activeFilter
    ? `${activeFilter.provider} / ${activeFilter.model}`
    : null
  const activeModelName = activeFilter?.model ?? null
  const activeProviderName = activeFilter?.provider ?? null
  const statusText =
    loadState === 'loading'
      ? 'Refreshing usage API...'
      : loadState === 'error'
        ? 'Usage API unavailable'
        : activeFilterLabel
          ? `${formatNumber(totals.requests)} requests for ${activeFilterLabel}`
          : `${formatNumber(totals.requests)} requests tracked`

  function handleModelCardClick(provider: string, model: string) {
    setActiveFilter((current) =>
      current?.provider === provider && current?.model === model
        ? null
        : { provider, model },
    )
  }

  return (
    <>
      <header className="site-header">
        <a className="brand" href="#overview" aria-label="llm-tracker dashboard">
          <span className="brand-mark">L</span>
          <span>llm-tracker</span>
        </a>
        <nav className="nav-pills" aria-label="Dashboard sections">
          <a href="#overview">Overview</a>
          <a href="#models">Models</a>
          <a href="#requests">Requests</a>
        </nav>
      </header>

      <main>
        <section className="hero" id="overview">
          <div className="hero-copy">
            <p className="eyebrow">Usage intelligence for OpenAI-compatible traffic</p>
            <h1>Track every token moving through your LLM proxy.</h1>
            <p className="hero-text">
              Monitor spend pressure, model mix, latency, cache efficiency, and
              reasoning load from the lightweight usage logs already collected by
              llm-tracker.
            </p>
            <div className="hero-actions">
              <a className="primary-action" href="#requests">
                Inspect requests
              </a>
              <a className="secondary-action" href="#models">
                Compare models
              </a>
            </div>
          </div>

          <aside className="hero-card" aria-label="Total token usage">
            <div className="orb orb-one"></div>
            <div className="orb orb-two"></div>
            <p>Total tokens</p>
            <strong>{formatCompact(totals.totalTokens)}</strong>
            <span>
              {formatCompact(totals.promptTokens)} input ·{' '}
              {formatCompact(totals.completionTokens)} output
            </span>
            <div className="hero-bars" aria-hidden="true">
              <span style={{ height: tokenPercent(totals.promptTokens, totals.totalTokens) }} />
              <span style={{ height: tokenPercent(totals.completionTokens, totals.totalTokens) }} />
              <span style={{ height: tokenPercent(totals.reasoningTokens, totals.totalTokens) }} />
              <span style={{ height: tokenPercent(totals.cachedTokens, totals.totalTokens) }} />
              <span style={{ height: tokenPercent(totals.requests, Math.max(totals.requests, 1)) }} />
            </div>
          </aside>
        </section>

        <section className="metrics-grid" aria-label="Usage metrics">
          <MetricCard label="Requests" value={formatNumber(totals.requests)} note="Total tracked proxy calls" />
          <MetricCard label="Input tokens" value={formatNumber(totals.promptTokens)} note="Prompt load across providers" />
          <MetricCard label="Output tokens" value={formatNumber(totals.completionTokens)} note="Generated response volume" />
          <MetricCard label="Avg latency" value={formatLatency(totals.avgLatency)} note="Weighted by request count" />
        </section>

        <section className="section-header" id="models">
          <div>
            <p className="eyebrow">Model matrix</p>
            <h2>Provider and model mix</h2>
          </div>
          <div className={`status-pill ${loadState === 'error' ? 'is-error' : ''}`}>
            {statusText}
          </div>
        </section>

        {error ? <div className="notice">{error}</div> : null}

        <section className="model-grid" aria-label="Model usage cards">
          {topModels.length > 0 ? (
            topModels.map((row, index) => (
              <button
                type="button"
                className={`model-card ${
                  activeFilter?.provider === row.provider &&
                  activeFilter?.model === row.model
                    ? 'is-active'
                    : ''
                }`}
                key={`${row.provider}:${row.model}`}
                onClick={() => handleModelCardClick(row.provider, row.model)}
                aria-pressed={
                  activeFilter?.provider === row.provider &&
                  activeFilter?.model === row.model
                }
              >
                <span className="model-rank">{String(index + 1).padStart(2, '0')}</span>
                <p>{row.provider}</p>
                <h3>{row.model}</h3>
                <div className="model-card-footer">
                  <span>{formatNumber(row.requests)} requests</span>
                  <strong>{formatCompact(row.total_tokens)} tokens</strong>
                </div>
              </button>
            ))
          ) : (
            <EmptyState title="No usage yet" text="Send traffic through the proxy and this model matrix will populate automatically." />
          )}
        </section>

        <section className="usage-layout">
          <article className="panel chart-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Token composition</p>
                <h2>{activeModelName ? `Usage for ${activeModelName}` : 'Where usage accumulates'}</h2>
              </div>
            </div>
            <div className="token-chart">
              <TokenBar label="Input" value={totals.promptTokens} total={totals.totalTokens} />
              <TokenBar label="Output" value={totals.completionTokens} total={totals.totalTokens} />
              <TokenBar label="Reasoning" value={totals.reasoningTokens} total={totals.totalTokens} />
              <TokenBar label="Cached" value={totals.cachedTokens} total={totals.totalTokens} />
            </div>
          </article>

          <article className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Efficiency</p>
                <h2>{activeProviderName ? `Signals for ${activeProviderName}` : 'Cache and reasoning signals'}</h2>
              </div>
            </div>
            <div className="signal-list">
              <Signal label="Cached tokens" value={formatNumber(totals.cachedTokens)} />
              <Signal label="Reasoning tokens" value={formatNumber(totals.reasoningTokens)} />
              <Signal label="Models observed" value={formatNumber(totals.modelCount)} />
              <Signal label="Providers observed" value={formatNumber(totals.providerCount)} />
            </div>
          </article>
        </section>

        <section className="panel request-panel" id="requests">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Recent activity</p>
              <h2>{activeModelName ? `Latest ${activeModelName} requests` : 'Latest proxy requests'}</h2>
            </div>
            <div className="request-controls">
              {activeFilterLabel ? (
                <button
                  type="button"
                  className="filter-chip"
                  onClick={() => setActiveFilter(null)}
                >
                  {activeFilterLabel} x
                </button>
              ) : null}
              <select
                aria-label="Number of recent requests"
                value={limit}
                onChange={(event) => setLimit(Number(event.target.value))}
              >
                <option value="25">25 rows</option>
                <option value="50">50 rows</option>
                <option value="100">100 rows</option>
              </select>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Provider</th>
                  <th>Model</th>
                  <th>Endpoint</th>
                  <th>Tokens</th>
                  <th>Latency</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {usageRows.length > 0 ? (
                  usageRows.map((row) => (
                    <tr key={row.id}>
                      <td>{formatTime(row.ts)}</td>
                      <td>{row.provider}</td>
                      <td>{row.model}</td>
                      <td>{row.endpoint}</td>
                      <td>{formatNumber(row.total_tokens)}</td>
                      <td>{formatLatency(row.latency_ms)}</td>
                      <td>
                        <span className={value(row.status) >= 400 ? 'status bad' : 'status'}>
                          {row.status ?? 'n/a'}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7}>No recent requests found.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      <footer>
        <span>llm-tracker</span>
        <span>Pass-through proxy visibility for model traffic.</span>
      </footer>
    </>
  )
}

function MetricCard({
  label,
  note,
  value: metricValue,
}: {
  label: string
  note: string
  value: string
}) {
  return (
    <article className="metric-card">
      <span>{label}</span>
      <strong>{metricValue}</strong>
      <p>{note}</p>
    </article>
  )
}

function TokenBar({ label, total, value: barValue }: { label: string; total: number; value: number }) {
  return (
    <div className="token-row">
      <div>
        <span>{label}</span>
        <strong>{formatNumber(barValue)}</strong>
      </div>
      <div className="track">
        <span style={{ width: tokenPercent(barValue, total) }} />
      </div>
    </div>
  )
}

function Signal({ label, value: signalValue }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{signalValue}</strong>
    </div>
  )
}

function EmptyState({ text, title }: { text: string; title: string }) {
  return (
    <article className="empty-state">
      <h3>{title}</h3>
      <p>{text}</p>
    </article>
  )
}

export default App
