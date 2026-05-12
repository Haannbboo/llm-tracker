import type { DateRangeOption, DailyUsage } from './types'
import { getTheme, type Theme } from './theme'

export const numberFormatter = new Intl.NumberFormat()
export const compactFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 1,
  notation: 'compact',
})
const costFormatters = new Map<number, Intl.NumberFormat>()
function getCostFormatter(maxDigits: number) {
  let fmt = costFormatters.get(maxDigits)
  if (!fmt) {
    fmt = new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: maxDigits,
    })
    costFormatters.set(maxDigits, fmt)
  }
  return fmt
}

export function value(input: number | null | undefined) {
  return input ?? 0
}

export function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function formatNumber(input: number | null | undefined) {
  return numberFormatter.format(value(input))
}

export function formatCompact(input: number | null | undefined) {
  return compactFormatter.format(value(input))
}

export function formatCost(input: number | null | undefined, maxDigits = 6) {
  const v = value(input)
  if (v === 0) return '$0.00'
  if (Math.abs(v) < 0.01) return `$${v.toFixed(Math.min(4, maxDigits))}`
  if (Math.abs(v) < 0.1) return `$${v.toFixed(Math.min(3, maxDigits))}`
  return getCostFormatter(maxDigits).format(v)
}

export function formatRate(input: number | null | undefined) {
  if (input === null || input === undefined) return ''
  return `$${input.toFixed(3)}/1M`
}

export function formatLatency(input: number | null | undefined) {
  const latency = value(input)
  return latency >= 1000 ? `${(latency / 1000).toFixed(2)}s` : `${Math.round(latency)}ms`
}

type DurationFormatOptions = {
  secondsFractionDigits?: number
}

function formatDurationSeconds(seconds: number, options: DurationFormatOptions): string {
  if (options.secondsFractionDigits === undefined) return `${seconds}s`
  return `${seconds.toFixed(options.secondsFractionDigits)}s`
}

export function formatDuration(seconds: number | null | undefined, options: DurationFormatOptions = {}): string {
  const s = value(seconds)
  if (s < 60) return formatDurationSeconds(s, options)
  const m = Math.floor(s / 60)
  const rem = s % 60
  if (m < 60) return rem > 0 ? `${m}m ${formatDurationSeconds(rem, options)}` : `${m}m`
  const h = Math.floor(m / 60)
  const remM = m % 60
  return remM > 0 ? `${h}h ${remM}m` : `${h}h`
}

export function formatThroughput(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return `${val.toFixed(1)} t/s`
}

