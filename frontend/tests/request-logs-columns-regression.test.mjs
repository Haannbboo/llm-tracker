import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'
import assert from 'node:assert/strict'

const root = join(import.meta.dirname, '..')
const cssSource = readFileSync(join(root, 'src', 'App.css'), 'utf-8')
const zhSource = readFileSync(join(root, 'src', 'i18n', 'zh.ts'), 'utf-8')
const logsPageSource = readFileSync(join(root, 'src', 'pages', 'LogsPage.tsx'), 'utf-8')
const requestLogColumnsSource = readFileSync(join(root, 'src', 'hooks', 'useRequestLogColumns.ts'), 'utf-8')
const controlPath = join(root, 'src', 'components', 'RequestLogColumnsControl.tsx')
if (!existsSync(controlPath)) {
  throw new Error(`Required file not found: ${controlPath}`)
}
const controlSource = readFileSync(controlPath, 'utf-8')

test('request log column hook provides a persisted registry with validation', () => {
  assert.match(requestLogColumnsSource, /const REQUEST_LOG_COLUMN_KEY = 'llm-tracker-request-log-columns'/)
  assert.match(requestLogColumnsSource, /export const DEFAULT_REQUEST_LOG_COLUMNS/)
  assert.match(requestLogColumnsSource, /localStorage\.getItem\(REQUEST_LOG_COLUMN_KEY\)/)
  assert.match(requestLogColumnsSource, /localStorage\.setItem\(REQUEST_LOG_COLUMN_KEY, JSON\.stringify/)
  assert.match(requestLogColumnsSource, /function normalizeRequestLogColumnIds\(/)
  assert.match(requestLogColumnsSource, /const requestedColumnIds = new Set\(/)
  assert.match(requestLogColumnsSource, /REQUEST_LOG_COLUMNS[\s\S]*?\.filter\(\(\{ id \}\) => requestedColumnIds\.has\(id\)\)/)
  assert.match(requestLogColumnsSource, /\.map\(\(\{ id \}\) => id\)/)
  assert.match(requestLogColumnsSource, /normalizedColumnIds\.length > 0 \? normalizedColumnIds : DEFAULT_REQUEST_LOG_COLUMNS/)
  assert.match(requestLogColumnsSource, /return normalizeRequestLogColumnIds\(parsed\)/)
  assert.match(requestLogColumnsSource, /setRawVisibleColumnIds\(\(current\) =>[\s\S]*?normalizeRequestLogColumnIds\(/)
  assert.doesNotMatch(requestLogColumnsSource, /from '\.\.\/i18n\/index\.ts'/)
  assert.doesNotMatch(requestLogColumnsSource, /\bt\(/)
})

test('request logs page uses the request log column hook instead of inline hidden state', () => {
  assert.match(logsPageSource, /useRequestLogColumns/)
  assert.doesNotMatch(logsPageSource, /resetRequestLogColumns/)
  assert.doesNotMatch(logsPageSource, /hiddenColumns|setHiddenColumns/)
})

test('request logs page renders table cells from visible columns', () => {
  assert.match(logsPageSource, /<RequestLogColumnsControl/)
  assert.match(logsPageSource, /visibleColumns\.map\(/)
  assert.match(logsPageSource, /visibleColumns\.length/)
  assert.match(logsPageSource, /colSpan=\{visibleColumns\.length\}/)
  assert.match(logsPageSource, /visibleColumns\.some\(\(column\) => column\.id === 'model'\)/)
})

test('request log columns control renders checkbox items and reset actions', () => {
  assert.match(controlSource, /type="checkbox"/)
  assert.match(controlSource, /Reset columns/)
  assert.match(controlSource, /All columns/)
  assert.match(cssSource, /\.request-log-columns/)
  assert.match(cssSource, /\.request-log-columns-menu/)
  assert.match(zhSource, /'Columns':/)
  assert.match(zhSource, /'Reset columns':/)
  assert.match(zhSource, /'All columns':/)
})
