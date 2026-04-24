import { useEffect, useMemo, useState } from 'react'
import yaml from 'js-yaml'
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
  input_cost_usd: number | null
  output_cost_usd: number | null
  total_cost_usd: number | null
}

type UsageRow = {
  id: number
  ts: string
  provider: string
  model: string
  endpoint: string
  prompt_tokens: number | null
  prompt_length: number | null
  completion_tokens: number | null
  reasoning_tokens: number | null
  cached_tokens: number | null
  total_tokens: number | null
  latency_ms: number | null
  ttft_ms: number | null
  tool_tokens: number | null
  input_cost_usd: number | null
  output_cost_usd: number | null
  total_cost_usd: number | null
  status: number | null
}

type DailyUsage = {
  period: string
  requests: number
  prompt_tokens: number | null
  completion_tokens: number | null
  cached_tokens: number | null
  total_tokens: number | null
  input_cost_usd: number | null
  output_cost_usd: number | null
  total_cost_usd: number | null
}

type ActiveFilter = { provider: string; model: string } | null
type DateRangeOption = '5h' | '24h' | '7d' | '30d' | 'all' | 'custom'

const numberFormatter = new Intl.NumberFormat()
const compactFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 1,
  notation: 'compact',
})
const costFormatter = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 6,
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

function formatCost(input: number | null | undefined) {
  const v = value(input)
  if (v === 0) return '$0.00'
  return costFormatter.format(v)
}

