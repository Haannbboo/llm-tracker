import { useMemo, type ReactNode } from 'react'
import { t, useLang } from './i18n/index'
import { formatCost, formatLatency, value } from './utils'
import type { UsageSummary, DailyUsage } from './types'

export function InsightCards({ 
  summary, 
  dailyUsage,
  onClick
}: { 
  summary: UsageSummary[], 
  dailyUsage: DailyUsage[],
  onClick?: (id: string, metadata?: { provider?: string, model?: string, status?: number }) => void
}) {
  const { lang } = useLang()

  const insights = useMemo(() => {
    if (summary.length === 0) return []
    
    const results: Array<{
      id: string
      title: string
      value: string
      detail: ReactNode
      icon: string
      warning?: boolean
      success?: boolean
      clickable?: boolean
      metadata?: any
    }> = []

    // 1. Top Cost Driver
    const topCost = [...summary].sort((a, b) => value(b.total_cost_usd) - value(a.total_cost_usd))[0]
    if (topCost && value(topCost.total_cost_usd) > 0) {
      results.push({
        id: 'cost',
        title: t('Top Cost Driver'),
        value: `${topCost.model}`,
        detail: formatCost(value(topCost.total_cost_usd)),
        icon: '💰',
        clickable: true,
        metadata: { provider: topCost.provider, model: topCost.model }
      })
    }

    // 2. Latency Watch
    const topLatency = [...summary].sort((a, b) => value(b.avg_latency_ms) - value(a.avg_latency_ms))[0]
    if (topLatency && value(topLatency.avg_latency_ms) > 2000) {
      results.push({
        id: 'latency',
        title: t('Latency Watch'),
        value: `${topLatency.model}`,
        detail: formatLatency(topLatency.avg_latency_ms),
        icon: '⏳',
        warning: true,
        clickable: true,
        metadata: { provider: topLatency.provider, model: topLatency.model }
      })
    }

    // 3. Usage Trend
    if (dailyUsage.length >= 2) {
      const mid = Math.floor(dailyUsage.length / 2)
      const firstHalfCount = mid
      const secondHalfCount = dailyUsage.length - mid

      const firstHalf = dailyUsage.slice(0, mid).reduce((sum, d) => sum + d.requests, 0)
      const secondHalf = dailyUsage.slice(mid).reduce((sum, d) => sum + d.requests, 0)
      
      const firstHalfAvg = firstHalf / firstHalfCount
      const secondHalfAvg = secondHalf / secondHalfCount

      if (firstHalfAvg > 0) {
        const trend = ((secondHalfAvg - firstHalfAvg) / firstHalfAvg) * 100
        if (Math.abs(trend) > 5) {
          results.push({
            id: 'trend',
            title: t('Usage Trend'),
            value: trend > 0 ? t('Trending Up') : t('Trending Down'),
            detail: `${Math.abs(trend).toFixed(0)}% ${t('change')}`,
            icon: trend > 0 ? '📈' : '📉'
          })
        }
      }
    }

    // 4. Reliability Watch
    const totalFailures = summary.reduce((sum, s) => sum + value(s.failed_requests), 0)
    
    let detail: ReactNode = totalFailures > 0 ? t('Check logs for details') : t('System healthy')
    if (totalFailures > 0) {
      const s429 = summary.reduce((sum, s) => sum + value(s.status_429), 0)
      const s4xx = summary.reduce((sum, s) => sum + value(s.status_4xx), 0)
      const s5xx = summary.reduce((sum, s) => sum + value(s.status_5xx), 0)
      const sUnknown = summary.reduce((sum, s) => sum + value(s.status_unknown), 0)
      
      const parts = []
      if (s429 > 0) parts.push({ label: '429', count: s429, status: 429 })
      if (s5xx > 0) parts.push({ label: '5xx', count: s5xx, status: 500 })
      if (s4xx > 0) parts.push({ label: '4xx', count: s4xx, status: 400 })
      if (sUnknown > 0) parts.push({ label: '?', count: sUnknown, status: -1 })
      
      if (parts.length > 0) {
        detail = (
          <div 
            className="stat-label"
            style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', textTransform: 'none', color: 'inherit' }}
          >
            {parts.map((p, i) => (
              <span key={p.label}>
                <span 
                  className="status-link" 
                  onClick={(e) => {
                    e.stopPropagation();
                    onClick?.('reliability', { status: p.status });
                  }}
                >
                  {p.label}: {p.count}
                </span>
                {i < parts.length - 1 && <span style={{ marginLeft: '6px', opacity: 0.3 }}>/</span>}
              </span>
            ))}
          </div>
        )
      }
    }

    results.push({
      id: 'reliability',
      title: t('Reliability Watch'),
      value: `${totalFailures} ${t('failed requests')}`,
      detail,
      icon: totalFailures > 0 ? '🚨' : '✅',
      warning: totalFailures > 0,
      success: totalFailures === 0,
      clickable: totalFailures > 0
    })

    return results
  }, [summary, dailyUsage, lang, onClick])

  if (insights.length === 0) return null

  return (
    <div className="insights-grid">
      {insights.map(insight => (
        <div 
          key={insight.id} 
          className={`insight-card ${insight.warning ? 'warning' : ''} ${insight.success ? 'success' : ''} ${insight.clickable ? 'clickable' : ''}`}
          onClick={() => insight.clickable && onClick?.(insight.id, (insight as any).metadata)}
          style={insight.clickable ? { cursor: 'pointer' } : undefined}
        >
          <div className="insight-icon">{insight.icon}</div>
          <div className="insight-content">
            <div className="insight-title">{insight.title}</div>
            <div className="insight-value">{insight.value}</div>
            <div className="insight-detail">{insight.detail}</div>
          </div>
        </div>
      ))}
    </div>
  )
}
