import { useMemo } from 'react'
import type { Theme } from '../theme'
import type { ProviderUsage } from '../types'
import { getProviderBadgeBg, getProviderBadgeText, getProviderIcon, PALETTE } from '../utils'
import { HorizontalBarChart } from './HorizontalBarChart'
import type { BarItem } from './HorizontalBarChart'

const providerColors: Record<string, string> = {
  'anthropic': '#cc7c5e',
  'google': '#528af2',
  'openai': '#94a3b8',
  'xiaomi': '#dcc496',
}

export function ProviderTokenChart({
  data,
  title,
  theme
}: {
  data: ProviderUsage[],
  title: string
  theme: Theme
}) {
  const items: BarItem[] = useMemo(() =>
    data.map((s, i) => {
      const tokens = s.total_tokens ?? 0
      const cost = s.total_cost_usd ?? 0
      return {
        name: s.provider,
        icon: getProviderIcon(s.provider, theme),
        tokens,
        cost,
        pricePerMillion: s.avg_effective_price_per_million_usd
          ?? (tokens > 0 ? (cost / tokens) * 1_000_000 : null),
        color: providerColors[s.provider.toLowerCase()] || PALETTE[i % PALETTE.length],
        badgeBg: getProviderBadgeBg(s.provider, theme),
        badgeText: getProviderBadgeText(s.provider, theme),
      }
    }),
    [data, theme]
  )

  return (
    <HorizontalBarChart title={title} icon="🏢" items={items} />
  )
}
