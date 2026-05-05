import { useMemo } from 'react'
import type { ProviderUsage } from '../types'
import { getProviderBadgeBg, getProviderBadgeText, getProviderIcon, PALETTE } from '../utils'
import { HorizontalBarChart } from './HorizontalBarChart'
import type { BarItem } from './HorizontalBarChart'

export function ProviderTokenChart({
  data,
  title
}: {
  data: ProviderUsage[],
  title: string
}) {
  const providerColors: Record<string, string> = {
    'anthropic': '#cc7c5e',
    'google': '#528af2',
    'openai': '#94a3b8',
    'xiaomi': '#dcc496',
  }

  const items: BarItem[] = useMemo(() =>
    data.map((s, i) => ({
      name: s.provider,
      icon: getProviderIcon(s.provider),
      tokens: s.total_tokens ?? 0,
      cost: s.total_cost_usd ?? 0,
      color: providerColors[s.provider.toLowerCase()] || PALETTE[i % PALETTE.length],
      badgeBg: getProviderBadgeBg(s.provider),
      badgeText: getProviderBadgeText(s.provider),
    })),
    [data]
  )

  return (
    <HorizontalBarChart title={title} icon="🏢" items={items} />
  )
}
