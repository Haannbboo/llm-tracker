import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'
import assert from 'node:assert/strict'

const root = join(import.meta.dirname, '..')
const logsPageSource = readFileSync(join(root, 'src', 'pages', 'LogsPage.tsx'), 'utf-8')
const selectorHookSource = readFileSync(join(root, 'src', 'hooks', 'useSessionSelectorData.ts'), 'utf-8')

test('Request Logs uses selector-specific sessions hook', () => {
  assert.match(logsPageSource, /useSessionSelectorData/)
  assert.doesNotMatch(logsPageSource, /useSessionsData\(\{ activeSource, dateRange, customSince, customUntil \}\)/)
})

test('selector hook requests /sessions with view=selector', () => {
  assert.match(selectorHookSource, /new URL\('\/sessions'/)
  assert.match(selectorHookSource, /sessionsUrl\.searchParams\.set\('view', 'selector'\)/)
  assert.match(selectorHookSource, /sessionsUrl\.searchParams\.set\('sort_by', 'started'\)/)
  assert.match(selectorHookSource, /sessionsUrl\.searchParams\.set\('sort_order', 'desc'\)/)
  assert.match(selectorHookSource, /sessionsUrl\.searchParams\.set\('limit', '50'\)/)
})
