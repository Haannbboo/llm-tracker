import { useCountUp } from '../useCountUp'
import { TrendChart } from '../charts/TrendChart'
import { TopUsageChart } from '../charts/TopUsageChart'
import { ToolCallsChart } from '../charts/ToolCallsChart'
import { DailyHeatmap } from '../charts/DailyHeatmap'
import { Sparkline } from '../Sparkline'
import { CopyButton } from '../components/CopyButton'
import { t } from '../i18n/index.ts'
import {
  formatCompact, formatCost, formatLatency, formatNumber, formatRate, formatThroughput,
  value, getAgentDisplayName,
} from '../utils'

type OverviewTabProps = {
  theme: any
  summary: any[]
  dailyUsage: any[]
  heatmapData: any[]
  dashboardInitialLoading: boolean
  dashboardRefreshing: boolean
  dateRange: string
  dashboardFilterParams: any
  totals: any
  showFirstRunOnboarding: boolean
  verifyPhase: string
  verificationResult: any
  copiedOnboardingCommand: any
  armOnboardingVerification: (value: any) => void
  resetVerification: () => void
  setupConfiguredAgents: number
  setupSummaryText: string
  setupSummaryColor: string
  verifyTimeoutGuidance: string
  setupDiagnostics: any
  localAgents: Record<string, { found: boolean; path: string | null }> | null
  sources: string[]
  error: string | null
  setActiveFilter: (value: any) => void
  onNavigateToLogs: (filters?: any) => void
}

export function OverviewTab({
  theme,
  summary,
  dailyUsage,
  heatmapData,
  dashboardInitialLoading,
  dashboardRefreshing,
  dateRange,
  dashboardFilterParams,
  totals,
  showFirstRunOnboarding,
  verifyPhase,
  verificationResult,
  copiedOnboardingCommand,
  armOnboardingVerification,
  resetVerification,
  setupConfiguredAgents,
  setupSummaryText,
  setupSummaryColor,
  verifyTimeoutGuidance,
  setupDiagnostics,
  localAgents,
  sources,
  error,
  setActiveFilter,
  onNavigateToLogs,
}: OverviewTabProps) {
  const animatedTotalTokens = useCountUp(dashboardInitialLoading ? 0 : totals.totalTokens)
  const animatedRequests = useCountUp(dashboardInitialLoading ? 0 : totals.requests)
  const animatedCost = useCountUp(dashboardInitialLoading ? 0 : totals.totalCost)
  const animatedRpm = useCountUp(dashboardInitialLoading ? 0 : totals.rpm)
  const animatedLatency = useCountUp(dashboardInitialLoading ? 0 : totals.avgLatency)
  const animatedThroughput = useCountUp(dashboardInitialLoading ? 0 : totals.avgThroughput)

  return (
    <>

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
          Array.from({ length: 6 }, (_, i) => (
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
                {/* cache_creation_tokens is disjoint from prompt_tokens (Anthropic semantics),
                    so it's added to the denominator for a true hit rate. */}
                <Sparkline data={dailyUsage.map(d => (value(d.prompt_tokens) + value(d.cache_creation_tokens)) > 0 ? (value(d.cached_tokens) / (value(d.prompt_tokens) + value(d.cache_creation_tokens))) * 100 : 0)} color="var(--color-green)" />
              </div>
            </div>
            <div className="stat-label" style={{ marginBottom: 0 }}>
              {/* cache_creation_tokens folds into "In" (fresh input, billed
                  differently from cache-read) so In + Out reconciles with
                  the Token Usage total above. */}
              {t('In:')} {formatCompact(totals.promptTokens + totals.cacheCreationTokens)} / {t('Out:')} {formatCompact(totals.completionTokens)}
            </div>
            <div className="stat-label" style={{ fontSize: '11px', marginBottom: 0 }}>
              {t('Cached:')} {formatCompact(totals.cachedTokens)}
              <span style={{ marginLeft: '6px', color: 'var(--color-green)', fontWeight: 600 }}>
                ({(totals.promptTokens + totals.cacheCreationTokens) > 0 ? ((value(totals.cachedTokens) / (totals.promptTokens + totals.cacheCreationTokens)) * 100).toFixed(1) : 0}% {t('Hit)')}
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
                        setActiveFilter({ provider: '', model: null, only_failed: true })
                        onNavigateToLogs()
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
                      setActiveFilter({ provider: '', model: null, status_429: true })
                      onNavigateToLogs()
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
                      setActiveFilter({ provider: '', model: null, status_5xx: true })
                      onNavigateToLogs()
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
                      setActiveFilter({ provider: '', model: null, status_4xx: true })
                      onNavigateToLogs()
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

        <div className="widget">
          <div className="widget-body" style={{ flexDirection: 'column', alignItems: 'stretch', justifyContent: 'center' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div className="icon-box icon-purple">🚀</div>
                <div>
                  <div className="stat-label">{t('Average Throughput')}</div>
                  <div className="stat-value">{formatThroughput(animatedThroughput)}</div>
                </div>
              </div>
              <div style={{ width: '100px' }}>
                <Sparkline data={dailyUsage.map(d => value(d.avg_throughput))} color="var(--color-purple)" />
              </div>
            </div>
          </div>
        </div>
          </>
        )}
      </div>

      <div className="overview-split-row" style={{ marginBottom: '24px' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <TopUsageChart
            summary={summary}
            theme={theme}
            filterParams={dashboardFilterParams}
            showTrend={false}
          />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <ToolCallsChart filterParams={dashboardFilterParams} />
        </div>
      </div>

      <div className="overview-split-row overview-trend-row">
        <div style={{ flex: '1 1 0', minWidth: 0 }}>
          <TrendChart
            data={dailyUsage}
            title={`${dateRange === '24h' ? t('Hourly Usage Trend') : t('Daily Usage Trend')}`}
            granularity={dateRange === '24h' ? 'hour' : 'day'}
            periodCount={dateRange === '24h' ? 24 : dateRange === '7d' ? 7 : dateRange === '30d' ? 30 : 365}
            showDots={dateRange !== 'all'}
          />
        </div>
        <div style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <DailyHeatmap mode="activity" data={heatmapData} />
            <DailyHeatmap mode="success-rate" data={heatmapData} />
          </div>
      </div>
      </div>

      )}

    </>
  )
}
