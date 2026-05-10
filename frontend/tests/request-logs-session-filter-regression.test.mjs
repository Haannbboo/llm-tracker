import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')
const cssSource = readFileSync(join(here, 'src', 'App.css'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

const logsStart = appSource.indexOf("{view === 'logs' && (")
assert.notEqual(logsStart, -1, 'logs view block not found')
const logsSection = appSource.slice(logsStart, logsStart + 17000)

test('request logs render a compact session column without dumping full ids in rows', () => {
  assert.match(logsSection, /<th[^>]*>\{t\('Session'\)\}<\/th>/)
  assert.match(logsSection, /className="request-log-session-cell"/)
  assert.match(logsSection, /const sessionId = row\.session_id/)
  assert.match(logsSection, /shortSessionId\(sessionId\)/)
  assert.doesNotMatch(logsSection, /\{row\.session_id\}\s*<\/button>/)
})

test('request log session id pill title exposes full id and click filters by full id', () => {
  assert.match(logsSection, /className="request-log-session-filter"/)
  assert.match(logsSection, /title=\{sessionId\}/)
  assert.match(logsSection, /aria-label=\{`\$\{t\('Filter logs by session'\)\}: \$\{sessionId\}`\}/)
  assert.match(logsSection, /e\.stopPropagation\(\)[\s\S]*setSessionFilter\(sessionId\)[\s\S]*resetPage\(\)/)
})

test('request log row session ID is only a filter button, no separate copy button', () => {
  assert.match(logsSection, /className="request-log-session-filter"/)
  assert.doesNotMatch(logsSection, /className="btn-ghost request-log-session-copy"/)
  assert.doesNotMatch(logsSection, /copyTextToClipboard\(sessionId, showToast\)/)
})

test('active request log session filter badge is visible, compact, titled, and clears only session filter', () => {
  assert.match(logsSection, /className="badge request-log-session-filter-badge"/)
  assert.match(logsSection, /title=\{sessionFilter\}/)
  assert.match(logsSection, /\{t\('Session'\)\}: \{shortSessionId\(sessionFilter\)\}/)
  assert.match(logsSection, /aria-label=\{t\('Clear session filter'\)\}/)
  assert.match(logsSection, /onClick=\{\(\) => \{ setSessionFilter\(null\); resetPage\(\) \}\}/)
  assert.doesNotMatch(logsSection, /setActiveFilter\('all'\)[\s\S]*setSessionFilter\(null\)/)
  assert.doesNotMatch(logsSection, /setActiveSource\(null\)[\s\S]*setSessionFilter\(null\)/)
})

test('session_id remains wired into usage URL when active', () => {
  assert.match(appSource, /if \(sessionFilter\) url\.searchParams\.set\('session_id', sessionFilter\)/)
})

test('request logs session polish has readable compact styles', () => {
  assert.match(cssSource, /\.request-log-session-cell/)
  assert.match(cssSource, /\.request-log-session-filter/)
  assert.doesNotMatch(cssSource, /\.request-log-session-copy/)
  assert.match(cssSource, /\.request-log-session-filter-badge/)
})

test('chinese translations include request log session polish strings', () => {
  for (const key of ['Filter logs by session', 'Clear session filter']) {
    assert.match(zhSource, new RegExp(`'${key}':`))
  }
})
