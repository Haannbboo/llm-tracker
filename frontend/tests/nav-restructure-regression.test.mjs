import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')
const navbarSource = readFileSync(join(here, 'src', 'components', 'Navbar.tsx'), 'utf-8')
const dashboardSource = readFileSync(join(here, 'src', 'pages', 'DashboardPage.tsx'), 'utf-8')
const settingsSource = readFileSync(join(here, 'src', 'pages', 'SettingsPage.tsx'), 'utf-8')
const cssSource = readFileSync(join(here, 'src', 'App.css'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

// Top-level nav: exactly 3 tabs
test('top nav has exactly Dashboard, Request Logs, Settings', () => {
  assert.match(navbarSource, /nav-item[\s\S]*currentView === 'dashboard'[\s\S]*Dashboard/)
  assert.match(navbarSource, /nav-item[\s\S]*currentView === 'logs'[\s\S]*Request Logs/)
  assert.match(navbarSource, /nav-item[\s\S]*currentView === 'settings'[\s\S]*Settings/)
})

test('Sessions is NOT a top-level nav item', () => {
  assert.doesNotMatch(navbarSource, /className=\{`nav-item.*currentView === 'sessions'/)
})

test('Connectivity Test is NOT a top-level nav item', () => {
  assert.doesNotMatch(navbarSource, /className=\{`nav-item.*currentView === 'test'/)
})

test('view state type is dashboard | logs | settings', () => {
  assert.match(appSource, /const currentView = location.pathname.startsWith\('\/logs'\)/)
  assert.match(appSource, /\| 'settings'\) => \{/)
})

// Dashboard secondary tabs
test('dashboard has secondary tabs: Overview | Sessions', () => {
  assert.match(dashboardSource, /className="dashboard-tabs"/)
  assert.match(dashboardSource, /dashboardTab === 'overview' \? 'active' : ''/)
  assert.match(dashboardSource, /dashboardTab === 'sessions' \? 'active' : ''/)
})

test('overview tab is the default', () => {
  assert.match(dashboardSource, /useState<'overview' \| 'sessions'>\('overview'\)/)
})

test('overview tab content renders dashboard charts', () => {
  assert.match(dashboardSource, /\{dashboardTab === 'overview' && \(<>/)
})

// Connectivity test moved into settings
test('connectivity test panel is inside settings view', () => {
  assert.match(settingsSource, /t\('Upstream Connectivity Test'\)/)
})

test('standalone test view block is removed', () => {
  assert.doesNotMatch(appSource, /\{view === 'test' && \(/)
})

test('connectivity test form fields exist in settings', () => {
  assert.match(settingsSource, /t\('Base URL'\)/)
  assert.match(settingsSource, /t\('API Key'\)/)
  assert.match(settingsSource, /t\('Run Connectivity Test'\)/)
  assert.match(settingsSource, /t\('Manual curl equivalent'\)/)
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
