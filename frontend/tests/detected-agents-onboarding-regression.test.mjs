import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

const detectedAgentsStart = appSource.indexOf('{/* Detected agents */}')
assert.notEqual(detectedAgentsStart, -1)
const detectedAgentsEnd = appSource.indexOf('</div>\n                  </div>', detectedAgentsStart)
assert.notEqual(detectedAgentsEnd, -1)
const detectedAgentsBlock = appSource.slice(detectedAgentsStart, detectedAgentsEnd)

test('detected agents card explains where detection comes from', () => {
  assert.match(detectedAgentsBlock, /Detected from your local config and available commands\./)
})

test('detected agents use readable display labels instead of raw internal names only', () => {
  assert.match(appSource, /getAgentDisplayName/)
  assert.match(appSource, /vectorengine.*Claude Code/s)
  assert.match(appSource, /codesonline.*Codex/s)
  assert.match(detectedAgentsBlock, /getAgentDisplayName\(name\)/)
})

test('detected agent rows show status without duplicating test commands', () => {
  assert.match(detectedAgentsBlock, /\{info\.found \? t\('Ready'\) : t\('Not found'\)\}/)
  assert.doesNotMatch(detectedAgentsBlock, /\{t\('Test:'\)\}/)
  assert.doesNotMatch(detectedAgentsBlock, /getAgentTestCommand\(name\)/)
})

test('detected agent rows include detected path or unknown fallback', () => {
  assert.match(detectedAgentsBlock, /\{t\('Detected:'\)\}/)
  assert.match(detectedAgentsBlock, /info\.path \|\| t\('Unknown'\)/)
})

test('no-agent fallback remains actionable with test commands', () => {
  assert.match(detectedAgentsBlock, /No agents detected yet\. Run any test command below to create your first event\./)
  assert.match(appSource, /llm-tracker -- codex exec/)
  assert.match(appSource, /llm-tracker -- claude/)
})

test('chinese translations include detected-agent onboarding strings', () => {
  for (const key of [
    'Detected from your local config and available commands.',
    'Ready',
    'Unknown',
    'Test:',
    'Detected:',
    'No agents detected yet. Run any test command below to create your first event.',
  ]) {
    assert.match(zhSource, new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
  }
})
