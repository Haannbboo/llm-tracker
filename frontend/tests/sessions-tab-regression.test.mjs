import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')
const dashboardSource = readFileSync(join(here, 'src', 'pages', 'DashboardPage.tsx'), 'utf-8')
const detailPanelSource = readFileSync(join(here, 'src', 'components', 'SessionDetailPanel.tsx'), 'utf-8')
const typesSource = readFileSync(join(here, 'src', 'types.ts'), 'utf-8')
const utilsSource = readFileSync(join(here, 'src', 'utils.tsx'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

test('view state type includes dashboard and logs only (no standalone sessions)', () => {
  assert.match(appSource, /const currentView = location\.pathname\.startsWith\('\/logs'\)/)
})

test('dashboardTab state is declared with overview and sessions', () => {
  assert.match(dashboardSource, /const \[dashboardTab, setDashboardTab\] = useState<'overview' \| 'sessions'>\('overview'\)/)
})

test('sessions is NOT a top-level nav tab', () => {
  const navbarSource = readFileSync(join(here, 'src', 'components', 'Navbar.tsx'), 'utf-8')
  assert.doesNotMatch(navbarSource, /nav-item.*currentView === 'sessions'/)
})

test('sessions secondary tab button exists in dashboard', () => {
  assert.match(dashboardSource, /dashboardTab === 'sessions' \? 'active' : ''/)
  assert.match(dashboardSource, /onClick=\{.*setDashboardTab\('sessions'\)/)
})

test('sessions state variables are declared', () => {
  const useSessionsSource = readFileSync(join(here, 'src', 'hooks', 'useSessionsData.ts'), 'utf-8')
  assert.match(useSessionsSource, /const \[sessions, setSessions\]/)
  assert.match(dashboardSource, /const \[sessionsSummary, setSessionsSummary\]/)
  assert.match(useSessionsSource, /const \[sessionsLoading, setSessionsLoading\]/)
  assert.match(useSessionsSource, /const \[sessionSortBy, setSessionSortBy\]/)
  assert.match(useSessionsSource, /const \[sessionSortOrder, setSessionSortOrder\]/)
  assert.match(useSessionsSource, /const \[selectedSession, setSelectedSession\]/)
})

test('sessions view block exists under dashboardTab', () => {
  assert.match(dashboardSource, /\{dashboardTab === 'sessions' && \(/)
})

test('sessions summary cards are rendered', () => {
  const sessionsStart = dashboardSource.indexOf("{dashboardTab === 'sessions' && (")
  assert.ok(sessionsStart !== -1, 'sessions tab block not found')
  const sessionsSection = dashboardSource.slice(sessionsStart, sessionsStart + 3000)
  assert.match(sessionsSection, /t\('Total Sessions'\)/)
  assert.match(sessionsSection, /t\('Avg Duration'\)/)
  assert.match(sessionsSection, /t\('Estimated Cost'\)/)
  assert.match(sessionsSection, /t\('Avg Latency'\)/)
})

test('sessions average duration rounds seconds to two decimal places', () => {
  assert.match(utilsSource, /secondsFractionDigits\?: number/)
  assert.match(
    dashboardSource,
    /formatDuration\(sessionsSummary\.avg_duration_s, \{ secondsFractionDigits: 2 \}\)/,
  )
})

test('sessions insight cards are rendered above the sessions table', () => {
  const sessionsStart = dashboardSource.indexOf("{dashboardTab === 'sessions' && (")
  assert.ok(sessionsStart !== -1, 'sessions tab block not found')
  const sessionsSection = dashboardSource.slice(sessionsStart, sessionsStart + 20000)
  const insightsIndex = sessionsSection.indexOf('session-insights-grid')
  const tableIndex = sessionsSection.indexOf('<table className="table sessions-table">')
  assert.ok(insightsIndex !== -1, 'session insights grid not found')
  assert.ok(tableIndex !== -1, 'sessions table not found')
  assert.ok(insightsIndex < tableIndex, 'insight cards should appear before the sessions table')
  assert.match(sessionsSection, /sessionInsights\.map\(insight =>/)
  assert.match(utilsSource, /title: 'Most Expensive Session'/)
  assert.match(utilsSource, /title: 'Slowest Session'/)
  assert.match(utilsSource, /title: 'Biggest Token Burner'/)
  assert.match(utilsSource, /title: 'Best Cache Saver'/)
  assert.match(utilsSource, /title: 'Reliability Watch'/)
  assert.match(dashboardSource, /handleViewInLogs\(insight\.session, \{ onlyFailed: insight\.onlyFailed \}\)/)
})

test('sessions insight cards are derived from loaded filtered sessions only', () => {
  assert.match(utilsSource, /export function buildSessionInsights\(sessions: import\('\.\/types'\)\.SessionSummary\[\]\)/)
  assert.match(utilsSource, /mostExpensive.*sort.*total_cost_usd/s)
  assert.match(utilsSource, /slowest.*sort.*avg_latency_ms/s)
  assert.match(utilsSource, /tokenBurner.*sort.*total_tokens/s)
  assert.match(utilsSource, /cacheSaver.*cached_tokens > 0/s)
  assert.match(utilsSource, /reliabilityWatch.*failed_requests > 0/s)
})

test('sessions insight cards keep no-data state clean and do not fake optional insights', () => {
  assert.match(utilsSource, /if \(sessions\.length === 0\) return \[\]/)
  assert.match(utilsSource, /if \(cacheSaver\) \{/)
  assert.match(utilsSource, /if \(reliabilityWatch\) \{/)
  assert.doesNotMatch(utilsSource, /No insights/)
  assert.doesNotMatch(utilsSource, /placeholder/i)
})

test('empty sessions renders a standalone first-session card instead of an empty table row', () => {
  const sessionsStart = dashboardSource.indexOf("{dashboardTab === 'sessions' && (")
  assert.ok(sessionsStart !== -1, 'sessions tab block not found')
  const sessionsSection = dashboardSource.slice(sessionsStart, sessionsStart + 20000)
  assert.match(sessionsSection, /sessions\.length === 0 && !sessionsLoading/)
  assert.match(sessionsSection, /className="sessions-empty-state panel"/)
  assert.match(sessionsSection, /t\('No sessions yet\.'\)/)
  assert.match(sessionsSection, /t\('Run llm-tracker codex, llm-tracker claude, or llm-tracker gemini to create your first tracked session\.'\)/)
  assert.match(sessionsSection, /\(sessions\.length > 0 \|\| sessionsLoading\)/)
})

test('sessions table has supported sortable columns', () => {
  assert.match(dashboardSource, /handleSessionSort/)
  assert.match(dashboardSource, /handleSessionSort\('avg_latency_ms'\)/)
  assert.match(dashboardSource, /handleSessionSort\('total_cost_usd'\)/)
  assert.match(dashboardSource, /handleSessionSort\('duration_s'\)/)
})

test('sessions table renders session data', () => {
  assert.match(dashboardSource, /sessions\.filter\([\s\S]*\)\.map\(session =>/)
  assert.match(dashboardSource, /session\.session_id/)
  assert.match(dashboardSource, /formatDuration\(session\.duration_s\)/)
  assert.match(dashboardSource, /formatCost\(session\.total_cost_usd\)/)
})

test('sessions table uses human-first row hierarchy with compact health', () => {
  const sessionsStart = dashboardSource.indexOf("{dashboardTab === 'sessions' && (")
  assert.ok(sessionsStart !== -1, 'sessions tab block not found')
  const sessionsSection = dashboardSource.slice(sessionsStart, sessionsStart + 20000)
  assert.match(sessionsSection, /<table className="table sessions-table">/)
  assert.match(sessionsSection, /t\('Session'\)/)
  assert.match(sessionsSection, /t\('Agent'\)/)
  assert.match(sessionsSection, /t\('Health'\)/)
  assert.match(sessionsSection, /sessionDisplayName\(session\).*formatTime\(session\.started\)/s)
  assert.match(sessionsSection, /shortSessionId\(session\.session_id\)/)
  assert.match(sessionsSection, /<ClickToCopy text=\{session\.session_id\} onCopy=\{showToast\}>/)
  assert.match(sessionsSection, /session-health-badge session-health-latency/)
  assert.match(sessionsSection, /session-health-badge session-health-ttft/)
})

test('session detail panel exists', () => {
  assert.match(dashboardSource, /selectedSession && \(/)
  assert.match(dashboardSource, /t\('Session Details'\)/)
  assert.match(dashboardSource, /t\('View in Logs'\)/)
})

test('session detail content component is diagnostic with summary and mini stats', () => {
  assert.match(detailPanelSource, /export function SessionDetailContent/)
  assert.match(detailPanelSource, /t\('Timeline'\)/)
  assert.match(detailPanelSource, /t\('Cost'\)/)
  assert.match(detailPanelSource, /t\('Token Usage'\)/)
  assert.match(detailPanelSource, /t\('Performance'\)/)
  assert.match(detailPanelSource, /t\('Requests'\)/)
  assert.match(detailPanelSource, /t\('Cache Hit Rate'\)/)
  assert.match(detailPanelSource, /t\('Avg Throughput'\)/)
  assert.match(detailPanelSource, /<ClickToCopy text=\{session\.session_id\} onCopy=\{showToast\}>/)
})

test('view in logs handler navigates to logs with session filter', () => {
  assert.match(appSource, /const handleNavigateToLogs = useCallback\(\(filters\?: \{ sessionFilter\?: string; activeFilter\?: ActiveFilter \}\) => \{/)
  assert.match(appSource, /navigate\('\/logs'\)/)
})

test('session filter state is used in logs page and hooks', () => {
  const logsPageSource = readFileSync(join(here, 'src', 'pages', 'LogsPage.tsx'), 'utf-8')
  assert.match(logsPageSource, /const \[sessionFilter, setSessionFilter\] = useState<string \| null>/)
  const useLogsSource = readFileSync(join(here, 'src', 'hooks', 'useLogsData.ts'), 'utf-8')
  assert.match(useLogsSource, /if \(opts\.sessionFilter\) usageUrl\.searchParams\.set\('session_id', opts\.sessionFilter\)/)
})

test('sessions data is fetched from /sessions endpoint with correct params', () => {
  const useSessionsSource = readFileSync(join(here, 'src', 'hooks', 'useSessionsData.ts'), 'utf-8')
  assert.match(useSessionsSource, /new URL\('\/sessions'/)
  assert.match(dashboardSource, /new URL\('\/sessions\/summary'/)
  assert.match(useSessionsSource, /sessionsUrl\.searchParams\.set\('sort_by', sessionSortBy\)/)
  assert.match(useSessionsSource, /sessionsUrl\.searchParams\.set\('sort_order', sessionSortOrder\)/)
  assert.match(useSessionsSource, /sessionsUrl\.searchParams\.set\('limit', '50'\)/)
  assert.match(useSessionsSource, /sessionsUrl\.searchParams\.set\('offset', String\(\(sessionPage - 1\) \* 50\)\)/)
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
  assert.match(utilsSource, /return rem > 0 \? `\$\{m\}m \$\{formatDurationSeconds\(rem, options\)\}` : `\$\{m\}m`/)
})
