import { useEffect, useMemo, useRef, useState } from 'react'
import yaml from 'js-yaml'
import './App.css'
import {
  getModelBadgeBackgroundColor,
  getModelColor,
  getModelTextColor,
} from './model-badge'

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
  successful_requests: number
  failed_requests: number
}

type ProviderUsage = {
  provider: string
  requests: number | null
  prompt_tokens: number | null
  completion_tokens: number | null
  reasoning_tokens: number | null
  cached_tokens: number | null
  total_tokens: number | null
  avg_latency_ms: number | null
  input_cost_usd: number | null
  output_cost_usd: number | null
  total_cost_usd: number | null
  successful_requests: number | null
  failed_requests: number | null
}

type SourceUsage = {
  client_source: string | null
  requests: number | null
  prompt_tokens: number | null
  completion_tokens: number | null
  reasoning_tokens: number | null
  cached_tokens: number | null
  total_tokens: number | null
  avg_latency_ms: number | null
  input_cost_usd: number | null
  output_cost_usd: number | null
  total_cost_usd: number | null
  successful_requests: number | null
  failed_requests: number | null
}

type UsageRow = {
  id: number
  ts: string
  provider: string
  model: string
  client_source: string | null
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

type ActiveFilter = { provider: string; model: string | null } | null
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
  if (m.includes('mimo') || m.includes('xiaomi')) return <img src="/models/xiaomi.svg" alt="" style={style} />

  return null
}