export function formatTime(input: string) {
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

export function getSinceDate(option: DateRangeOption): string | null {
  if (option === 'custom' || option === 'all') return null
  const now = new Date()
  if (option === '24h') now.setHours(now.getHours() - 24)
  else if (option === '7d') now.setDate(now.getDate() - 7)
  else if (option === '30d') now.setDate(now.getDate() - 30)
  return now.toISOString()
}

export function fillGaps(data: DailyUsage[], granularity: 'hour' | 'day', periodCount: number): DailyUsage[] {
  const zeroRow = (period: string): DailyUsage => ({
    period, requests: 0, prompt_tokens: 0, completion_tokens: 0,
    cached_tokens: 0, total_tokens: 0, input_cost_usd: 0,
    output_cost_usd: 0, total_cost_usd: 0, avg_latency_ms: 0,
    latency_sum_ms: 0,
    avg_throughput: 0,
    successful_requests: 0, failed_requests: 0,
    status_429: 0, status_4xx: 0, status_5xx: 0, status_unknown: 0,
  })

  const map = new Map(data.map(d => [d.period, d]))
  const result: DailyUsage[] = []
  const now = new Date()

  if (granularity === 'hour') {
    const start = new Date(now)
    start.setMinutes(0, 0, 0)
    start.setHours(start.getHours() - (periodCount - 1))
    for (let i = 0; i < periodCount; i++) {
      const d = new Date(start)
      d.setHours(d.getHours() + i)
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:00`
      result.push(map.get(key) ?? zeroRow(key))
    }
  } else {
    const start = new Date(now)
    start.setHours(0, 0, 0, 0)
    start.setDate(start.getDate() - (periodCount - 1))
    for (let i = 0; i < periodCount; i++) {
      const d = new Date(start)
      d.setDate(d.getDate() + i)
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      result.push(map.get(key) ?? zeroRow(key))
    }
  }

  return result
}

export function getTimezoneOffset(): string {
  const offset = -new Date().getTimezoneOffset();
  const absOffset = Math.abs(offset);
  const hours = Math.floor(absOffset / 60);
  const mins = absOffset % 60;
  const sign = offset >= 0 ? '+' : '-';
  return `${sign}${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`;
}

export const PALETTE = [
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

export const FIXED_PROVIDER_COLORS: Record<string, string> = {
  'anthropic': '#cc7c5e',
  'google': '#528af2',
  'openai': '#94a3b8',
  'openrouter': '#6366f1',
};

export function getProviderColor(provider: string, providerColors: Record<string, string>): string {
  return providerColors[provider] || '#94a3b8';
}

export function getModelIcon(model: string, theme: Theme = getTheme()) {
  const m = model.toLowerCase()
  const style = { width: 14, height: 14, display: 'block', objectFit: 'contain' as const }
  const dark = theme === 'dark'
  if (m.startsWith('tencent/') || m.startsWith('hy3')) return <img src="/models/hunyuan-color.svg" alt="" style={style} />
  if (m.includes('gpt') || m.includes('codex')) return <img src={dark ? '/models/chatgpt-dark.png' : '/models/chatgpt.svg'} alt="" style={style} />
  if (m.includes('claude')) return <img src="/models/claude-ai-icon.svg" alt="" style={style} />
  if (m.includes('gemini')) return <img src="/models/google-gemini-icon.svg" alt="" style={style} />
  if (m.includes('minimax') || m.includes('mimimax')) return <img src="/models/minimax-color.svg" alt="" style={style} />
  if (m.includes('mimo') || m.includes('xiaomi')) return <img src="/models/xiaomi.svg" alt="" style={style} />
  if (m.includes('inclusionai')) return <img src="/models/inclusionai.png" alt="" style={style} />
  if (m.includes('openrouter')) return <img src={dark ? '/models/openrouter-dark.svg' : '/models/openrouter.svg'} alt="" style={style} />
  return null
}

export function getProviderBadgeColor(provider: string): string {
  const p = provider.toLowerCase()
  if (p.startsWith('tencent/')) return '#0052D9'
  if (p.includes('anthropic')) return '#cc7c5e'
  if (p.includes('google')) return '#528af2'
  if (p.includes('openai')) return '#dcdcdc'
  if (p.includes('minimax')) return '#ec6b53'
  if (p.includes('xiaomi')) return '#dcc496'
  if (p.includes('openrouter')) return '#6366f1'
  return '#f1f5f9'
}

export function getProviderBadgeBg(provider: string, theme: Theme = getTheme()): string {
  const base = getProviderBadgeColor(provider)
  const dark = theme === 'dark'
  const p = provider.toLowerCase()
  if (p.startsWith('tencent/')) return dark ? '#0052D980' : '#0052D926'
  if (p.includes('openai') || p.includes('xiaomi')) return dark ? `${base}90` : `${base}80`
  if (p.includes('anthropic') || p.includes('google') || p.includes('minimax') || p.includes('openrouter')) return dark ? `${base}40` : `${base}26`
  return dark ? '#334155' : '#f1f5f9'
}

export function getProviderBadgeText(provider: string, theme: Theme = getTheme()): string {
  const dark = theme === 'dark'
  const p = provider.toLowerCase()
  if (p.startsWith('tencent/')) return dark ? '#d0dff5' : '#003a8c'
  if (p.includes('openai')) return dark ? '#94a3b8' : '#475569'
  if (p.includes('xiaomi')) return dark ? '#dcc496' : '#6b4f2a'
  if (p.includes('openrouter')) return dark ? '#a5b4fc' : '#6366f1'
  if (p.includes('anthropic') || p.includes('google') || p.includes('minimax')) return getProviderBadgeColor(provider)
  return dark ? '#94a3b8' : '#475569'
}

export function getProviderIcon(provider: string, theme: Theme = getTheme()) {
  const p = provider.toLowerCase()
  const style = { width: 14, height: 14, display: 'block', objectFit: 'contain' as const }
  const dark = theme === 'dark'
  if (p.startsWith('tencent/')) return <img src="/models/hunyuan-color.svg" alt="" style={style} />
  if (p.includes('anthropic')) return <img src="/models/claude-ai-icon.svg" alt="" style={style} />
  if (p.includes('openai')) return <img src={dark ? '/models/chatgpt-dark.png' : '/models/chatgpt.svg'} alt="" style={style} />
  if (p.includes('google')) return <img src="/models/google-gemini-icon.svg" alt="" style={style} />
  if (p.includes('minimax')) return <img src="/models/minimax-color.svg" alt="" style={style} />
  if (p.includes('xiaomi')) return <img src="/models/xiaomi.svg" alt="" style={style} />
  if (p.includes('openrouter')) return <img src={dark ? '/models/openrouter-dark.svg' : '/models/openrouter.svg'} alt="" style={style} />
  if (p.includes('inclusionai')) return <img src="/models/inclusionai.png" alt="" style={style} />
  return null
}

export function getSourceBadgeBg(name: string): string {
  const dark = getTheme() === 'dark'
  if (name === 'codex') return dark ? '#dcdcdc90' : '#dcdcdc80'
  if (name === 'claude-code') return dark ? '#cc7c5e40' : '#cc7c5e26'
  if (name === 'gemini-cli') return dark ? '#528af240' : '#528af226'
  if (name === 'proxy') return dark ? '#8b5cf640' : '#8b5cf626'
  return dark ? '#334155' : '#f1f5f9'
}

export function getSourceBadgeText(name: string): string {
  const dark = getTheme() === 'dark'
  if (name === 'codex') return dark ? '#0f172a' : '#475569'
  if (name === 'claude-code') return '#cc7c5e'
  if (name === 'gemini-cli') return '#528af2'
  if (name === 'proxy') return '#8b5cf6'
  return dark ? '#94a3b8' : '#475569'
}

export function shortSessionId(id: string) {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id
}

export function sessionAgentName(source: string | null | undefined) {
  const raw = source || 'unknown'
  return raw
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ') || 'Unknown'
}

export function sessionDisplayName(session: { client_source: string }) {
  return `${sessionAgentName(session.client_source)} session`
}

export type SessionInsight = {
  key: string
  title: string
  session: import('./types').SessionSummary
  value: string
  detail: string
  tone?: 'warning' | 'danger' | 'success'
  onlyFailed?: boolean
}

export function buildSessionInsights(sessions: import('./types').SessionSummary[]): SessionInsight[] {
  if (sessions.length === 0) return []

  const insightSessions = [...sessions]
  const mostExpensive = [...insightSessions].sort((a, b) => b.total_cost_usd - a.total_cost_usd)[0]
  const slowest = [...insightSessions].sort((a, b) => b.avg_latency_ms - a.avg_latency_ms)[0]
  const tokenBurner = [...insightSessions].sort((a, b) => b.total_tokens - a.total_tokens)[0]
  const cacheSaver = [...insightSessions].filter(session => session.cached_tokens > 0).sort((a, b) => b.cached_tokens - a.cached_tokens)[0]
  const reliabilityWatch = [...insightSessions].filter(session => session.failed_requests > 0).sort((a, b) => b.failed_requests - a.failed_requests)[0]

  const insights: SessionInsight[] = []

  if (mostExpensive && mostExpensive.total_cost_usd > 0) {
    insights.push({
      key: 'most-expensive',
      title: 'Most Expensive Session',
      session: mostExpensive,
      value: formatCost(mostExpensive.total_cost_usd),
      detail: `${formatNumber(mostExpensive.request_count)} requests · ${formatCompact(mostExpensive.total_tokens)} tokens`,
    })
  }

  if (slowest && slowest.avg_latency_ms > 0) {
    insights.push({
      key: 'slowest',
      title: 'Slowest Session',
      session: slowest,
      value: formatLatency(slowest.avg_latency_ms),
      detail: `${formatNumber(slowest.request_count)} requests · ${formatDuration(slowest.duration_s)}`,
      tone: slowest.avg_latency_ms >= 5000 ? 'warning' : undefined,
    })
  }

  if (tokenBurner && tokenBurner.total_tokens > 0) {
    insights.push({
      key: 'token-burner',
      title: 'Biggest Token Burner',
      session: tokenBurner,
      value: formatCompact(tokenBurner.total_tokens),
      detail: `${formatCompact(tokenBurner.prompt_tokens)} in · ${formatCompact(tokenBurner.completion_tokens)} out`,
    })
  }

  if (cacheSaver) {
    insights.push({
      key: 'cache-saver',
      title: 'Best Cache Saver',
      session: cacheSaver,
      value: formatCompact(cacheSaver.cached_tokens),
      detail: `${cacheSaver.prompt_tokens > 0 ? Math.round((cacheSaver.cached_tokens / cacheSaver.prompt_tokens) * 100) : 0}% cache hit estimate`,
      tone: 'success',
    })
  }

  if (reliabilityWatch) {
    insights.push({
      key: 'reliability-watch',
      title: 'Reliability Watch',
      session: reliabilityWatch,
      value: `${formatNumber(reliabilityWatch.failed_requests)} failed`,
      detail: `${reliabilityWatch.request_count > 0 ? Math.round((reliabilityWatch.successful_requests / reliabilityWatch.request_count) * 100) : 0}% success rate`,
      tone: 'danger',
      onlyFailed: true,
    })
  }

  return insights
}

export function getAgentDisplayName(name: string) {
  const normalized = name.toLowerCase()
  if (normalized.includes('vectorengine') || normalized.includes('claude')) return 'Claude Code'
  if (normalized.includes('codesonline') || normalized.includes('codex')) return 'Codex'
  if (normalized.includes('gemini')) return 'Gemini CLI'
  return name
}

export function getSetupAgentKey(name: string) {
  const normalized = name.toLowerCase()
  if (normalized.includes('vectorengine') || normalized.includes('claude')) return 'claude'
  if (normalized.includes('codesonline') || normalized.includes('codex')) return 'codex'
  if (normalized.includes('gemini')) return 'gemini'
  return normalized
}
