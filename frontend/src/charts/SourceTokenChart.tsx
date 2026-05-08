import { useMemo } from 'react'
import type { Theme } from '../theme'
import type { SourceUsage } from '../types'
import { getSourceBadgeBg, getSourceBadgeText, getProviderIcon } from '../utils'
import { t } from '../i18n/index.ts'
import { HorizontalBarChart } from './HorizontalBarChart'
import type { BarItem } from './HorizontalBarChart'

const sourceColors: Record<string, string> = {
  'claude-code': '#cc7c5e',
  'codex': '#dcdcdc',
  'gemini-cli': '#528af2',
  'proxy': '#8b5cf6',
}

export function SourceTokenChart({
  data,
  title,
  theme
}: {
  data: SourceUsage[],
  title: string
  theme: Theme
}) {
  const items: BarItem[] = useMemo(() =>
    data.map(s => {
      const name = s.client_source || t('unknown')
      const successful = s.successful_requests ?? 0
      const total = successful + (s.failed_requests ?? 0)
      return {
        name,
        icon: getProviderIcon(name, theme),
        tokens: s.total_tokens ?? 0,
        cost: s.total_cost_usd ?? 0,
        throughput: (s.latency_sum_ms ?? 0) > 0 ? ((s.completion_tokens ?? 0) * 1000) / (s.latency_sum_ms ?? 0) : 0,
        successRate: total > 0 ? (successful / total) * 100 : 100,
        color: sourceColors[name] || '#94a3b8',
        badgeBg: getSourceBadgeBg(name),
        badgeText: getSourceBadgeText(name),
      }
    }),
    [data, theme]
  )

  return (
    <HorizontalBarChart title={title} icon="📡" items={items} />
  )
}
