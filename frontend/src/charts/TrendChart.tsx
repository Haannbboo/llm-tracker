import { useState } from 'react'
import type { DailyUsage } from '../types'
import { formatCost, formatNumber, value } from '../utils'

export function TrendChart({
  data,
  title
}: {
  data: DailyUsage[],
  title: string
}) {
  const [metric, setMetric] = useState<'tokens' | 'cost'>('tokens');
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const maxTokens = Math.max(...data.map(x => value(x.total_tokens)), 1);
  const maxCost = Math.max(...data.map(x => value(x.total_cost_usd)), 0.001);
  const maxRequests = Math.max(...data.map(x => value(x.requests)), 1);
  const paddingX = 60;
  const chartWidth = 1000 - (paddingX * 2);

  const hoveredData = hoveredIdx !== null ? data[hoveredIdx] : null;
  const hCached = hoveredData ? value(hoveredData.cached_tokens) : 0;
  const hInput = hoveredData ? Math.max(0, value(hoveredData.prompt_tokens) - hCached) : 0;
  const hOutput = hoveredData ? value(hoveredData.completion_tokens) : 0;

  return (
    <div className="widget" style={{ minHeight: '400px', width: '100%', position: 'relative' }}>
      <div className="widget-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>📈 {title}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ display: 'flex', gap: '16px' }}>
            {metric === 'tokens' ? (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ width: '12px', height: '12px', background: '#94a3b8', borderRadius: '2px' }} />
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>Input</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ width: '12px', height: '12px', background: 'var(--color-green)', borderRadius: '2px' }} />
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>Cached</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ width: '12px', height: '12px', background: 'var(--color-blue)', borderRadius: '2px' }} />
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>Output</span>
                </div>
              </>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ width: '12px', height: '12px', background: '#d97706', borderRadius: '2px' }} />
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>Input Cost</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ width: '12px', height: '12px', background: '#a855f7', borderRadius: '2px' }} />
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>Output Cost</span>
                </div>
              </>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '12px', height: '3px', background: 'var(--color-pink)', borderRadius: '2px' }} />
              <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>Requests</span>
            </div>
          </div>
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
      </div>
      <div style={{
        flex: 1,
        padding: '20px 0',
        height: '280px',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column'
      }}>
        {data.length === 0 ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>No trend data available</div>
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
                minWidth: '200px',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                backdropFilter: 'blur(4px)'
              }}>
                <div style={{ fontWeight: 600, marginBottom: '8px', borderBottom: '1px solid rgba(255, 255, 255, 0.2)', paddingBottom: '4px', fontSize: '13px' }}>
                  {hoveredData.period}
                </div>
                {metric === 'tokens' ? (
                  <>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '4px' }}>
                      <span style={{ color: '#94a3b8' }}>Input:</span>
                      <span style={{ fontWeight: 600 }}>{formatNumber(hInput)}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '4px' }}>
                      <span style={{ color: 'var(--color-green)' }}>Cached:</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {value(hoveredData.prompt_tokens) > 0 && (
                          <span style={{ fontSize: '10px', color: 'var(--color-green)', opacity: 0.8 }}>
                            ({((hCached / value(hoveredData.prompt_tokens)) * 100).toFixed(1)}%)
                          </span>
                        )}
                        <span style={{ fontWeight: 600 }}>{formatNumber(hCached)}</span>
                      </div>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '4px' }}>
                      <span style={{ color: 'var(--color-blue)' }}>Output:</span>
                      <span style={{ fontWeight: 600 }}>{formatNumber(hOutput)}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginTop: '8px', paddingTop: '8px', borderTop: '1px solid rgba(255, 255, 255, 0.2)' }}>
                      <span style={{ fontWeight: 700 }}>Total Tokens:</span>
                      <span style={{ fontWeight: 800 }}>{formatNumber(value(hoveredData.total_tokens))}</span>
                    </div>
                    {hoveredData.total_cost_usd !== null && value(hoveredData.total_cost_usd) > 0 && (
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginTop: '4px' }}>
                        <span style={{ color: '#f472b6' }}>Est. Cost:</span>
                        <span style={{ fontWeight: 800, color: '#f472b6' }}>{formatCost(hoveredData.total_cost_usd)}</span>
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '4px' }}>
                      <span style={{ color: '#d97706' }}>Input Cost:</span>
                      <span style={{ fontWeight: 600 }}>{formatCost(hoveredData.input_cost_usd)}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '4px' }}>
                      <span style={{ color: '#a855f7' }}>Output Cost:</span>
                      <span style={{ fontWeight: 600 }}>{formatCost(hoveredData.output_cost_usd)}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginTop: '8px', paddingTop: '8px', borderTop: '1px solid rgba(255, 255, 255, 0.2)' }}>
                      <span style={{ fontWeight: 700 }}>Total Cost:</span>
                      <span style={{ fontWeight: 800 }}>{formatCost(hoveredData.total_cost_usd)}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginTop: '4px' }}>
                      <span style={{ color: 'var(--text-muted)' }}>Tokens:</span>
                      <span style={{ fontWeight: 600 }}>{formatNumber(value(hoveredData.total_tokens))}</span>
                    </div>
                  </>
                )}
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginTop: '4px' }}>
                  <span style={{ color: 'var(--color-pink)' }}>Requests:</span>
                  <span style={{ fontWeight: 600, color: 'var(--color-pink)' }}>{formatNumber(hoveredData.requests)}</span>
                </div>
              </div>
            )}

            <svg
              viewBox="0 0 1000 200"
              preserveAspectRatio="none"
              style={{ width: '100%', height: '220px', overflow: 'visible' }}
            >
              {[0, 0.25, 0.5, 0.75, 1].map(tick => (
                <line
                  key={tick}
                  x1="0" y1={200 - tick * 200}
                  x2="1000" y2={200 - tick * 200}
                  stroke="var(--chart-grid)"
                  strokeWidth="1"
                />
              ))}

              {data.map((d, i) => {
                const x = paddingX + (i / (Math.max(data.length - 1, 1))) * chartWidth;
                const barWidth = Math.min(chartWidth / (data.length * 1.5), 60);
                const slotWidth = data.length > 1 ? chartWidth / (data.length - 1) : chartWidth;

                const isHovered = hoveredIdx === i;
                const isDimmed = hoveredIdx !== null && !isHovered;

                let bars: { y: number; h: number; fill: string }[];
                if (metric === 'tokens') {
                  const cached = value(d.cached_tokens);
                  const input = Math.max(0, value(d.prompt_tokens) - cached);
                  const output = value(d.completion_tokens);
                  const hInputRect = (input / maxTokens) * 200;
                  const hCachedRect = (cached / maxTokens) * 200;
                  const hOutputRect = (output / maxTokens) * 200;
                  bars = [
                    { y: 200 - hInputRect, h: hInputRect, fill: '#94a3b8' },
                    { y: 200 - hInputRect - hCachedRect, h: hCachedRect, fill: 'var(--color-green)' },
                    { y: 200 - hInputRect - hCachedRect - hOutputRect, h: hOutputRect, fill: 'var(--color-blue)' },
                  ];
                } else {
                  const inputCost = value(d.input_cost_usd);
                  const outputCost = value(d.output_cost_usd);
                  const hInputCost = (inputCost / maxCost) * 200;
                  const hOutputCost = (outputCost / maxCost) * 200;
                  bars = [
                    { y: 200 - hInputCost, h: hInputCost, fill: '#d97706' },
                    { y: 200 - hInputCost - hOutputCost, h: hOutputCost, fill: '#a855f7' },
                  ];
                }

                return (
                  <g
                    key={i}
                    onMouseEnter={() => setHoveredIdx(i)}
                    onMouseLeave={() => setHoveredIdx(null)}
                  >
                    {bars.map((bar, bi) => (
                      <rect
                        key={bi}
                        x={x - barWidth/2} y={bar.y}
                        width={barWidth} height={bar.h}
                        fill={bar.fill}
                        opacity={isDimmed ? 0.3 : 1}
                        style={{ transition: 'all 0.2s' }}
                      />
                    ))}
                    <rect
                      x={x - slotWidth/2} y={0}
                      width={slotWidth} height={200}
                      fill="transparent"
                      style={{ cursor: 'pointer' }}
                    />
                  </g>
                );
              })}

              {(() => {
                const points = data.map((d, i) => {
                  const x = paddingX + (i / (Math.max(data.length - 1, 1))) * chartWidth;
                  const y = 200 - (value(d.requests) / maxRequests) * 200;
                  return `${x},${y}`;
                }).join(' ');

                return (
                  <>
                    <polyline
                      points={points}
                      fill="none"
                      stroke="var(--color-pink)"
                      strokeWidth="3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{ pointerEvents: 'none', opacity: hoveredIdx === null ? 1 : 0.4 }}
                    />
                    {data.map((d, i) => {
                      const x = paddingX + (i / (Math.max(data.length - 1, 1))) * chartWidth;
                      const y = 200 - (value(d.requests) / maxRequests) * 200;
                      return (
                        <circle
                          key={i}
                          cx={x} cy={y} r={hoveredIdx === i ? "5" : "3"}
                          fill="var(--chart-dot-fill)"
                          stroke="var(--color-pink)"
                          strokeWidth={hoveredIdx === i ? "3" : "2"}
                          style={{ pointerEvents: 'none', transition: 'all 0.2s', opacity: hoveredIdx === null || hoveredIdx === i ? 1 : 0.4 }}
                        />
                      );
                    })}
                  </>
                );
              })()}
            </svg>

            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              marginTop: '20px',
              borderTop: '1px solid var(--chart-footer-border)',
              paddingTop: '10px',
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
