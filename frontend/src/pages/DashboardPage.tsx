import { useState, Fragment, useEffect, useMemo, useRef, useCallback } from 'react'
import { useApp } from '../contexts/AppContext'
import { useDashboardData } from '../hooks/useDashboardData'
import { useSessionsData } from '../hooks/useSessionsData'
import { useModelEffectivenessData } from '../hooks/useModelEffectivenessData'
import { useOnboarding } from '../hooks/useOnboarding'
import { useCountUp } from '../useCountUp'
import { ModelSelector } from '../ModelSelector'
import { TrendChart } from '../charts/TrendChart'
import { CacheHitRateChart } from '../charts/CacheHitRateChart'
import { TopUsageChart } from '../charts/TopUsageChart'
import { DailyHeatmap } from '../charts/DailyHeatmap'
import { InsightCards } from '../InsightCards'
import { Sparkline } from '../Sparkline'
import { CopyButton, ClickToCopy } from '../components/CopyButton'
import { SessionDetailContent } from '../components/SessionDetailPanel'
import { t } from '../i18n/index.ts'
import {
  formatCompact, formatCost, formatDuration, formatLatency, formatNumber, formatRate,
  formatTime, value, getModelIcon, getSourceBadgeBg, getSourceBadgeText,
  shortSessionId, sessionAgentName, sessionDisplayName, getAgentDisplayName, getSinceDate,
} from '../utils'
import { getModelBadgeBackgroundColor, getModelTextColor } from '../model-badge'
import type { ActiveFilter, DailyEffectivenessReport, EvaluationJobProgress, ModelEffectivenessGroup, SessionSummary, SessionsSummary } from '../types'

type Props = {
  onNavigateToLogs: (filters?: { sessionFilter?: string; activeFilter?: ActiveFilter }) => void
}

function getOutcomeBadge(outcome: string | null | undefined): { label: string; className: string } {
  switch (outcome) {
    case 'solved': return { label: 'Solved', className: 'session-outcome-solved' }
    case 'partial': return { label: 'Partial', className: 'session-outcome-partial' }
    case 'failed': return { label: 'Failed', className: 'session-outcome-failed' }
    case 'stuck': return { label: 'Stuck', className: 'session-outcome-stuck' }
    case 'no_op': return { label: 'No-op', className: 'session-outcome-no_op' }
    default: return { label: 'Unknown', className: 'session-outcome-unknown' }
  }
}

function formatEffectivenessShare(count: number, evaluatedCount: number): string {
  if (evaluatedCount === 0) return '—'
  return `${Math.round((count / evaluatedCount) * 100)}%`
}

function modelEffectivenessClassifiedCount(group: ModelEffectivenessGroup): number {
  return group.evaluated_count + group.no_op_count
}

function formatEvaluationJobBadge(job?: EvaluationJobProgress | null): string | null {
  if (!job) return null
  if (job.status === 'running') return t('Evaluating...')
  if (job.status === 'queued') {
    return `${t('Queued')}${job.queue_position ? ` #${job.queue_position}` : ''}`
  }
  return null
}