function ModelSelector({
  activeFilter,
  summary,
  providerColors,
  onChange
}: {
  activeFilter: ActiveFilter,
  summary: UsageSummary[],
  providerColors: Record<string, string>,
  onChange: (filter: ActiveFilter) => void
}) {
  const [isOpen, setIsOpen] = useState(false);

  // Group summary entries by provider
  const grouped = useMemo(() => {
    const map = new Map<string, UsageSummary[]>();
    for (const s of summary) {
      const arr = map.get(s.provider) ?? [];
      arr.push(s);
      map.set(s.provider, arr);
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [summary]);

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
            activeFilter.model ? (
              <>
                {getModelIcon(activeFilter.model)}
                <span style={{ fontSize: '13px' }}>{activeFilter.model}</span>
              </>
            ) : (
              <span style={{
                padding: '2px 8px',
                borderRadius: '4px',
                display: 'inline-flex',
                fontSize: '10px',
                backgroundColor: getProviderColor(activeFilter.provider, providerColors) + '22',
                color: getProviderColor(activeFilter.provider, providerColors),
                fontWeight: 600,
                border: `1px solid ${getProviderColor(activeFilter.provider, providerColors)}44`
              }}>
                {activeFilter.provider}
              </span>
            )
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
            minWidth: '240px',
            maxHeight: '360px',
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
            {grouped.map(([provider, models]) => (
              <div key={provider}>
                <button
                  onClick={() => { onChange({ provider, model: null }); setIsOpen(false); }}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    borderRadius: '6px',
                    background: activeFilter?.provider === provider && activeFilter.model === null ? '#f1f5f9' : 'transparent',
                    textAlign: 'left',
                    borderTop: '1px solid var(--border-color)',
                    marginTop: '4px',
                    paddingTop: '10px'
                  }}
                >
                  <span style={{
                    padding: '2px 8px',
                    borderRadius: '4px',
                    display: 'inline-flex',
                    fontSize: '10px',
                    backgroundColor: (getProviderColor(provider, providerColors)) + '22',
                    color: getProviderColor(provider, providerColors),
                    fontWeight: 600,
                    border: `1px solid ${getProviderColor(provider, providerColors)}44`
                  }}>
                    {provider}
                  </span>
                  <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 'auto', fontSize: '11px' }}>
                    {models.length} model{models.length > 1 ? 's' : ''}
                  </span>
                </button>
                {models.map(s => (
                  <button
                    key={`${s.provider}:${s.model}`}
                    onClick={() => { onChange({ provider: s.provider, model: s.model }); setIsOpen(false); }}
                    style={{
                      width: '100%',
                      padding: '6px 12px 6px 32px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      borderRadius: '6px',
                      background: activeFilter?.model === s.model ? '#f1f5f9' : 'transparent',
                      textAlign: 'left',
                      fontSize: '13px'
                    }}
                  >
                    {getModelIcon(s.model)}
                    <span>{s.model}</span>
                  </button>
                ))}
              </div>
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
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const maxTokens = Math.max(...data.map(x => value(x.total_tokens)), 1);
  const maxRequests = Math.max(...data.map(x => value(x.requests)), 1);
  const paddingX = 60; // Internal horizontal padding
  const chartWidth = 1000 - (paddingX * 2);

  const hoveredData = hoveredIdx !== null ? data[hoveredIdx] : null;
  const hCached = hoveredData ? value(hoveredData.cached_tokens) : 0;
  const hInput = hoveredData ? Math.max(0, value(hoveredData.prompt_tokens) - hCached) : 0;
  const hOutput = hoveredData ? value(hoveredData.completion_tokens) : 0;
  
  return (
    <div className="widget" style={{ minHeight: '400px', width: '100%', position: 'relative' }}>
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
            {hoveredIdx !== null && hoveredData && (
              <div style={{
                position: 'absolute',
                top: '-10px',
                left: `${(paddingX + (hoveredIdx / (Math.max(data.length - 1, 1))) * chartWidth) / 10}%`,
                transform: 'translateX(-50%)',
                backgroundColor: 'rgba(15, 23, 42, 0.95)',
                color: 'white',
                padding: '12px',
                borderRadius: '8px',
                fontSize: '12px',
                zIndex: 100,
                pointerEvents: 'none',
                boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
                minWidth: '200px',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                backdropFilter: 'blur(4px)'
              }}>
                <div style={{ fontWeight: 600, marginBottom: '8px', borderBottom: '1px solid rgba(255, 255, 255, 0.2)', paddingBottom: '4px', fontSize: '13px' }}>
                  {hoveredData.period}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '4px' }}>
                  <span style={{ color: '#94a3b8' }}>Input:</span>
                  <span style={{ fontWeight: 600 }}>{formatNumber(hInput)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--color-green)' }}>Cached:</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {value(hoveredData.prompt_tokens) > 0 && (
                      <span style={{ fontSize: '10px', color: 'var(--color-green)', opacity: 0.8 }}>
                        ({((hCached / value(hoveredData.prompt_tokens)) * 100).toFixed(1)}%)
                      </span>
                    )}
                    <span style={{ fontWeight: 600 }}>{formatNumber(hCached)}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--color-blue)' }}>Output:</span>
                  <span style={{ fontWeight: 600 }}>{formatNumber(hOutput)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginTop: '8px', paddingTop: '8px', borderTop: '1px solid rgba(255, 255, 255, 0.2)' }}>
                  <span style={{ fontWeight: 700 }}>Total Tokens:</span>
                  <span style={{ fontWeight: 800 }}>{formatNumber(value(hoveredData.total_tokens))}</span>
                </div>
                {hoveredData.total_cost_usd !== null && value(hoveredData.total_cost_usd) > 0 && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginTop: '4px' }}>
                    <span style={{ color: '#f472b6' }}>Est. Cost:</span>
                    <span style={{ fontWeight: 800, color: '#f472b6' }}>{formatCost(hoveredData.total_cost_usd)}</span>
                  </div>
                )}
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginTop: '4px' }}>
                  <span style={{ color: 'var(--color-pink)' }}>Requests:</span>
                  <span style={{ fontWeight: 600, color: 'var(--color-pink)' }}>{formatNumber(hoveredData.requests)}</span>
                </div>
              </div>
            )}

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
                const slotWidth = data.length > 1 ? chartWidth / (data.length - 1) : chartWidth;
                
                const cached = value(d.cached_tokens);
                const input = Math.max(0, value(d.prompt_tokens) - cached);
                const output = value(d.completion_tokens);
                
                const hInputRect = (input / maxTokens) * 200;
                const hCachedRect = (cached / maxTokens) * 200;
                const hOutputRect = (output / maxTokens) * 200;

                const isHovered = hoveredIdx === i;
                const isDimmed = hoveredIdx !== null && !isHovered;

                return (
                  <g 
                    key={i}
                    onMouseEnter={() => setHoveredIdx(i)}
                    onMouseLeave={() => setHoveredIdx(null)}
                  >
                    {/* Input */}
                    <rect 
                      x={x - barWidth/2} y={200 - hInputRect} 
                      width={barWidth} height={hInputRect} 
                      fill="#94a3b8" 
                      opacity={isDimmed ? 0.3 : 1}
                      style={{ transition: 'all 0.2s' }}
                    />
                    {/* Cached */}
                    <rect 
                      x={x - barWidth/2} y={200 - hInputRect - hCachedRect} 
                      width={barWidth} height={hCachedRect} 
                      fill="var(--color-green)" 
                      opacity={isDimmed ? 0.3 : 1}
                      style={{ transition: 'all 0.2s' }}
                    />
                    {/* Output */}
                    <rect 
                      x={x - barWidth/2} y={200 - hInputRect - hCachedRect - hOutputRect} 
                      width={barWidth} height={hOutputRect} 
                      fill="var(--color-blue)" 
                      opacity={isDimmed ? 0.3 : 1}
                      style={{ transition: 'all 0.2s' }}
                    />
                    
                    {/* Invisible overlay for easier hovering */}
                    <rect 
                      x={x - slotWidth/2} y={0} 
                      width={slotWidth} height={200} 
                      fill="transparent" 
                      style={{ cursor: 'pointer' }}
                    />
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
                      style={{ pointerEvents: 'none', opacity: hoveredIdx === null ? 1 : 0.4 }}
                    />
                    {data.map((d, i) => {
                      const x = paddingX + (i / (Math.max(data.length - 1, 1))) * chartWidth;
                      const y = 200 - (value(d.requests) / maxRequests) * 200;
                      return (
                        <circle 
                          key={i} 
                          cx={x} cy={y} r={hoveredIdx === i ? "5" : "3"} 
                          fill="white" 
                          stroke="var(--color-pink)" 
                          strokeWidth={hoveredIdx === i ? "3" : "2"}
                          style={{ pointerEvents: 'none', transition: 'all 0.2s', opacity: hoveredIdx === null || hoveredIdx === i ? 1 : 0.4 }}
                        />
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
                      backgroundColor: getModelBadgeBackgroundColor(s.model),
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

function getProviderIcon(provider: string) {
  const p = provider.toLowerCase()
  const style = { width: 14, height: 14, display: 'block', objectFit: 'contain' as const }
  if (p.includes('anthropic')) return <img src="/models/claude-ai-icon.svg" alt="" style={style} />
  if (p.includes('openai')) return <img src="/models/chatgpt.svg" alt="" style={style} />
  if (p.includes('google')) return <img src="/models/google-gemini-icon.svg" alt="" style={style} />
  if (p.includes('minimax')) return <img src="/models/minimax-color.svg" alt="" style={style} />
  if (p.includes('xiaomi')) return <img src="/models/xiaomi.svg" alt="" style={style} />
  return null
}

function ProviderTokenChart({
  data,
  title
}: {
  data: ProviderUsage[],
  title: string
}) {
  const [metric, setMetric] = useState<'tokens' | 'cost'>('tokens');

  const sorted = useMemo(() => {
    return [...data].sort((a, b) =>
      metric === 'tokens'
        ? (b.total_tokens ?? 0) - (a.total_tokens ?? 0)
        : (b.total_cost_usd ?? 0) - (a.total_cost_usd ?? 0)
    );
  }, [data, metric]);

  const maxValue = Math.max(
    ...sorted.map(s => metric === 'tokens' ? (s.total_tokens ?? 0) : (s.total_cost_usd ?? 0)),
    1
  );

  const providerColors: Record<string, string> = {
    'anthropic': '#cc7c5e',
    'google': '#528af2',
    'openai': '#94a3b8',
  };

  return (
    <div className="widget" style={{ flex: 1 }}>
      <div className="widget-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>🏢 {title}</span>
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
        {sorted.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>No data available</div>
        ) : (
          sorted.map((s, index) => {
            const currentVal = metric === 'tokens' ? (s.total_tokens ?? 0) : (s.total_cost_usd ?? 0);
            const percentage = (currentVal / maxValue) * 100;
            const name = s.provider;
            const color = providerColors[name.toLowerCase()] || PALETTE[index % PALETTE.length];

            return (
              <div key={`${name}-${index}`} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                    {getProviderIcon(name)}
                    <span style={{
                      padding: '1px 6px',
                      borderRadius: '4px',
                      backgroundColor: '#f1f5f9',
                      color: '#475569',
                      fontSize: '11px',
                      fontWeight: 600,
                      border: '1px solid #e2e8f0'
                    }}>{name}</span>
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
                    style={{ width: `${percentage}%`, height: '100%', background: color }}
                  />
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function SourceTokenChart({
  data,
  title
}: {
  data: SourceUsage[],
  title: string
}) {
  const [metric, setMetric] = useState<'tokens' | 'cost'>('tokens');

  const sorted = useMemo(() => {
    return [...data].sort((a, b) =>
      metric === 'tokens'
        ? (b.total_tokens ?? 0) - (a.total_tokens ?? 0)
        : (b.total_cost_usd ?? 0) - (a.total_cost_usd ?? 0)
    );
  }, [data, metric]);

  const maxValue = Math.max(
    ...sorted.map(s => metric === 'tokens' ? (s.total_tokens ?? 0) : (s.total_cost_usd ?? 0)),
    1
  );

  const sourceColors: Record<string, string> = {
    'claude-code': '#d97706',
    'codex': '#10b981',
    'gemini-cli': '#3b82f6',
    'proxy': '#8b5cf6',
  };

  return (
    <div className="widget" style={{ flex: 1 }}>
      <div className="widget-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>📡 {title}</span>
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
        {sorted.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>No data available</div>
        ) : (
          sorted.map((s, index) => {
            const currentVal = metric === 'tokens' ? (s.total_tokens ?? 0) : (s.total_cost_usd ?? 0);
            const percentage = (currentVal / maxValue) * 100;
            const name = s.client_source || 'unknown';
            const color = sourceColors[name] || '#94a3b8';

            return (
              <div key={`${name}-${index}`} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
                  <span style={{
                    padding: '1px 6px',
                    borderRadius: '4px',
                    backgroundColor: '#f1f5f9',
                    color: '#475569',
                    fontSize: '11px',
                    fontWeight: 600,
                    border: '1px solid #e2e8f0'
                  }}>{name}</span>
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
                    style={{ width: `${percentage}%`, height: '100%', background: color }}
                  />
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function UsageHeatmap({
  activeFilter,
  activeSource,
}: {
  activeFilter: ActiveFilter
  activeSource: string | null
}) {
  const [hoveredCell, setHoveredCell] = useState<{ date: string; data: DailyUsage | null; x: number; y: number } | null>(null)
  const [heatmapData, setHeatmapData] = useState<DailyUsage[]>([])
  const [containerWidth, setContainerWidth] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width)
      }
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const until = new Date().toISOString()
    const since = new Date(Date.now() - 730 * 24 * 60 * 60 * 1000).toISOString()
    const url = new URL('/usage/daily', window.location.origin)
    url.searchParams.set('since', since)
    url.searchParams.set('until', until)
    url.searchParams.set('granularity', 'day')
    url.searchParams.set('tz_offset', getTimezoneOffset())
    if (activeFilter) {
      url.searchParams.set('provider', activeFilter.provider)
      if (activeFilter.model) url.searchParams.set('model', activeFilter.model)
    }
    if (activeSource) url.searchParams.set('client_source', activeSource)
    fetch(url.toString(), { signal: controller.signal })
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then((data: DailyUsage[]) => setHeatmapData(data))
      .catch(() => {})
    return () => controller.abort()
  }, [activeFilter, activeSource])

  const allWeeks = useMemo(() => {
    const dataMap = new Map<string, DailyUsage>()
    for (const d of heatmapData) dataMap.set(d.period, d)

    const today = new Date()
    const endDate = new Date(today.getFullYear(), today.getMonth(), today.getDate())
    const startDate = new Date(endDate)
    startDate.setDate(startDate.getDate() - 728)
    while (startDate.getDay() !== 0) startDate.setDate(startDate.getDate() - 1)

    let max = 0
    const weeks: { date: Date; tokens: number; data: DailyUsage | null }[][] = []
    const cursor = new Date(startDate)

    while (cursor <= endDate) {
      const week: { date: Date; tokens: number; data: DailyUsage | null }[] = []
      for (let d = 0; d < 7; d++) {
        if (cursor > endDate) {
          week.push({ date: new Date(cursor), tokens: -1, data: null })
        } else {
          const key = cursor.toISOString().split('T')[0]
          const dayData = dataMap.get(key) ?? null
          const tokens = dayData ? value(dayData.total_tokens) : 0
          if (tokens > max) max = tokens
          week.push({ date: new Date(cursor), tokens, data: dayData })
        }
        cursor.setDate(cursor.getDate() + 1)
      }
      weeks.push(week)
    }
    return { weeks, maxTokens: max }
  }, [heatmapData])

  const cellSize = 13
  const gap = 3
  const leftPad = 36
  const topPad = 20
  const step = cellSize + gap

  const visibleCount = Math.max(1, Math.min(allWeeks.weeks.length, Math.floor((containerWidth - leftPad - 8) / step)))
  const visibleWeeks = allWeeks.weeks.slice(-visibleCount)

  const monthLabels = useMemo(() => {
    const labels: { label: string; col: number }[] = []
    let lastMonth = -1
    for (let wi = 0; wi < visibleWeeks.length; wi++) {
      const firstDay = visibleWeeks[wi][0]
      if (firstDay && firstDay.tokens >= 0 && firstDay.date.getMonth() !== lastMonth) {
        labels.push({ label: firstDay.date.toLocaleString(undefined, { month: 'short' }), col: wi })
        lastMonth = firstDay.date.getMonth()
      }
    }
    return labels
  }, [visibleWeeks])

  function getColor(tokens: number): string {
    if (tokens < 0) return 'transparent'
    if (tokens === 0) return '#ebedf0'
    const ratio = Math.min(tokens / (allWeeks.maxTokens || 1), 1)
    if (ratio < 0.25) return '#9be9a8'
    if (ratio < 0.5) return '#40c463'
    if (ratio < 0.75) return '#30a14e'
    return '#00b578'
  }

  const gridWidth = visibleWeeks.length * step
  const gridHeight = 7 * step

  return (
    <div ref={containerRef} className="widget" style={{ width: '100%', position: 'relative', overflow: 'visible' }}>
      <div className="widget-header">
        <span>🗓 Daily Activity</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginLeft: 'auto', fontSize: '10px', color: 'var(--text-muted)' }}>
          <span>Less</span>
          {['#ebedf0', '#9be9a8', '#40c463', '#30a14e', '#00b578'].map(c => (
            <div key={c} style={{ width: '11px', height: '11px', borderRadius: '2px', background: c, border: '1px solid rgba(0,0,0,0.06)' }} />
          ))}
          <span>More</span>
        </div>
      </div>
      <div style={{ padding: '8px 0 12px' }}>
        <svg width={leftPad + gridWidth + 8} height={topPad + gridHeight + 4} style={{ display: 'block' }}>
          {monthLabels.map((m, i) => (
            <text key={i} x={leftPad + m.col * step} y={14} fontSize={10} fill="#94a3b8" fontWeight={500}>
              {m.label}
            </text>
          ))}
          {[1, 3, 5].map(d => (
            <text key={d} x={0} y={topPad + d * step + cellSize - 2} fontSize={10} fill="#94a3b8" fontWeight={500}>
              {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d]}
            </text>
          ))}
          {visibleWeeks.map((week, wi) =>
            week.map((day, di) => {
              const x = leftPad + wi * step
              const y = topPad + di * step
              const isFuture = day.tokens < 0
              return (
                <rect
                  key={`${wi}-${di}`}
                  x={x}
                  y={y}
                  width={cellSize}
                  height={cellSize}
                  rx={2}
                  ry={2}
                  fill={isFuture ? 'transparent' : getColor(day.tokens)}
                  stroke={hoveredCell?.date === day.date.toISOString().split('T')[0] ? '#1e293b' : 'rgba(0,0,0,0.06)'}
                  strokeWidth={hoveredCell?.date === day.date.toISOString().split('T')[0] ? 2 : 1}
                  style={{ cursor: isFuture ? 'default' : 'pointer', transition: 'stroke 0.1s' }}
                  onMouseEnter={(e) => {
                    if (isFuture) return
                    const rect = e.currentTarget.getBoundingClientRect()
                    const parent = e.currentTarget.closest('svg')!.getBoundingClientRect()
                    setHoveredCell({
                      date: day.date.toISOString().split('T')[0],
                      data: day.data,
                      x: rect.left - parent.left + cellSize / 2,
                      y: rect.top - parent.top,
                    })
                  }}
                  onMouseLeave={() => setHoveredCell(null)}
                />
              )
            })
          )}
        </svg>
        {hoveredCell && (() => {
          const d = hoveredCell.data
          const hCached = d ? value(d.cached_tokens) : 0
          const hInput = d ? Math.max(0, value(d.prompt_tokens) - hCached) : 0
          const hOutput = d ? value(d.completion_tokens) : 0
          const total = d ? value(d.total_tokens) : 0
          const requests = d ? value(d.requests) : 0
          const cost = d ? value(d.total_cost_usd) : 0
          const dateObj = new Date(hoveredCell.date + 'T12:00:00')
          const dateLabel = dateObj.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
          return (
            <div style={{
              position: 'absolute',
              left: hoveredCell.x,
              top: hoveredCell.y - 8,
              transform: 'translate(-50%, -100%)',
              backgroundColor: 'rgba(15, 23, 42, 0.95)',
              color: 'white',
              padding: '10px 14px',
              borderRadius: '8px',
              fontSize: '12px',
              zIndex: 200,
              pointerEvents: 'none',
              boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)',
              minWidth: '180px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              whiteSpace: 'nowrap',
            }}>
              <div style={{ fontWeight: 600, marginBottom: '6px', borderBottom: '1px solid rgba(255,255,255,0.2)', paddingBottom: '4px' }}>
                {dateLabel}
              </div>
              {total === 0 ? (
                <div style={{ color: '#94a3b8' }}>No activity</div>
              ) : (
                <>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', marginBottom: '3px' }}>
                    <span style={{ color: '#94a3b8' }}>Input:</span>
                    <span style={{ fontWeight: 600 }}>{formatNumber(hInput)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', marginBottom: '3px' }}>
                    <span style={{ color: '#40c463' }}>Cached:</span>
                    <span style={{ fontWeight: 600 }}>{formatNumber(hCached)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', marginBottom: '3px' }}>
                    <span style={{ color: '#3b82f6' }}>Output:</span>
                    <span style={{ fontWeight: 600 }}>{formatNumber(hOutput)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', marginTop: '6px', paddingTop: '6px', borderTop: '1px solid rgba(255,255,255,0.2)' }}>
                    <span style={{ fontWeight: 700 }}>Total:</span>
                    <span style={{ fontWeight: 800 }}>{formatNumber(total)}</span>
                  </div>
                  {cost > 0 && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', marginTop: '3px' }}>
                      <span style={{ color: '#f472b6' }}>Cost:</span>
                      <span style={{ fontWeight: 800, color: '#f472b6' }}>{formatCost(cost)}</span>
                    </div>
                  )}
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', marginTop: '3px' }}>
                    <span style={{ color: '#f43f5e' }}>Requests:</span>
                    <span style={{ fontWeight: 600, color: '#f43f5e' }}>{formatNumber(requests)}</span>
                  </div>
                </>
              )}
            </div>
          )
        })()}
      </div>
    </div>
  )
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

  // Fetch available sources for the time window (independent of activeSource)
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

  // Reset page when filters change
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

              <UsageHeatmap activeFilter={activeFilter} activeSource={activeSource} />

              <TrendChart
                data={dailyUsage}
                title={`${(dateRange === '5h' || dateRange === '24h') ? 'Hourly' : 'Daily'} Usage Trend`}
              />

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
                          <td style={{ color: '#64748b' }}>{formatTime(row.ts)}</td>
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
                              backgroundColor: '#f1f5f9',
                              color: '#475569',
                              width: 'fit-content',
                              border: '1px solid #e2e8f0',
                              fontWeight: 600
                            }}>
                              {row.client_source || '—'}
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
