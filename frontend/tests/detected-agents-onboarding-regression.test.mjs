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

const settingsStart = appSource.indexOf("{view === 'settings' && (")
assert.notEqual(settingsStart, -1)
const settingsEnd = appSource.indexOf("</div>\n          )}", settingsStart)
assert.notEqual(settingsEnd, -1)
const settingsBlock = appSource.slice(settingsStart, settingsEnd)
const settingsDetectedAgentsStart = settingsBlock.indexOf("{/* Settings detected local agents */}")
const settingsOtlpStart = settingsBlock.indexOf('OTLP Tracking Setup')
const settingsConfigStart = settingsBlock.indexOf('Configuration (YAML)')

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
  assert.match(detectedAgentsBlock, /No local Agent/)
  assert.match(appSource, /llm-tracker codex exec/)
  assert.match(appSource, /llm-tracker claude/)
  assert.doesNotMatch(appSource, /llm-tracker --/)
})

test('settings page has separate detected local agents status section', () => {
  assert.notEqual(settingsDetectedAgentsStart, -1, 'settings should show a local detected agents panel')
  assert.notEqual(settingsOtlpStart, -1, 'settings should keep OTLP Tracking Setup panel')
  assert.notEqual(settingsConfigStart, -1, 'settings should keep Configuration (YAML) panel')

  const settingsDetectedAgentsBlock = settingsBlock.slice(settingsDetectedAgentsStart, settingsOtlpStart)
  assert.match(settingsDetectedAgentsBlock, /Detected Agents/)
  assert.match(settingsDetectedAgentsBlock, /Detected from your local config and available commands\./)
  assert.match(settingsDetectedAgentsBlock, /getAgentDisplayName\(name\)/)
  assert.match(settingsDetectedAgentsBlock, /\{info\.found \? t\('Ready'\) : t\('Not found'\)\}/)
  assert.match(settingsDetectedAgentsBlock, /\{t\('Detected:'\)\}/)
  assert.match(settingsDetectedAgentsBlock, /info\.path \|\| t\('Unknown'\)/)
  assert.match(settingsDetectedAgentsBlock, /t\('No local Agent'\)/)
  assert.doesNotMatch(settingsDetectedAgentsBlock, /OTLP configured/)
  assert.doesNotMatch(settingsDetectedAgentsBlock, /Expected endpoint/)
  assert.doesNotMatch(settingsDetectedAgentsBlock, /Configured endpoint/)
  assert.doesNotMatch(settingsDetectedAgentsBlock, /Fix setup/)
  assert.doesNotMatch(settingsDetectedAgentsBlock, /setupCommand/)
  assert.doesNotMatch(settingsDetectedAgentsBlock, /Copy bootstrap command/)
})

test('settings local agent detection does not imply OTLP setup readiness', () => {
  const settingsDetectedAgentsBlock = settingsBlock.slice(settingsDetectedAgentsStart, settingsOtlpStart)
  const settingsOtlpBlock = settingsBlock.slice(settingsOtlpStart, settingsConfigStart)

  assert.match(settingsDetectedAgentsBlock, /localAgents/)
  assert.doesNotMatch(settingsDetectedAgentsBlock, /setupDiagnostics/)
  assert.match(settingsOtlpBlock, /setupDiagnostics/)
  assert.match(settingsOtlpBlock, /endpoint_matches/)
})

test('chinese translations include detected-agent onboarding strings', () => {
  for (const key of [
    'Detected Agents',
    'Detected from your local config and available commands.',
    'Ready',
    'Unknown',
    'Detected:',
    'No local Agent',
  ]) {
    assert.match(zhSource, new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
  }
  assert.match(zhSource, /已检测到的Agent/)
  assert.doesNotMatch(zhSource, /已检测到的代理/)
})
