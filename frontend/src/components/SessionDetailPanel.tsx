import { useState, useEffect, useRef, useCallback } from 'react'
import { ClickToCopy } from './CopyButton'
import { t } from '../i18n/index.ts'
import { useApp } from '../contexts/AppContext'
import { formatCompact, formatCost, formatDuration, formatLatency, formatNumber, formatTime, value, getModelIcon, sessionTaskTitle, resolveTimezone, ToolBadge } from '../utils'
import { getModelBadgeBackgroundColor, getModelTextColor } from '../model-badge'
import type { EvaluatorOption, EvaluatorType, EvaluationJobProgress, SessionEvaluation, SessionOutcome, SessionSummary } from '../types'

// ─── Shared session detail content (used by both inline and panel) ─────────────

type SessionLogFilters = {
  onlyFailed?: boolean
  status429?: boolean
  status5xx?: boolean
  status4xx?: boolean
}

export function SessionDetailContent({
  session,
  onNavigateToLogs,
  showToast,
  onEvaluationUpdate,
  onEvaluationPersisted,
  activeEvaluationJob,
}: {
  session: SessionSummary
  onNavigateToLogs: (session: SessionSummary, filters?: SessionLogFilters) => void
  showToast?: (msg: string) => void
  onEvaluationUpdate?: (evaluation: SessionEvaluation | null) => void
  onEvaluationPersisted?: () => void
  activeEvaluationJob?: EvaluationJobProgress | null
}) {
  const { lang, evaluationEvaluator, evaluationEvaluators, timezone } = useApp()
  const tz = resolveTimezone(timezone)
  const [localEvaluationOverride, setLocalEvaluationOverride] = useState<{ sessionId: string; evaluation: SessionEvaluation | null } | null>(null)
  const [llmEvaluationStatus, setLlmEvaluationStatus] = useState<'idle' | 'queued' | 'running' | 'succeeded' | 'failed'>('idle')
  const [evaluationJobHistory, setEvaluationJobHistory] = useState<EvaluationJobProgress[]>([])
  const [evaluatorCatalog, setEvaluatorCatalog] = useState<EvaluatorOption[]>([])
  const [globalEvaluatorType, setGlobalEvaluatorType] = useState<EvaluatorType>(evaluationEvaluator)
  const [globalEvaluatorAvailable, setGlobalEvaluatorAvailable] = useState(true)
  const [selectedEvaluatorType, setSelectedEvaluatorType] = useState<EvaluatorType>(evaluationEvaluator)
  const [historyLoading, setHistoryLoading] = useState(false)
  const llmEvaluationPollRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const localEvaluation = localEvaluationOverride?.sessionId === session.session_id ? localEvaluationOverride.evaluation : session.evaluation
  const displaySession = { ...session, evaluation: localEvaluation }
  const sessionTitle = sessionTaskTitle(displaySession, lang)
  const setLocalEvaluation = (evaluation: SessionEvaluation | null) => {
    setLocalEvaluationOverride({ sessionId: session.session_id, evaluation })
  }

  useEffect(() => {
    return () => {
      if (llmEvaluationPollRef.current) clearTimeout(llmEvaluationPollRef.current)
    }
  }, [])

  const evaluatorOptions = evaluatorCatalog.length > 0 ? evaluatorCatalog : evaluationEvaluators
  const fallbackEvaluatorOptions: EvaluatorOption[] = evaluatorOptions.length > 0
    ? evaluatorOptions
    : [
        { id: 'codex', label: 'Codex', command: 'codex', available: true },
        { id: 'claude', label: 'Claude Code', command: 'claude', available: true },
      ]
  const availableEvaluators = fallbackEvaluatorOptions
  const selectedEvaluator = availableEvaluators.find((item) => item.id === selectedEvaluatorType)
  const historyRequestRef = useRef(0)
  const selectedEvaluatorAvailable = selectedEvaluator?.available === true
  const globalEvaluator = availableEvaluators.find((item) => item.id === globalEvaluatorType)
  const evaluatorLabel = (evaluatorType?: string | null) => {
    const evaluator = availableEvaluators.find((item) => item.id === evaluatorType)
    return evaluator?.label || (evaluatorType ? evaluatorType : 'Codex')
  }

  const loadEvaluationJobHistory = useCallback(async () => {
    const requestId = ++historyRequestRef.current
    setHistoryLoading(true)
    try {
      const response = await fetch(`/sessions/${encodeURIComponent(session.session_id)}/evaluation-jobs`)
      if (!response.ok) throw new Error('Failed to load evaluation job history')
      const data: {
        jobs: EvaluationJobProgress[]
        evaluators: EvaluatorOption[]
        global_evaluator_type: EvaluatorType
        global_evaluator_available: boolean
      } = await response.json()
      if (requestId !== historyRequestRef.current) return
      setEvaluationJobHistory(data.jobs || [])
      setEvaluatorCatalog(data.evaluators || [])
      setGlobalEvaluatorType(data.global_evaluator_type || evaluationEvaluator)
      setGlobalEvaluatorAvailable(data.global_evaluator_available !== false)
      setSelectedEvaluatorType(data.global_evaluator_type || evaluationEvaluator)
    } catch {
      if (requestId !== historyRequestRef.current) return
      showToast?.('Failed to load evaluation job history')
    } finally {
      if (requestId === historyRequestRef.current) setHistoryLoading(false)
    }
  }, [session.session_id, evaluationEvaluator, showToast])

  useEffect(() => {
    setEvaluationJobHistory([])
    setEvaluatorCatalog([])
    setSelectedEvaluatorType(evaluationEvaluator)
    void loadEvaluationJobHistory()
  }, [session.session_id, evaluationEvaluator, loadEvaluationJobHistory])

  const isLlmEvaluationRunning = llmEvaluationStatus === 'queued' || llmEvaluationStatus === 'running'
  const activeJobStatus = activeEvaluationJob?.status
  const activeJobRunning = activeJobStatus === 'queued' || activeJobStatus === 'running'
  const displayEvaluationRunning = isLlmEvaluationRunning || activeJobRunning
  const progressLabel =
    activeEvaluationJob?.status === 'queued'
      ? `${t('Queued')}${activeEvaluationJob.queue_position ? ` #${activeEvaluationJob.queue_position}` : ''}`
      : activeEvaluationJob?.status === 'running'
        ? t('Evaluating...')
        : null

  const refreshPersistedEvaluation = async () => {
    const response = await fetch(`/sessions/${encodeURIComponent(session.session_id)}/evaluation`)
    if (!response.ok) throw new Error('Failed to refresh session evaluation')

    const data: { evaluation: SessionEvaluation | null } = await response.json()
    setLocalEvaluation(data.evaluation)
    onEvaluationUpdate?.(data.evaluation)
  }

  const pollLlmEvaluationJob = async (job: { job_id: string }) => {
    try {
      const response = await fetch(`/poll/${encodeURIComponent(job.job_id)}`)
      if (!response.ok) throw new Error('Failed to poll LLM evaluation job')

      const pollResult = await response.json()
      if (pollResult.status === 'succeeded') {
        setLlmEvaluationStatus('succeeded')
        await refreshPersistedEvaluation()
        await loadEvaluationJobHistory()
        onEvaluationPersisted?.()
        showToast?.('Session evaluated with LLM')
        return
      }

      if (pollResult.status === 'failed') {
        setLlmEvaluationStatus('failed')
        await loadEvaluationJobHistory()
        showToast?.('Failed to evaluate session with LLM')
        return
      }

      setLlmEvaluationStatus(pollResult.status === 'running' ? 'running' : 'queued')
      llmEvaluationPollRef.current = setTimeout(() => pollLlmEvaluationJob(job), 1500)
    } catch {
      setLlmEvaluationStatus('failed')
      showToast?.('Failed to evaluate session with LLM')
    }
  }

  const startLlmEvaluation = async () => {
    if (displayEvaluationRunning) return
    if (!selectedEvaluatorAvailable) {
      showToast?.('Evaluator unavailable')
      return
    }
    if (llmEvaluationPollRef.current) clearTimeout(llmEvaluationPollRef.current)

    setLocalEvaluationOverride(null)
    setLlmEvaluationStatus('queued')
    try {
      const response = await fetch(`/sessions/${encodeURIComponent(session.session_id)}/evaluate-with-llm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ evaluator_type: selectedEvaluatorType }),
      })
      if (!response.ok) throw new Error('Failed to start LLM evaluation')

      const job = await response.json()
      setLlmEvaluationStatus(job.status === 'running' ? 'running' : 'queued')
      await loadEvaluationJobHistory()
      pollLlmEvaluationJob(job)
    } catch {
      setLlmEvaluationStatus('failed')
      showToast?.('Failed to evaluate session with LLM')
    }
  }

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
            task_title_zh: null,
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

        <div style={{ minWidth: 0, maxWidth: '320px', flex: '1 1 160px' }}>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Session Title')}</div>
          <div className="session-task-title" title={sessionTitle}>
            {sessionTitle}
          </div>
        </div>

        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Timeline')}</div>
          <div style={{ fontSize: '12px', color: 'var(--text-primary)' }}>
            <div style={{ fontWeight: 600 }}>{formatTime(session.started, tz)}</div>
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
            <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--color-green)' }}>{formatCost(session.total_cost_usd, 2)}</div>
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

        {session.tool_calls_json && Object.keys(session.tool_calls_json).length > 0 && (
          <div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Tool Usage')}</div>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              {Object.entries(session.tool_calls_json).map(([name, count]) => (
                <ToolBadge key={name} name={name} count={count} />
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="session-eval-section">
        <div className="session-eval-label">{t('Evaluation')}</div>
        {!globalEvaluatorAvailable && (
          <div className="evaluation-warning">
            {t('Evaluator unavailable')}: {globalEvaluator?.label || evaluatorLabel(globalEvaluatorType)}
          </div>
        )}
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
              className={`session-eval-btn${localEvaluation?.outcome === o ? ` session-eval-btn-active-${o}` : ''}`}
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
          <div className="session-evaluator-picker">
            <select
              className="input-plain"
              value={selectedEvaluatorType}
              onChange={(event) => setSelectedEvaluatorType(event.target.value as EvaluatorType)}
              disabled={displayEvaluationRunning}
            >
              {availableEvaluators.map((evaluator) => (
                <option key={evaluator.id} value={evaluator.id} disabled={!evaluator.available}>
                  {evaluator.label}{evaluator.available ? '' : ` (${t('Not found')})`}
                </option>
              ))}
            </select>
          </div>
        </div>
        <button
          className={`session-eval-btn-primary${isLlmEvaluationRunning ? ' running' : ''}`}
          disabled={displayEvaluationRunning || !selectedEvaluatorAvailable}
          onClick={startLlmEvaluation}
        >
          {progressLabel || (isLlmEvaluationRunning ? t('Evaluating...') : t('Evaluate with LLM'))}
        </button>
        <div className="evaluation-job-history">
          <div className="evaluation-job-history-title">{t('Evaluator Jobs')}</div>
          {historyLoading && <div className="evaluation-job-history-empty">{t('Loading...')}</div>}
          {!historyLoading && evaluationJobHistory.length === 0 && (
            <div className="evaluation-job-history-empty">{t('No evaluator jobs yet.')}</div>
          )}
          {!historyLoading && evaluationJobHistory.map((job) => {
            const failed = job.status === 'failed'
            const errorPreview = job.error?.split('\n')[0] || t('No failure reason recorded')
            const outcomeLabels: Record<string, string> = { solved: 'Solved', partial: 'Partial', failed: 'Failed', stuck: 'Stuck', no_op: 'No-op', unknown: 'Unknown' }
            return (
              <details key={job.job_id} className={`evaluation-job-history-item evaluation-job-history-${job.status}`} open={failed}>
                <summary>
                  <span className={`evaluation-job-status evaluation-job-status-${job.status}`}>
                    {job.status === 'running' ? t('Running') : job.status === 'queued' ? t('Queued') : job.status === 'succeeded' ? t('Succeeded') : t('Failed')}
                  </span>
                  {job.outcome && (
                    <span className={`evaluation-job-outcome evaluation-job-outcome-${job.outcome}`}>
                      {t(outcomeLabels[job.outcome] ?? job.outcome)}
                    </span>
                  )}
                  <span>{evaluatorLabel(job.evaluator_type)}</span>
                  <span>{job.trigger === 'auto' ? t('Auto') : t('Manual')}</span>
                  {failed && <span className="evaluation-job-error-preview">{errorPreview}</span>}
                </summary>
                <div className="evaluation-job-detail">
                  <div>{t('Created')}: {job.created_at ? formatTime(job.created_at, tz) : '—'}</div>
                  <div>{t('Started')}: {job.started_at ? formatTime(job.started_at, tz) : '—'}</div>
                  <div>{t('Finished')}: {job.finished_at ? formatTime(job.finished_at, tz) : '—'}</div>
                  <div>{t('Evaluator')}: {evaluatorLabel(job.evaluator_type)}</div>
                  <div>{t('Trigger')}: {job.trigger === 'auto' ? t('Auto') : t('Manual')}</div>
                  {job.outcome && (
                    <div>{t('Outcome')}: <span className={`evaluation-job-outcome evaluation-job-outcome-${job.outcome}`}>{t(outcomeLabels[job.outcome] ?? job.outcome)}</span></div>
                  )}
                  {job.error && <pre>{job.error}</pre>}
                  {failed && (
                    <button
                      type="button"
                      className="session-eval-btn"
                      disabled={displayEvaluationRunning || !selectedEvaluatorAvailable}
                      onClick={startLlmEvaluation}
                    >
                      {t('Restart')}
                    </button>
                  )}
                </div>
              </details>
            )
          })}
        </div>
      </div>
    </div>
  )
}
