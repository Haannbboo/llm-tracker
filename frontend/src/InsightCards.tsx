import { useMemo } from 'react'
import { t, useLang } from './i18n/index'
import { formatCost, formatLatency, value } from './utils'
import type { UsageSummary, DailyUsage } from './types'

export function InsightCards({ 
  summary, 
  dailyUsage 
}: { 
  summary: UsageSummary[], 
  dailyUsage: DailyUsage[] 
}) {
  const { lang } = useLang()

  const insights = useMemo(() => {
    if (summary.length === 0) return []
    
    const results = []

    // 1. Top Cost Driver
    const topCost = [...summary].sort((a, b) => value(b.total_cost_usd) - value(a.total_cost_usd))[0]
    if (topCost && value(topCost.total_cost_usd) > 0) {
      results.push({
        id: 'cost',
        title: t('Top Cost Driver'),
        value: `${topCost.model}`,
        detail: formatCost(value(topCost.total_cost_usd)),
        icon: '💰'
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
        warning: true
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
    if (totalFailures > 0) {
      results.push({
        id: 'reliability',
        title: t('Reliability Watch'),
        value: `${totalFailures} ${t('failed requests')}`,
        detail: t('Check logs for details'),
        icon: '🚨',
        warning: true
      })
    }

    return results
  }, [summary, dailyUsage, lang])

  if (insights.length === 0) return null

  return (
    <div className="insights-grid">
      {insights.map(insight => (
        <div key={insight.id} className={`insight-card ${insight.warning ? 'warning' : ''}`}>
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