function getLocalDateKey(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function DashboardPage({ onNavigateToLogs }: Props) {
  const { theme, showToast, error, localAgents, setupDiagnostics, requestUsageRefresh, refreshTrigger, setError } = useApp()

  // Toggle to hide no-op and single-request sessions from tables and aggregations
  const [hideNoop, setHideNoop] = useState(true)

  // Dashboard data hook
  const {
    summary, dailyUsage, heatmapData, totalTrackedEvents, sources,
    dashboardInitialLoading, dashboardRefreshing,
    activeFilter, setActiveFilter, activeSource, setActiveSource,
    dateRange, setDateRange, customSince, customUntil,
    providerColors, dashboardFilterParams, totals,
  } = useDashboardData()

  // Sessions data hook
  const {
    sessions,
    setSessions,
    sessionsLoading,
    hasMoreSessions,
    sessionSortBy,
    sessionSortOrder,
    selectedSession,
    setSelectedSession,
    handleSessionSort,
    sessionInsights,
    setSessionPage,
  } = useSessionsData({ activeSource, dateRange, customSince, customUntil, hideNoop })

  // Sessions summary (fetched directly for the stats cards)
  const [sessionsSummary, setSessionsSummary] = useState<SessionsSummary | null>(null)
  useEffect(() => {
    const url = new URL('/sessions/summary', window.location.origin)
    if (activeSource) url.searchParams.set('client_source', activeSource)
    if (dateRange !== 'all') {
      const since = dateRange === 'custom' ? customSince : getSinceDate(dateRange)
      if (since) url.searchParams.set('since', since)
      if (customUntil) url.searchParams.set('until', customUntil)
    }
    if (hideNoop) url.searchParams.set('hide_noop', 'true')
    fetch(url.toString())
      .then(r => r.json())
      .then(setSessionsSummary)
      .catch(() => setSessionsSummary(null))
  }, [activeSource, dateRange, customSince, customUntil, hideNoop])

  const {
    modelEffectiveness,
    modelEffectivenessLoading,
    refreshModelEffectiveness,
  } = useModelEffectivenessData({ activeSource, dateRange, customSince, customUntil, hideNoop })

  const [dashboardTab, setDashboardTab] = useState<'overview' | 'sessions'>('overview')
  const [activeEvaluationJobs, setActiveEvaluationJobs] = useState<Record<string, EvaluationJobProgress>>({})
  const activeEvaluationJobsRef = useRef<Record<string, EvaluationJobProgress>>({})
  const activeEvaluationJobsPollRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    activeEvaluationJobsRef.current = activeEvaluationJobs
  }, [activeEvaluationJobs])

  const activeEvaluationJobList = useMemo(
    () => Object.values(activeEvaluationJobs).sort((a, b) => {
      const aPosition = a.queue_position ?? Number.MAX_SAFE_INTEGER
      const bPosition = b.queue_position ?? Number.MAX_SAFE_INTEGER
      if (aPosition !== bPosition) return aPosition - bPosition
      return (a.created_at ?? '').localeCompare(b.created_at ?? '')
    }),
    [activeEvaluationJobs]
  )
  const runningEvaluationJobs = activeEvaluationJobList.filter((job) => job.status === 'running')
  const queuedEvaluationJobs = activeEvaluationJobList.filter((job) => job.status === 'queued')

  const pollActiveEvaluationJobs = useCallback(async () => {
    if (dashboardTab !== 'sessions') {
      setActiveEvaluationJobs({})
      activeEvaluationJobsRef.current = {}
      return
    }

    try {
      const response = await fetch('/evaluation-jobs/active')
      if (!response.ok) return

      const data: { jobs: Record<string, EvaluationJobProgress> } = await response.json()
      const previousHadActive = Object.keys(activeEvaluationJobsRef.current).length > 0
      const nextHasActive = Object.values(data.jobs).some(
        (job) => job.status === 'queued' || job.status === 'running'
      )
      activeEvaluationJobsRef.current = data.jobs
      setActiveEvaluationJobs(data.jobs)

      if (previousHadActive && !nextHasActive) {
        requestUsageRefresh()
        refreshModelEffectiveness()
      }
    } finally {
      if (dashboardTab === 'sessions') {
        activeEvaluationJobsPollRef.current = setTimeout(pollActiveEvaluationJobs, 2000)
      }
    }
  }, [dashboardTab, refreshModelEffectiveness, requestUsageRefresh])

  useEffect(() => {
    if (activeEvaluationJobsPollRef.current) {
      clearTimeout(activeEvaluationJobsPollRef.current)
      activeEvaluationJobsPollRef.current = null
    }
    void pollActiveEvaluationJobs()
    return () => {
      if (activeEvaluationJobsPollRef.current) {
        clearTimeout(activeEvaluationJobsPollRef.current)
        activeEvaluationJobsPollRef.current = null
      }
    }
  }, [pollActiveEvaluationJobs])

  const modelEffectivenessTotals = useMemo(() => {
    return modelEffectiveness.groups.reduce(
      (totals, group) => ({
        evaluated: totals.evaluated + modelEffectivenessClassifiedCount(group),
        unknown: totals.unknown + group.unknown_count,
        noOp: totals.noOp + group.no_op_count,
        hasSmallSample: totals.hasSmallSample || (group.evaluated_count > 0 && group.evaluated_count < 5),
      }),
      { evaluated: 0, unknown: 0, noOp: 0, hasSmallSample: false }
    )
  }, [modelEffectiveness.groups])

  const todayDateKey = getLocalDateKey(new Date())
  const [dailyEffectivenessReport, setDailyEffectivenessReport] = useState<DailyEffectivenessReport | null>(null)

  const fetchDailyEffectivenessReport = useCallback(async () => {
    try {
      const url = new URL('/sessions/daily-effectiveness', window.location.origin)
      url.searchParams.set('date', todayDateKey)
      const response = await fetch(url.toString())
      if (!response.ok) throw new Error(t('Failed to fetch daily effectiveness report'))
      setDailyEffectivenessReport(await response.json() as DailyEffectivenessReport)
    } catch (err) {
      setDailyEffectivenessReport(null)
      setError(err instanceof Error ? err.message : t('Unknown error'))
    }
  }, [setError, todayDateKey])

  useEffect(() => {
    void fetchDailyEffectivenessReport()
  }, [fetchDailyEffectivenessReport, refreshTrigger])

  // Onboarding hook
  const {
    verifyPhase,
    verificationResult,
    copiedOnboardingCommand,
    armOnboardingVerification,
    resetVerification,
    showFirstRunOnboarding,
    setupConfiguredAgents,
    setupSummaryText,
    setupSummaryColor,
    verifyTimeoutGuidance,
  } = useOnboarding({ totalTrackedEvents, onFirstEvent: requestUsageRefresh })

  // Evaluation update handler
  const [fadingOutSessions, setFadingOutSessions] = useState<Set<string>>(new Set())
  const handleEvaluationUpdate = (sessionId: string, evaluation: any | null) => {
    // Update the evaluation optimistically
    setSessions((prev) =>
      prev.map((s) => (s.session_id === sessionId ? { ...s, evaluation } : s))
    )
    if (selectedSession?.session_id === sessionId) {
      setSelectedSession({ ...selectedSession, evaluation })
    }
    // Fade out no-op sessions when hideNoop is active
    if (hideNoop && evaluation?.outcome === 'no_op') {
      setFadingOutSessions(prev => new Set(prev).add(sessionId))
      // Remove from state after the CSS transition (0.5s) completes
      setTimeout(() => {
        setFadingOutSessions(prev => { const next = new Set(prev); next.delete(sessionId); return next })
        setSessions((prev) => prev.filter((s) => s.session_id !== sessionId))
      }, 550)
    }
  }

  // Local state
  const [sessionSearch, setSessionSearch] = useState('')
  const [loadingMore, setLoadingMore] = useState(false)
  const sessionsTableRef = useRef<HTMLDivElement>(null)

  // Infinite scroll for sessions
  useEffect(() => {
    if (dashboardTab !== 'sessions') return

    const handleScroll = () => {
      if (!sessionsTableRef.current || sessionsLoading || loadingMore || !hasMoreSessions) return
      const { scrollTop, scrollHeight, clientHeight } = sessionsTableRef.current
      if (scrollTop + clientHeight >= scrollHeight - 100) {
        setLoadingMore(true)
        setSessionPage(p => p + 1)
      }
    }

    const el = sessionsTableRef.current
    el?.addEventListener('scroll', handleScroll)
    return () => el?.removeEventListener('scroll', handleScroll)
  }, [dashboardTab, sessionsLoading, loadingMore, hasMoreSessions])

  // Reset loading more when sessionPage changes
  useEffect(() => {
    if (!sessionsLoading) setLoadingMore(false)
  }, [sessionsLoading])

  // Animated counters
  const animatedTotalTokens = useCountUp(dashboardInitialLoading ? 0 : totals.totalTokens)
  const animatedRequests = useCountUp(dashboardInitialLoading ? 0 : totals.requests)
  const animatedCost = useCountUp(dashboardInitialLoading ? 0 : totals.totalCost)
  const animatedRpm = useCountUp(dashboardInitialLoading ? 0 : totals.rpm)
  const animatedLatency = useCountUp(dashboardInitialLoading ? 0 : totals.avgLatency)

  // Reset pagination when filters change
  const resetPage = () => setSessionPage(1)

  // Navigate to logs with session context
  const handleViewInLogs = (session: SessionSummary, filters?: { onlyFailed?: boolean; status429?: boolean; status4xx?: boolean; status5xx?: boolean }) => {
    const navFilters: { sessionFilter: string; activeFilter?: ActiveFilter } = {
      sessionFilter: session.session_id,
    }
    if (filters) {
      navFilters.activeFilter = {
        provider: '',
        model: null,
        only_failed: filters.onlyFailed,
        status_429: filters.status429,
        status_4xx: filters.status4xx,
        status_5xx: filters.status5xx,
      }
    }
    onNavigateToLogs(navFilters)
  }

  return (
    <>
      {totalTrackedEvents !== 0 && (
      <div className="dashboard-filter-row" style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
          <select
            className="input-plain"
            value={dateRange}
            onChange={(e) => { setDateRange(e.target.value as any); resetPage(); }}
          >
            <option value="24h">{t('Last 24 Hours')}</option>
            <option value="7d">{t('Last 7 Days')}</option>
            <option value="30d">{t('Last 30 Days')}</option>
            <option value="all">{t('All Time')}</option>
            <option value="custom">{t('Custom Range')}</option>
          </select>
          <ModelSelector
            activeFilter={activeFilter}
            summary={summary}
            providerColors={providerColors}
            onChange={(f) => { setActiveFilter(f); resetPage(); }}
          />
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
          <button
            className={`btn-ghost btn-refresh ${dashboardRefreshing ? 'is-refreshing' : ''}`}
            onClick={requestUsageRefresh}
            disabled={dashboardRefreshing}
            aria-label={t('Refresh')}
            title={t('Refresh')}
          >
            <span className="refresh-icon">↻</span>
          </button>
        </div>
      )}
      <div className="dashboard-tabs" style={{ display: 'flex', gap: '4px', borderBottom: '1px solid var(--border-color)', marginBottom: '16px' }}>
        <button className={`dashboard-tab ${dashboardTab === 'overview' ? 'active' : ''}`} onClick={() => setDashboardTab('overview')}>{t('Overview')}</button>
        <button className={`dashboard-tab ${dashboardTab === 'sessions' ? 'active' : ''}`} onClick={() => setDashboardTab('sessions')}>{t('Sessions')}</button>
      </div>
      {dashboardTab === 'overview' && (<>

      {dashboardInitialLoading ? (
        <div />
      ) : showFirstRunOnboarding ? (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '40px 24px',
          textAlign: 'center',
          gap: '24px',
        }}>
          <div style={{ maxWidth: '560px' }}>
            <div style={{ fontSize: '28px', marginBottom: '8px' }}>
              {t('No traffic tracked yet')}
            </div>
            <div style={{ fontSize: '15px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              {t('Run one test command below. When llm-tracker sees the request, usage, cost, and latency will appear here.')}
            </div>
          </div>

          {/* Step 1: Bootstrap */}
          <div style={{ width: '100%', maxWidth: '680px', textAlign: 'left' }}>
            <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '12px', textTransform: 'uppercase' }}>
              {t('Step 1: Bootstrap')}
            </div>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 16px',
              borderRadius: '8px',
              background: 'var(--surface-hover)',
              border: '1px solid var(--border-color)',
            }}>
              <code style={{ fontSize: '13px', fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>llm-tracker bootstrap</code>
              <CopyButton
                text="llm-tracker bootstrap"
                style={{ fontSize: '11px', padding: '4px 10px', whiteSpace: 'nowrap' }}
                idleLabel={`📋 ${t('Copy')}`}
                copiedLabel={`✓ ${t('Copied!')}`}
              />
            </div>
          </div>

          {/* Step 2: Run a test command */}
          <div style={{ width: '100%', maxWidth: '680px', textAlign: 'left' }}>
            <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '12px', textTransform: 'uppercase' }}>
              {t('Step 2: Run a test command')}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {[
                { cmd: 'llm-tracker claude', source: 'Claude Code' },
                { cmd: 'llm-tracker codex exec "hello"', source: 'Codex' },
                { cmd: 'llm-tracker gemini -p "hello"', source: 'Gemini CLI' },
              ].map(({ cmd, source }) => (
                <div key={cmd} style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 16px',
                  borderRadius: '8px',
                  background: 'var(--surface-hover)',
                  border: '1px solid var(--border-color)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', minWidth: '80px' }}>{source}</span>
                    <code style={{ fontSize: '13px', fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{cmd}</code>
                  </div>
                  <CopyButton
                    text={cmd}
                    style={{ fontSize: '11px', padding: '4px 10px', whiteSpace: 'nowrap' }}
                    idleLabel={`📋 ${t('Copy')}`}
                    copiedLabel={`✓ ${t('Copied!')}`}
                    onCopied={() => armOnboardingVerification({ source, command: cmd })}
                  />
                </div>
              ))}
            </div>
          </div>

          {/* Step 3: Wait for event */}
          <div style={{ width: '100%', maxWidth: '680px', textAlign: 'left' }}>
            <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '12px', textTransform: 'uppercase' }}>
              {t('Step 3: Wait for event')}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {verificationResult ? (
                <>
                  <div style={{
                    padding: '8px 12px',
                    borderRadius: '6px',
                    background: 'var(--icon-green-bg)',
                    color: 'var(--color-green)',
                    fontWeight: 600,
                    fontSize: '13px',
                  }}>
                    {t('Tracking works. Your first request is recorded.')}
                  </div>
                  <div style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <div><span style={{ color: 'var(--text-muted)' }}>{t('Source:')}</span> {verificationResult.client_source || '—'}</div>
                    <div><span style={{ color: 'var(--text-muted)' }}>{t('Model:')}</span> {verificationResult.model || '—'}</div>
                    <div><span style={{ color: 'var(--text-muted)' }}>{t('Tokens:')}</span> {formatNumber(verificationResult.prompt_tokens)} {t('In:')} / {formatNumber(verificationResult.completion_tokens)} {t('Out:')}</div>
                    <div><span style={{ color: 'var(--text-muted)' }}>{t('Cost:')}</span> {formatCost(value(verificationResult.total_cost_usd))}</div>
                    <div><span style={{ color: 'var(--text-muted)' }}>{t('Latency:')}</span> {formatLatency(verificationResult.latency_ms)}</div>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <button className="btn-primary" onClick={() => onNavigateToLogs()} style={{ fontSize: '12px', alignSelf: 'flex-start' }}>
                      {t('View request logs')}
                    </button>
                    <button className="btn-ghost" onClick={resetVerification} style={{ fontSize: '12px', alignSelf: 'flex-start' }}>
                      {t('Reset')}
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div
                    aria-live="polite"
                    title={copiedOnboardingCommand?.command}
                    style={{
                      fontSize: '12px',
                      color: verifyPhase === 'timeout'
                        ? 'var(--color-red)'
                        : copiedOnboardingCommand && verifyPhase === 'idle'
                          ? 'var(--color-green)'
                          : 'var(--text-muted)',
                      padding: copiedOnboardingCommand && verifyPhase === 'idle' ? '8px 10px' : undefined,
                      borderRadius: copiedOnboardingCommand && verifyPhase === 'idle' ? '6px' : undefined,
                      background: copiedOnboardingCommand && verifyPhase === 'idle' ? 'var(--icon-green-bg)' : undefined,
                    }}
                  >
                    {verifyPhase === 'polling'
                      ? t('Waiting for your first event...')
                      : verifyPhase === 'timeout'
                        ? t(verifyTimeoutGuidance)
                        : copiedOnboardingCommand
                          ? <><span style={{ fontWeight: 700 }}>{copiedOnboardingCommand.source}</span>: {t('Agent command copied. Run it in your terminal — checking automatically.')}</>
                          : t('This page is checking automatically. Run a command above to generate your first event.')}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Setup health + Detected agents */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: '16px',
            width: '100%',
            maxWidth: '680px',
          }}>
            {/* Setup health */}
            <div className="panel" style={{ textAlign: 'left' }}>
              <div className="panel-tabs">
                <div className="tab active"><span>🏥</span> {t('Setup health')}</div>
              </div>
              <div className="panel-body" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                  gap: '8px',
                }}>
                  <div style={{
                    padding: '10px 12px',
                    borderRadius: '8px',
                    background: 'var(--bg-secondary)',
                  }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 700, marginBottom: '4px' }}>{t('API server')}</div>
                    <div style={{ fontSize: '13px', color: error ? 'var(--color-red)' : 'var(--color-green)', fontWeight: 700 }}>
                      {error ? t('Broken') : t('Reachable')}
                    </div>
                  </div>
                  <div style={{
                    padding: '10px 12px',
                    borderRadius: '8px',
                    background: 'var(--bg-secondary)',
                  }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 700, marginBottom: '4px' }}>{t('OTLP configured')}</div>
                    <div style={{ fontSize: '13px', color: setupSummaryColor, fontWeight: 700 }}>
                      {setupSummaryText}
                    </div>
                  </div>
                </div>
                {setupDiagnostics && setupConfiguredAgents === 0 && (
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    {t('No local OTLP config found yet. Run bootstrap, then run a test command above. This page checks automatically.')}
                  </div>
                )}
              </div>
            </div>

            {/* Detected agents */}
            <div className="panel" style={{ textAlign: 'left' }}>
              <div className="panel-tabs">
                <div className="tab active"><span>🤖</span> {t('Detected Agents')}</div>
              </div>
              <div className="panel-body" style={{ padding: '16px' }}>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '12px' }}>
                  {t('Detected from your local config and available commands.')}
                </div>
                {localAgents ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {Object.entries(localAgents).map(([name, info]) => (
                      <div key={name} style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '12px',
                        padding: '10px 12px',
                        borderRadius: '8px',
                        background: 'var(--bg-secondary)',
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                          <span style={{
                            width: '8px', height: '8px', borderRadius: '50%',
                            background: info.found ? 'var(--color-green)' : 'var(--text-muted)',
                            flexShrink: 0,
                          }} />
                          <div style={{ minWidth: 0 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                              <span style={{ fontWeight: 700, fontSize: '13px' }}>{getAgentDisplayName(name)}</span>
                              <span style={{ fontSize: '11px', color: info.found ? 'var(--color-green)' : 'var(--text-muted)', fontWeight: 700 }}>
                                {info.found ? t('Ready') : t('Not found')}
                              </span>
                            </div>
                            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '3px', wordBreak: 'break-all' }}>
                              {t('Detected:')} {info.path || t('Unknown')}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : sources.length > 0 ? (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {sources.map(src => (
                      <span key={src} style={{
                        padding: '4px 12px',
                        borderRadius: '6px',
                        background: 'var(--icon-green-bg)',
                        color: 'var(--color-green)',
                        fontWeight: 600,
                        fontSize: '13px',
                      }}>{src}</span>
                    ))}
                  </div>
                ) : (
                  <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                    {t('No local Agent')}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      ) : (
      <div className={`dashboard-refresh-surface ${dashboardRefreshing ? 'is-refreshing' : ''}`}>
      <div className="widgets-grid">
        {dashboardInitialLoading ? (
          Array.from({ length: 5 }, (_, i) => (
            <div key={i} className="widget">
              <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center', gap: '10px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div className="skeleton" style={{ width: 40, height: 40, borderRadius: 12 }} />
                    <div>
                      <div className="skeleton skeleton-text" style={{ width: 80 }} />
                      <div className="skeleton skeleton-value" />
                    </div>
                  </div>
                  <div className="skeleton" style={{ width: 100, height: 32, borderRadius: 6 }} />
                </div>
                <div className="skeleton skeleton-text-sm" style={{ width: '60%' }} />
                <div className="skeleton skeleton-text-sm" style={{ width: '40%' }} />
              </div>
            </div>
          ))
        ) : (
          <>
        <div className="widget">
          <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div className="icon-box icon-green">$</div>
                <div>
                  <div className="stat-label">{t('Estimated Cost')}</div>
                  <div className="stat-value">{formatCost(animatedCost, 2)}</div>
                </div>
              </div>
              <div style={{ width: '100px' }}>
                <Sparkline data={dailyUsage.map(d => d.requests > 0 ? value(d.total_cost_usd) / d.requests : 0)} color="var(--color-blue)" />
              </div>
            </div>
            <div className="stat-label" style={{ marginTop: '-2px' }}>
              {t('Avg:')} <span style={{ color: 'var(--color-blue)', fontWeight: 600 }}>{formatCost(totals.avgEffectivePrice, 3)} {t('/ req')}</span>
            </div>
            <div className="stat-label" style={{ fontSize: '11px', marginBottom: 0 }}>
              {t('Avg $/M tokens:')} <span style={{ color: 'var(--color-green)', fontWeight: 600 }}>{formatRate(totals.avgEffectivePricePerMillion)}</span>
            </div>
          </div>
        </div>

        <div className="widget">
          <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div className="icon-box icon-yellow">#</div>
                <div>
                  <div className="stat-label">{t('Token Usage')}</div>
                  <div className="stat-value">{formatCompact(animatedTotalTokens)}</div>
                </div>
              </div>
              <div style={{ width: '100px' }}>
                <Sparkline data={dailyUsage.map(d => value(d.prompt_tokens) > 0 ? (value(d.cached_tokens) / value(d.prompt_tokens)) * 100 : 0)} color="var(--color-green)" />
              </div>
            </div>
            <div className="stat-label" style={{ marginBottom: 0 }}>
              {t('In:')} {formatCompact(totals.promptTokens)} / {t('Out:')} {formatCompact(totals.completionTokens)}
            </div>
            <div className="stat-label" style={{ fontSize: '11px', marginBottom: 0 }}>
              {t('Cached:')} {formatCompact(totals.cachedTokens)}
              <span style={{ marginLeft: '6px', color: 'var(--color-green)', fontWeight: 600 }}>
                ({totals.totalTokens > 0 ? ((value(totals.cachedTokens) / totals.totalTokens) * 100).toFixed(1) : 0}% {t('Hit)')}
              </span>
            </div>
          </div>
        </div>

        <div className="widget">
          <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div className="icon-box icon-green">↑</div>
                <div>
                  <div className="stat-label">{t('Requests')}</div>
                  <div className="stat-value">{formatNumber(animatedRequests)}</div>
                </div>
              </div>
              <div style={{ width: '100px' }}>
                <Sparkline data={dailyUsage.map(d => d.requests)} color="var(--color-pink)" />
              </div>
            </div>
            <div className="stat-label" style={{ marginTop: '-2px' }}>
              {t('Avg:')} <span style={{ color: 'var(--color-purple)', fontWeight: 600 }}>{formatCompact(totals.avgTokensPerRequest)} {t('tokens/req')}</span>
            </div>
          </div>
        </div>

        <div className="widget">
          <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div className={`icon-box ${totals.successRate < 100 ? 'icon-pink' : 'icon-green'}`}>
                  {totals.successRate < 100 ? '🚨' : '✅'}
                </div>
                <div>
                  <div className="stat-label">{t('Success Rate')}</div>
                  <div
                    className="stat-value"
                    style={{ color: totals.successRate < 100 ? 'var(--color-red)' : 'var(--color-green)', cursor: totals.successRate < 100 ? 'pointer' : 'default' }}
                    onClick={() => {
                      if (totals.successRate < 100) {
                        onNavigateToLogs({ activeFilter: { provider: '', model: null, only_failed: true } })
                      }
                    }}
                    title={totals.successRate < 100 ? t('View failed requests in logs') : undefined}
                  >
                    {totals.successRate.toFixed(1)}%
                  </div>
                </div>
              </div>
              <div style={{ width: '100px' }}>
                <Sparkline data={dailyUsage.map(d => d.requests > 0 ? (value(d.successful_requests) / d.requests) * 100 : 100)} color={totals.successRate < 100 ? 'var(--color-pink)' : 'var(--color-green)'} />
              </div>
            </div>
            {totals.successRate < 100 && (
              <div
                className="stat-label"
                style={{ marginTop: '4px', display: 'flex', gap: '8px', textTransform: 'none' }}
              >
                {totals.statusBreakdown.s429 > 0 && (
                  <span
                    className="status-link"
                    onClick={(e) => {
                      e.stopPropagation();
                      onNavigateToLogs({ activeFilter: { provider: '', model: null, status_429: true } });
                    }}
                  >
                    429: {totals.statusBreakdown.s429}
                  </span>
                )}
                {totals.statusBreakdown.s5xx > 0 && (
                  <span
                    className="status-link"
                    onClick={(e) => {
                      e.stopPropagation();
                      onNavigateToLogs({ activeFilter: { provider: '', model: null, status_5xx: true } });
                    }}
                  >
                    5xx: {totals.statusBreakdown.s5xx}
                  </span>
                )}
                {totals.statusBreakdown.s4xx > 0 && (
                  <span
                    className="status-link"
                    onClick={(e) => {
                      e.stopPropagation();
                      onNavigateToLogs({ activeFilter: { provider: '', model: null, status_4xx: true } });
                    }}
                  >
                    4xx: {totals.statusBreakdown.s4xx}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="widget">
          <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div className="icon-box icon-blue">⚡</div>
                <div>
                  <div className="stat-label">{t('Performance')}</div>
                  <div className="stat-value">{animatedRpm.toFixed(3)} <span style={{ fontSize: '12px', fontWeight: 500 }}>{t('RPM')}</span></div>
                </div>
              </div>
              <div style={{ width: '100px' }}>
                <Sparkline data={dailyUsage.map(d => value(d.total_tokens))} color="var(--color-purple)" />
              </div>
            </div>
            <div className="stat-label" style={{ marginTop: '-2px' }}>
              {t('Avg Throughput:')} <span style={{ color: 'var(--color-purple)', fontWeight: 600 }}>{formatCompact(totals.tpm)} {t('TPM')}</span>
            </div>
          </div>
        </div>

        <div className="widget">
          <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div className="icon-box icon-pink">~</div>
                <div>
                  <div className="stat-label">{t('Average Response')}</div>
                  <div className="stat-value">{formatLatency(animatedLatency)}</div>
                </div>
              </div>
              <div style={{ width: '100px' }}>
                <Sparkline data={dailyUsage.map(d => value(d.avg_latency_ms))} color="var(--color-pink)" />
              </div>
            </div>
          </div>
        </div>
          </>
        )}
      </div>

      <div style={{ display: 'flex', gap: '24px', marginBottom: '24px', alignItems: 'stretch' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <TopUsageChart
            summary={summary}
            theme={theme}
            filterParams={dashboardFilterParams}
            showTrend={false}
          />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <InsightCards
            summary={summary}
            dailyUsage={dailyUsage}
            onClick={(id, metadata) => {
              if (id === 'reliability') {
                if (metadata && (metadata as any).status) {
                  const status = (metadata as any).status;
                  setActiveFilter({
                    provider: '',
                    model: null,
                    status_429: status === 429,
                    status_4xx: status === 400,
                    status_5xx: status === 500
                  })
                } else {
                  setActiveFilter({ provider: '', model: null, only_failed: true })
                }
                onNavigateToLogs()
                resetPage()
              } else if ((id === 'cost' || id === 'latency') && metadata) {
                setActiveFilter({
                  provider: metadata.provider || '',
                  model: metadata.model || null
                })
                resetPage()
              }
            }}
          />
        </div>
      </div>

      <div style={{ display: 'flex', gap: '24px', height: '400px' }}>
        <div style={{ flex: '1 1 0', minWidth: 0 }}>
          <TrendChart
            data={dailyUsage}
            title={`${dateRange === '24h' ? t('Hourly Usage Trend') : t('Daily Usage Trend')}`}
            granularity={dateRange === '24h' ? 'hour' : 'day'}
            periodCount={dateRange === '24h' ? 24 : dateRange === '7d' ? 7 : dateRange === '30d' ? 30 : 365}
            showDots={dateRange !== 'all'}
          />
        </div>
        <div style={{ flex: '1 1 0', minWidth: 0, display: 'flex', gap: '24px' }}>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
            <CacheHitRateChart
              data={dailyUsage}
              title={t('Cache Hit Rate')}
            />
          </div>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <DailyHeatmap mode="activity" data={heatmapData} />
            <DailyHeatmap mode="success-rate" data={heatmapData} />
          </div>
        </div>
      </div>
      </div>

      )}
      </>
      )}
      {dashboardTab === 'sessions' && (
      <div className="sessions-page">
        {/* Summary stat cards */}
        <div className="widgets-grid" style={{ marginBottom: '24px' }}>
          <div className="widget">
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Total Sessions')}</div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: 'var(--text-primary)' }}>{sessionsSummary ? formatNumber(sessionsSummary.session_count) : '—'}</div>
          </div>
          <div className="widget">
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Avg Duration')}</div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: 'var(--text-primary)' }}>{sessionsSummary ? formatDuration(sessionsSummary.avg_duration_s, { secondsFractionDigits: 2 }) : '—'}</div>
          </div>
          <div className="widget">
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Total Tokens')}</div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: 'var(--text-primary)' }}>{sessionsSummary ? formatCompact(sessionsSummary.total_tokens) : '—'}</div>
          </div>
          <div className="widget">
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Estimated Cost')}</div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: 'var(--color-green)' }}>{sessionsSummary ? formatCost(sessionsSummary.total_cost_usd, 2) : '—'}</div>
          </div>
          <div className="widget">
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700 }}>{t('Avg Latency')}</div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: 'var(--text-primary)' }}>{sessionsSummary ? formatLatency(sessionsSummary.avg_latency_ms) : '—'}</div>
          </div>
        </div>

        {sessionInsights.length > 0 && (
          <div className="session-insights-grid" aria-label="Session insights">
            {sessionInsights.map(insight => (
              <div key={insight.key} className={`session-insight-card${insight.tone ? ` session-insight-${insight.tone}` : ''}`}>
                <div className="session-insight-header">
                  <div className="session-insight-title">{t(insight.title)}</div>
                  <ClickToCopy text={insight.session.session_id} onCopy={showToast}>
                    <span className="session-insight-id">{shortSessionId(insight.session.session_id)}</span>
                  </ClickToCopy>
                </div>
                <div className="session-insight-session">{sessionDisplayName(insight.session)}</div>
                <div className="session-insight-value">{insight.value}</div>
                <div className="session-insight-detail">{insight.detail}</div>
                <button
                  type="button"
                  className="btn-ghost session-insight-action"
                  onClick={() => handleViewInLogs(insight.session, { onlyFailed: insight.onlyFailed })}
                >
                  {t('View in Logs')}
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="panel daily-effectiveness-panel">
          <div className="daily-effectiveness-header">
            <div>
              <div className="daily-effectiveness-title">{t('Today’s AI Work')}</div>
              <div className="daily-effectiveness-subtitle">
                {dailyEffectivenessReport ? dailyEffectivenessReport.summary : t('No daily effectiveness report yet.')}
              </div>
            </div>
          </div>

          {dailyEffectivenessReport && (
            <div className="daily-effectiveness-body">
              <div className="daily-effectiveness-metrics">
                <div>
                  <div className="daily-effectiveness-metric-value">{formatNumber(dailyEffectivenessReport.session_count)}</div>
                  <div className="daily-effectiveness-metric-label">{t('Sessions')}</div>
                </div>
                <div>
                  <div className="daily-effectiveness-metric-value">{formatNumber(dailyEffectivenessReport.evaluated_count)}</div>
                  <div className="daily-effectiveness-metric-label">{t('Evaluated')}</div>
                </div>
                <div>
                  <div className="daily-effectiveness-metric-value">{formatNumber(dailyEffectivenessReport.classified_count)}</div>
                  <div className="daily-effectiveness-metric-label">{t('Classified')}</div>
                </div>
                <div>
                  <div className="daily-effectiveness-metric-value">{formatCost(dailyEffectivenessReport.total_cost_usd, 2)}</div>
                  <div className="daily-effectiveness-metric-label">{t('Estimated Cost')}</div>
                </div>
              </div>

              <div className="daily-effectiveness-lists">
                {dailyEffectivenessReport.highlights.length > 0 && (
                  <div>
                    <div className="daily-effectiveness-list-title">{t('Highlights')}</div>
                    <ul className="daily-effectiveness-list">
                      {dailyEffectivenessReport.highlights.map(item => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                )}
                {dailyEffectivenessReport.needs_attention.length > 0 && (
                  <div>
                    <div className="daily-effectiveness-list-title">{t('Needs attention')}</div>
                    <ul className="daily-effectiveness-list">
                      {dailyEffectivenessReport.needs_attention.map(item => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                )}
                {dailyEffectivenessReport.model_takeaways.length > 0 && (
                  <div>
                    <div className="daily-effectiveness-list-title">{t('Model Takeaways')}</div>
                    <ul className="daily-effectiveness-list">
                      {dailyEffectivenessReport.model_takeaways.map(item => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="panel model-effectiveness-panel">
          <div className="model-effectiveness-header">
            <div>
              <div className="model-effectiveness-title">{t('Model Effectiveness')}</div>
              <div className="model-effectiveness-subtitle">
                {t('Based on')} {formatNumber(modelEffectivenessTotals.evaluated)} {t('evaluated sessions')} · {formatNumber(modelEffectivenessTotals.unknown)} {t('unknown')}
                {modelEffectivenessTotals.noOp > 0 && (
                  <> · {formatNumber(modelEffectivenessTotals.noOp)} {t('no-op')}</>
                )}
              </div>
            </div>
            {modelEffectivenessTotals.hasSmallSample && (
              <div className="model-effectiveness-warning">
                {t('Small sample — treat this as directional.')}
              </div>
            )}
          </div>

          {modelEffectivenessTotals.evaluated === 0 && !modelEffectivenessLoading ? (
            <div className="model-effectiveness-empty">
              <div className="model-effectiveness-empty-title">{t('No evaluated sessions yet.')}</div>
              <div className="model-effectiveness-empty-copy">
                {t('Mark a few sessions as solved or failed to compare models on your real tasks.')}
              </div>
            </div>
          ) : (
            <div className="model-effectiveness-table-wrap">
              <table className="table model-effectiveness-table">
                <thead>
                  <tr>
                    <th>{t('Model')}</th>
                    <th>{t('Evaluated')}</th>
                    <th>{t('Solved')}</th>
                    <th>{t('Partial')}</th>
                    <th>{t('Failed')}</th>
                    <th>{t('Stuck')}</th>
                    <th>{t('No-op')}</th>
                    <th>{t('Unknown')}</th>
                    <th>{t('Cost / solved')}</th>
                  </tr>
                </thead>
                <tbody>
                  {modelEffectivenessLoading && modelEffectiveness.groups.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="model-effectiveness-loading">—</td>
                    </tr>
                  ) : (
                    modelEffectiveness.groups.map((group: ModelEffectivenessGroup) => (
                      <tr key={group.key}>
                        <td>
                          <div className="model-effectiveness-model" title={group.key}>
                            {getModelIcon(group.key)}
                            <span>{group.key}</span>
                          </div>
                        </td>
                        <td>
                          <span className="model-effectiveness-count">{formatNumber(modelEffectivenessClassifiedCount(group))}</span>
                          <span className="model-effectiveness-muted"> / {formatNumber(group.session_count)}</span>
                        </td>
                        <td>
                          <div className="model-effectiveness-share model-effectiveness-share-solved">
                            {formatEffectivenessShare(group.solved_count, group.evaluated_count)}
                          </div>
                          <div className="model-effectiveness-muted">{formatNumber(group.solved_count)}</div>
                        </td>
                        <td>
                          <div className="model-effectiveness-share model-effectiveness-share-partial">
                            {formatEffectivenessShare(group.partial_count, group.evaluated_count)}
                          </div>
                          <div className="model-effectiveness-muted">{formatNumber(group.partial_count)}</div>
                        </td>
                        <td>
                          <div className="model-effectiveness-share model-effectiveness-share-failed">
                            {formatEffectivenessShare(group.failed_count, group.evaluated_count)}
                          </div>
                          <div className="model-effectiveness-muted">{formatNumber(group.failed_count)}</div>
                        </td>
                        <td>
                          <div className="model-effectiveness-share model-effectiveness-share-stuck">
                            {formatEffectivenessShare(group.stuck_count, group.evaluated_count)}
                          </div>
                          <div className="model-effectiveness-muted">{formatNumber(group.stuck_count)}</div>
                        </td>
                        <td>
                          <span className="model-effectiveness-count">{formatNumber(group.no_op_count)}</span>
                        </td>
                        <td>
                          <span className="model-effectiveness-count">{formatNumber(group.unknown_count)}</span>
                        </td>
                        <td>{group.cost_per_solved === null ? '—' : formatCost(group.cost_per_solved, 2)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {activeEvaluationJobList.length > 0 && (
          <div className="panel evaluator-queue-panel">
            <div className="evaluator-queue-header">
              <div>
                <div className="evaluator-queue-title">{t('Evaluator Queue')}</div>
                <div className="evaluator-queue-subtitle">
                  {formatNumber(runningEvaluationJobs.length)} {t('running')} · {formatNumber(queuedEvaluationJobs.length)} {t('queued')}
                </div>
              </div>
            </div>
            <div className="evaluator-queue-list">
              {activeEvaluationJobList.map((job) => (
                <div key={job.job_id} className="evaluation-job-row">
                  <div className={`evaluation-job-status evaluation-job-status-${job.status}`}>
                    {job.status === 'running' ? t('Running') : t('Queued')}
                  </div>
                  <div className="evaluation-job-main">
                    <div className="evaluation-job-session">
                      <ClickToCopy text={job.session_id} onCopy={showToast}>
                        <span>{shortSessionId(job.session_id)}</span>
                      </ClickToCopy>
                      <span className="evaluation-job-trigger">
                        {job.trigger === 'auto' ? t('Auto') : t('Manual')}
                      </span>
                      {job.client_source && (
                        <span className="evaluation-job-source">{sessionAgentName(job.client_source)}</span>
                      )}
                    </div>
                    <div className="evaluation-job-meta">
                      {job.queue_position ? `${t('Position')} #${job.queue_position}` : t('Active')}
                      {' · '}
                      {job.started_at ? `${t('Started')} ${formatTime(job.started_at)}` : `${t('Created')} ${job.created_at ? formatTime(job.created_at) : '—'}`}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {sessions.length === 0 && !sessionsLoading && (
          <div className="sessions-empty-state panel">
            <div className="sessions-empty-title">{t('No sessions yet.')}</div>
            <div className="sessions-empty-copy">
              {t('Run llm-tracker codex, llm-tracker claude, or llm-tracker gemini to create your first tracked session.')}
            </div>
          </div>
        )}

        {/* Sessions table */}
        {(sessions.length > 0 || sessionsLoading) && (
        <div className="panel" ref={sessionsTableRef} style={{ maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '8px', position: 'sticky', top: 0, background: 'var(--card-bg)', zIndex: 1 }}>
            <input
              className="input-plain"
              type="text"
              placeholder={t('Search sessions…')}
              value={sessionSearch}
              onChange={e => setSessionSearch(e.target.value)}
              style={{ flex: 1, minWidth: 0 }}
            />
            <button
              className={`btn-ghost${hideNoop ? ' active' : ''}`}
              onClick={() => setHideNoop(prev => !prev)}
              title={t('Hide no-op and single-request sessions')}
              style={{ fontSize: '11px', padding: '4px 10px', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '4px' }}
            >
              <span style={{ opacity: hideNoop ? 1 : 0.5 }}>🚫</span>
              {t('Hide no-op')}
            </button>
          </div>
          <div className="panel-body" style={{ padding: 0 }}>
            <table className="table sessions-table">
              <thead>
                <tr>
                  <th className="sessions-col-session">
                    {t('Session')}
                  </th>
                  <th>
                    {t('Agent')}
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSessionSort('started')}>
                    {t('Started')} {sessionSortBy === 'started' ? (sessionSortOrder === 'asc' ? '↑' : '↓') : ''}
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSessionSort('duration_s')}>
                    {t('Duration')} {sessionSortBy === 'duration_s' ? (sessionSortOrder === 'asc' ? '↑' : '↓') : ''}
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSessionSort('request_count')}>
                    {t('Requests')} {sessionSortBy === 'request_count' ? (sessionSortOrder === 'asc' ? '↑' : '↓') : ''}
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSessionSort('total_tokens')}>
                    {t('Tokens')} {sessionSortBy === 'total_tokens' ? (sessionSortOrder === 'asc' ? '↑' : '↓') : ''}
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSessionSort('total_cost_usd')}>
                    {t('Cost')} {sessionSortBy === 'total_cost_usd' ? (sessionSortOrder === 'asc' ? '↑' : '↓') : ''}
                  </th>
                  <th style={{ width: '90px' }}>Outcome</th>
                </tr>
              </thead>
              <tbody>
                {sessions.filter(s => {
                    if (!sessionSearch.trim()) return true
                    const q = sessionSearch.toLowerCase()
                    return s.session_id.toLowerCase().includes(q) ||
                      sessionDisplayName(s).toLowerCase().includes(q) ||
                      s.client_source.toLowerCase().includes(q)
                  }).map(session => (
                  <Fragment key={session.session_id}>
                  <tr
                    className={fadingOutSessions.has(session.session_id) ? 'session-fade-out' : undefined}
                    style={{ cursor: 'pointer', background: selectedSession?.session_id === session.session_id ? 'var(--surface-hover)' : undefined }}
                    onClick={() => setSelectedSession(selectedSession?.session_id === session.session_id ? null : session)}
                  >
                    <td className="sessions-session-cell" title={session.session_id}>
                      <div className="session-primary">{sessionDisplayName(session)} · {formatTime(session.started)}</div>
                      <div className="session-secondary">
                        {formatNumber(session.request_count)} {t('requests')} · {formatDuration(session.duration_s)} · <ClickToCopy text={session.session_id} onCopy={showToast}>
                          <span className="session-short-id">{shortSessionId(session.session_id)}</span>
                        </ClickToCopy>
                      </div>
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontSize: '11px',
                          fontWeight: 600,
                          background: getSourceBadgeBg(session.client_source),
                          color: getSourceBadgeText(session.client_source),
                        }}>
                          {sessionAgentName(session.client_source)}
                        </span>
                        {session.model && (
                          <div style={{
                            padding: '4px 6px',
                            borderRadius: '6px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            fontSize: '11px',
                            backgroundColor: getModelBadgeBackgroundColor(session.model),
                            color: getModelTextColor(session.model),
                            fontWeight: 600,
                            maxWidth: '140px',
                          }} title={session.model}>
                            {getModelIcon(session.model)}
                            <span style={{
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}>
                              {session.model}
                            </span>
                          </div>
                        )}
                      </div>
                    </td>
                    <td style={{ fontSize: '12px' }}>{formatTime(session.started)}</td>
                    <td style={{ fontSize: '12px' }}>{formatDuration(session.duration_s)}</td>
                    <td style={{ fontSize: '12px' }}>{formatNumber(session.request_count)}</td>
                    <td style={{ fontSize: '12px' }}>{formatCompact(session.total_tokens)}</td>
                    <td style={{ fontSize: '12px' }}>{formatCost(session.total_cost_usd, 2)}</td>
                    <td>
                      <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
                        <span className={`session-outcome-badge ${getOutcomeBadge(session.evaluation?.outcome).className}`}>
                          {getOutcomeBadge(session.evaluation?.outcome).label}
                        </span>
                        {activeEvaluationJobs[session.session_id] && (
                          <span className="session-evaluation-job-badge">
                            {formatEvaluationJobBadge(activeEvaluationJobs[session.session_id])}
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                  {selectedSession?.session_id === session.session_id && (
                    <tr key={session.session_id + '-detail'} className={fadingOutSessions.has(session.session_id) ? 'session-fade-out' : undefined}>
                      <td colSpan={8} className="session-detail-cell">
                        <SessionDetailInline
                          session={session}
                          onNavigateToLogs={handleViewInLogs}
                          showToast={showToast}
                          onEvaluationUpdate={(evalData) => handleEvaluationUpdate(session.session_id, evalData)}
                          onEvaluationPersisted={refreshModelEffectiveness}
                          activeEvaluationJob={activeEvaluationJobs[session.session_id] ?? null}
                        />
                      </td>
                    </tr>
                  )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          {loadingMore && (
              <div style={{ padding: '12px 24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px', borderTop: '1px solid var(--border-color)' }}>
                {t('Loading more...')}
              </div>
            )}
            {!hasMoreSessions && sessions.length > 50 && (
              <div style={{ padding: '12px 24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px', borderTop: '1px solid var(--border-color)' }}>
                {t('All sessions loaded')}
              </div>
            )}
          </div>
        </div>
        )}

      </div>
      )}
    </>
  )
}

// ─── Inline expanded session detail (inside table row) ────────────────────────

function SessionDetailInline({
  session,
  onNavigateToLogs,
  showToast,
  onEvaluationUpdate,
  onEvaluationPersisted,
  activeEvaluationJob,
}: {
  session: SessionSummary
  onNavigateToLogs: (session: SessionSummary, filters?: any) => void
  showToast: (msg: string) => void
  onEvaluationUpdate: (evalData: any | null) => void
  onEvaluationPersisted: () => void
  activeEvaluationJob?: EvaluationJobProgress | null
}) {
  return (
    <div className="session-detail-expanded" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 24px', flexWrap: 'wrap', gap: '20px' }}>
      <SessionDetailContent session={session} onNavigateToLogs={onNavigateToLogs} showToast={showToast} onEvaluationUpdate={onEvaluationUpdate} onEvaluationPersisted={onEvaluationPersisted} activeEvaluationJob={activeEvaluationJob} />
      <div style={{ display: 'flex', gap: '8px' }}>
        <button
          style={{ padding: '8px 18px', background: 'var(--color-blue)', color: 'white', borderRadius: '8px', fontSize: '13px', fontWeight: 700, cursor: 'pointer', border: 'none', boxShadow: '0 2px 4px rgba(59, 130, 246, 0.3)', display: 'flex', alignItems: 'center', gap: '6px' }}
          onClick={(e) => { e.stopPropagation(); onNavigateToLogs(session); }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
          </svg>
          {t('View in Logs')}
        </button>
      </div>
    </div>
  )
}
