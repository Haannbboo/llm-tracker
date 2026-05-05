import { useMemo } from 'react'
import type { UsageSummary } from '../types'
import { getModelIcon, value } from '../utils'
import { getModelBadgeBackgroundColor, getModelColor, getModelTextColor } from '../model-badge'
import { HorizontalBarChart } from './HorizontalBarChart'
import type { BarItem } from './HorizontalBarChart'

export function ModelTokenChart({
  summary,
  title
}: {
  summary: UsageSummary[],
  title: string
}) {
  const items: BarItem[] = useMemo(() => {
    const map = new Map<string, { tokens: number; cost: number }>()
    for (const s of summary) {
      const existing = map.get(s.model) || { tokens: 0, cost: 0 }
      existing.tokens += value(s.total_tokens)
      existing.cost += value(s.total_cost_usd)
      map.set(s.model, existing)
    }
    return Array.from(map.entries()).map(([model, v]) => ({
      name: model,
      icon: getModelIcon(model),
      tokens: v.tokens,
      cost: v.cost,
      color: getModelColor(model),
      badgeBg: getModelBadgeBackgroundColor(model),
      badgeText: getModelTextColor(model),
    }))
  }, [summary])

  return (
    <HorizontalBarChart title={title} icon="📊" items={items} />
  )
}
