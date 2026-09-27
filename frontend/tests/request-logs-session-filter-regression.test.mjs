import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const logsSource = readFileSync(join(here, 'src', 'pages', 'LogsPage.tsx'), 'utf-8')
const useLogsSource = readFileSync(join(here, 'src', 'hooks', 'useLogsData.ts'), 'utf-8')
const requestLogColumnsSource = readFileSync(join(here, 'src', 'hooks', 'useRequestLogColumns.ts'), 'utf-8')
const cssSource = readFileSync(join(here, 'src', 'App.css'), 'utf-8')
const indexCssSource = readFileSync(join(here, 'src', 'index.css'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

const logsSection = logsSource

test('request logs render a compact session column without dumping full ids in rows', () => {
  assert.match(requestLogColumnsSource, /\{\s*id:\s*'session'[^}]*label:\s*'Session'/)
  assert.match(logsSection, /renderHeaderContent\(column\.id, column\.label\)/)
  assert.match(logsSection, /className="request-log-session-cell"/)
  assert.match(logsSection, /const sessionId = row\.session_id/)
  assert.match(logsSection, /shortSessionId\(sessionId\)/)
  assert.doesNotMatch(logsSection, /\{row\.session_id\}\s*<\/button>/)
})

test('request log session id pill title exposes full id and click filters by full id', () => {
  assert.match(logsSection, /className=\{`request-log-session-filter/)
  assert.match(logsSection, /title=\{sessionId\}/)
  assert.match(logsSection, /aria-label=\{`\$\{t\('Filter logs by session'\)\}: \$\{sessionId\}`\}/)
  assert.match(logsSection, /e\.stopPropagation\(\)[\s\S]*setSessionFilter\(sessionId\)[\s\S]*resetPage\(\)/)
})

test('request log row session ID is only a filter button, no separate copy button', () => {
  assert.match(logsSection, /className=\{`request-log-session-filter/)
  assert.doesNotMatch(logsSection, /className="btn-ghost request-log-session-copy"/)
})

test('active request log session filter badge is visible, compact, titled, and clears only session filter', () => {
  const badgeStart = logsSection.indexOf('className="badge request-log-session-filter-badge"')
  assert.ok(badgeStart !== -1, 'session filter badge not found')
  const badgeBlock = logsSection.slice(badgeStart, badgeStart + 1000)

  assert.match(badgeBlock, /title=\{sessionFilter\}/)
  assert.match(badgeBlock, /\{t\('Session'\)\}: \{shortSessionId\(sessionFilter\)\}/)
  assert.match(badgeBlock, /aria-label=\{t\('Clear session filter'\)\}/)
  assert.match(badgeBlock, /onClick=\{\(\) => \{ setSessionFilter\(null\); resetPage\(\) \}\}/)
  assert.doesNotMatch(badgeBlock, /setActiveFilter\(null\)/)
  assert.doesNotMatch(badgeBlock, /setActiveSource\(null\)/)
})

test('session_id remains wired into usage URL when active', () => {
  assert.match(useLogsSource, /if \(opts\.sessionFilter\) usageUrl\.searchParams\.set\('session_id', opts\.sessionFilter\)/)
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

test('hovering a request log row highlights the session pill of sibling rows, not the row', () => {
  assert.match(logsSection, /onMouseEnter=\{\(\) => setHoveredSession\(row\.session_id \?\? null\)\}/)
  assert.match(logsSection, /onMouseLeave=\{\(\) => setHoveredSession\(null\)\}/)
  assert.match(logsSection, /className=\{`request-log-session-filter\$\{hoveredSession === sessionId \? ' session-hover-active' : ''\}`\}/)
  // the class must never land on the <tr>: rows stay clean, only the pill is styled
  assert.doesNotMatch(logsSection, /expandable-row[^`]*\$\{hoveredSession/)
  assert.match(cssSource, /\.request-log-session-filter\.session-hover-active \{[^}]*background:/)
  assert.doesNotMatch(indexCssSource, /tr\.session-hover-active/)
})
