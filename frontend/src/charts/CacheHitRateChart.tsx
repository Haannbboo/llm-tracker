import { useState } from 'react'
import type { DailyUsage } from '../types'
import { formatNumber, value } from '../utils'

export function CacheHitRateChart({
  data,
  title
}: {
  data: DailyUsage[],
  title: string
}) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const paddingX = 20;
  const chartWidth = 1000 - (paddingX * 2);

  const rates = data.map(d => {
    const p = value(d.prompt_tokens);
    return p > 0 ? (value(d.cached_tokens) / p) * 100 : 0;
  });
  const avg = rates.length > 0 ? rates.reduce((a, b) => a + b, 0) / rates.length : 0;
  const hasData = data.length > 0 && rates.some(r => r > 0);

  const hoveredData = hoveredIdx !== null ? data[hoveredIdx] : null;
  const hoveredRate = hoveredIdx !== null ? rates[hoveredIdx] : 0;

  return (
    <div className="widget" style={{ flex: 1, width: '100%', position: 'relative', display: 'flex', flexDirection: 'column' }}>
      <div className="widget-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 12px' }}>
        <span>📈 {title}</span>
        <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--color-green)' }}>
          {avg.toFixed(1)}% avg
        </span>
      </div>
      <div style={{
        flex: 1,
        padding: '2px 0',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column'
      }}>
        {!hasData ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>No cache data available</div>
        ) : (
          <>
            {hoveredIdx !== null && hoveredData && (
              <div style={{
                position: 'absolute',
                top: '-10px',
                left: `${(paddingX + (hoveredIdx / (Math.max(data.length - 1, 1))) * chartWidth) / 10}%`,
                transform: 'translateX(-50%)',
                backgroundColor: 'rgba(15, 23, 42, 0.95)',
                color: 'white',
                padding: '12px',
                borderRadius: '8px',
                fontSize: '12px',
                zIndex: 100,
                pointerEvents: 'none',
                boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
                minWidth: '180px',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                backdropFilter: 'blur(4px)'
              }}>
                <div style={{ fontWeight: 600, marginBottom: '8px', borderBottom: '1px solid rgba(255, 255, 255, 0.2)', paddingBottom: '4px', fontSize: '13px' }}>
                  {hoveredData.period}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--color-green)' }}>Hit Rate:</span>
                  <span style={{ fontWeight: 700, color: 'var(--color-green)' }}>{hoveredRate.toFixed(1)}%</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Cached:</span>
                  <span style={{ fontWeight: 600 }}>{formatNumber(hoveredData.cached_tokens)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Prompt:</span>
                  <span style={{ fontWeight: 600 }}>{formatNumber(hoveredData.prompt_tokens)}</span>
                </div>
              </div>
            )}

            <svg
              viewBox="0 0 1000 200"
              preserveAspectRatio="none"
              style={{ width: '100%', height: '100%', overflow: 'visible' }}
            >
              <line
                x1={paddingX}
                y1={200 - (avg / 100) * 200}
                x2={1000 - paddingX}
                y2={200 - (avg / 100) * 200}
                stroke="var(--color-green)"
                strokeWidth="1"
                strokeDasharray="6 4"
                opacity="0.5"
              />

              <defs>
                <linearGradient id="cacheGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-green)" stopOpacity="0.3" />
                  <stop offset="100%" stopColor="var(--color-green)" stopOpacity="0.02" />
                </linearGradient>
              </defs>
              {(() => {
                const points = data.map((_, i) => {
                  const x = paddingX + (i / (Math.max(data.length - 1, 1))) * chartWidth;
                  const y = 200 - (rates[i] / 100) * 200;
                  return `${x},${y}`;
                }).join(' ');
                return (
                  <polygon
                    points={`${paddingX},${200 - (rates[0] / 100) * 200} ${points} ${1000 - paddingX},${200 - (rates[rates.length - 1] / 100) * 200} ${1000 - paddingX},200 ${paddingX},200`}
                    fill="url(#cacheGrad)"
                    style={{ pointerEvents: 'none' }}
                  />
                );
              })()}

              {(() => {
                const points = data.map((_, i) => {
                  const x = paddingX + (i / (Math.max(data.length - 1, 1))) * chartWidth;
                  const y = 200 - (rates[i] / 100) * 200;
                  return `${x},${y}`;
                }).join(' ');

                return (
                  <>
                    <polyline
                      points={points}
                      fill="none"
                      stroke="var(--color-green)"
                      strokeWidth="3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{ pointerEvents: 'none', opacity: hoveredIdx === null ? 1 : 0.5 }}
                    />
                    {data.map((_, i) => {
                      const x = paddingX + (i / (Math.max(data.length - 1, 1))) * chartWidth;
                      const y = 200 - (rates[i] / 100) * 200;
                      return (
                        <circle
                          key={i}
                          cx={x} cy={y} r={hoveredIdx === i ? "5" : "3"}
                          fill="white"
                          stroke="var(--color-green)"
                          strokeWidth={hoveredIdx === i ? "3" : "2"}
                          style={{ pointerEvents: 'none', transition: 'all 0.2s', opacity: hoveredIdx === null || hoveredIdx === i ? 1 : 0.4 }}
                        />
                      );
                    })}
                  </>
                );
              })()}

              {data.map((_, i) => {
                const x = paddingX + (i / (Math.max(data.length - 1, 1))) * chartWidth;
                const slotWidth = data.length > 1 ? chartWidth / (data.length - 1) : chartWidth;
                return (
                  <rect
                    key={i}
                    x={x - slotWidth / 2} y={0}
                    width={slotWidth} height={200}
                    fill="transparent"
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={() => setHoveredIdx(i)}
                    onMouseLeave={() => setHoveredIdx(null)}
                  />
                );
              })}
            </svg>

            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              marginTop: '4px',
              borderTop: '1px solid #f1f5f9',
              paddingTop: '4px',
              paddingLeft: `${(paddingX / 1000) * 100}%`,
              paddingRight: `${(paddingX / 1000) * 100}%`
            }}>
              {data.map((d, i) => {
                if (data.length > 12 && i % Math.ceil(data.length / 12) !== 0 && i !== data.length - 1) {
                  return null;
                }
                const label = d.period.includes(':')
                  ? d.period.split(' ')[1]
                  : d.period.split('-').slice(1).join('/');
                return (
                  <div key={d.period} style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                    {label}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
