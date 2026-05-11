import { useState, useMemo, useEffect } from 'react'
import type { Theme } from '../theme'
import type { UsageSummary } from '../types'
import { getModelColor, getModelBadgeBackgroundColor, getModelTextColor } from '../model-badge'
import { getModelIcon, getProviderIcon, getProviderBadgeBg, getProviderBadgeText, getSourceBadgeBg, getSourceBadgeText, PALETTE } from '../utils'
import { HorizontalBarChart } from './HorizontalBarChart'
import type { BarItem, Metric } from './HorizontalBarChart'
import { SparklineTrendPanel } from './SparklineTrendPanel'
import { t } from '../i18n/index.ts'

type Dimension = 'model' | 'provider' | 'source'

type DailyDimensionData = {
  dimension: string
  period: string
  total_tokens: number | null
  prompt_tokens: number | null
  cached_tokens: number | null
  total_cost_usd: number | null
  completion_tokens: number | null
  latency_sum_ms: number | null
  successful_requests: number | null
  failed_requests: number | null
}

type SourceSummaryRow = {
  client_source: string | null
  requests: number | null
  total_tokens: number | null
  prompt_tokens: number | null
  cached_tokens: number | null
  completion_tokens: number | null
  latency_sum_ms: number | null
  avg_throughput: number | null
  total_cost_usd: number | null
  successful_requests: number | null
  failed_requests: number | null
}

const providerColors: Record<string, string> = {
  'anthropic': '#cc7c5e',
  'google': '#528af2',
  'openai': '#94a3b8',
  'xiaomi': '#dcc496',
}

