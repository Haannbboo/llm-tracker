import { useMemo, useState } from 'react'
import type { UsageSummary } from '../types'
import { formatCompact, formatCost, getModelIcon, value } from '../utils'
import { getModelBadgeBackgroundColor, getModelColor, getModelTextColor } from '../model-badge'

export function ModelTokenChart({
  summary,
  title
}: {
  summary: UsageSummary[],
  title: string
}) {
  const [metric, setMetric] = useState<'tokens' | 'cost'>('tokens');

  const aggregated = useMemo(() => {
    const map = new Map<string, {
      model: string,
      provider: string,
      total_tokens: number,
      prompt_tokens: number,
      completion_tokens: number,
      cached_tokens: number,
      total_cost_usd: number
    }>();

    for (const s of summary) {
      const existing = map.get(s.model) || {
        model: s.model,
        provider: s.provider,
        total_tokens: 0,
        prompt_tokens: 0,
        completion_tokens: 0,
        cached_tokens: 0,
        total_cost_usd: 0
      };

      existing.total_tokens += value(s.total_tokens);
      existing.prompt_tokens += value(s.prompt_tokens);
      existing.completion_tokens += value(s.completion_tokens);
      existing.cached_tokens += value(s.cached_tokens);
      existing.total_cost_usd += value(s.total_cost_usd);

      map.set(s.model, existing);
    }

    return Array.from(map.values())
      .sort((a, b) => metric === 'tokens' ? b.total_tokens - a.total_tokens : b.total_cost_usd - a.total_cost_usd)
      .slice(0, 6);
  }, [summary, metric]);

  const maxValue = Math.max(...aggregated.map(s => metric === 'tokens' ? s.total_tokens : s.total_cost_usd), 1);

  return (
    <div className="widget" style={{ flex: 1 }}>
      <div className="widget-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>📊 {title}</span>
        <div className="tab-group" style={{ display: 'flex', background: '#f1f5f9', padding: '2px', borderRadius: '6px' }}>
          <button
            onClick={() => setMetric('tokens')}
            style={{
              padding: '2px 8px',
              fontSize: '10px',
              borderRadius: '4px',
              fontWeight: 600,
              border: 'none',
              cursor: 'pointer',
              background: metric === 'tokens' ? 'white' : 'transparent',
              color: metric === 'tokens' ? 'var(--color-blue)' : '#64748b',
              boxShadow: metric === 'tokens' ? '0 1px 2px rgba(0,0,0,0.05)' : 'none'
            }}
          >Tokens</button>
          <button
            onClick={() => setMetric('cost')}
            style={{
              padding: '2px 8px',
              fontSize: '10px',
              borderRadius: '4px',
              fontWeight: 600,
              border: 'none',
              cursor: 'pointer',
              background: metric === 'cost' ? 'white' : 'transparent',
              color: metric === 'cost' ? 'var(--color-blue)' : '#64748b',
              boxShadow: metric === 'cost' ? '0 1px 2px rgba(0,0,0,0.05)' : 'none'
            }}
          >Cost</button>
        </div>
      </div>
      <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {aggregated.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>No data available</div>
        ) : (
          aggregated.map(s => {
            const currentVal = metric === 'tokens' ? s.total_tokens : s.total_cost_usd;
            const percentage = (currentVal / maxValue) * 100;
            const mColor = getModelColor(s.model);

            return (
              <div key={s.model} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                    {getModelIcon(s.model)}
                    <span style={{
                      padding: '1px 6px',
                      borderRadius: '4px',
                      backgroundColor: getModelBadgeBackgroundColor(s.model),
                      color: getModelTextColor(s.model),
                      fontSize: '11px'
                    }}>{s.model}</span>
                  </div>
                  <div style={{ color: 'var(--text-secondary)', fontWeight: 700 }}>
                    {metric === 'tokens' ? formatCompact(currentVal) : formatCost(currentVal)}
                  </div>
                </div>
                <div style={{
                  height: '8px',
                  width: '100%',
                  background: '#f1f5f9',
                  borderRadius: '4px',
                  overflow: 'hidden',
                  display: 'flex'
                }}>
                  <div
                    style={{ width: `${percentage}%`, height: '100%', background: mColor }}
                  />
                </div>
              </div>
            );
          })
        )}
      </div>
      {metric === 'tokens' && aggregated.length > 0 && (
        <div style={{ padding: '0 20px 20px', display: 'flex', gap: '12px', fontSize: '10px', color: 'var(--text-muted)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <div style={{ width: '8px', height: '8px', background: '#94a3b8', borderRadius: '2px' }} /> Input
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <div style={{ width: '8px', height: '8px', background: 'var(--color-green)', borderRadius: '2px' }} /> Cached
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <div style={{ width: '8px', height: '8px', background: 'var(--color-blue)', borderRadius: '2px' }} /> Output
          </div>
        </div>
      )}
    </div>
  );
}
