import { useState } from 'react'
import { formatCompact, formatCost, formatRate, formatThroughput } from '../utils'
import { t } from '../i18n/index.ts'

export type BarItem = {
  name: string
  icon: React.ReactNode
  tokens: number
  cost: number
  throughput?: number | null
  pricePerMillion?: number | null
  color: string
  badgeBg: string
  badgeText: string
}

type Metric = 'tokens' | 'cost' | 'throughput'

export function HorizontalBarChart({
  title,
  icon,
  items,
  maxCount = 6,
  children,
}: {
  title: string
  icon: string
  items: BarItem[]
  maxCount?: number
  children?: React.ReactNode
}) {
  const [metric, setMetric] = useState<Metric>('tokens')
  const getMetricValue = (item: BarItem) => {
    if (metric === 'tokens') return item.tokens
    if (metric === 'cost') return item.cost
    return item.throughput ?? 0
  }

  const sorted = [...items]
    .sort((a, b) => getMetricValue(b) - getMetricValue(a))
    .slice(0, maxCount)

  const maxValue = Math.max(
    ...sorted.map(getMetricValue),
    1
  )

  return (
    <div className="widget" style={{ flex: 1 }}>
      <div className="widget-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>{icon} {title}</span>
        <div className="tab-toggle">
          <button
            className={`tab-toggle-btn ${metric === 'tokens' ? 'active' : ''}`}
            onClick={() => setMetric('tokens')}
          >{t('Tokens')}</button>
          <button
            className={`tab-toggle-btn ${metric === 'cost' ? 'active' : ''}`}
            onClick={() => setMetric('cost')}
          >{t('Cost')}</button>
          <button
            className={`tab-toggle-btn ${metric === 'throughput' ? 'active' : ''}`}
            onClick={() => setMetric('throughput')}
          >{t('Speed')}</button>
        </div>
      </div>
      <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {sorted.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>{t('No data available')}</div>
        ) : (
          sorted.map((s, index) => {
            const currentVal = getMetricValue(s)
            const percentage = (currentVal / maxValue) * 100

            return (
              <div key={`${s.name}-${index}`} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                    {s.icon}
                    <span style={{
                      padding: '1px 6px',
                      borderRadius: '4px',
                      backgroundColor: s.badgeBg,
                      color: s.badgeText,
                      fontSize: '11px',
                      fontWeight: 600,
                    }}>{s.name}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
                    <span style={{ color: 'var(--text-secondary)', fontWeight: 700 }}>
                      {metric === 'tokens' ? formatCompact(currentVal) : metric === 'cost' ? formatCost(currentVal, 2) : formatThroughput(currentVal)}
                    </span>
                    {metric === 'cost' && s.pricePerMillion != null && (
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                        {formatRate(s.pricePerMillion)}
                      </span>
                    )}
                  </div>
                </div>
                <div className="progress-track" style={{ width: '100%', display: 'flex' }}>
                  <div
                    style={{ width: `${percentage}%`, height: '100%', background: s.color }}
                  />
                </div>
              </div>
            )
          })
        )}
      </div>
      {children}
    </div>
  )
}