export function TopUsageChart({
  summary,
  theme,
  filterParams = {},
  showTrend = true,
}: {
  summary: UsageSummary[]
  theme: Theme
  filterParams?: {
    provider?: string
    model?: string | null
    client_source?: string | null
    since?: string | null
    until?: string | null
    only_failed?: boolean
  }
  showTrend?: boolean
}) {
  const [dimension, setDimension] = useState<Dimension>('model')
  const [metric, setMetric] = useState<Metric>('tokens')
  const [trendData, setTrendData] = useState<DailyDimensionData[]>([])
  const [sourceSummary, setSourceSummary] = useState<SourceSummaryRow[]>([])

  // Fetch source summary data when source dimension is selected
  useEffect(() => {
    if (dimension !== 'source') return
    const controller = new AbortController()
    async function fetchSourceSummary() {
      try {
        const url = new URL('/usage/by-source', window.location.origin)
        if (filterParams.provider) url.searchParams.set('provider', filterParams.provider)
        if (filterParams.model) url.searchParams.set('model', filterParams.model)
        if (filterParams.client_source) url.searchParams.set('client_source', filterParams.client_source)
        if (filterParams.since) url.searchParams.set('since', filterParams.since)
        if (filterParams.until) url.searchParams.set('until', filterParams.until)
        if (filterParams.only_failed) url.searchParams.set('only_failed', 'true')

        const res = await fetch(url.toString(), { signal: controller.signal })
        if (res.ok) {
          setSourceSummary(await res.json())
        }
      } catch {
        // Ignore abort errors
      }
    }
    fetchSourceSummary()
    return () => controller.abort()
  }, [dimension, filterParams])

  // Fetch trend data when dimension changes
  useEffect(() => {
    const controller = new AbortController()
    async function fetchTrend() {
      try {
        const url = new URL('/usage/daily-by-dimension', window.location.origin)
        url.searchParams.set('dimension', dimension === 'source' ? 'client_source' : dimension)
        
        if (filterParams.provider) url.searchParams.set('provider', filterParams.provider)
        if (filterParams.model) url.searchParams.set('model', filterParams.model)
        if (filterParams.client_source) url.searchParams.set('client_source', filterParams.client_source)
        if (filterParams.since) url.searchParams.set('since', filterParams.since)
        if (filterParams.until) url.searchParams.set('until', filterParams.until)
        if (filterParams.only_failed) url.searchParams.set('only_failed', 'true')

        const res = await fetch(url.toString(), { signal: controller.signal })
        if (res.ok) {
          setTrendData(await res.json())
        }
      } catch {
        // Ignore abort errors
      }
    }
    fetchTrend()
    return () => controller.abort()
  }, [dimension, filterParams])

  const items: BarItem[] = useMemo(() => {
    if (dimension === 'model') {
      const map = new Map<string, { tokens: number; completion: number; prompt: number; cached: number; latency: number; cost: number; priceWeight: number; priceTokens: number; successful: number; total: number }>()
      for (const s of summary) {
        const existing = map.get(s.model) || { tokens: 0, completion: 0, prompt: 0, cached: 0, latency: 0, cost: 0, priceWeight: 0, priceTokens: 0, successful: 0, total: 0 }
        const tokens = s.total_tokens ?? 0
        existing.tokens += tokens
        existing.completion += s.completion_tokens ?? 0
        existing.prompt += s.prompt_tokens ?? 0
        existing.cached += s.cached_tokens ?? 0
        existing.latency += s.latency_sum_ms ?? 0
        existing.cost += s.total_cost_usd ?? 0
        existing.successful += s.successful_requests ?? 0
        existing.total += (s.successful_requests ?? 0) + (s.failed_requests ?? 0)
        if (s.avg_effective_price_per_million_usd != null) {
          existing.priceWeight += s.avg_effective_price_per_million_usd * tokens
          existing.priceTokens += tokens
        }
        map.set(s.model, existing)
      }
      return Array.from(map.entries()).map(([model, v]) => ({
        name: model,
        icon: getModelIcon(model, theme),
        tokens: v.tokens,
        cost: v.cost,
        throughput: v.latency > 0 ? (v.completion * 1000) / v.latency : 0,
        pricePerMillion: v.priceTokens > 0
          ? v.priceWeight / v.priceTokens
          : v.tokens > 0 ? (v.cost / v.tokens) * 1_000_000 : null,
        successRate: v.total > 0 ? (v.successful / v.total) * 100 : 100,
        cacheHitRate: v.prompt > 0 ? (v.cached / v.prompt) * 100 : 0,
        color: getModelColor(model),
        badgeBg: getModelBadgeBackgroundColor(model, theme),
        badgeText: getModelTextColor(model, theme),
      }))
    }

    if (dimension === 'provider') {
      const map = new Map<string, { tokens: number; completion: number; prompt: number; cached: number; latency: number; cost: number; successful: number; total: number }>()
      for (const s of summary) {
        const existing = map.get(s.provider) || { tokens: 0, completion: 0, prompt: 0, cached: 0, latency: 0, cost: 0, successful: 0, total: 0 }
        existing.tokens += s.total_tokens ?? 0
        existing.completion += s.completion_tokens ?? 0
        existing.prompt += s.prompt_tokens ?? 0
        existing.cached += s.cached_tokens ?? 0
        existing.latency += s.latency_sum_ms ?? 0
        existing.cost += s.total_cost_usd ?? 0
        existing.successful += s.successful_requests ?? 0
        existing.total += (s.successful_requests ?? 0) + (s.failed_requests ?? 0)
        map.set(s.provider, existing)
      }
      return Array.from(map.entries()).map(([provider, v], i) => ({
        name: provider,
        icon: getProviderIcon(provider, theme),
        tokens: v.tokens,
        cost: v.cost,
        throughput: v.latency > 0 ? (v.completion * 1000) / v.latency : 0,
        successRate: v.total > 0 ? (v.successful / v.total) * 100 : 100,
        cacheHitRate: v.prompt > 0 ? (v.cached / v.prompt) * 100 : 0,
        color: providerColors[provider.toLowerCase()] || PALETTE[i % PALETTE.length],
        badgeBg: getProviderBadgeBg(provider, theme),
        badgeText: getProviderBadgeText(provider, theme),
      }))
    }

    // source dimension
    return sourceSummary.map((row, i) => {
      const name = row.client_source || 'unknown'
      const tokens = row.total_tokens ?? 0
      const cost = row.total_cost_usd ?? 0
      const total = (row.successful_requests ?? 0) + (row.failed_requests ?? 0)
      const prompt = row.prompt_tokens ?? 0
      const cached = row.cached_tokens ?? 0
      return {
        name,
        icon: null,
        tokens,
        cost,
        throughput: row.avg_throughput ?? 0,
        pricePerMillion: tokens > 0 ? (cost / tokens) * 1_000_000 : null,
        successRate: total > 0 ? ((row.successful_requests ?? 0) / total) * 100 : 100,
        cacheHitRate: prompt > 0 ? (cached / prompt) * 100 : 0,
        color: PALETTE[i % PALETTE.length],
        badgeBg: getSourceBadgeBg(name),
        badgeText: getSourceBadgeText(name),
      }
    })
  }, [summary, dimension, theme, sourceSummary])

  const topNames = useMemo(() => items.slice(0, 6).map(i => i.name), [items])
  const nameColors = useMemo(() => {
    const colors: Record<string, string> = {}
    for (const item of items) {
      colors[item.name] = item.color
    }
    return colors
  }, [items])

  const dimensionLabel = dimension === 'model' ? t('Models') : dimension === 'provider' ? t('Providers') : t('Sources')

  const chart = (
    <HorizontalBarChart
      title={`${t('Top')} ${dimensionLabel}`}
      icon="📊"
      items={items}
      metric={metric}
    >
      <div style={{
        padding: '8px 12px',
        borderTop: '1px solid var(--border-color)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <div style={{ display: 'flex', gap: '2px', background: 'var(--tab-toggle-bg)', borderRadius: '6px', padding: '2px' }}>
          {(['model', 'provider', 'source'] as Dimension[]).map(d => (
            <button
              key={d}
              className={`tab-toggle-btn ${dimension === d ? 'active' : ''}`}
              onClick={() => setDimension(d)}
            >
              {d === 'model' ? t('Models') : d === 'provider' ? t('Providers') : t('Sources')}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: '2px', background: 'var(--tab-toggle-bg)', borderRadius: '6px', padding: '2px' }}>
          {(['tokens', 'cost', 'throughput', 'successRate', 'cacheHitRate'] as Metric[]).map(m => (
            <button
              key={m}
              className={`tab-toggle-btn ${metric === m ? 'active' : ''}`}
              onClick={() => setMetric(m)}
            >
              {m === 'tokens' ? t('Tokens') : m === 'cost' ? t('Cost') : m === 'throughput' ? t('Speed') : m === 'successRate' ? t('Success') : t('Cache')}
            </button>
          ))}
        </div>
      </div>
    </HorizontalBarChart>
  )

  if (!showTrend) return chart

  return (
    <div style={{ display: 'flex', gap: '16px', alignItems: 'stretch' }}>
      <div style={{ flex: 2 }}>
        {chart}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <SparklineTrendPanel
          data={trendData}
          metric={metric}
          topNames={topNames}
          nameColors={nameColors}
        />
      </div>
    </div>
  )
}
