import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')
const dashboardSource = readFileSync(join(here, 'src', 'pages', 'DashboardPage.tsx'), 'utf-8')
const settingsSource = readFileSync(join(here, 'src', 'pages', 'SettingsPage.tsx'), 'utf-8')
const utilsSource = readFileSync(join(here, 'src', 'utils.tsx'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

const detectedAgentsStart = dashboardSource.indexOf('{/* Detected agents */}')
assert.notEqual(detectedAgentsStart, -1)
const detectedAgentsEnd = dashboardSource.indexOf('</div>\n                  </div>', detectedAgentsStart)
assert.notEqual(detectedAgentsEnd, -1)
const detectedAgentsBlock = dashboardSource.slice(detectedAgentsStart, detectedAgentsEnd)

const settingsDetectedAgentsStart = settingsSource.indexOf('{/* Detected Agents */}')
assert.notEqual(settingsDetectedAgentsStart, -1)
const settingsOtlpStart = settingsSource.indexOf('OTLP Tracking Setup')
const settingsConfigStart = settingsSource.indexOf('Configuration (YAML)')
const settingsBlock = settingsSource

test('detected agents card explains where detection comes from', () => {
  assert.match(detectedAgentsBlock, /Detected from your local config and available commands\./)
})

test('detected agents use readable display labels instead of raw internal names only', () => {
  assert.match(utilsSource, /export function getAgentDisplayName/)
  assert.match(utilsSource, /claude.*Claude Code/s)
  assert.match(utilsSource, /codex.*Codex/s)
  assert.match(detectedAgentsBlock, /getAgentDisplayName\(name\)/)
})

test('detected agent rows show status without duplicating test commands', () => {
  assert.match(detectedAgentsBlock, /\{info\.found \? t\('Ready'\) : t\('Not found'\)\}/)
  assert.doesNotMatch(detectedAgentsBlock, /\{t\('Test:'\)\}/)
})

test('detected agent rows include detected path or unknown fallback', () => {
  assert.match(detectedAgentsBlock, /\{t\('Detected:'\)\}/)
  assert.match(detectedAgentsBlock, /info\.path \|\| t\('Unknown'\)/)
})

test('no-agent fallback remains actionable with test commands', () => {
  assert.match(detectedAgentsBlock, /No local Agent/)
  assert.match(dashboardSource, /llm-tracker codex exec/)
  assert.match(dashboardSource, /llm-tracker claude/)
  assert.doesNotMatch(dashboardSource, /llm-tracker --/)
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
