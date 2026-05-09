import { useMemo } from 'react'
import type { Metric } from './HorizontalBarChart'
import { t } from '../i18n/index.ts'

type DailyDimensionData = {
  dimension: string
  period: string
  total_tokens: number | null
  total_cost_usd: number | null
  completion_tokens: number | null
  latency_sum_ms: number | null
  successful_requests: number | null
  failed_requests: number | null
}

type SparklineItem = {
  name: string
  color: string
  data: number[]
  changePercent: number
}

function getMetricValue(row: DailyDimensionData, metric: Metric): number {
  if (metric === 'tokens') return row.total_tokens ?? 0
  if (metric === 'cost') return row.total_cost_usd ?? 0
  if (metric === 'throughput') {
    const latency = row.latency_sum_ms ?? 0
    return latency > 0 ? ((row.completion_tokens ?? 0) * 1000) / latency : 0
  }
  // successRate
  const total = (row.successful_requests ?? 0) + (row.failed_requests ?? 0)
  return total > 0 ? ((row.successful_requests ?? 0) / total) * 100 : 100
}

export function SparklineTrendPanel({
  data,
  metric,
  topNames,
  nameColors,
}: {
  data: DailyDimensionData[]
  metric: Metric
  topNames: string[]
  nameColors: Record<string, string>
}) {
  const items = useMemo<SparklineItem[]>(() => {
    return topNames.map(name => {
      const rows = data.filter(d => d.dimension === name).sort((a, b) => a.period.localeCompare(b.period))
      const values = rows.map(r => getMetricValue(r, metric))

      // Calculate change percentage (last vs first)
      let changePercent = 0
      if (values.length >= 2) {
        const first = values[0]
        const last = values[values.length - 1]
        if (first > 0) {
          changePercent = ((last - first) / first) * 100
        } else if (last > 0) {
          changePercent = 100
        }
      }

      return {
        name,
        color: nameColors[name] || '#94a3b8',
        data: values,
        changePercent,
      }
    })
  }, [data, metric, topNames, nameColors])

  if (items.length === 0) return null

  return (
    <div className="widget" style={{ flex: 1, minWidth: 0 }}>
      <div className="widget-header">
        <span>📈 {t('Trend')}</span>
      </div>
      <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {items.map(item => (
          <SparklineRow key={item.name} item={item} />
        ))}
      </div>
    </div>
  )
}

function SparklineRow({ item }: { item: SparklineItem }) {
  const { name, color, data, changePercent } = item

  if (data.length < 2) {
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{name}</span>
          <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>—</span>
        </div>
        <div style={{ height: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{t('Insufficient data')}</span>
        </div>
      </div>
    )
  }

  const height = 24
  const w = 100
  const max = Math.max(...data, 0.001)
  const min = Math.min(...data, 0)
  const range = max - min || 1

  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w
    const y = height - ((v - min) / range) * (height - 4) - 2
    return `${x},${y}`
  }).join(' ')

  const changeColor = Math.abs(changePercent) < 1
    ? 'var(--text-muted)'
    : changePercent > 0
      ? 'var(--color-green)'
      : 'var(--color-red)'

  const changeText = Math.abs(changePercent) < 1
    ? '—'
    : `${changePercent > 0 ? '+' : ''}${changePercent.toFixed(0)}%`

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{name}</span>
        <span style={{ fontSize: '10px', color: changeColor, fontWeight: 600 }}>{changeText}</span>
      </div>
      <svg viewBox={`0 0 ${w} ${height}`} style={{ width: '100%', height, display: 'block' }} preserveAspectRatio="none">
        <defs>
          <linearGradient id={`gradient-${name}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.15} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <polygon
          fill={`url(#gradient-${name})`}
          points={`${points} ${w},${height} 0,${height}`}
        />
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  )
}
