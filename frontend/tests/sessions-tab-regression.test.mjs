import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')
const typesSource = readFileSync(join(here, 'src', 'types.ts'), 'utf-8')
const utilsSource = readFileSync(join(here, 'src', 'utils.tsx'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

test('view state type includes sessions', () => {
  assert.match(appSource, /useState<'dashboard' \| 'logs' \| 'sessions' \| 'settings' \| 'test'>/)
})

test('sessions tab button exists in navbar', () => {
  assert.match(appSource, /view === 'sessions' \? 'active' : ''\}/)
  assert.match(appSource, /\{t\('Sessions'\)\}/)
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

test('sessions view block exists', () => {
  assert.match(appSource, /\{view === 'sessions' && \(/)
})

test('sessions summary cards are rendered', () => {
  const sessionsStart = appSource.indexOf("{view === 'sessions' && (")
  assert.ok(sessionsStart !== -1, 'sessions view block not found')
  const sessionsSection = appSource.slice(sessionsStart, sessionsStart + 3000)
  assert.match(sessionsSection, /t\('Total Sessions'\)/)
  assert.match(sessionsSection, /t\('Avg Duration'\)/)
  assert.match(sessionsSection, /t\('Estimated Cost'\)/)
  assert.match(sessionsSection, /t\('Average Response'\)/)
})

test('sessions table has sortable columns', () => {
  assert.match(appSource, /handleSessionSort/)
  assert.match(appSource, /sessionSortBy === 'session_id'/)
  assert.match(appSource, /sessionSortBy === 'total_cost_usd'/)
  assert.match(appSource, /sessionSortBy === 'duration_s'/)
})

test('sessions table renders session data', () => {
  assert.match(appSource, /sessions\.map\(session =>/)
  assert.match(appSource, /session\.session_id/)
  assert.match(appSource, /formatDuration\(session\.duration_s\)/)
  assert.match(appSource, /formatCost\(session\.total_cost_usd\)/)
})

test('session detail panel exists', () => {
  assert.match(appSource, /selectedSession && \(/)
  assert.match(appSource, /t\('Session Details'\)/)
  assert.match(appSource, /t\('View in Logs'\)/)
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
  const logsSection = appSource.slice(logsStart, logsStart + 5000)
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
  assert.match(zhSource, /'Sessions': '会话'/)
  assert.match(zhSource, /'Total Sessions': '总会话数'/)
  assert.match(zhSource, /'View in Logs': '在日志中查看'/)
})
