import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')
const cssSource = readFileSync(join(here, 'src', 'App.css'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

// Top-level nav: exactly 3 tabs
test('top nav has exactly Dashboard, Request Logs, Settings', () => {
  assert.match(appSource, /nav-item[\s\S]*view === 'dashboard'[\s\S]*Dashboard/)
  assert.match(appSource, /nav-item[\s\S]*view === 'logs'[\s\S]*Request Logs/)
  assert.match(appSource, /nav-item[\s\S]*view === 'settings'[\s\S]*Settings/)
})

test('Sessions is NOT a top-level nav item', () => {
  assert.doesNotMatch(appSource, /className=\{`nav-item.*view === 'sessions'/)
})

test('Connectivity Test is NOT a top-level nav item', () => {
  assert.doesNotMatch(appSource, /className=\{`nav-item.*view === 'test'/)
})

test('view state type is dashboard | logs | settings', () => {
  assert.match(appSource, /useState<'dashboard' \| 'logs' \| 'settings'>/)
})

// Dashboard secondary tabs
test('dashboard has secondary tabs: Overview | Sessions', () => {
  assert.match(appSource, /className="dashboard-tabs"/)
  assert.match(appSource, /dashboardTab === 'overview' \? 'active' : ''/)
  assert.match(appSource, /dashboardTab === 'sessions' \? 'active' : ''/)
})

test('overview tab is the default', () => {
  assert.match(appSource, /useState<'overview' \| 'sessions'>\('overview'\)/)
})

test('overview tab content renders dashboard charts', () => {
  assert.match(appSource, /\{dashboardTab === 'overview' && \(</)
})

// Connectivity test moved into settings
test('connectivity test panel is inside settings view', () => {
  const settingsStart = appSource.indexOf("{view === 'settings' && (")
  assert.ok(settingsStart !== -1, 'settings view block not found')
  // Find the Upstream Connectivity Test label after the settings start
  const settingsSection = appSource.slice(settingsStart)
  assert.match(settingsSection, /t\('Upstream Connectivity Test'\)/)
})

test('standalone test view block is removed', () => {
  assert.doesNotMatch(appSource, /\{view === 'test' && \(/)
})

test('connectivity test form fields exist in settings', () => {
  const settingsStart = appSource.indexOf("{view === 'settings' && (")
  assert.ok(settingsStart !== -1)
  const settingsSection = appSource.slice(settingsStart)
  assert.match(settingsSection, /t\('Base URL'\)/)
  assert.match(settingsSection, /t\('API Key'\)/)
  assert.match(settingsSection, /t\('Run Connectivity Test'\)/)
  assert.match(settingsSection, /t\('Manual curl equivalent'\)/)
})

// CSS for dashboard tabs
test('dashboard-tab CSS class exists', () => {
  assert.match(cssSource, /\.dashboard-tab\s*\{/)
  assert.match(cssSource, /\.dashboard-tab\.active/)
})

// i18n
test('Overview translation exists', () => {
  assert.match(zhSource, /'Overview': '概览'/)
})
