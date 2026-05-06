import type { DateRangeOption, DailyUsage } from './types'
import { getTheme } from './theme'

export const numberFormatter = new Intl.NumberFormat()
export const compactFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 1,
  notation: 'compact',
})
export const costFormatter = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})

export function value(input: number | null | undefined) {
  return input ?? 0
}

export function formatNumber(input: number | null | undefined) {
  return numberFormatter.format(value(input))
}

export function formatCompact(input: number | null | undefined) {
  return compactFormatter.format(value(input))
}

export function formatCost(input: number | null | undefined) {
  const v = value(input)
  if (v === 0) return '$0.00'
  return costFormatter.format(v)
}

export function formatRate(input: number | null | undefined) {
  if (input === null || input === undefined) return ''
  return `$${input.toFixed(3)}/1M`
}

export function formatLatency(input: number | null | undefined) {
  const latency = value(input)
  return latency >= 1000 ? `${(latency / 1000).toFixed(2)}s` : `${Math.round(latency)}ms`
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
    successful_requests: 0, failed_requests: 0,
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
};

export function getProviderColor(provider: string, providerColors: Record<string, string>): string {
  return providerColors[provider] || '#94a3b8';
}

export function getModelIcon(model: string) {
  const m = model.toLowerCase()
  const style = { width: 14, height: 14, display: 'block', objectFit: 'contain' as const }
  if (m.includes('gpt') || m.includes('codex')) return <img src="/models/chatgpt.svg" alt="" style={style} />
  if (m.includes('claude')) return <img src="/models/claude-ai-icon.svg" alt="" style={style} />
  if (m.includes('gemini')) return <img src="/models/google-gemini-icon.svg" alt="" style={style} />
  if (m.includes('minimax') || m.includes('mimimax')) return <img src="/models/minimax-color.svg" alt="" style={style} />
  if (m.includes('mimo') || m.includes('xiaomi')) return <img src="/models/xiaomi.svg" alt="" style={style} />
  return null
}

export function getProviderBadgeColor(provider: string): string {
  const p = provider.toLowerCase()
  if (p.includes('anthropic')) return '#cc7c5e'
  if (p.includes('google')) return '#528af2'
  if (p.includes('openai')) return '#dcdcdc'
  if (p.includes('minimax')) return '#ec6b53'
  if (p.includes('xiaomi')) return '#dcc496'
  return '#f1f5f9'
}

export function getProviderBadgeBg(provider: string): string {
  const base = getProviderBadgeColor(provider)
  const dark = getTheme() === 'dark'
  const p = provider.toLowerCase()
  if (p.includes('openai') || p.includes('xiaomi')) return dark ? `${base}90` : `${base}80`
  if (p.includes('anthropic') || p.includes('google') || p.includes('minimax')) return dark ? `${base}40` : `${base}26`
  return dark ? '#334155' : '#f1f5f9'
}

export function getProviderBadgeText(provider: string): string {
  const dark = getTheme() === 'dark'
  const p = provider.toLowerCase()
  if (p.includes('openai')) return dark ? '#94a3b8' : '#475569'
  if (p.includes('xiaomi')) return dark ? '#dcc496' : '#6b4f2a'
  if (p.includes('anthropic') || p.includes('google') || p.includes('minimax')) return getProviderBadgeColor(provider)
  return dark ? '#94a3b8' : '#475569'
}

export function getProviderIcon(provider: string) {
  const p = provider.toLowerCase()
  const style = { width: 14, height: 14, display: 'block', objectFit: 'contain' as const }
  if (p.includes('anthropic')) return <img src="/models/claude-ai-icon.svg" alt="" style={style} />
  if (p.includes('openai')) return <img src="/models/chatgpt.svg" alt="" style={style} />
  if (p.includes('google')) return <img src="/models/google-gemini-icon.svg" alt="" style={style} />
  if (p.includes('minimax')) return <img src="/models/minimax-color.svg" alt="" style={style} />
  if (p.includes('xiaomi')) return <img src="/models/xiaomi.svg" alt="" style={style} />
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
  if (name === 'codex') return dark ? '#94a3b8' : '#475569'
  if (name === 'claude-code') return '#cc7c5e'
  if (name === 'gemini-cli') return '#528af2'
  if (name === 'proxy') return '#8b5cf6'
  return dark ? '#94a3b8' : '#475569'
}
