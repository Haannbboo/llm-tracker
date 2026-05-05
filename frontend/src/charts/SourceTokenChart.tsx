import { useMemo, useState } from 'react'
import type { SourceUsage } from '../types'
import { formatCompact, formatCost, getSourceBadgeBg, getSourceBadgeText } from '../utils'

export function SourceTokenChart({
  data,
  title
}: {
  data: SourceUsage[],
  title: string
}) {
  const [metric, setMetric] = useState<'tokens' | 'cost'>('tokens');

  const sorted = useMemo(() => {
    return [...data].sort((a, b) =>
      metric === 'tokens'
        ? (b.total_tokens ?? 0) - (a.total_tokens ?? 0)
        : (b.total_cost_usd ?? 0) - (a.total_cost_usd ?? 0)
    ).slice(0, 6);
  }, [data, metric]);

  const maxValue = Math.max(
    ...sorted.map(s => metric === 'tokens' ? (s.total_tokens ?? 0) : (s.total_cost_usd ?? 0)),
    1
  );

  const sourceColors: Record<string, string> = {
    'claude-code': '#cc7c5e',
    'codex': '#dcdcdc',
    'gemini-cli': '#528af2',
    'proxy': '#8b5cf6',
  };

  return (
    <div className="widget" style={{ flex: 1 }}>
      <div className="widget-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>📡 {title}</span>
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
            const currentVal = metric === 'tokens' ? (s.total_tokens ?? 0) : (s.total_cost_usd ?? 0);
            const percentage = (currentVal / maxValue) * 100;
            const name = s.client_source || 'unknown';
            const color = sourceColors[name] || '#94a3b8';

            return (
              <div key={`${name}-${index}`} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
                  <span style={{
                    padding: '1px 6px',
                    borderRadius: '4px',
                    backgroundColor: getSourceBadgeBg(name),
                    color: getSourceBadgeText(name),
                    fontSize: '11px',
                    fontWeight: 600,
                  }}>{name}</span>
                  <div style={{ color: 'var(--text-secondary)', fontWeight: 700 }}>
                    {metric === 'tokens' ? formatCompact(currentVal) : formatCost(currentVal)}
                  </div>
                </div>
                <div className="progress-track" style={{ width: '100%', display: 'flex' }}>
                  <div
                    style={{ width: `${percentage}%`, height: '100%', background: color }}
                  />
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
