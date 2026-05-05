import type { DateRangeOption } from './types'

export const numberFormatter = new Intl.NumberFormat()
export const compactFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 1,
  notation: 'compact',
})
export const costFormatter = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 6,
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
  if (option === '5h') now.setHours(now.getHours() - 5)
  else if (option === '24h') now.setHours(now.getHours() - 24)
  else if (option === '7d') now.setDate(now.getDate() - 7)
  else if (option === '30d') now.setDate(now.getDate() - 30)
  return now.toISOString()
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
  const p = provider.toLowerCase()
  if (p.includes('openai') || p.includes('xiaomi')) return `${base}80`
  if (p.includes('anthropic') || p.includes('google') || p.includes('minimax')) return `${base}26`
  return '#f1f5f9'
}

export function getProviderBadgeText(provider: string): string {
  const p = provider.toLowerCase()
  if (p.includes('openai')) return '#475569'
  if (p.includes('xiaomi')) return '#6b4f2a'
  if (p.includes('anthropic') || p.includes('google') || p.includes('minimax')) return getProviderBadgeColor(provider)
  return '#475569'
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
  if (name === 'codex') return '#dcdcdc80'
  if (name === 'claude-code') return '#cc7c5e26'
  if (name === 'gemini-cli') return '#528af226'
  if (name === 'proxy') return '#8b5cf626'
  return '#f1f5f9'
}

export function getSourceBadgeText(name: string): string {
  if (name === 'codex') return '#475569'
  if (name === 'claude-code') return '#cc7c5e'
  if (name === 'gemini-cli') return '#528af2'
  if (name === 'proxy') return '#8b5cf6'
  return '#475569'
}
