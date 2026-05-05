import { useState } from 'react'
import { formatCompact, formatCost } from '../utils'

export type BarItem = {
  name: string
  icon: React.ReactNode
  tokens: number
  cost: number
  color: string
  badgeBg: string
  badgeText: string
}

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
  const [metric, setMetric] = useState<'tokens' | 'cost'>('tokens')

  const sorted = [...items]
    .sort((a, b) => metric === 'tokens' ? b.tokens - a.tokens : b.cost - a.cost)
    .slice(0, maxCount)

  const maxValue = Math.max(
    ...sorted.map(s => metric === 'tokens' ? s.tokens : s.cost),
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
          >Tokens</button>
          <button
            className={`tab-toggle-btn ${metric === 'cost' ? 'active' : ''}`}
            onClick={() => setMetric('cost')}
          >Cost</button>
        </div>
      </div>
      <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {sorted.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>No data available</div>
        ) : (
          sorted.map((s, index) => {
            const currentVal = metric === 'tokens' ? s.tokens : s.cost
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
                  <div style={{ color: 'var(--text-secondary)', fontWeight: 700 }}>
                    {metric === 'tokens' ? formatCompact(currentVal) : formatCost(currentVal)}
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