function formatRate(input: number | null | undefined) {
  if (input === null || input === undefined) return ''
  return `$${input.toFixed(3)}/1M`
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
  if (option === 'custom' || option === 'all') return null
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

const PALETTE = [
  '#00b578', // Emerald/Teal
  '#3b82f6', // Blue
  '#f59e0b', // Amber
  '#06b6d4', // Cyan
  '#84cc16', // Lime
  '#f43f5e', // Rose
  '#8b5cf6', // Violet
  '#6366f1', // Indigo
  '#a855f7', // Purple
  '#ec4899', // Pink
];

const FIXED_PROVIDER_COLORS: Record<string, string> = {
  'anthropic': '#cc7c5e',
  'google': '#528af2',
  'openai': '#94a3b8', // Using the slate-ish gray for OpenAI/GPT
};

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

function getProviderColor(provider: string, providerColors: Record<string, string>): string {
  return providerColors[provider] || '#94a3b8';
}

function getModelIcon(model: string) {
  const m = model.toLowerCase()
  const style = { width: 14, height: 14, display: 'block', objectFit: 'contain' as const }
  if (m.includes('gpt') || m.includes('codex')) return <img src="/models/chatgpt.svg" alt="" style={style} />
  if (m.includes('claude')) return <img src="/models/claude-ai-icon.svg" alt="" style={style} />
  if (m.includes('gemini')) return <img src="/models/google-gemini-icon.svg" alt="" style={style} />
  if (m.includes('minimax') || m.includes('mimimax')) return <img src="/models/minimax-color.svg" alt="" style={style} />
  
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

function ModelTokenChart({ 
  summary, 
  title
}: { 
  summary: UsageSummary[], 
  title: string
}) {
  const [metric, setMetric] = useState<'tokens' | 'cost'>('tokens');

  const aggregated = useMemo(() => {
    const map = new Map<string, {
      model: string,
      provider: string,
      total_tokens: number,
      prompt_tokens: number,
      completion_tokens: number,
      cached_tokens: number,
      total_cost_usd: number
    }>();

    for (const s of summary) {
      const existing = map.get(s.model) || {
        model: s.model,
        provider: s.provider,
        total_tokens: 0,
        prompt_tokens: 0,
        completion_tokens: 0,
        cached_tokens: 0,
        total_cost_usd: 0
      };
      
      existing.total_tokens += value(s.total_tokens);
      existing.prompt_tokens += value(s.prompt_tokens);
      existing.completion_tokens += value(s.completion_tokens);
      existing.cached_tokens += value(s.cached_tokens);
      existing.total_cost_usd += value(s.total_cost_usd);
      
      map.set(s.model, existing);
    }
    
    return Array.from(map.values())
      .sort((a, b) => metric === 'tokens' ? b.total_tokens - a.total_tokens : b.total_cost_usd - a.total_cost_usd)
      .slice(0, 6);
  }, [summary, metric]);

  const maxValue = Math.max(...aggregated.map(s => metric === 'tokens' ? s.total_tokens : s.total_cost_usd), 1);
  
  return (
    <div className="widget" style={{ flex: 1 }}>
      <div className="widget-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>📊 {title}</span>
        <div className="tab-group" style={{ display: 'flex', background: '#f1f5f9', padding: '2px', borderRadius: '6px' }}>
          <button 
            onClick={() => setMetric('tokens')}
            style={{ 
              padding: '2px 8px', 
              fontSize: '10px', 
              borderRadius: '4px',
              fontWeight: 600,
              border: 'none',
              cursor: 'pointer',
              background: metric === 'tokens' ? 'white' : 'transparent',
              color: metric === 'tokens' ? 'var(--color-blue)' : '#64748b',
              boxShadow: metric === 'tokens' ? '0 1px 2px rgba(0,0,0,0.05)' : 'none'
            }}
          >Tokens</button>
          <button 
            onClick={() => setMetric('cost')}
            style={{ 
              padding: '2px 8px', 
              fontSize: '10px', 
              borderRadius: '4px',
              fontWeight: 600,
              border: 'none',
              cursor: 'pointer',
              background: metric === 'cost' ? 'white' : 'transparent',
              color: metric === 'cost' ? 'var(--color-blue)' : '#64748b',
              boxShadow: metric === 'cost' ? '0 1px 2px rgba(0,0,0,0.05)' : 'none'
            }}
          >Cost</button>
        </div>
      </div>
      <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {aggregated.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>No data available</div>
        ) : (
          aggregated.map(s => {
            const currentVal = metric === 'tokens' ? s.total_tokens : s.total_cost_usd;
            const percentage = (currentVal / maxValue) * 100;
            const mColor = getModelColor(s.model);
            
            return (
              <div key={s.model} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                    {getModelIcon(s.model)}
                    <span style={{ 
                      padding: '1px 6px', 
                      borderRadius: '4px', 
                      backgroundColor: mColor + (s.model.toLowerCase().includes('gpt-5') || s.model.toLowerCase().includes('gpt-4') ? '80' : '26'),
                      color: getModelTextColor(s.model),
                      fontSize: '11px'
                    }}>{s.model}</span>
                  </div>
                  <div style={{ color: 'var(--text-secondary)', fontWeight: 700 }}>
                    {metric === 'tokens' ? formatCompact(currentVal) : formatCost(currentVal)}
                  </div>
                </div>
                <div style={{ 
                  height: '8px', 
                  width: '100%', 
                  background: '#f1f5f9', 
                  borderRadius: '4px', 
                  overflow: 'hidden',
                  display: 'flex'
                }}>
                  <div 
                    style={{ width: `${percentage}%`, height: '100%', background: mColor }} 
                  />
                </div>
              </div>
            );
          })
        )}
      </div>
      {metric === 'tokens' && aggregated.length > 0 && (
        <div style={{ padding: '0 20px 20px', display: 'flex', gap: '12px', fontSize: '10px', color: 'var(--text-muted)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <div style={{ width: '8px', height: '8px', background: '#94a3b8', borderRadius: '2px' }} /> Input
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <div style={{ width: '8px', height: '8px', background: 'var(--color-green)', borderRadius: '2px' }} /> Cached
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <div style={{ width: '8px', height: '8px', background: 'var(--color-blue)', borderRadius: '2px' }} /> Output
          </div>
        </div>
      )}
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
  const [jumpPage, setJumpPage] = useState('')
  
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>(null)
  const [dateRange, setDateRange] = useState<DateRangeOption>('24h')
  const [customSince, setCustomSince] = useState('')
  const [customUntil, setCustomUntil] = useState('')
  
  const [configContent, setConfigContent] = useState('')
  const [configParsed, setConfigParsed] = useState<any>(null)
  const [selectedPricingProvider, setSelectedPricingProvider] = useState('global')
  const [configStatus, setConfigStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  
  const [error, setError] = useState<string | null>(null)

  const providerColors = useMemo(() => {
    const allProviders = Array.from(new Set(summary.map(s => s.provider))).sort();
    const map: Record<string, string> = {};
    
    // First, assign fixed colors
    allProviders.forEach(p => {
      const lowP = p.toLowerCase();
      if (FIXED_PROVIDER_COLORS[lowP]) {
        map[p] = FIXED_PROVIDER_COLORS[lowP];
      }
    });

    // Then, assign rotational colors to the rest
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
    const totalCost = data.reduce((sum, row) => sum + value(row.total_cost_usd), 0)
    const latencyWeight = data.reduce((sum, row) => sum + value(row.avg_latency_ms) * value(row.requests), 0)
    
    // Calculate Success Rate from usageRows
    const successfulRequests = usageRows.filter(r => r.status === 200 || r.status === null).length
    const successRate = usageRows.length > 0 ? (successfulRequests / usageRows.length) * 100 : 100

    // Calculate RPM/TPM based on dateRange
    let minutes = 1440; // Default 24h
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
  }, [activeFilter, summary, usageRows, dateRange])

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
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="icon">☁️</div>
          <span>llm-tracker</span>
        </div>
        <div className="sidebar-menu">
          <div className="menu-group">
            <div className="menu-title">Monitoring</div>
            <button className={`menu-item ${view === 'dashboard' ? 'active' : ''}`} onClick={() => setView('dashboard')}>
              📊 Dashboard
            </button>
            <button className={`menu-item ${view === 'logs' ? 'active' : ''}`} onClick={() => setView('logs')}>
              📜 Request Logs
            </button>
          </div>
          <div className="menu-group">
            <div className="menu-title">Management</div>
            <button className={`menu-item ${view === 'settings' ? 'active' : ''}`} onClick={() => setView('settings')}>
              ⚙️ Settings
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
                    <option value="all">All Time</option>
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
                  <div className="widget-body">
                    <div className="icon-box icon-yellow">🪙</div>
                    <div className="stat-group">
                      <div className="stat-label">Token Usage</div>
                      <div className="stat-value">{formatCompact(totals.totalTokens)}</div>
                      <div className="stat-label">
                        In: {formatCompact(totals.promptTokens)} / Out: {formatCompact(totals.completionTokens)}
                      </div>
                      <div className="stat-label" style={{ fontSize: '11px' }}>
                        Cached: {formatCompact(totals.cachedTokens)}
                        <span style={{ marginLeft: '6px', color: 'var(--color-green)', fontWeight: 600 }}>
                          ({totals.totalTokens > 0 ? ((value(totals.cachedTokens) / totals.totalTokens) * 100).toFixed(1) : 0}% Hit)
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
                
                <div className="widget">
                  <div className="widget-body">
                    <div className="icon-box icon-green">📈</div>
                    <div className="stat-group">
                      <div className="stat-label">Requests</div>
                      <div className="stat-value">{formatNumber(totals.requests)}</div>
                      <div className="stat-label">
                        Avg: <span style={{ color: 'var(--color-purple)', fontWeight: 600 }}>{formatCompact(totals.avgTokensPerRequest)} tokens/req</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="widget">
                  <div className="widget-body">
                    <div className="icon-box icon-green">💰</div>
                    <div className="stat-group">
                      <div className="stat-label">Estimated Cost</div>
                      <div className="stat-value">{formatCost(totals.totalCost)}</div>
                      <div className="stat-label">
                        Avg: <span style={{ color: 'var(--color-blue)', fontWeight: 600 }}>{formatCost(totals.requests > 0 ? totals.totalCost / totals.requests : 0)} / req</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="widget">
                  <div className="widget-body">
                    <div className="icon-box icon-blue">⚡</div>
                    <div className="stat-group">
                      <div className="stat-label">Performance</div>
                      <div className="stat-value">{totals.rpm.toFixed(3)} <span style={{ fontSize: '12px', fontWeight: 500 }}>RPM</span></div>
                      <div className="stat-label">
                        Avg Throughput: <span style={{ color: 'var(--color-purple)', fontWeight: 600 }}>{formatCompact(totals.tpm)} TPM</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="widget">
                  <div className="widget-body">
                    <div className="icon-box icon-pink">⏱️</div>
                    <div className="stat-group">
                      <div className="stat-label">Average Response</div>
                      <div className="stat-value">{formatLatency(totals.avgLatency)}</div>
                      <div className="stat-label">
                        Success Rate: <span style={{ color: 'var(--color-green)', fontWeight: 600 }}>{totals.successRate.toFixed(1)}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div style={{ marginTop: '24px', display: 'flex', gap: '24px', alignItems: 'stretch' }}>
                <div style={{ flex: 2 }}>
                  <TrendChart 
                    data={dailyUsage}
                    title={`${(dateRange === '5h' || dateRange === '24h') ? 'Hourly' : 'Daily'} Usage Trend`}
                  />
                </div>
                <div style={{ flex: 1, display: 'flex' }}>
                  <ModelTokenChart 
                    summary={summary}
                    title="Usage by Model"
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
                        <th style={{ width: '150px', padding: '12px 8px' }}>Model</th>
                        <th style={{ width: '120px', padding: '12px 8px' }}>Provider</th>
                        <th style={{ minWidth: '140px' }}>Input (Prompt)</th>
                        <th style={{ minWidth: '120px' }}>Output</th>
                        <th style={{ minWidth: '100px' }}>Cost</th>
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
                          <td style={{ verticalAlign: 'top' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                              <div style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>
                                {formatNumber(row.prompt_tokens)}
                                <span style={{ fontSize: '10px', fontWeight: 400, marginLeft: '4px', color: '#64748b' }}>tokens</span>
                                {value(row.prompt_length) > 0 && (
                                  <span style={{ fontSize: '10px', fontWeight: 400, marginLeft: '6px', color: '#94a3b8' }}>
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
                            <td style={{ fontSize: '12px', color: '#64748b', fontFamily: 'var(--font-mono)' }}>{conf.base_url}</td>
                            <td>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                                {models.map((m: string) => {
                                  const hasOverride = conf.models?.[m]?.cost !== undefined;
                                  return (
                                    <span key={m} style={{ 
                                      fontSize: '10px', 
                                      padding: '2px 6px', 
                                      background: hasOverride ? '#fffbeb' : '#f1f5f9', 
                                      borderRadius: '4px',
                                      color: hasOverride ? '#b45309' : '#475569',
                                      border: hasOverride ? '1px solid #fde68a' : '1px solid #e2e8f0',
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
                        background: '#f8fafc',
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
                            background: activeCost[field] === undefined && selectedPricingProvider !== 'global' ? 'transparent' : 'white',
                            borderBottom: '1px solid #e2e8f0',
                            fontSize: '13px',
                            color: activeCost[field] === undefined && selectedPricingProvider !== 'global' ? 'var(--text-muted)' : 'var(--text-primary)',
                            outline: 'none',
                            textAlign: 'left' as const
                          }
                        });

                        return (
                          <tr key={name} style={{ background: isOverridden ? '#fffbeb' : 'transparent' }}>
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
