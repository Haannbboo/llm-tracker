import { useMemo } from 'react'
import type { Theme } from '../theme'
import type { UsageSummary } from '../types'
import { getModelIcon, value } from '../utils'
import { getModelBadgeBackgroundColor, getModelColor, getModelTextColor } from '../model-badge'
import { HorizontalBarChart } from './HorizontalBarChart'
import type { BarItem } from './HorizontalBarChart'

export function ModelTokenChart({
  summary,
  title,
  theme
}: {
  summary: UsageSummary[],
  title: string
  theme: Theme
}) {
  const items: BarItem[] = useMemo(() => {
    const map = new Map<string, { tokens: number; cost: number; priceWeight: number; priceTokens: number }>()
    for (const s of summary) {
      const existing = map.get(s.model) || { tokens: 0, cost: 0, priceWeight: 0, priceTokens: 0 }
      const tokens = value(s.total_tokens)
      existing.tokens += tokens
      existing.cost += value(s.total_cost_usd)
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
      pricePerMillion: v.priceTokens > 0
        ? v.priceWeight / v.priceTokens
        : v.tokens > 0 ? (v.cost / v.tokens) * 1_000_000 : null,
      color: getModelColor(model),
      badgeBg: getModelBadgeBackgroundColor(model, theme),
      badgeText: getModelTextColor(model, theme),
    }))
  }, [summary, theme])

  return (
    <HorizontalBarChart title={title} icon="📊" items={items} />
  )
}
