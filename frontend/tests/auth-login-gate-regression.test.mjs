import { test, describe } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = join(__dirname, '..')
const app = readFileSync(join(root, 'src/App.tsx'), 'utf8')
const context = readFileSync(join(root, 'src/contexts/AppContext.tsx'), 'utf8')
const gate = readFileSync(join(root, 'src/components/LoginGate.tsx'), 'utf8')
const navbar = readFileSync(join(root, 'src/components/Navbar.tsx'), 'utf8')
const settings = readFileSync(join(root, 'src/pages/SettingsPage.tsx'), 'utf8')
const css = readFileSync(join(root, 'src/App.css'), 'utf8')

describe('Login gate', () => {
  test('AppContext resolves the session from /auth/me on mount', () => {
    assert.match(context, /fetch\(['"]\/auth\/me['"]/)
  })

  test('a 401 from /auth/me means auth is enabled without a session', () => {
    assert.match(context, /response\.status === 401/)
    assert.match(context, /enabled: true, user: null/)
  })

  test('isApiPath treats /local/* routes as API paths so a 401 there logs out', () => {
    // Regression: isApiPath used to check pathname === '/local/', which never
    // matches real routes like /local/agents or /local/setup-health, so a 401
    // from those endpoints silently failed to trigger markLoggedOut().
    assert.match(context, /pathname\.startsWith\('\/local\/'\)/)
    assert.doesNotMatch(context, /pathname === '\/local\/'/)
  })

  test('App renders LoginGate when auth is enabled without a user', () => {
    assert.match(app, /auth\.enabled && !auth\.user/)
    assert.match(app, /<LoginGate \/>/)
  })

  test('LoginGate links to the Google login route', () => {
    assert.match(gate, /href=\{?['"]\/auth\/google\/login/)
  })

  test('LoginGate maps auth_error query values to messages', () => {
    assert.match(gate, /invalid_state/)
    assert.match(gate, /email_unverified/)
    assert.match(gate, /not_allowlisted/)
    assert.match(gate, /oauth_failed/)
  })

  test('LoginGate strips the auth_error query param after reading it', () => {
    assert.match(gate, /history\.replaceState/)
  })

  test('CSS includes login-gate styles', () => {
    assert.match(css, /\.login-gate-card/)
  })
})

describe('User identity', () => {
  test('Navbar settings tab shows the user avatar and name only when auth is enabled', () => {
    assert.match(navbar, /auth\.enabled && auth\.user/)
    assert.match(navbar, /user-avatar/)
    assert.match(navbar, /user-email/)
  })

  test('Navbar no longer owns sign out (moved to Settings devices panel)', () => {
    assert.doesNotMatch(navbar, /signOut/)
  })

  test('SettingsPage devices panel shows sign out', () => {
    assert.match(settings, /Sign out/)
    assert.match(settings, /signOut/)
  })

  test('signOut posts to /auth/logout then reloads', () => {
    assert.match(context, /fetch\(['"]\/auth\/logout['"], \{ method: 'POST' \}\)/)
    assert.match(context, /window\.location\.reload\(\)/)
  })

  test('CSS includes user-avatar styles', () => {
    assert.match(css, /\.user-avatar/)
  })
})

describe('Devices list', () => {
  test('SettingsPage offers a Devices tab only when auth is enabled', () => {
    assert.match(settings, /auth\.enabled && auth\.user/)
    assert.match(settings, /\{ id: 'devices', label: t\('Devices'\) \}\]/)
  })

  test('SettingsPage fetches /auth/devices and revokes via POST', () => {
    assert.match(settings, /\/auth\/devices/)
    assert.match(settings, /\/auth\/devices\/\$\{deviceId\}\/revoke/)
    assert.match(settings, /method: 'POST'/)
  })

  test('SettingsPage marks the current device', () => {
    assert.match(settings, /device\.current/)
  })
})
