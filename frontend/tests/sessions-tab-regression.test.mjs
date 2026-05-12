import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')
const dashboardSource = readFileSync(join(here, 'src', 'pages', 'DashboardPage.tsx'), 'utf-8')
const typesSource = readFileSync(join(here, 'src', 'types.ts'), 'utf-8')
const utilsSource = readFileSync(join(here, 'src', 'utils.tsx'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

test('view state type includes dashboard and logs only (no standalone sessions)', () => {
  assert.match(appSource, /useState<'dashboard' \| 'logs' \| 'settings'>/)
})

test('dashboardTab state is declared with overview and sessions', () => {
  assert.match(appSource, /const \[dashboardTab, setDashboardTab\] = useState<'overview' \| 'sessions'>\('overview'\)/)
})

test('sessions is NOT a top-level nav tab', () => {
  assert.doesNotMatch(appSource, /nav-item.*view === 'sessions'/)
})

test('sessions secondary tab button exists in dashboard', () => {
  assert.match(appSource, /dashboardTab === 'sessions' \? 'active' : ''/)
  assert.match(appSource, /onClick=\{.*setDashboardTab\('sessions'\)/)
})

test('sessions state variables are declared', () => {
  assert.match(appSource, /const \[sessions, setSessions\]/)
  assert.match(appSource, /const \[sessionsSummary, setSessionsSummary\]/)
  assert.match(appSource, /const \[sessionCount, setSessionCount\]/)
  assert.match(appSource, /const \[sessionsLoading, setSessionsLoading\]/)
  assert.match(appSource, /const \[sessionSortBy, setSessionSortBy\]/)
  assert.match(appSource, /const \[sessionSortOrder, setSessionSortOrder\]/)
  assert.match(appSource, /const \[selectedSession, setSelectedSession\]/)
})

test('sessions view block exists under dashboardTab', () => {
  assert.match(appSource, /\{dashboardTab === 'sessions' && \(/)
})

test('sessions summary cards are rendered', () => {
  const sessionsStart = appSource.indexOf("{dashboardTab === 'sessions' && (")
  assert.ok(sessionsStart !== -1, 'sessions tab block not found')
  const sessionsSection = appSource.slice(sessionsStart, sessionsStart + 3000)
  assert.match(sessionsSection, /t\('Total Sessions'\)/)
  assert.match(sessionsSection, /t\('Avg Duration'\)/)
  assert.match(sessionsSection, /t\('Estimated Cost'\)/)
  assert.match(sessionsSection, /t\('Average Response'\)/)
})

test('sessions average duration rounds seconds to two decimal places', () => {
  assert.match(utilsSource, /secondsFractionDigits\?: number/)
  assert.match(
    dashboardSource,
    /formatDuration\(sessionsSummary\.avg_duration_s, \{ secondsFractionDigits: 2 \}\)/,
  )
})

test('sessions insight cards are rendered above the sessions table', () => {
  const sessionsStart = appSource.indexOf("{dashboardTab === 'sessions' && (")
  assert.ok(sessionsStart !== -1, 'sessions tab block not found')
  const sessionsSection = appSource.slice(sessionsStart, sessionsStart + 5000)
  const insightsIndex = sessionsSection.indexOf('session-insights-grid')
  const tableIndex = sessionsSection.indexOf('<table className="table sessions-table">')
  assert.ok(insightsIndex !== -1, 'session insights grid not found')
  assert.ok(tableIndex !== -1, 'sessions table not found')
  assert.ok(insightsIndex < tableIndex, 'insight cards should appear before the sessions table')
  assert.match(sessionsSection, /sessionInsights\.map\(insight =>/)
  assert.match(appSource, /title: 'Most Expensive Session'/)
  assert.match(appSource, /title: 'Slowest Session'/)
  assert.match(appSource, /title: 'Biggest Token Burner'/)
  assert.match(appSource, /title: 'Best Cache Saver'/)
  assert.match(appSource, /title: 'Reliability Watch'/)
  assert.match(sessionsSection, /handleViewInLogs\(insight\.session\)/)
})

test('sessions insight cards are derived from loaded filtered sessions only', () => {
  assert.match(appSource, /const sessionInsights = useMemo\(\(\) => \{/)
  const helperStart = appSource.indexOf('function buildSessionInsights')
  assert.ok(helperStart !== -1, 'buildSessionInsights helper not found')
  const helperSource = appSource.slice(helperStart, helperStart + 4500)
  assert.match(helperSource, /sessions: SessionSummary\[\]/)
  assert.match(helperSource, /mostExpensive.*sort.*total_cost_usd/s)
  assert.match(helperSource, /slowest.*sort.*avg_latency_ms/s)
  assert.match(helperSource, /tokenBurner.*sort.*total_tokens/s)
  assert.match(helperSource, /cacheSaver.*cached_tokens > 0/s)
  assert.match(helperSource, /reliabilityWatch.*failed_requests > 0/s)
  assert.doesNotMatch(helperSource, /sessionsSummary/)
  assert.doesNotMatch(helperSource, /fetch\(/)
})

test('sessions insight cards keep no-data state clean and do not fake optional insights', () => {
  const helperStart = appSource.indexOf('function buildSessionInsights')
  assert.ok(helperStart !== -1, 'buildSessionInsights helper not found')
  const helperSource = appSource.slice(helperStart, helperStart + 4500)
  assert.match(helperSource, /if \(sessions\.length === 0\) return \[\]/)
  assert.match(helperSource, /if \(cacheSaver\) \{/)
  assert.match(helperSource, /if \(reliabilityWatch\) \{/)
  assert.doesNotMatch(helperSource, /No insights/)
  assert.doesNotMatch(helperSource, /placeholder/i)
})

test('empty sessions renders a standalone first-session card instead of an empty table row', () => {
  const sessionsStart = appSource.indexOf("{dashboardTab === 'sessions' && (")
  assert.ok(sessionsStart !== -1, 'sessions tab block not found')
  const sessionsSection = appSource.slice(sessionsStart, sessionsStart + 9000)
  assert.match(sessionsSection, /sessions\.length === 0 && !sessionsLoading/)
  assert.match(sessionsSection, /className="sessions-empty-state panel"/)
  assert.match(sessionsSection, /t\('No sessions yet\.'\)/)
  assert.match(sessionsSection, /t\('Run llm-tracker codex, llm-tracker claude, or llm-tracker gemini to create your first tracked session\.'\)/)
  assert.match(sessionsSection, /sessions\.length > 0 \|\| sessionsLoading/)
  assert.doesNotMatch(sessionsSection, /<td colSpan=\{8\}[\s\S]*No sessions found for the selected filters\./)
})

test('sessions table has supported sortable columns', () => {
  assert.match(appSource, /handleSessionSort/)
  assert.match(appSource, /sessionSortBy === 'avg_latency_ms'/)
  assert.match(appSource, /sessionSortBy === 'total_cost_usd'/)
  assert.match(appSource, /sessionSortBy === 'duration_s'/)
})

test('sessions table renders session data', () => {
  assert.match(appSource, /sessions\.map\(session =>/)
  assert.match(appSource, /session\.session_id/)
  assert.match(appSource, /formatDuration\(session\.duration_s\)/)
  assert.match(appSource, /formatCost\(session\.total_cost_usd\)/)
})

test('sessions table uses human-first row hierarchy with compact health', () => {
  const sessionsStart = appSource.indexOf("{dashboardTab === 'sessions' && (")
  assert.ok(sessionsStart !== -1, 'sessions tab block not found')
  const sessionsSection = appSource.slice(sessionsStart, sessionsStart + 9000)
  assert.match(sessionsSection, /<table className="table sessions-table">/)
  assert.match(sessionsSection, /t\('Session'\)/)
  assert.match(sessionsSection, /t\('Agent'\)/)
  assert.match(sessionsSection, /t\('Health'\)/)
  assert.match(sessionsSection, /sessionDisplayName\(session\).*formatTime\(session\.started\)/s)
  assert.match(sessionsSection, /shortSessionId\(session\.session_id\)/)
  assert.match(sessionsSection, /<ClickToCopy text=\{session\.session_id\} onCopy=\{showToast\}>/)
  assert.doesNotMatch(sessionsSection, /className="btn-ghost session-copy-id"/)
  assert.match(sessionsSection, /session-health-badge session-health-latency/)
  assert.match(sessionsSection, /session-health-badge session-health-ttft/)
  assert.doesNotMatch(sessionsSection, /t\('Avg Response'\).*<\/th>/s)
  assert.doesNotMatch(sessionsSection, /t\('Avg TTFT'\).*<\/th>/s)
})

test('session detail panel exists', () => {
  assert.match(appSource, /selectedSession && \(/)
  assert.match(appSource, /t\('Session Details'\)/)
  assert.match(appSource, /t\('View in Logs'\)/)
})

test('expanded session detail is diagnostic with summary, supported badges, mini stats, and actions', () => {
  assert.match(appSource, /function buildSessionDiagnosis\(session: SessionSummary, translate: SessionDiagnosisTranslator/)
  assert.match(appSource, /translate\('High-volume'\)|translate\('Light-volume'\)/)
  assert.match(appSource, /translate\('excellent cache reuse'\)|translate\('little cache reuse'\)/)
  assert.match(appSource, /translate\('moderate latency'\)|translate\('slow latency'\)|translate\('fast latency'\)/)
  assert.match(appSource, /translate\('session diagnosis summary'/)
  assert.match(appSource, /function buildSessionBadges\(session: SessionSummary\)/)
  assert.match(appSource, /label: 'High cost'/)
  assert.match(appSource, /label: 'Slow'/)
  assert.match(appSource, /label: 'Great cache'/)
  assert.match(appSource, /label: 'Many requests'/)
  assert.match(appSource, /label: 'Error spike'/)

  const expandedStart = appSource.indexOf('className="session-detail-expanded"')
  assert.ok(expandedStart !== -1, 'expanded session detail block not found')
  const expandedBlock = appSource.slice(expandedStart, expandedStart + 4500)
  assert.match(expandedBlock, /className="session-detail-summary"[\s\S]*buildSessionDiagnosis\(session, translateSessionDiagnosis\.bind\(null, t\)\)/)
  assert.match(expandedBlock, /aria-label=\{t\('Session signals'\)\}/)
  assert.doesNotMatch(expandedBlock, /aria-label="Session signals"/)
  assert.match(expandedBlock, /buildSessionBadges\(session\)\.map\(badge =>/)
  assert.match(expandedBlock, /className=\{`session-detail-badge session-detail-badge-\$\{badge\.tone\}`\}/)
  assert.match(expandedBlock, /className="session-mini-stats"/)
  assert.match(expandedBlock, /t\('Cost'\)[\s\S]*formatCost\(session\.total_cost_usd\)/)
  assert.match(expandedBlock, /t\('Tokens'\)[\s\S]*formatCompact\(session\.total_tokens\)/)
  assert.match(expandedBlock, /session\.cached_tokens > 0[\s\S]*t\('Cache'\)/)
  assert.match(expandedBlock, /t\('Latency\/TTFT'\)[\s\S]*formatLatency\(session\.avg_latency_ms\)/)
  assert.match(expandedBlock, /t\('Requests'\)[\s\S]*formatNumber\(session\.request_count\)/)
  assert.match(expandedBlock, /className="session-detail-actions"/)
  assert.match(expandedBlock, /handleViewInLogs\(session\)/)
  assert.doesNotMatch(expandedBlock, /copyTextToClipboard\(session\.session_id, showToast\)/)
  assert.match(expandedBlock, /<ClickToCopy text=\{session\.session_id\} onCopy=\{showToast\}>/)
  assert.match(expandedBlock, /className="session-detail-full-id"/)
  assert.doesNotMatch(expandedBlock, /t\('Timeline'\)/)
  assert.doesNotMatch(expandedBlock, /t\('Avg Throughput'\)/)
  assert.doesNotMatch(expandedBlock, /t\('Token Usage'\)/)
})

test('standalone selected session panel uses same diagnostic detail component', () => {
  const panelStart = appSource.indexOf('{selectedSession && (')
  assert.ok(panelStart !== -1, 'selected session panel not found')
  const panelBlock = appSource.slice(panelStart, panelStart + 4500)
  assert.match(panelBlock, /className="session-detail-panel(?: panel)?"/)
  assert.match(panelBlock, /buildSessionDiagnosis\(selectedSession, translateSessionDiagnosis\.bind\(null, t\)\)/)
  assert.match(panelBlock, /buildSessionBadges\(selectedSession\)/)
  assert.match(panelBlock, /<ClickToCopy text=\{selectedSession\.session_id\} onCopy=\{showToast\}>/)
  assert.doesNotMatch(panelBlock, /copyTextToClipboard\(selectedSession\.session_id, showToast\)/)
  assert.doesNotMatch(panelBlock, /gridTemplateColumns: '1fr 1fr 1fr'/)
  assert.doesNotMatch(panelBlock, /t\('Source'\)/)
  assert.doesNotMatch(panelBlock, /t\('Avg TTFT'\)/)
})

test('view in logs handler switches view and sets session filter', () => {
  assert.match(appSource, /handleViewInLogs/)
  assert.match(appSource, /setSessionFilter\(session\.session_id\)/)
  assert.match(appSource, /setView\('logs'\)/)
})

test('session filter state exists and is used in applyFilterParams', () => {
  assert.match(appSource, /const \[sessionFilter, setSessionFilter\]/)
  assert.match(appSource, /sessionFilter.*searchParams\.set\('session_id'/)
})

test('session filter badge appears in logs view when active', () => {
  const logsStart = appSource.indexOf("{view === 'logs' && (")
  assert.ok(logsStart !== -1)
  const logsSection = appSource.slice(logsStart, logsStart + 7000)
  assert.match(logsSection, /sessionFilter && \(/)
})

test('sessions data is fetched from /sessions endpoint with correct params', () => {
  assert.match(appSource, /new URL\('\/sessions'/)
  assert.match(appSource, /new URL\('\/sessions\/summary'/)
  assert.match(appSource, /sessionsUrl\.searchParams\.set\('sort_by', sessionSortBy\)/)
  assert.match(appSource, /sessionsUrl\.searchParams\.set\('sort_order', sessionSortOrder\)/)
  assert.match(appSource, /sessionsUrl\.searchParams\.set\('limit', '50'\)/)
  assert.match(appSource, /sessionsUrl\.searchParams\.set\('offset'/)
})

test('sessions fetch guard fires for dashboard sessions tab and logs', () => {
  assert.match(appSource, /view === 'logs' \|\| \(view === 'dashboard' && dashboardTab === 'sessions'\)/)
})

test('sessions fetch useEffect includes dashboardTab in deps', () => {
  assert.match(appSource, /}, \[view, dashboardTab, activeSource/)
})

test('View in Logs sets session_id URL param on /usage fetch', () => {
  assert.match(appSource, /if \(sessionFilter\) url\.searchParams\.set\('session_id', sessionFilter\)/)
  assert.match(appSource, /sessionFilter\]/)
})

test('View in Logs handler clears session filter via button', () => {
  assert.match(appSource, /setSessionFilter\(null\); resetPage\(\)/)
})

test('SessionSummary type is defined', () => {
  assert.match(typesSource, /export type SessionSummary/)
  assert.match(typesSource, /session_id: string/)
  assert.match(typesSource, /duration_s: number/)
  assert.match(typesSource, /total_cost_usd: number/)
})

test('SessionsSummary type is defined', () => {
  assert.match(typesSource, /export type SessionsSummary/)
  assert.match(typesSource, /session_count: number/)
})

test('formatDuration helper exists', () => {
  assert.match(utilsSource, /export function formatDuration/)
  assert.match(utilsSource, /\$\{m\}m \$\{rem\}s/)
  assert.match(utilsSource, /\$\{h\}h \$\{remM\}m/)
})

test('Chinese translations include session keys', () => {
  for (const key of [
    'Sessions',
    'Total Sessions',
    'View in Logs',
    'Health',
    'Copy ID',
    'High cost',
    'Slow',
    'Great cache',
    'Many requests',
    'Error spike',
    'Copy session ID',
    'Latency/TTFT',
    'hit',
    'Session signals',
    'High-volume',
    'Moderate-volume',
    'Light-volume',
    'little cache reuse',
    'excellent cache reuse',
    'some cache reuse',
    'slow latency',
    'moderate latency',
    'fast latency',
    'no recorded errors',
    'session failed requests',
    'session diagnosis summary',
    'failed',
    'No sessions yet.',
    'Run llm-tracker codex, llm-tracker claude, or llm-tracker gemini to create your first tracked session.',
  ]) {
    assert.match(zhSource, new RegExp(`'${key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}':`))
  }
  assert.match(zhSource, /'failed': '失败'/)
})
