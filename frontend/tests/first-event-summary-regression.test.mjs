import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const dashboardSource = readFileSync(join(here, 'src', 'pages', 'DashboardPage.tsx'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

// Extract the success block (when verificationResult is truthy)
const successBlockStart = dashboardSource.indexOf('{verificationResult ? (')
assert.notEqual(successBlockStart, -1)
const successBlockEnd = dashboardSource.indexOf(': (', successBlockStart + 30)
const successBlock = dashboardSource.slice(successBlockStart, successBlockEnd)

test('success copy says tracking works with first request recorded', () => {
  assert.match(successBlock, /Tracking works\. Your first request is recorded\./)
  assert.doesNotMatch(successBlock, /\{t\('Tracking works'\)\}/)
})

test('success summary shows source with fallback dash', () => {
  assert.match(successBlock, /\{t\('Source:'\)\}/)
  assert.match(successBlock, /client_source \|\| '—'/)
})

test('success summary shows model with fallback dash', () => {
  assert.match(successBlock, /\{t\('Model:'\)\}/)
  assert.match(successBlock, /verificationResult\.model \|\| '—'|verificationResult\.model \?\? '—'/)
})

test('success summary shows tokens', () => {
  assert.match(successBlock, /\{t\('Tokens:'\)\}/)
})

test('success summary shows cost', () => {
  assert.match(successBlock, /\{t\('Cost:'\)\}/)
})

test('success summary shows latency', () => {
  assert.match(successBlock, /\{t\('Latency:'\)\}/)
})

test('success block has view request logs CTA that navigates to logs', () => {
  assert.match(successBlock, /View request logs/)
  assert.match(successBlock, /onNavigateToLogs\(\)/)
})

test('success block still has reset button', () => {
  assert.match(successBlock, /\{t\('Reset'\)\}/)
})

test('chinese translations include new commit 3 strings', () => {
  assert.match(zhSource, /'Tracking works\. Your first request is recorded\.'/)
  assert.match(zhSource, /'View request logs'/)
})
