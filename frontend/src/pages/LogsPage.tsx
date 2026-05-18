import { useState, useEffect } from 'react'
import { useApp } from '../contexts/AppContext'
import { useDashboardData } from '../hooks/useDashboardData'
import { useLogsData } from '../hooks/useLogsData'
import { useSessionSelectorData } from '../hooks/useSessionSelectorData'
import { ModelSelector } from '../ModelSelector'
import { SessionSelector } from '../components/SessionSelector'
import { ClickToCopy } from '../components/CopyButton'
import { t } from '../i18n/index.ts'
import {
  formatCost, formatLatency, formatNumber, formatRate, formatTime,
  value, getProviderColor, getModelIcon, shortSessionId,
} from '../utils'
import { getModelBadgeBackgroundColor, getModelTextColor } from '../model-badge'
import type { ActiveFilter, DateRangeOption } from '../types'

type Props = {
  initialSessionFilter?: string | null
  initialActiveFilter?: ActiveFilter | null
}

export function LogsPage({ initialSessionFilter, initialActiveFilter }: Props) {
  // Read initial filters from sessionStorage (set by DashboardPage navigation)
  const storedFilters = (() => {
    try {
      const raw = sessionStorage.getItem('llm-tracker-logs-filters')
      if (raw) {
        sessionStorage.removeItem('llm-tracker-logs-filters')
        return JSON.parse(raw)
      }
    } catch { /* ignore */ }
    return null
  })()

  const effectiveSessionFilter = initialSessionFilter ?? storedFilters?.sessionFilter ?? null
  const effectiveActiveFilter = initialActiveFilter ?? storedFilters?.activeFilter ?? null

  const { showToast, configParsed, requestUsageRefresh } = useApp()

  // Dashboard data for filters and shared state
  const {
    summary, sources,
    activeFilter, setActiveFilter, activeSource, setActiveSource,
    dateRange, setDateRange, customSince, setCustomSince, customUntil, setCustomUntil,
    providerColors,
  } = useDashboardData()

  // Session filter state (local to logs view)
  const [sessionFilter, setSessionFilter] = useState<string | null>(effectiveSessionFilter)

  // Apply initial active filter from props
  useEffect(() => {
    if (effectiveActiveFilter) {
      setActiveFilter(effectiveActiveFilter)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Logs data hook
  const {
    usageRows, totalLogs, totalPages,
    limit, setLimit, page, setPage, jumpPage, setJumpPage, resetPage,
    logsLoading, expandedRow, setExpandedRow,
    modelColWidth, handleResizeStart,
  } = useLogsData({ activeFilter, activeSource, sessionFilter, dateRange, customSince, customUntil })

  // Sessions data for the session filter dropdown
  const { sessions } = useSessionSelectorData({ activeSource, dateRange, customSince, customUntil })

  return (
    <div className="logs-page">
      <div className="filter-bar">
        <div className="filter-group">
          <div className="filter-label">{t('Model')}</div>
          <ModelSelector
            activeFilter={activeFilter}
            summary={summary}
            providerColors={providerColors}
            onChange={(f) => { setActiveFilter(f); resetPage(); }}
          />
          </div>

        <div className="filter-group">
          <div className="filter-label">{t('Source')}</div>
          <select
            className="input-plain"
            value={activeSource || ''}
            onChange={(e) => { setActiveSource(e.target.value || null); resetPage(); }}
          >
            <option value="">{t('All Sources')}</option>
            {sources.map(source => (
              <option key={source} value={source}>{source}</option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <div className="filter-label">{t('Session')}</div>
          <SessionSelector
            sessions={sessions}
            sessionFilter={sessionFilter}
            onChange={(id) => { setSessionFilter(id); resetPage(); }}
            sourceColors={providerColors}
          />
        </div>

        <div className="filter-group">
          <div className="filter-label">{t('Date Range')}</div>
          <select
            className="input-plain"
            value={dateRange}
            onChange={(e) => setDateRange(e.target.value as DateRangeOption)}
          >
            <option value="24h">{t('Last 24 Hours')}</option>
            <option value="7d">{t('Last 7 Days')}</option>
            <option value="30d">{t('Last 30 Days')}</option>
            <option value="all">{t('All Time')}</option>
            <option value="custom">{t('Custom Range')}</option>
          </select>
        </div>

        {dateRange === 'custom' && (
          <>
            <div className="filter-group">
              <div className="filter-label">{t('Since')}</div>
              <input
                type="datetime-local"
                className="input-plain"
                value={customSince.split('.')[0]}
                onChange={(e) => { setCustomSince(new Date(e.target.value).toISOString()); resetPage(); }}
                />                    </div>
            <div className="filter-group">
              <div className="filter-label">{t('Until')}</div>
              <input
                type="datetime-local"
                className="input-plain"
                value={customUntil.split('.')[0]}
                onChange={(e) => { setCustomUntil(new Date(e.target.value).toISOString()); resetPage(); }}
                />                    </div>
          </>
        )}

        <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px', alignItems: 'center', alignSelf: 'flex-end' }}>
           <button
            className="btn-ghost btn-refresh"
            onClick={requestUsageRefresh}
            aria-label={t('Refresh')}
            title={t('Refresh')}
           >
             <span className="refresh-icon">&#x21bb;</span>
           </button>
           <button
            style={{ padding: '8px 16px', background: 'var(--tab-toggle-bg)', color: 'var(--text-secondary)', borderRadius: '8px', fontSize: '12px', fontWeight: 600, border: '1px solid var(--border-color)' }}
            onClick={() => {
              setActiveFilter(null)
              setActiveSource(null)
              setSessionFilter(null)
              setDateRange('24h')
              setCustomSince('')
              setCustomUntil('')
              setPage(1)
            }}
           >
             {t('Reset')}
           </button>
        </div>
      </div>

      {sessionFilter && (
        <div style={{ marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="badge request-log-session-filter-badge" title={sessionFilter}>
            {t('Session')}: {shortSessionId(sessionFilter)}
            <button
              className="btn-ghost"
              aria-label={t('Clear session filter')}
              onClick={() => { setSessionFilter(null); resetPage() }}
              style={{ padding: '2px 6px', fontSize: '11px' }}
            >
              &times;
            </button>
          </span>
        </div>
      )}

      <div className="panel">
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: '120px' }}>{t('Time')}</th>
                <th style={{ width: modelColWidth, padding: '12px 8px', position: 'relative' }}>
                  {t('Model')}
                  <div
                    onMouseDown={handleResizeStart}
                    style={{
                      position: 'absolute',
                      right: 0,
                      top: 0,
                      bottom: 0,
                      width: '3px',
                      cursor: 'col-resize',
                      userSelect: 'none',
                      backgroundColor: 'rgba(128,128,128,0.2)',
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(128,128,128,0.5)'}
                    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'rgba(128,128,128,0.2)'}
                  />
                </th>
                <th style={{ width: '120px', padding: '12px 8px' }}>{t('Provider')}</th>
                <th style={{ width: '110px', padding: '12px 8px' }}>{t('Source')}</th>
                <th style={{ width: '120px', padding: '12px 8px' }}>{t('Session')}</th>
                <th style={{ minWidth: '140px' }}>{t('Input (Prompt)')}</th>
                <th style={{ minWidth: '120px' }}>{t('Output')}</th>
                <th style={{ minWidth: '100px' }}>{t('Cost')}</th>
                <th style={{ padding: '12px 8px' }}>
                  <div className="has-tooltip">
                    TTFT / Latency
                    <div className="tooltip-text">
                      <b>Claude Code:</b> {t('Claude Code: No TTFT')}<br/>
                      <b>Gemini CLI:</b> {t('Gemini CLI: Time to first chunk')}<br/>
                      <b>Codex:</b> {t('Codex: Actual TTFT')}<br/>
                      <b>Proxy:</b> {t('Proxy: Time to first chunk')}
                    </div>
                  </div>
                </th>
                <th style={{ width: '80px' }}>{t('Status')}</th>
              </tr>
            </thead>
            <tbody>
              {logsLoading ? (
                Array.from({ length: 5 }, (_, i) => (
                  <tr key={`skeleton-${i}`}>
                    <td><div className="skeleton" style={{ width: 90, height: 14 }} /></td>
                    <td><div className="skeleton" style={{ width: 120, height: 24, borderRadius: 6 }} /></td>
                    <td><div className="skeleton" style={{ width: 70, height: 20, borderRadius: 4 }} /></td>
                    <td><div className="skeleton" style={{ width: 60, height: 20, borderRadius: 4 }} /></td>
                    <td><div className="skeleton" style={{ width: 80, height: 20, borderRadius: 999 }} /></td>
                    <td><div className="skeleton" style={{ width: 80, height: 14 }} /></td>
                    <td><div className="skeleton" style={{ width: 60, height: 14 }} /></td>
                    <td><div className="skeleton" style={{ width: 50, height: 14 }} /></td>
                    <td><div className="skeleton" style={{ width: 100, height: 20, borderRadius: 999 }} /></td>
                    <td><div className="skeleton" style={{ width: 40, height: 20, borderRadius: 6 }} /></td>
                  </tr>
                ))
              ) : usageRows.map(row => (
                <>
                <tr
                  key={row.id}
                  className={`expandable-row${expandedRow === row.id ? ' expanded' : ''}`}
                  onClick={() => setExpandedRow(expandedRow === row.id ? null : row.id)}
                >
                  <td style={{ color: 'var(--text-secondary)' }}>{formatTime(row.ts)}</td>
                  <td style={{ padding: '8px' }}>
                    <div style={{
                      padding: '4px 6px',
                      borderRadius: '6px',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '11px',
                      backgroundColor: getModelBadgeBackgroundColor(row.model),
                      color: getModelTextColor(row.model),
                      maxWidth: modelColWidth - 10,
                      fontWeight: 600,
                      cursor: 'pointer'
                    }} title={row.model}>
                      {getModelIcon(row.model)}
                      <span style={{
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap'
                      }}>
                        {row.model}
                      </span>
                    </div>
                  </td>
                  <td style={{ padding: '8px' }}>
                    <div style={{
                      padding: '2px 8px',
                      borderRadius: '4px',
                      display: 'inline-flex',
                      fontSize: '10px',
                      backgroundColor: getProviderColor(row.provider, providerColors) + '22',
                      color: getProviderColor(row.provider, providerColors),
                      width: 'fit-content',
                      border: `1px solid ${getProviderColor(row.provider, providerColors)}44`,
                      fontWeight: 600
                    }}>
                      {row.provider}
                    </div>
                  </td>
                  <td style={{ padding: '8px' }}>
                    <div style={{
                      padding: '2px 8px',
                      borderRadius: '4px',
                      display: 'inline-flex',
                      fontSize: '10px',
                      backgroundColor: 'var(--tab-toggle-bg)',
                      color: 'var(--text-secondary)',
                      width: 'fit-content',
                      border: '1px solid var(--border-color)',
                      fontWeight: 600
                    }}>
                      {row.client_source || '—'}
                    </div>
                  </td>
                  <td className="request-log-session-cell">
                    {row.session_id ? (() => {
                      const sessionId = row.session_id
                      return (
                        <div className="request-log-session-actions">
                          <button
                            type="button"
                            className="request-log-session-filter"
                            title={sessionId}
                            aria-label={`${t('Filter logs by session')}: ${sessionId}`}
                            onClick={(e) => { e.stopPropagation(); setSessionFilter(sessionId); resetPage() }}
                          >
                            {shortSessionId(sessionId)}
                          </button>
                        </div>
                      )
                    })() : (
                      <span className="request-log-session-empty">&mdash;</span>
                    )}
                  </td>                          <td style={{ verticalAlign: 'top' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <div style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>
                        {formatNumber(row.prompt_tokens)}
                        <span style={{ fontSize: '10px', fontWeight: 400, marginLeft: '4px', color: 'var(--text-secondary)' }}>{t('tokens')}</span>
                        {value(row.prompt_length) > 0 && (
                          <span style={{ fontSize: '10px', fontWeight: 400, marginLeft: '6px', color: 'var(--text-muted)' }}>
                            {t('(Prompt:')} {formatNumber(row.prompt_length)}{t(' chars)')}
                          </span>
                        )}
                      </div>
                      {value(row.cached_tokens) > 0 && (
                        <div style={{ fontSize: '9px', color: 'var(--color-green)', fontWeight: 700 }}>
                          {t('Cache read')} {formatNumber(row.cached_tokens)} ({Math.round((value(row.cached_tokens) / (value(row.prompt_tokens) || 1)) * 100)}%)
                        </div>
                      )}
                    </div>
                    <div className="has-tooltip" style={{ width: '100%', borderBottom: 'none' }}>
                      {(() => {
                        const promptUncached = Math.max(0, value(row.prompt_tokens) - value(row.cached_tokens));
                        const total = value(row.total_tokens) || 1;
                        return (
                          <>
                            <div style={{
                              width: '100%',
                              height: '3px',
                              background: 'var(--progress-bg)',
                              borderRadius: '2px',
                              marginTop: '4px',
                              overflow: 'hidden',
                              border: '1px solid var(--border-color)',
                              display: 'flex'
                            }}>
                              <div style={{ height: '100%', background: 'var(--color-green)', width: `${(value(row.cached_tokens) / total) * 100}%` }} />
                              <div style={{ height: '100%', background: 'var(--color-blue)', width: `${(promptUncached / total) * 100}%`, opacity: 0.7 }} />
                              <div style={{ height: '100%', background: 'var(--color-purple)', width: `${(value(row.completion_tokens) / total) * 100}%` }} />
                            </div>
                            <div className="tooltip-text">
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                  <span style={{ color: 'var(--color-green)' }}>&bull; {t('Cached')}:</span>
                                  <span style={{ fontWeight: 600 }}>{formatNumber(row.cached_tokens)}</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                  <span style={{ color: 'var(--color-blue)' }}>&bull; {t('Input')}:</span>
                                  <span style={{ fontWeight: 600 }}>{formatNumber(promptUncached)}</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                  <span style={{ color: 'var(--color-purple)' }}>&bull; {t('Output')}:</span>
                                  <span style={{ fontWeight: 600 }}>{formatNumber(row.completion_tokens)}</span>
                                </div>
                              </div>
                            </div>
                          </>
                        );
                      })()}
                    </div>
                  </td>
                  <td style={{ fontWeight: 600, color: 'var(--color-blue)', verticalAlign: 'top' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <div>{formatNumber(row.completion_tokens)}</div>
                      {value(row.reasoning_tokens) > 0 && (
                        <div style={{ fontSize: '9px', color: 'var(--text-secondary)', fontWeight: 700 }}>
                          {t('Reasoning')} {formatNumber(row.reasoning_tokens)} ({Math.round((value(row.reasoning_tokens) / (value(row.completion_tokens) || 1)) * 100)}%)
                        </div>
                      )}
                    </div>
                    {value(row.reasoning_tokens) > 0 && (
                      <div
                        style={{
                          width: '100%',
                          height: '3px',
                          background: 'var(--progress-bg)',
                          borderRadius: '2px',
                          marginTop: '4px',
                          overflow: 'hidden',
                          border: '1px solid var(--border-color)',
                          display: 'flex'
                        }}
                      >
                        {value(row.reasoning_tokens) > 0 && (
                          <div
                            title={`Reasoning: ${formatNumber(row.reasoning_tokens)} tokens`}
                            style={{
                              width: `${(value(row.reasoning_tokens) / (value(row.completion_tokens) || 1)) * 100}%`,
                              height: '100%',
                              background: '#64748b'
                            }}
                          />
                        )}
                      </div>
                    )}
                  </td>
                  <td style={{ verticalAlign: 'top' }}>
                    {(() => {
                      const total = value(row.total_cost_usd);
                      if (total === 0) return <div style={{ color: 'var(--color-green)', fontWeight: 500 }}>$0.00</div>;

                      const prompt = value(row.prompt_tokens);
                      const cached = value(row.cached_tokens);
                      const inputCost = value(row.input_cost_usd);
                      const outputCost = value(row.output_cost_usd);

                      const cacheRatio = prompt > 0 ? (cached / prompt) : 0;
                      const cacheCost = inputCost * cacheRatio;
                      const actualInputCost = inputCost - cacheCost;

                      const uncachedTokens = Math.max(0, prompt - cached);
                      const completionTokens = value(row.completion_tokens);

                      const modelConfig = configParsed?.providers?.[row.provider]?.models?.[row.model]?.cost || configParsed?.models?.[row.model]?.cost;

                      return (
                        <div className="has-tooltip" style={{ borderBottom: 'none' }}>
                          <div style={{ color: 'var(--color-green)', fontWeight: 500, cursor: 'pointer' }}>
                            {formatCost(total)}
                          </div>
                          <div className="tooltip-text" style={{ width: '200px', marginLeft: '-100px' }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                                <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>{t('Input:')}</span>
                                <div style={{ textAlign: 'right' }}>
                                  <div>{formatCost(actualInputCost)}</div>
                                  {modelConfig?.input !== undefined && (
                                    <div style={{ fontSize: '9px', color: 'rgba(255, 255, 255, 0.4)' }}>{formatNumber(uncachedTokens)} tokens x {formatRate(modelConfig.input)}</div>
                                  )}
                                </div>
                              </div>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                                <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>{t('Output:')}</span>
                                <div style={{ textAlign: 'right' }}>
                                  <div>{formatCost(outputCost)}</div>
                                  {modelConfig?.output !== undefined && (
                                    <div style={{ fontSize: '9px', color: 'rgba(255, 255, 255, 0.4)' }}>{formatNumber(completionTokens)} tokens x {formatRate(modelConfig.output)}</div>
                                  )}
                                </div>
                              </div>
                              {cacheCost > 0 && (
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                                  <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>{t('Cache:')}</span>
                                  <div style={{ textAlign: 'right' }}>
                                    <div style={{ color: 'var(--color-green)' }}>{formatCost(cacheCost)}</div>
                                    {modelConfig?.cacheRead !== undefined && (
                                      <div style={{ fontSize: '9px', color: 'rgba(255, 255, 255, 0.4)' }}>{formatNumber(cached)} tokens x {formatRate(modelConfig.cacheRead)}</div>
                                    )}
                                  </div>
                                </div>
                              )}
                              <div style={{ marginTop: '4px', paddingTop: '4px', borderTop: '1px solid #334155', display: 'flex', justifyContent: 'space-between', color: 'white' }}>
                                <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>{t('Total:')}</span>
                                <span>{formatCost(total)}</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })()}
                  </td>
                  <td style={{ padding: '8px' }}>
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      {value(row.ttft_ms) > 0 && (
                        <div style={{
                          backgroundColor: 'var(--badge-success-bg)',
                          color: 'var(--badge-success-text)',
                          padding: '2px 12px',
                          borderRadius: '999px',
                          fontSize: '12px',
                          whiteSpace: 'nowrap'
                        }} title={t('Time To First Token')}>
                          {formatLatency(row.ttft_ms)}
                        </div>
                      )}
                      <div style={{
                        backgroundColor: 'var(--badge-error-bg)',
                        color: 'var(--badge-error-text)',
                        padding: '2px 12px',
                        borderRadius: '999px',
                        fontSize: '12px',
                        whiteSpace: 'nowrap'
                      }} title={t('Total Latency')}>
                        {formatLatency(row.latency_ms)}
                      </div>
                    </div>
                  </td>
                  <td>
                    <span className={`badge ${value(row.status) >= 400 ? 'badge-error' : 'badge-success'}`}>
                      {row.status ?? '200'}
                    </span>
                  </td>
                </tr>
                {expandedRow === row.id && (
                  <tr className="expanded-row">
                    <td colSpan={10}>
                      <div className="expanded-detail">
                        {row.session_id && (
                          <div className="detail-group">
                            <span className="detail-label">{t('Session ID')}</span>
                            <span className="detail-value">
                              <ClickToCopy text={row.session_id} onCopy={showToast}>
                                {row.session_id}
                              </ClickToCopy>
                            </span>
                          </div>
                        )}
                        <div className="detail-group">
                          <span className="detail-label">{t('Request ID')}</span>
                          <span className="detail-value">#{row.id}</span>
                        </div>
                        <div className="detail-group">
                          <span className="detail-label">{t('Full Timestamp')}</span>
                          <span className="detail-value">{row.ts}</span>
                        </div>
                        <div className="detail-group">
                          <span className="detail-label">{t('Endpoint')}</span>
                          <span className="detail-value">{row.endpoint}</span>
                        </div>
                        <div className="detail-group">
                          <span className="detail-label">{t('Total Tokens')}</span>
                          <span className="detail-value">{formatNumber(row.total_tokens ?? (value(row.prompt_tokens) + value(row.completion_tokens)))}</span>
                        </div>
                        {value(row.tool_tokens) > 0 && (
                          <div className="detail-group">
                            <span className="detail-label">{t('Tool Tokens')}</span>
                            <span className="detail-value">{formatNumber(row.tool_tokens)}</span>
                          </div>
                        )}
                        {value(row.prompt_length) > 0 && (
                          <div className="detail-group">
                            <span className="detail-label">{t('Prompt Length')}</span>
                            <span className="detail-value">{formatNumber(row.prompt_length)} {t('chars')}</span>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
                </>
              ))}
              {usageRows.length === 0 && !logsLoading && (
                <tr>
                  <td colSpan={10} style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                    {t('No requests found for the selected filters.')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div style={{
          padding: '16px 24px',
          borderTop: '1px solid var(--border-color)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'var(--surface-hover)'
        }}>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            {t('Showing')} <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{Math.min(totalLogs, (page - 1) * limit + 1)}-{Math.min(totalLogs, page * limit)}</span> {t('of')} <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{totalLogs}</span> {t('logs')}
          </div>

          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              disabled={page === 1}
              onClick={() => setPage(p => Math.max(1, p - 1))}
              className="pagination-btn"
              style={{
                cursor: page === 1 ? 'not-allowed' : 'pointer',
                opacity: page === 1 ? 0.5 : 1
              }}
            >
              &#x25c0; {t('Prev')}
            </button>

            <div style={{ display: 'flex', gap: '4px' }}>
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                let pageNum = i + 1;
                if (totalPages > 5 && page > 3) {
                  pageNum = page - 3 + i + 1;
                  if (pageNum > totalPages) pageNum = totalPages - (4 - i);
                }
                return (
                  <button
                    key={pageNum}
                    onClick={() => setPage(pageNum)}
                    style={{
                      width: '32px',
                      height: '32px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      borderRadius: '6px',
                      fontSize: '12px',
                      fontWeight: 700,
                      background: page === pageNum ? 'var(--color-blue)' : 'var(--input-bg)',
                      color: page === pageNum ? '#fff' : 'var(--text-primary)',
                      border: '1px solid var(--border-color)',
                      cursor: 'pointer'
                    }}
                  >
                    {pageNum}
                  </button>
                );
              })}
            </div>

            <button
              disabled={page === totalPages || totalPages === 0}
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              className="pagination-btn"
              style={{
                cursor: (page === totalPages || totalPages === 0) ? 'not-allowed' : 'pointer',
                opacity: (page === totalPages || totalPages === 0) ? 0.5 : 1
              }}
            >
              {t('Next')} &#x25b6;
            </button>

            <div style={{ marginLeft: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{t('Jump:')}</span>
              <input
                type="text"
                value={jumpPage}
                onChange={(e) => {
                  const val = e.target.value;
                  if (val === '' || /^\d+$/.test(val)) {
                    setJumpPage(val);
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    const p = parseInt(jumpPage);
                    if (!isNaN(p) && p >= 1 && p <= totalPages) {
                      setPage(p);
                      setJumpPage('');
                    }
                  }
                }}
                placeholder={String(page)}
                style={{
                  width: '40px',
                  height: '28px',
                  padding: '0 4px',
                  borderRadius: '4px',
                  border: '1px solid var(--border-color)',
                  fontSize: '12px',
                  textAlign: 'center',
                  outline: 'none'
                }}
              />
            </div>

            <div style={{ marginLeft: '12px', height: '16px', width: '1px', background: 'var(--border-color)' }} />

            <select
              value={limit}
              onChange={(e) => { setLimit(Number(e.target.value)); resetPage(); }}                      style={{
                border: 'none',
                background: 'transparent',
                fontWeight: 700,
                fontSize: '13px',
                color: 'var(--text-primary)',
                outline: 'none',
                cursor: 'pointer'
              }}
            >
              <option value={10}>10 {t('/ page')}</option>
              <option value={25}>25 {t('/ page')}</option>
              <option value={50}>50 {t('/ page')}</option>
              <option value={100}>100 {t('/ page')}</option>
            </select>
          </div>
        </div>
      </div>
    </div>
  )
}
