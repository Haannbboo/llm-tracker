import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')
const appStyles = readFileSync(join(here, 'src', 'App.css'), 'utf-8')

test('manual refresh button uses the shared usage refresh callback', () => {
  assert.match(appSource, /const requestUsageRefresh = useCallback/)
  assert.match(appSource, /onClick=\{requestUsageRefresh\}/)
})

test('dashboard toolbar exposes the shared refresh action', () => {
  const dashboardStart = appSource.indexOf("{view === 'dashboard' && (")
  const widgetsStart = appSource.indexOf('<div className="widgets-grid">')

  assert.notEqual(dashboardStart, -1)
  assert.notEqual(widgetsStart, -1)

  const dashboardToolbar = appSource.slice(dashboardStart, widgetsStart)

  assert.match(dashboardToolbar, /onClick=\{requestUsageRefresh\}/)
  assert.match(dashboardToolbar, /className="btn-ghost btn-refresh"/)
  assert.match(dashboardToolbar, /aria-label=\{t\('Refresh'\)\}/)
  assert.match(dashboardToolbar, /title=\{t\('Refresh'\)\}/)
  assert.match(dashboardToolbar, /className="refresh-icon"/)
  assert.doesNotMatch(dashboardToolbar, /<\/span>\s*\{t\('Refresh'\)\}/)
})

test('refresh button keeps minimal outer padding', () => {
  assert.match(appStyles, /\.btn-refresh\s*\{[^}]*padding: 4px;/s)
})

test('refresh button reveals a subtle chart-like background on hover', () => {
  assert.match(appStyles, /\.btn-refresh::before\s*\{[^}]*opacity: 0;/s)
  assert.match(appStyles, /\.btn-refresh:hover\s*\{[^}]*transform: scale\(1\.04\);/s)
  assert.match(appStyles, /\.btn-refresh:hover\s*\{[^}]*box-shadow: 0 4px 12px -2px rgba\(0, 0, 0, 0\.1\);/s)
  assert.match(appStyles, /\.btn-refresh:hover::before\s*\{[^}]*opacity: 1;/s)
})

test('navbar items share the refresh hover lift and shadow', () => {
  assert.match(appStyles, /\.nav-item\s*\{[^}]*transition: [^;}]*transform 0\.2s ease[^;}]*box-shadow 0\.2s ease/s)
  assert.match(appStyles, /\.nav-item:hover\s*\{[^}]*transform: scale\(1\.04\);/s)
  assert.match(appStyles, /\.nav-item:hover\s*\{[^}]*box-shadow: 0 4px 12px -2px rgba\(0, 0, 0, 0\.1\);/s)
})

test('dashboard and logs filters share the refresh hover lift and shadow', () => {
  assert.match(appSource, /className="dashboard-filter-row"/)
  assert.match(appStyles, /\.dashboard-filter-row \.input-plain,\s*\.filter-bar \.input-plain\s*\{[^}]*transition: border-color 0\.2s ease, box-shadow 0\.2s ease, transform 0\.2s ease;/s)
  assert.match(appStyles, /\.dashboard-filter-row \.input-plain:hover,\s*\.filter-bar \.input-plain:hover\s*\{[^}]*transform: scale\(1\.04\);/s)
  assert.match(appStyles, /\.dashboard-filter-row \.input-plain:hover,\s*\.filter-bar \.input-plain:hover\s*\{[^}]*box-shadow: 0 4px 12px -2px rgba\(0, 0, 0, 0\.1\);/s)
})

test('request logs 24h shortcut is labeled by its actual range', () => {
  assert.match(appSource, /\{t\('Last 24h'\)\}/)
  assert.doesNotMatch(appSource, /\{t\('Today'\)\}/)
})
