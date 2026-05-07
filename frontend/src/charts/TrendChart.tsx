import { useMemo, useState } from 'react'
import type { DailyUsage } from '../types'
import { fillGaps, formatCost, formatNumber, value } from '../utils'
import { ChartTooltip, TooltipRow, TooltipDivider } from './ChartTooltip'
import { t } from '../i18n/index.ts'

export function TrendChart({
  data,
  title,
  granularity = 'day',
  periodCount,
  showDots = true,
}: {
  data: DailyUsage[],
  title: string,
  granularity?: 'hour' | 'day',
  periodCount: number,
  showDots?: boolean,
}) {
  const [metric, setMetric] = useState<'tokens' | 'cost'>('tokens');
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const filled = useMemo(() => fillGaps(data, granularity, periodCount), [data, granularity, periodCount]);
  const maxTokens = Math.max(...filled.map(x => value(x.total_tokens)), 1);
  const maxCost = Math.max(...filled.map(x => value(x.total_cost_usd)), 0.001);
  const maxRequests = Math.max(...filled.map(x => value(x.requests)), 1);
  const paddingX = 60;
  const chartWidth = 1000 - (paddingX * 2);

  const hoveredData = hoveredIdx !== null ? filled[hoveredIdx] : null;
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
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>{t('Input')}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ width: '12px', height: '12px', background: 'var(--color-green)', borderRadius: '2px' }} />
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>{t('Cached')}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ width: '12px', height: '12px', background: 'var(--color-blue)', borderRadius: '2px' }} />
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>{t('Output')}</span>
                </div>
              </>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ width: '12px', height: '12px', background: '#d97706', borderRadius: '2px' }} />
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>{t('Input Cost')}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ width: '12px', height: '12px', background: '#a855f7', borderRadius: '2px' }} />
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>{t('Output Cost')}</span>
                </div>
              </>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '12px', height: '3px', background: 'var(--color-pink)', borderRadius: '2px' }} />
              <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>{t('Requests')}</span>
            </div>
          </div>
          <div className="tab-toggle">
            <button
              className={`tab-toggle-btn ${metric === 'tokens' ? 'active' : ''}`}
              onClick={() => setMetric('tokens')}
            >{t('Tokens')}</button>
            <button
              className={`tab-toggle-btn ${metric === 'cost' ? 'active' : ''}`}
              onClick={() => setMetric('cost')}
            >{t('Cost')}</button>
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
        {filled.length === 0 ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>{t('No trend data available')}</div>
        ) : (
          <>
            {hoveredIdx !== null && hoveredData && (
              <ChartTooltip left={`${(paddingX + ((hoveredIdx + 0.5) / filled.length) * chartWidth) / 10}%`}>
                <div style={{ fontWeight: 600, marginBottom: '8px', borderBottom: '1px solid var(--border-color)', paddingBottom: '4px', fontSize: '13px' }}>
                  {hoveredData.period}
                </div>
                {metric === 'tokens' ? (
                  <>
                    <TooltipRow label={t('Input:')} labelColor="#94a3b8">
                      <span style={{ fontWeight: 600 }}>{formatNumber(hInput)}</span>
                    </TooltipRow>
                    <TooltipRow label={t('Cached:')} labelColor="var(--color-green)">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {value(hoveredData.prompt_tokens) > 0 && (
                          <span style={{ fontSize: '10px', color: 'var(--color-green)', opacity: 0.8 }}>
                            ({((hCached / value(hoveredData.prompt_tokens)) * 100).toFixed(1)}%)
                          </span>
                        )}
                        <span style={{ fontWeight: 600 }}>{formatNumber(hCached)}</span>
                      </div>
                    </TooltipRow>
                    <TooltipRow label={t('Output:')} labelColor="var(--color-blue)">
                      <span style={{ fontWeight: 600 }}>{formatNumber(hOutput)}</span>
                    </TooltipRow>
                    <TooltipDivider />
                    <TooltipRow label={t('Total Tokens:')}>
                      <span style={{ fontWeight: 800 }}>{formatNumber(value(hoveredData.total_tokens))}</span>
                    </TooltipRow>
                    {hoveredData.total_cost_usd !== null && value(hoveredData.total_cost_usd) > 0 && (
                      <TooltipRow label={t('Est. Cost:')} labelColor="#f472b6">
                        <span style={{ fontWeight: 800, color: '#f472b6' }}>{formatCost(hoveredData.total_cost_usd)}</span>
                      </TooltipRow>
                    )}
                  </>
                ) : (
                  <>
                    <TooltipRow label={t('Input Cost:')} labelColor="#d97706">
                      <span style={{ fontWeight: 600 }}>{formatCost(hoveredData.input_cost_usd)}</span>
                    </TooltipRow>
                    <TooltipRow label={t('Output Cost:')} labelColor="#a855f7">
                      <span style={{ fontWeight: 600 }}>{formatCost(hoveredData.output_cost_usd)}</span>
                    </TooltipRow>
                    <TooltipDivider />
                    <TooltipRow label={t('Total Cost:')}>
                      <span style={{ fontWeight: 800 }}>{formatCost(hoveredData.total_cost_usd)}</span>
                    </TooltipRow>
                    <TooltipRow label={t('Tokens:')}>
                      <span style={{ fontWeight: 600 }}>{formatNumber(value(hoveredData.total_tokens))}</span>
                    </TooltipRow>
                  </>
                )}
                <TooltipRow label={t('Requests:')} labelColor="var(--color-pink)">
                  <span style={{ fontWeight: 600, color: 'var(--color-pink)' }}>{formatNumber(hoveredData.requests)}</span>
                </TooltipRow>
              </ChartTooltip>
            )}

            <svg
              viewBox="0 0 1000 200"
              preserveAspectRatio="none"
              style={{ width: '100%', height: '220px', overflow: 'visible' }}
            >
              <defs>
                <linearGradient id="grad-tokens-input" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#94a3b8" stopOpacity="0.85" />
                  <stop offset="100%" stopColor="#94a3b8" stopOpacity="0.3" />
                </linearGradient>
                <linearGradient id="grad-tokens-cached" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-green)" stopOpacity="0.85" />
                  <stop offset="100%" stopColor="var(--color-green)" stopOpacity="0.3" />
                </linearGradient>
                <linearGradient id="grad-tokens-output" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-blue)" stopOpacity="0.85" />
                  <stop offset="100%" stopColor="var(--color-blue)" stopOpacity="0.3" />
                </linearGradient>
                <linearGradient id="grad-cost-input" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#d97706" stopOpacity="0.85" />
                  <stop offset="100%" stopColor="#d97706" stopOpacity="0.3" />
                </linearGradient>
                <linearGradient id="grad-cost-output" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#a855f7" stopOpacity="0.85" />
                  <stop offset="100%" stopColor="#a855f7" stopOpacity="0.3" />
                </linearGradient>
              </defs>
              {[0, 0.25, 0.5, 0.75, 1].map(tick => (
                <line
                  key={tick}
                  x1="0" y1={200 - tick * 200}
                  x2="1000" y2={200 - tick * 200}
                  stroke="var(--chart-grid)"
                  strokeWidth="1"
                />
              ))}

              {/* Stacked Bars */}
              {(() => {
                const barSlot = chartWidth / filled.length;
                const barW = barSlot * 0.65;
                const radius = Math.min(3, barW / 4);

                const roundedRect = (x: number, y: number, w: number, h: number, rTop: number, rBot: number) => {
                  if (h <= 0) return '';
                  const t = Math.min(rTop, h / 2);
                  const b = Math.min(rBot, h / 2);
                  return `M ${x + t},${y} L ${x + w - t},${y} Q ${x + w},${y} ${x + w},${y + t} L ${x + w},${y + h - b} Q ${x + w},${y + h} ${x + w - b},${y + h} L ${x + b},${y + h} Q ${x},${y + h} ${x},${y + h - b} L ${x},${y + t} Q ${x},${y} ${x + t},${y} Z`;
                };

                return filled.map((d, i) => {
                  const cx = paddingX + (i + 0.5) / filled.length * chartWidth;
                  const x = cx - barW / 2;
                  const dimmed = hoveredIdx !== null && hoveredIdx !== i;

                  if (metric === 'tokens') {
                    const cached = value(d.cached_tokens);
                    const input = Math.max(0, value(d.prompt_tokens) - cached);
                    const output = value(d.completion_tokens);
                    const total = input + cached + output;
                    if (total === 0) return null;

                    const hOutput = (output / maxTokens) * 200;
                    const hCached = (cached / maxTokens) * 200;
                    const hInput = (input / maxTokens) * 200;

                    const yOutput = 200 - hOutput;
                    const yCached = yOutput - hCached;
                    const yInput = yCached - hInput;

                    const isTop = hInput > 0;
                    const hasMiddle = hCached > 0;
                    const hasBottom = hOutput > 0;

                    return (
                      <g key={i} style={{ opacity: dimmed ? 0.3 : 1, transition: 'opacity 0.2s' }}>
                        {hasBottom && (
                          <path d={roundedRect(x, yOutput, barW, hOutput, hasMiddle ? 0 : isTop ? 0 : radius, radius)} fill="url(#grad-tokens-output)" />
                        )}
                        {hasMiddle && (
                          <path d={roundedRect(x, yCached, barW, hCached, isTop ? 0 : radius, 0)} fill="url(#grad-tokens-cached)" />
                        )}
                        {isTop && (
                          <path d={roundedRect(x, yInput, barW, hInput, radius, 0)} fill="url(#grad-tokens-input)" />
                        )}
                      </g>
                    );
                  } else {
                    const inputCost = value(d.input_cost_usd);
                    const outputCost = value(d.output_cost_usd);
                    const total = inputCost + outputCost;
                    if (total === 0) return null;

                    const hOutput = (outputCost / maxCost) * 200;
                    const hInput = (inputCost / maxCost) * 200;

                    const yOutput = 200 - hOutput;
                    const yInput = yOutput - hInput;

                    const isTop = hInput > 0;
                    const hasBottom = hOutput > 0;

                    return (
                      <g key={i} style={{ opacity: dimmed ? 0.3 : 1, transition: 'opacity 0.2s' }}>
                        {hasBottom && (
                          <path d={roundedRect(x, yOutput, barW, hOutput, isTop ? 0 : radius, radius)} fill="url(#grad-cost-output)" />
                        )}
                        {isTop && (
                          <path d={roundedRect(x, yInput, barW, hInput, radius, 0)} fill="url(#grad-cost-input)" />
                        )}
                      </g>
                    );
                  }
                });
              })()}

              {/* Hover hitboxes */}
              {filled.map((_, i) => {
                const barSlot = chartWidth / filled.length;
                const cx = paddingX + (i + 0.5) / filled.length * chartWidth;
                return (
                  <rect
                    key={i}
                    x={cx - barSlot / 2} y={0}
                    width={barSlot} height={200}
                    fill="transparent"
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={() => setHoveredIdx(i)}
                    onMouseLeave={() => setHoveredIdx(null)}
                  />
                );
              })}

              {/* Requests line */}
              {(() => {
                const points = filled.map((d, i) => {
                  const x = paddingX + (i + 0.5) / filled.length * chartWidth;
                  const y = 200 - (value(d.requests) / maxRequests) * 200;
                  return `${x},${y}`;
                }).join(' ');

                return (
                  <>
                    <polyline
                      points={points}
                      fill="none"
                      stroke="var(--color-pink)"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{ pointerEvents: 'none', opacity: hoveredIdx === null ? 0.6 : 0.3 }}
                    />
                    {showDots && filled.map((d, i) => {
                      const x = paddingX + (i + 0.5) / filled.length * chartWidth;
                      const y = 200 - (value(d.requests) / maxRequests) * 200;
                      return (
                        <circle
                          key={i}
                          cx={x} cy={y} r={hoveredIdx === i ? "5" : "3"}
                          fill="var(--chart-dot-fill)"
                          stroke="var(--color-pink)"
                          strokeWidth={hoveredIdx === i ? "3" : "2"}
                          style={{ pointerEvents: 'none', transition: 'all 0.2s', opacity: hoveredIdx === null || hoveredIdx === i ? 0.6 : 0.3 }}
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
              {filled.map((d, i) => {
                if (filled.length > 12 && i % Math.ceil(filled.length / 12) !== 0 && i !== filled.length - 1) {
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
