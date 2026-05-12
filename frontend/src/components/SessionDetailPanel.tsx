import { useState, useEffect } from 'react'
import { ClickToCopy } from './CopyButton'
import { t } from '../i18n/index.ts'
import { formatCompact, formatCost, formatDuration, formatLatency, formatNumber, formatTime, value, getModelIcon } from '../utils'
import { getModelBadgeBackgroundColor, getModelTextColor } from '../model-badge'
import type { SessionEvaluation, SessionOutcome, SessionSummary } from '../types'

// ─── Shared session detail content (used by both inline and panel) ─────────────

export function SessionDetailContent({
  session,
  onNavigateToLogs,
  showToast,
  onEvaluationUpdate,
  onEvaluationPersisted,
}: {
  session: SessionSummary
  onNavigateToLogs: (session: SessionSummary, filters?: any) => void
  showToast?: (msg: string) => void
  onEvaluationUpdate?: (evaluation: SessionEvaluation | null) => void
  onEvaluationPersisted?: () => void
}) {
  const [localEvaluation, setLocalEvaluation] = useState(session.evaluation)
  useEffect(() => {
    setLocalEvaluation(session.evaluation)
  }, [session.evaluation])

  const updateEvaluation = async (outcome: SessionOutcome | 'reset') => {
    const prev = localEvaluation
    const newEval: SessionEvaluation | null =
      outcome === 'reset'
        ? null
        : {
            session_id: session.session_id,
            outcome,
            source: 'manual',
            confidence: null,
            task_title: null,
            summary: null,
            evidence: ['User marked outcome manually'],
            failure_reason: null,
            evaluated_at: new Date().toISOString(),
          }

    // Optimistic update
    setLocalEvaluation(newEval)
    if (onEvaluationUpdate) onEvaluationUpdate(newEval)

    try {
      let response: Response
      if (outcome === 'reset') {
        response = await fetch(`/sessions/${encodeURIComponent(session.session_id)}/evaluation`, {
          method: 'DELETE',
        })
      } else {
        response = await fetch(`/sessions/${encodeURIComponent(session.session_id)}/evaluation`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            outcome,
            source: 'manual',
            evidence: ['User marked outcome manually'],
          }),
        })
      }
      if (!response.ok) throw new Error('Failed to update evaluation')
      onEvaluationPersisted?.()
    } catch {
      setLocalEvaluation(prev) // Revert on error
      if (onEvaluationUpdate) onEvaluationUpdate(prev)
      if (showToast) showToast('Failed to update evaluation')
    }
  }

  const outcomeLabels: Record<string, string> = { solved: 'Solved', partial: 'Partial', failed: 'Failed', stuck: 'Stuck', no_op: 'No-op' }

  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '20px', width: '100%' }}>
      <div style={{ display: 'flex', gap: '32px', flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ minWidth: '140px' }}>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Session ID')}</div>
          <div style={{ fontFamily: 'monospace', fontSize: '12px', wordBreak: 'break-all', maxWidth: '320px', color: 'var(--text-primary)' }}>
            {showToast ? (
              <ClickToCopy text={session.session_id} onCopy={showToast}>
                {session.session_id}
              </ClickToCopy>
            ) : (
              <span style={{ userSelect: 'all' }}>{session.session_id}</span>
            )}
          </div>
        </div>

        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Timeline')}</div>
          <div style={{ fontSize: '12px', color: 'var(--text-primary)' }}>
            <div style={{ fontWeight: 600 }}>{formatTime(session.started)}</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>{formatDuration(session.duration_s)} {t('duration')}</div>
          </div>
        </div>

        {'model' in session && session.model && (
          <div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Model')}</div>
            <div style={{
              padding: '4px 6px',
              borderRadius: '6px',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '11px',
              backgroundColor: getModelBadgeBackgroundColor(session.model),
              color: getModelTextColor(session.model),
              fontWeight: 600
            }} title={session.model}>
              {getModelIcon(session.model)}
              <span style={{
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                maxWidth: '160px'
              }}>
                {session.model}
              </span>
            </div>
          </div>
        )}

        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Cache Hit Rate')}</div>
          <div style={{ width: '120px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
              <span style={{ fontWeight: 700, color: 'var(--color-green)' }}>{session.prompt_tokens > 0 ? Math.round((session.cached_tokens / session.prompt_tokens) * 100) : 0}%</span>
              <span style={{ color: 'var(--text-muted)' }}>{formatCompact(session.cached_tokens)} {t('tokens')}</span>
            </div>
            <div style={{ height: '6px', background: 'var(--progress-bg)', borderRadius: '3px', overflow: 'hidden', border: '1px solid var(--border-color)' }}>
              <div style={{ height: '100%', background: 'var(--color-green)', width: `${session.prompt_tokens > 0 ? (session.cached_tokens / session.prompt_tokens) * 100 : 0}%` }} />
            </div>
          </div>
        </div>

        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Avg Throughput')}</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
            <span style={{ fontSize: '18px', fontWeight: 800, color: 'var(--text-primary)' }}>
              {session.latency_sum_ms > 0 ? ((session.completion_tokens * 1000) / session.latency_sum_ms).toFixed(1) : '0.0'}
            </span>
            <span style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: 600 }}>t/s</span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '20px' }}>
          <div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Requests')}</div>
            <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)' }}>{formatNumber(session.request_count)}</div>
            {session.failed_requests > 0 && (
              <div
                style={{ fontSize: '10px', color: 'var(--color-red)', marginTop: '2px', fontWeight: 600, cursor: 'pointer', textDecoration: 'underline' }}
                onClick={(e) => { e.stopPropagation(); onNavigateToLogs(session, { onlyFailed: true }); }}
                title={t('View failed requests in logs')}
              >
                {session.failed_requests} {t('failed')}
              </div>
            )}
          </div>
          <div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Success Rate')}</div>
            <div
              style={{ fontSize: '14px', fontWeight: 700, color: session.failed_requests === 0 ? 'var(--color-green)' : 'var(--color-orange)', cursor: session.failed_requests > 0 ? 'pointer' : 'default', textDecoration: session.failed_requests > 0 ? 'underline' : 'none' }}
              onClick={(e) => { if (session.failed_requests > 0) { e.stopPropagation(); onNavigateToLogs(session, { onlyFailed: true }); } }}
              title={session.failed_requests > 0 ? t('View failed requests in logs') : undefined}
            >
              {session.request_count > 0 ? Math.round((session.successful_requests / session.request_count) * 100) : 0}%
            </div>
            {session.failed_requests > 0 && (
              <div
                className="stat-label"
                style={{ marginTop: '4px', display: 'flex', gap: '6px', textTransform: 'none' }}
              >
                {value(session.status_429) > 0 && (
                  <span
                    className="status-link"
                    onClick={(e) => { e.stopPropagation(); onNavigateToLogs(session, { status429: true }); }}
                  >
                    429: {session.status_429}
                  </span>
                )}
                {value(session.status_5xx) > 0 && (
                  <span
                    className="status-link"
                    onClick={(e) => { e.stopPropagation(); onNavigateToLogs(session, { status5xx: true }); }}
                  >
                    5xx: {session.status_5xx}
                  </span>
                )}
                {value(session.status_4xx) > 0 && (
                  <span
                    className="status-link"
                    onClick={(e) => { e.stopPropagation(); onNavigateToLogs(session, { status4xx: true }); }}
                  >
                    4xx: {session.status_4xx}
                  </span>
                )}
              </div>
            )}
          </div>
          <div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Cost')}</div>
            <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--color-green)' }}>{formatCost(session.total_cost_usd)}</div>
          </div>
        </div>

        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Performance')}</div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <div style={{ background: 'var(--badge-success-bg)', color: 'var(--badge-success-text)', padding: '2px 10px', borderRadius: '4px', fontSize: '11px', fontWeight: 600 }}>
              {formatLatency(session.avg_ttft_ms)} TTFT
            </div>
            <div style={{ background: 'var(--badge-error-bg)', color: 'var(--badge-error-text)', padding: '2px 10px', borderRadius: '4px', fontSize: '11px', fontWeight: 600 }}>
              {formatLatency(session.avg_latency_ms)} Latency
            </div>
          </div>
        </div>

        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Token Usage')}</div>
          <div style={{ width: '160px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
              <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{formatCompact(session.total_tokens)}</span>
              <span style={{ color: 'var(--text-muted)' }}>{t('total')}</span>
            </div>
            <div className="has-tooltip" style={{ borderBottom: 'none', display: 'block', width: '100%' }}>
              {(() => {
                const promptUncached = Math.max(0, value(session.prompt_tokens) - value(session.cached_tokens));
                const barTotal = value(session.total_tokens) || 1;
                return (
                  <>
                    <div style={{ height: '6px', background: 'var(--progress-bg)', borderRadius: '3px', overflow: 'hidden', border: '1px solid var(--border-color)', display: 'flex', width: '100%' }}>
                      <div style={{ height: '100%', background: 'var(--color-green)', width: `${(value(session.cached_tokens) / barTotal) * 100}%` }} />
                      <div style={{ height: '100%', background: 'var(--color-blue)', width: `${(promptUncached / barTotal) * 100}%`, opacity: 0.7 }} />
                      <div style={{ height: '100%', background: 'var(--color-purple)', width: `${(value(session.completion_tokens) / barTotal) * 100}%` }} />
                    </div>
                    <div className="tooltip-text" style={{ width: '180px', marginLeft: '-90px' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--color-green)' }}>● {t('Cached')}:</span>
                          <span>{formatNumber(session.cached_tokens)}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--color-blue)' }}>● {t('Input')}:</span>
                          <span>{formatNumber(promptUncached)}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--color-purple)' }}>● {t('Output')}:</span>
                          <span>{formatNumber(session.completion_tokens)}</span>
                        </div>
                      </div>
                    </div>
                  </>
                );
              })()}
            </div>
            <div style={{ display: 'flex', gap: '8px', marginTop: '6px', fontSize: '9px', fontWeight: 600 }}>
              <span style={{ color: 'var(--color-green)' }}>● {t('Cache')}</span>
              <span style={{ color: 'var(--color-blue)' }}>● {t('In')}</span>
              <span style={{ color: 'var(--color-purple)' }}>● {t('Out')}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="session-eval-section">
        <div className="session-eval-label">{t('Evaluation')}</div>
        {localEvaluation && (
          <div style={{ marginBottom: '8px' }}>
            <span className={`session-outcome-badge session-outcome-${localEvaluation.outcome}`}>
              {outcomeLabels[localEvaluation.outcome] || localEvaluation.outcome}
            </span>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '8px' }}>
              {t('Source')}: {localEvaluation.source === 'manual' ? t('Manual') : localEvaluation.source === 'heuristic' ? t('Heuristic') : t('LLM')}
            </span>
            {localEvaluation.evidence && localEvaluation.evidence.length > 0 && (
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                {localEvaluation.evidence.join(', ')}
              </div>
            )}
          </div>
        )}
        <div className="session-eval-buttons">
          {(['solved', 'partial', 'failed', 'stuck', 'no_op'] as const).map((o) => (
            <button
              key={o}
              className={`session-eval-btn${localEvaluation?.outcome === o ? ' active' : ''}`}
              onClick={() => updateEvaluation(o)}
            >
              {outcomeLabels[o]}
            </button>
          ))}
          <button
            className="session-eval-btn session-eval-btn-reset"
            onClick={() => updateEvaluation('reset')}
          >
            {t('Reset')}
          </button>
        </div>
      </div>
    </div>
  )
}
