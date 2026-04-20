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
  ttft_ms: number | null
  tool_tokens: number | null
  status: number | null
}

type DailyUsage = {
  period: string
  requests: number
  prompt_tokens: number | null
  completion_tokens: number | null
  cached_tokens: number | null
  total_tokens: number | null
}

type ActiveFilter = { provider: string; model: string } | null
type DateRangeOption = '5h' | '24h' | '7d' | '30d' | 'custom'

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

function getSinceDate(option: DateRangeOption): string | null {
  if (option === 'custom') return null
  const now = new Date()
  if (option === '5h') now.setHours(now.getHours() - 5)
  else if (option === '24h') now.setHours(now.getHours() - 24)
  else if (option === '7d') now.setDate(now.getDate() - 7)
  else if (option === '30d') now.setDate(now.getDate() - 30)
  return now.toISOString()
}

function getTimezoneOffset(): string {
  const offset = -new Date().getTimezoneOffset();
  const absOffset = Math.abs(offset);
  const hours = Math.floor(absOffset / 60);
  const mins = absOffset % 60;
  const sign = offset >= 0 ? '+' : '-';
  return `${sign}${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`;
}

function getModelColor(model: string): string {
  const m = model.toLowerCase()
  if (m.includes('gpt-5') || m.includes('gpt-4')) return '#dcdcdc' // RGB 220 220 220
  if (m.includes('claude')) return '#cc7c5e' // RGB 204 124 94
  if (m.includes('gemini')) return '#528af2' // RGB 82 138 242
  if (m.includes('minimax')) return '#ec6b53' // RGB 236 107 83
  return '#f1f5f9'
}

function getModelTextColor(model: string): string {
  const m = model.toLowerCase()
  if (m.includes('gpt-5') || m.includes('gpt-4')) return '#475569'
  return getModelColor(model)
}

function getModelIcon(model: string) {
  const m = model.toLowerCase()
  const style = { width: 14, height: 14, display: 'block', objectFit: 'contain' as const }
  if (m.includes('gpt')) return <img src="/models/chatgpt.svg" alt="" style={style} />
  if (m.includes('claude')) return <img src="/models/claude-ai-icon.svg" alt="" style={style} />
  if (m.includes('gemini')) return <img src="/models/google-gemini-icon.svg" alt="" style={style} />
  if (m.includes('minimax')) return <img src="/models/minimax-color.svg" alt="" style={style} />
  
  return null
}

