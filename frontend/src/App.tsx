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
  return latency >= 1000 ? `${(latency / 1000).toFixed(2)}s` : `${Math.round(latency)}ms`
}

function formatTime(input: string) {
  const date = new Date(input)
  if (Number.isNaN(date.valueOf())) return input
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).format(date)
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
          throw new Error('Failed to fetch usage data')
        }

        const [summaryData, usageData] = (await Promise.all([
          summaryResponse.json(),
          usageResponse.json(),
        ])) as [UsageSummary[], UsageRow[]]

        setSummary(summaryData)
        setUsageRows(usageData)
        setLoadState('ready')
      } catch (err) {
        if (controller.signal.aborted) return
        setLoadState('error')
        setError(err instanceof Error ? err.message : 'Unknown error')
      }
    }

    void loadUsage()
    return () => controller.abort()
  }, [activeFilter, limit])

  const totals = useMemo(() => {
    const data = activeFilter 
      ? summary.filter(s => s.provider === activeFilter.provider && s.model === activeFilter.model)
      : summary

    const requests = data.reduce((sum, row) => sum + value(row.requests), 0)
    const promptTokens = data.reduce((sum, row) => sum + value(row.prompt_tokens), 0)
    const completionTokens = data.reduce((sum, row) => sum + value(row.completion_tokens), 0)
    const reasoningTokens = data.reduce((sum, row) => sum + value(row.reasoning_tokens), 0)
    const cachedTokens = data.reduce((sum, row) => sum + value(row.cached_tokens), 0)
    const totalTokens = data.reduce((sum, row) => sum + value(row.total_tokens), 0)
    const latencyWeight = data.reduce((sum, row) => sum + value(row.avg_latency_ms) * value(row.requests), 0)

    return {
      requests,
      promptTokens,
      completionTokens,
      reasoningTokens,
      cachedTokens,
      totalTokens,
      avgLatency: requests === 0 ? 0 : latencyWeight / requests,
    }
  }, [activeFilter, summary])

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="icon">☁️</div>
          <span>llm-tracker</span>
        </div>
        <div className="sidebar-menu">
          <div className="menu-group">
            <div className="menu-title">Main</div>
            <button className="menu-item active">
              <span>💻</span> Dashboard
            </button>
            <button className="menu-item">
              <span>🔑</span> API Keys
            </button>
            <button className="menu-item">
              <span>📖</span> Logs
            </button>
            <button className="menu-item">
              <span>🖼️</span> Image Gen
            </button>
            <button className="menu-item">
              <span>⚙️</span> Tasks
            </button>
          </div>
          <div className="menu-group">
            <div className="menu-title">User</div>
            <button className="menu-item">
              <span>💰</span> Wallet
            </button>
            <button className="menu-item">
              <span>🧾</span> Billing
            </button>
            <button className="menu-item">
              <span>👤</span> Settings
            </button>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="top-navbar">
          <div className="navbar-title">Dashboard</div>
          <div className="navbar-right">
             <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '18px' }}>📢</span>
                <span style={{ fontSize: '18px' }}>🌐</span>
                <div style={{ padding: '6px 12px', background: '#f1f5f9', borderRadius: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div style={{ background: '#fbbf24', width: 24, height: 24, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: '12px', fontWeight: 'bold' }}>G</div>
                  <span style={{ fontSize: '13px', fontWeight: 600 }}>ghbhanbo</span>
                  <span style={{ fontSize: '10px' }}>▼</span>
                </div>
             </div>
          </div>
        </header>

        <div className="content-body">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div className="welcome-msg">👋 Hello, ghbhanbo</div>
            <select 
              style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid var(--border-color)', outline: 'none' }}
              value={activeFilter ? `${activeFilter.provider}|${activeFilter.model}` : ''}
              onChange={(e) => {
                if (!e.target.value) setActiveFilter(null)
                else {
                  const [provider, model] = e.target.value.split('|')
                  setActiveFilter({ provider, model })
                }
              }}
            >
              <option value="">🌐 All Models</option>
              {summary.map(s => (
                <option key={`${s.provider}:${s.model}`} value={`${s.provider}|${s.model}`}>
                  {s.model}
                </option>
              ))}
            </select>
          </div>

          <div className="widgets-grid">
            <div className="widget">
              <div className="widget-header"><span>💼</span> Account</div>
              <div className="widget-body">
                <div className="icon-box icon-blue">💰</div>
                <div className="stat-group">
                  <div className="stat-label">Balance</div>
                  <div className="stat-value">$ 25.16</div>
                </div>
              </div>
              <div className="widget-body" style={{ marginTop: '12px' }}>
                <div className="icon-box icon-purple">📉</div>
                <div className="stat-group">
                  <div className="stat-label">Spent</div>
                  <div className="stat-value">$ 212.02</div>
                </div>
              </div>
            </div>
            
            <div className="widget">
              <div className="widget-header"><span>📈</span> Usage</div>
              <div className="widget-body">
                <div className="icon-box icon-green">🚀</div>
                <div className="stat-group">
                  <div className="stat-label">Requests</div>
                  <div className="stat-value">{formatNumber(totals.requests)}</div>
                </div>
              </div>
              <div className="widget-body" style={{ marginTop: '12px' }}>
                <div className="icon-box icon-blue">⏱️</div>
                <div className="stat-group">
                  <div className="stat-label">Latency</div>
                  <div className="stat-value">{formatLatency(totals.avgLatency)}</div>
                </div>
              </div>
            </div>

            <div className="widget">
              <div className="widget-header"><span>⚡</span> Resources</div>
              <div className="widget-body">
                <div className="icon-box icon-yellow">🪙</div>
                <div className="stat-group">
                  <div className="stat-label">Cost Estimate</div>
                  <div className="stat-value">$ {(totals.requests * 0.0001).toFixed(2)}</div>
                </div>
              </div>
              <div className="widget-body" style={{ marginTop: '12px' }}>
                <div className="icon-box icon-pink">🎟️</div>
                <div className="stat-group">
                  <div className="stat-label">Tokens</div>
                  <div className="stat-value">{formatCompact(totals.totalTokens)}</div>
                </div>
              </div>
            </div>

            <div className="widget">
              <div className="widget-header"><span>⏱️</span> Performance</div>
              <div className="widget-body">
                <div className="icon-box icon-blue">🔄</div>
                <div className="stat-group">
                  <div className="stat-label">RPM</div>
                  <div className="stat-value">0.071</div>
                </div>
              </div>
              <div className="widget-body" style={{ marginTop: '12px' }}>
                <div className="icon-box icon-yellow">🔂</div>
                <div className="stat-group">
                  <div className="stat-label">TPM</div>
                  <div className="stat-value">4143.06</div>
                </div>
              </div>
            </div>
          </div>

          <div className="content-grid">
            <div className="panel">
              <div className="panel-tabs">
                <div className="tab active"><span>🕒</span> Activity</div>
                <div className="tab"><span>📊</span> Distribution</div>
                <div className="tab"><span>📈</span> Trends</div>
                <div className="tab"><span>🏆</span> Ranking</div>
              </div>
              <div className="panel-body">
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
                   <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <button style={{ padding: '4px 8px', background: '#f1f5f9', borderRadius: '4px' }}>◀</button>
                      <span style={{ fontWeight: 600, fontSize: '13px' }}>📅 Apr 2026</span>
                      <button style={{ padding: '4px 8px', background: '#f1f5f9', borderRadius: '4px' }}>▶</button>
                      <button style={{ padding: '4px 12px', background: 'var(--color-blue)', color: 'white', borderRadius: '16px', fontSize: '12px', fontWeight: 600 }}>Today</button>
                   </div>
                   <div style={{ fontSize: '13px' }}>
                      Logs: <span style={{ color: 'var(--color-blue)', fontWeight: 600 }}>{usageRows.length}</span> | 
                      Limit: <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} style={{ border: 'none', background: 'transparent', fontWeight: 600, outline: 'none' }}>
                        <option value={25}>25</option>
                        <option value={50}>50</option>
                        <option value={100}>100</option>
                      </select>
                   </div>
                </div>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Model</th>
                      <th>Tokens</th>
                      <th>Latency</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usageRows.map(row => (
                      <tr key={row.id}>
                        <td style={{ color: '#64748b' }}>{formatTime(row.ts)}</td>
                        <td>
                          <div style={{ fontWeight: 600 }}>{row.model}</div>
                        </td>
                        <td style={{ fontWeight: 600, color: 'var(--color-blue)' }}>{formatNumber(row.total_tokens)}</td>
                        <td>{formatLatency(row.latency_ms)}</td>
                        <td>
                          <span className={`badge ${value(row.status) >= 400 ? 'badge-error' : 'badge-success'}`}>
                            {row.status ?? '200'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="panel">
              <div className="panel-tabs">
                <div className="tab active"><span>🔌</span> API Info</div>
              </div>
              <div className="panel-body">
                <div className="api-item">
                  <div className="api-title">
                     <span className="badge" style={{ background: '#dbeafe', color: 'var(--color-blue)' }}>Main</span> 
                     Primary Hub
                     <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px' }}>
                        <button style={{ padding: '2px 8px', border: '1px solid #e2e8f0', borderRadius: '4px', fontSize: '11px' }}>⏱️ Ping</button>
                        <button style={{ padding: '2px 8px', border: '1px solid #e2e8f0', borderRadius: '4px', fontSize: '11px' }}>↗️ Goto</button>
                     </div>
                  </div>
                  <div className="api-link">https://api.llm-tracker.local</div>
                  <div className="api-desc">US High-Availability Cluster</div>
                </div>
                
                <div className="api-item">
                  <div className="api-title">
                     <span className="badge" style={{ background: '#e0e7ff', color: 'var(--color-purple)' }}>Alt</span> 
                     Fallback Hub
                     <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px' }}>
                        <button style={{ padding: '2px 8px', border: '1px solid #e2e8f0', borderRadius: '4px', fontSize: '11px' }}>⏱️ Ping</button>
                        <button style={{ padding: '2px 8px', border: '1px solid #e2e8f0', borderRadius: '4px', fontSize: '11px' }}>↗️ Goto</button>
                     </div>
                  </div>
                  <div className="api-link">https://proxy.llm-tracker.local</div>
                  <div className="api-desc">EU Failover Node</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
