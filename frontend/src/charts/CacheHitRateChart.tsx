import { useState, useRef, useEffect, useCallback } from 'react'
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
  const [containerWidth, setContainerWidth] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const paddingX = 60;
  const chartWidth = 1000 - (paddingX * 2);

  const measure = useCallback(() => {
    if (containerRef.current) setContainerWidth(containerRef.current.offsetWidth);
  }, []);

  useEffect(() => {
    measure();
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [measure]);

  // Each label needs ~50px to not overlap; compute how many we can show
  const labelSlotPx = 70;
  const maxLabels = Math.max(2, Math.floor(containerWidth / labelSlotPx));

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
      <div className="widget-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>📈 {title}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div style={{ width: '12px', height: '12px', background: 'var(--color-green)', borderRadius: '2px' }} />
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>Hit Rate</span>
          </div>
          <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--color-green)' }}>
            {avg.toFixed(1)}% avg
          </span>
        </div>
      </div>
      <div style={{
        flex: 1,
        padding: '20px 0',
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
                backgroundColor: 'var(--glass-bg)',
                color: 'var(--text-primary)',
                padding: '12px',
                borderRadius: 'var(--radius-md)',
                fontSize: '12px',
                zIndex: 100,
                pointerEvents: 'none',
                boxShadow: 'var(--shadow-floating)',
                minWidth: '180px',
                border: '1px solid var(--glass-border)',
                backdropFilter: 'var(--glass-blur)',
                WebkitBackdropFilter: 'var(--glass-blur)'
              }}>
                <div style={{ fontWeight: 600, marginBottom: '8px', borderBottom: '1px solid var(--border-color)', paddingBottom: '4px', fontSize: '13px' }}>
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
              <defs>
                <linearGradient id="cacheAreaGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-green)" stopOpacity="0.4" />
                  <stop offset="100%" stopColor="var(--color-green)" stopOpacity="0.05" />
                </linearGradient>
              </defs>

              <line
                x1={paddingX}
                y1={200 - (avg / 100) * 200}
                x2={1000 - paddingX}
                y2={200 - (avg / 100) * 200}
                stroke="var(--color-green)"
                strokeWidth="1"
                strokeDasharray="6 4"
                opacity="0.3"
              />

              {(() => {
                const generatePath = (points: { x: number, y: number }[]) => {
                  if (points.length === 0) return '';
                  return [
                    `M ${points[0].x},${points[0].y}`,
                    ...points.slice(1).map(p => `L ${p.x},${p.y}`),
                    `L ${points[points.length - 1].x},200`,
                    `L ${points[0].x},200`,
                    'Z'
                  ].join(' ');
                };

                const points = data.map((_, i) => {
                  const x = paddingX + (i / (Math.max(data.length - 1, 1))) * chartWidth;
                  const y = 200 - (rates[i] / 100) * 200;
                  return { x, y };
                });

                return (
                  <path
                    d={generatePath(points)}
                    fill="url(#cacheAreaGrad)"
                    style={{ pointerEvents: 'none', transition: 'all 0.3s ease', opacity: hoveredIdx === null ? 1 : 0.6 }}
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
                  <polyline
                    points={points}
                    fill="none"
                    stroke="var(--color-green)"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    style={{ pointerEvents: 'none', transition: 'all 0.3s ease', opacity: hoveredIdx === null ? 1 : 0.4 }}
                  />
                );
              })()}

              {data.map((_, i) => {
                const x = paddingX + (i / (Math.max(data.length - 1, 1))) * chartWidth;
                const slotWidth = data.length > 1 ? chartWidth / (data.length - 1) : chartWidth;
                return (
                  <g key={i}>
                    <rect
                      x={x - slotWidth / 2} y={0}
                      width={slotWidth} height={200}
                      fill="transparent"
                      style={{ cursor: 'pointer' }}
                      onMouseEnter={() => setHoveredIdx(i)}
                      onMouseLeave={() => setHoveredIdx(null)}
                    />
                    {hoveredIdx === i && (
                      <line
                        x1={x} y1="0" x2={x} y2="200"
                        stroke="var(--text-muted)"
                        strokeWidth="1"
                        strokeDasharray="4"
                        style={{ pointerEvents: 'none' }}
                      />
                    )}
                  </g>
                );
              })}
            </svg>

            <div ref={containerRef} style={{
              position: 'relative',
              height: '30px',
              marginTop: '16px',
              borderTop: '1px solid var(--chart-footer-border)',
              paddingTop: '8px'
            }}>
              {data.map((d, i) => {
                // Always show first and last; skip others if too many for the space
                const isFirst = i === 0;
                const isLast = i === data.length - 1;
                if (!isFirst && !isLast) {
                  // Compute which interior indices to show for `maxLabels` total
                  const interiorCount = Math.max(0, maxLabels - 2);
                  if (interiorCount > 0) {
                    const step = (data.length - 1) / (interiorCount + 1);
                    const nearest = Math.round(Math.round(i / step) * step);
                    if (nearest !== i) return null;
                  } else {
                    return null;
                  }
                }
                const label = d.period.split('-').slice(1).join('/');
                const xPct = ((paddingX + (i / (Math.max(data.length - 1, 1))) * chartWidth) / 1000) * 100;
                return (
                  <div key={d.period} style={{
                    position: 'absolute',
                    left: `${xPct}%`,
                    transform: 'translateX(-50%)',
                    fontSize: '10px',
                    color: 'var(--text-muted)',
                    whiteSpace: 'nowrap'
                  }}>
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