function ModelSelector({ 
  activeFilter, 
  summary, 
  onChange 
}: { 
  activeFilter: ActiveFilter, 
  summary: UsageSummary[], 
  onChange: (filter: ActiveFilter) => void 
}) {
  const [isOpen, setIsOpen] = useState(false);
  
  return (
    <div style={{ position: 'relative' }}>
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="input-plain"
        style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: '8px', 
          minWidth: '180px',
          background: '#fff',
          justifyContent: 'space-between'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {activeFilter ? (
            <>
              {getModelIcon(activeFilter.model)}
              <span style={{ fontSize: '13px' }}>{activeFilter.model}</span>
            </>
          ) : (
            <>
              <span>🌐</span>
              <span style={{ fontWeight: 600 }}>All Models</span>
            </>
          )}
        </div>
        <span style={{ fontSize: '10px' }}>▼</span>
      </button>
      
      {isOpen && (
        <>
          <div 
            style={{ position: 'fixed', inset: 0, zIndex: 40 }} 
            onClick={() => setIsOpen(false)} 
          />
          <div style={{ 
            position: 'absolute', 
            top: '100%', 
            right: 0, 
            marginTop: '4px', 
            background: '#fff', 
            border: '1px solid var(--border-color)', 
            borderRadius: '8px', 
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
            zIndex: 50,
            minWidth: '220px',
            maxHeight: '300px',
            overflowY: 'auto',
            padding: '4px'
          }}>
            <button 
              onClick={() => { onChange(null); setIsOpen(false); }}
              style={{ 
                width: '100%', 
                padding: '8px 12px', 
                display: 'flex', 
                alignItems: 'center', 
                gap: '8px', 
                borderRadius: '6px',
                background: !activeFilter ? '#f1f5f9' : 'transparent',
                textAlign: 'left'
              }}
            >
              <span>🌐</span> All Models
            </button>
            {summary.map(s => (
              <button 
                key={`${s.provider}:${s.model}`}
                onClick={() => { onChange({ provider: s.provider, model: s.model }); setIsOpen(false); }}
                style={{ 
                  width: '100%', 
                  padding: '8px 12px', 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '8px', 
                  borderRadius: '6px',
                  background: activeFilter?.model === s.model ? '#f1f5f9' : 'transparent',
                  textAlign: 'left'
                }}
              >
                {getModelIcon(s.model)}
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <span style={{ fontSize: '13px' }}>{s.model}</span>
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{s.provider}</span>
                </div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function TrendChart({ 
  data, 
  title
}: { 
  data: DailyUsage[], 
  title: string
}) {
  const maxTokens = Math.max(...data.map(x => value(x.total_tokens)), 1);
  const maxRequests = Math.max(...data.map(x => value(x.requests)), 1);
  const paddingX = 60; // Internal horizontal padding
  const chartWidth = 1000 - (paddingX * 2);
  
  return (
    <div className="widget" style={{ minHeight: '400px', width: '100%' }}>
      <div className="widget-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>📈 {title}</span>
        <div style={{ display: 'flex', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div style={{ width: '12px', height: '12px', background: '#94a3b8', borderRadius: '2px' }} />
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>Input</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div style={{ width: '12px', height: '12px', background: 'var(--color-green)', borderRadius: '2px' }} />
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>Cached</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div style={{ width: '12px', height: '12px', background: 'var(--color-blue)', borderRadius: '2px' }} />
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>Output</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div style={{ width: '12px', height: '3px', background: 'var(--color-pink)', borderRadius: '2px' }} />
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>Requests</span>
          </div>
        </div>
      </div>
      <div style={{ 
        flex: 1, 
        padding: '20px 0',
        height: '280px',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column'
      }}>
        {data.length === 0 ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>No trend data available</div>
        ) : (
          <>
            <svg 
              viewBox="0 0 1000 200" 
              preserveAspectRatio="none"
              style={{ width: '100%', height: '220px', overflow: 'visible' }}
            >
              {[0, 0.25, 0.5, 0.75, 1].map(tick => (
                <line 
                  key={tick}
                  x1="0" y1={200 - tick * 200} 
                  x2="1000" y2={200 - tick * 200} 
                  stroke="#f1f5f9" 
                  strokeWidth="1"
                />
              ))}

              {/* Stacked Bars for Tokens */}
              {data.map((d, i) => {
                const x = paddingX + (i / (Math.max(data.length - 1, 1))) * chartWidth;
                const barWidth = Math.min(chartWidth / (data.length * 1.5), 60);
                
                const cached = value(d.cached_tokens);
                const input = Math.max(0, value(d.prompt_tokens) - cached);
                const output = value(d.completion_tokens);
                
                const hInput = (input / maxTokens) * 200;
                const hCached = (cached / maxTokens) * 200;
                const hOutput = (output / maxTokens) * 200;

                return (
                  <g key={i}>
                    {/* Input */}
                    <rect 
                      x={x - barWidth/2} y={200 - hInput} 
                      width={barWidth} height={hInput} 
                      fill="#94a3b8" 
                    />
                    {/* Cached */}
                    <rect 
                      x={x - barWidth/2} y={200 - hInput - hCached} 
                      width={barWidth} height={hCached} 
                      fill="var(--color-green)" 
                    />
                    {/* Output */}
                    <rect 
                      x={x - barWidth/2} y={200 - hInput - hCached - hOutput} 
                      width={barWidth} height={hOutput} 
                      fill="var(--color-blue)" 
                    />
                    <title>
                      {`${d.period}\nInput: ${formatNumber(input)}\nCached: ${formatNumber(cached)}\nOutput: ${formatNumber(output)}\nTotal: ${formatNumber(value(d.total_tokens))}`}
                    </title>
                  </g>
                );
              })}

              {/* Line for Requests */}
              {(() => {
                const points = data.map((d, i) => {
                  const x = paddingX + (i / (Math.max(data.length - 1, 1))) * chartWidth;
                  const y = 200 - (value(d.requests) / maxRequests) * 200;
                  return `${x},${y}`;
                }).join(' ');

                return (
                  <>
                    <polyline
                      points={points}
                      fill="none"
                      stroke="var(--color-pink)"
                      strokeWidth="3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    {data.map((d, i) => {
                      const x = paddingX + (i / (Math.max(data.length - 1, 1))) * chartWidth;
                      const y = 200 - (value(d.requests) / maxRequests) * 200;
                      return (
                        <circle 
                          key={i} 
                          cx={x} cy={y} r="3" 
                          fill="white" 
                          stroke="var(--color-pink)" 
                          strokeWidth="2"
                        >
                          <title>{`${d.period} - Requests: ${formatNumber(value(d.requests))}`}</title>
                        </circle>
                      );
                    })}
                  </>
                );
              })()}
            </svg>

            <div style={{ 
              display: 'flex', 
              justifyContent: 'space-between', 
              marginTop: '20px',
              borderTop: '1px solid #f1f5f9',
              paddingTop: '10px',
              paddingLeft: `${(paddingX / 1000) * 100}%`,
              paddingRight: `${(paddingX / 1000) * 100}%`
            }}>
              {data.map((d, i) => {
                if (data.length > 12 && i % Math.ceil(data.length / 12) !== 0 && i !== data.length - 1) {
                  return null;
                }
                const label = d.period.includes(':') 
                  ? d.period.split(' ')[1] 
                  : d.period.split('-').slice(1).join('/');
                return (
                  <div key={d.period} style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                    {label}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function App() {
  const [view, setView] = useState<'dashboard' | 'logs' | 'settings'>('dashboard')
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [summary, setSummary] = useState<UsageSummary[]>([])
  const [usageRows, setUsageRows] = useState<UsageRow[]>([])
  const [dailyUsage, setDailyUsage] = useState<DailyUsage[]>([])
  const [totalLogs, setTotalLogs] = useState(0)
  const [limit, setLimit] = useState(10)
  const [page, setPage] = useState(1)
  
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>(null)
  const [dateRange, setDateRange] = useState<DateRangeOption>('24h')
  const [customSince, setCustomSince] = useState('')
  const [customUntil, setCustomUntil] = useState('')
  
  const [configContent, setConfigContent] = useState('')
  const [configStatus, setConfigStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    async function loadData() {
      if (view === 'settings') {
        try {
          const response = await fetch('/config', { signal: controller.signal })
          if (response.ok) {
            const data = await response.json()
            setConfigContent(data.content)
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
          usageUrl.searchParams.set('model', activeFilter.model)
        }
        if (since) usageUrl.searchParams.set('since', since)
        if (until) usageUrl.searchParams.set('until', until)

        const summaryUrl = new URL('/usage/summary', window.location.origin)
        if (since) summaryUrl.searchParams.set('since', since)
        if (until) summaryUrl.searchParams.set('until', until)

        const countUrl = new URL('/usage/count', window.location.origin)
        if (activeFilter) {
          countUrl.searchParams.set('provider', activeFilter.provider)
          countUrl.searchParams.set('model', activeFilter.model)
        }
        if (since) countUrl.searchParams.set('since', since)
        if (until) countUrl.searchParams.set('until', until)

        const dailyUrl = new URL('/usage/daily', window.location.origin)
        if (activeFilter) {
          dailyUrl.searchParams.set('provider', activeFilter.provider)
          dailyUrl.searchParams.set('model', activeFilter.model)
        }
        if (since) dailyUrl.searchParams.set('since', since)
        if (until) dailyUrl.searchParams.set('until', until)
        dailyUrl.searchParams.set('tz_offset', getTimezoneOffset())
        if (dateRange === '5h' || dateRange === '24h') {
          dailyUrl.searchParams.set('granularity', 'hour')
        }

        const [summaryResponse, usageResponse, countResponse, dailyResponse] = await Promise.all([
          fetch(summaryUrl.toString(), { signal: controller.signal }),
          fetch(usageUrl.toString(), { signal: controller.signal }),
          fetch(countUrl.toString(), { signal: controller.signal }),
          fetch(dailyUrl.toString(), { signal: controller.signal }),
        ])

        if (!summaryResponse.ok || !usageResponse.ok || !countResponse.ok || !dailyResponse.ok) {
          throw new Error('Failed to fetch usage data')
        }

        const [summaryData, usageData, countData, dailyData] = (await Promise.all([
          summaryResponse.json(),
          usageResponse.json(),
          countResponse.json(),
          dailyResponse.json(),
        ])) as [UsageSummary[], UsageRow[], { total: number }, DailyUsage[]]

        setSummary(summaryData)
        setUsageRows(usageData)
        setTotalLogs(countData.total)
        setDailyUsage(dailyData)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(err instanceof Error ? err.message : 'Unknown error')
      }
    }

    void loadData()
    return () => controller.abort()
  }, [view, activeFilter, limit, page, dateRange, customSince, customUntil, refreshTrigger])

  // Reset page when filters change
  useEffect(() => {
    setPage(1)
  }, [activeFilter, dateRange, customSince, customUntil, limit])

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

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="icon">☁️</div>
          <span>llm-tracker</span>
        </div>
        <div className="sidebar-menu">
          <div className="menu-group">
            <div className="menu-title">Monitoring</div>
            <button className={`menu-item ${view === 'dashboard' ? 'active' : ''}`} onClick={() => setView('dashboard')}>
              <span>📊</span> Dashboard
            </button>
            <button className="menu-item">
              <span>📈</span> Analytics
            </button>
            <button className={`menu-item ${view === 'logs' ? 'active' : ''}`} onClick={() => setView('logs')}>
              <span>📜</span> Request Logs
            </button>
          </div>
          <div className="menu-group">
            <div className="menu-title">Management</div>
            <button className="menu-item">
              <span>🔑</span> API Keys
            </button>
            <button className={`menu-item ${view === 'settings' ? 'active' : ''}`} onClick={() => setView('settings')}>
              <span>⚙️</span> Settings
            </button>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="top-navbar">
          <div className="navbar-title">
            {view === 'dashboard' ? 'Dashboard' : view === 'logs' ? 'Request Logs' : 'Settings'}
          </div>
          <div className="navbar-right">
          </div>
        </header>

        <div className="content-body">
          {view === 'dashboard' && (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div className="welcome-msg">👋 Hello, ghbhanbo</div>
                <div style={{ display: 'flex', gap: '12px' }}>
                  <select 
                    className="input-plain"
                    value={dateRange}
                    onChange={(e) => setDateRange(e.target.value as DateRangeOption)}
                  >
                    <option value="5h">Last 5 Hours</option>
                    <option value="24h">Last 24 Hours</option>
                    <option value="7d">Last 7 Days</option>
                    <option value="30d">Last 30 Days</option>
                    <option value="custom">Custom Range</option>
                  </select>
                  <ModelSelector 
                    activeFilter={activeFilter}
                    summary={summary}
                    onChange={setActiveFilter}
                  />
                </div>
              </div>

              <div className="widgets-grid">
                <div className="widget">
                  <div className="widget-header"><span>📊</span> Token Usage</div>
                  <div className="widget-body">
                    <div className="icon-box icon-blue">🎟️</div>
                    <div className="stat-group">
                      <div className="stat-label">Total Volume</div>
                      <div className="stat-value">{formatCompact(totals.totalTokens)}</div>
                    </div>
                  </div>
                  <div style={{ marginTop: '12px', display: 'flex', gap: '16px' }}>
                    <div className="stat-group">
                      <div className="stat-label">Input</div>
                      <div style={{ fontSize: '14px', fontWeight: 700 }}>{formatCompact(totals.promptTokens)}</div>
                    </div>
                    <div className="stat-group">
                      <div className="stat-label">Cached</div>
                      <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--color-green)' }}>{formatCompact(totals.cachedTokens)}</div>
                    </div>
                    <div className="stat-group">
                      <div className="stat-label">Output</div>
                      <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--color-blue)' }}>{formatCompact(totals.completionTokens)}</div>
                    </div>
                  </div>
                </div>
                
                <div className="widget">
                  <div className="widget-header"><span>📈</span> Requests</div>
                  <div className="widget-body">
                    <div className="icon-box icon-green">🚀</div>
                    <div className="stat-group">
                      <div className="stat-label">Total Count</div>
                      <div className="stat-value">{formatNumber(totals.requests)}</div>
                    </div>
                  </div>
                  <div style={{ marginTop: '12px' }}>
                    <div className="stat-group">
                      <div className="stat-label">Throughput</div>
                      <div style={{ fontSize: '14px', fontWeight: 700 }}>{totals.requests > 0 ? (totals.requests / 1440).toFixed(2) : 0} req/min</div>
                    </div>
                  </div>
                </div>

                <div className="widget">
                  <div className="widget-header"><span>⚡</span> Performance</div>
                  <div className="widget-body">
                    <div className="icon-box icon-yellow">⏱️</div>
                    <div className="stat-group">
                      <div className="stat-label">Avg Latency</div>
                      <div className="stat-value">{formatLatency(totals.avgLatency)}</div>
                    </div>
                  </div>
                  <div style={{ marginTop: '12px' }}>
                    <div className="stat-group">
                      <div className="stat-label">Efficiency</div>
                      <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--color-green)' }}>
                        {totals.totalTokens > 0 ? ((value(totals.cachedTokens) / totals.totalTokens) * 100).toFixed(1) : 0}% cache rate
                      </div>
                    </div>
                  </div>
                </div>

                <div className="widget">
                  <div className="widget-header"><span>⏱️</span> Velocity</div>
                  <div className="widget-body">
                    <div className="icon-box icon-pink">🔄</div>
                    <div className="stat-group">
                      <div className="stat-label">Avg RPM</div>
                      <div className="stat-value">0.071</div>
                    </div>
                  </div>
                  <div style={{ marginTop: '12px' }}>
                    <div className="stat-group">
                      <div className="stat-label">Avg TPM</div>
                      <div style={{ fontSize: '14px', fontWeight: 700 }}>4143.06</div>
                    </div>
                  </div>
                </div>
              </div>

              <div style={{ marginTop: '24px' }}>
                <TrendChart 
                  data={dailyUsage}
                  title={`${(dateRange === '5h' || dateRange === '24h') ? 'Hourly' : 'Daily'} Usage Trend`}
                />
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
                    onChange={setActiveFilter}
                  />
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
                    style={{ 
                      padding: '8px 12px', 
                      background: '#fff', 
                      border: '1px solid var(--border-color)', 
                      borderRadius: '8px', 
                      fontSize: '12px', 
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px'
                    }}
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
                        <th style={{ width: '160px', padding: '12px 8px' }}>Model</th>
                        <th>Input</th>
                        <th>Output</th>
                        <th style={{ padding: '12px 8px' }}>
                          <div className="has-tooltip">
                            TTFT / Latency
                            <div className="tooltip-text">
                              <b>Claude Code:</b> No TTFT<br/>
                              <b>Gemini CLI:</b> Time to first chunk<br/>
                              <b>Codex:</b> Actual TTFT
                            </div>
                          </div>
                        </th>
                        <th style={{ width: '80px' }}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {usageRows.map(row => (
                        <tr key={row.id}>
                          <td style={{ color: '#64748b' }}>{formatTime(row.ts)}</td>
                          <td style={{ padding: '8px' }}>
                            <div style={{ 
                              padding: '4px 6px', 
                              borderRadius: '6px', 
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                              fontSize: '11px',
                              backgroundColor: getModelColor(row.model) + (row.model.toLowerCase().includes('gpt-5') || row.model.toLowerCase().includes('gpt-4') ? '80' : '26'),
                              color: getModelTextColor(row.model),
                              maxWidth: '140px'
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
                          <td style={{ verticalAlign: 'top' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                              <div style={{ color: 'var(--text-secondary)' }}>{formatNumber(row.prompt_tokens)}</div>
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
                                  background: '#f1f5f9', 
                                  borderRadius: '2px', 
                                  marginTop: '4px', 
                                  overflow: 'hidden',
                                  border: '1px solid #e2e8f0'
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
                                <div style={{ fontSize: '9px', color: '#64748b', fontWeight: 700 }}>
                                  Reasoning {formatNumber(row.reasoning_tokens)} ({Math.round((value(row.reasoning_tokens) / (value(row.completion_tokens) || 1)) * 100)}%)
                                </div>
                              )}
                            </div>
                            {value(row.reasoning_tokens) > 0 && (
                              <div 
                                style={{ 
                                  width: '100%', 
                                  height: '3px', 
                                  background: '#f1f5f9', 
                                  borderRadius: '2px', 
                                  marginTop: '4px', 
                                  overflow: 'hidden',
                                  border: '1px solid #e2e8f0',
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
                          <td style={{ padding: '8px' }}>
                            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                              {value(row.ttft_ms) > 0 && (
                                <div style={{ 
                                  backgroundColor: '#dcfce780', 
                                  color: '#15803d', 
                                  padding: '2px 12px', 
                                  borderRadius: '999px', 
                                  fontSize: '12px', 
                                  whiteSpace: 'nowrap'
                                }} title="Time To First Token">
                                  {formatLatency(row.ttft_ms)}
                                </div>
                              )}
                              <div style={{ 
                                backgroundColor: '#ffedd580', 
                                color: '#9a3412', 
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
                          <td colSpan={6} style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
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
                  background: '#f8fafc'
                }}>
                  <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                    Showing <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{Math.min(totalLogs, (page - 1) * limit + 1)}-{Math.min(totalLogs, page * limit)}</span> of <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{totalLogs}</span> logs
                  </div>
                  
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <button 
                      disabled={page === 1}
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                      style={{ 
                        padding: '6px 12px', 
                        background: '#fff', 
                        border: '1px solid var(--border-color)', 
                        borderRadius: '6px', 
                        fontSize: '12px',
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
                              background: page === pageNum ? 'var(--color-blue)' : '#fff',
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
                      style={{ 
                        padding: '6px 12px', 
                        background: '#fff', 
                        border: '1px solid var(--border-color)', 
                        borderRadius: '6px', 
                        fontSize: '12px',
                        cursor: (page === totalPages || totalPages === 0) ? 'not-allowed' : 'pointer',
                        opacity: (page === totalPages || totalPages === 0) ? 0.5 : 1
                      }}
                    >
                      Next ▶
                    </button>
                    
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
            <div className="settings-page">
              <div className="panel">
                <div className="panel-tabs">
                  <div className="tab active"><span>⚙️</span> Configuration (YAML)</div>
                </div>
                <div className="panel-body">
                  <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
                    Edit your proxy configuration directly. Changes require a server restart to take effect.
                  </p>
                  
                  <textarea
                    value={configContent}
                    onChange={(e) => setConfigContent(e.target.value)}
                    style={{
                      width: '100%',
                      height: '400px',
                      padding: '16px',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '13px',
                      border: '1px solid var(--border-color)',
                      borderRadius: '8px',
                      outline: 'none',
                      lineHeight: '1.6',
                      background: '#f8fafc'
                    }}
                    spellCheck={false}
                  />
                  
                  {error && view === 'settings' && (
                    <div style={{ 
                      marginTop: '16px', 
                      padding: '12px', 
                      background: '#fee2e2', 
                      color: '#b91c1c', 
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
                        cursor: configStatus === 'saving' ? 'not-allowed' : 'pointer'
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
