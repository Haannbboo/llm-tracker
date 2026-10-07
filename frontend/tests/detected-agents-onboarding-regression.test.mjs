import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const overviewSource = readFileSync(join(here, 'src', 'pages', 'OverviewTab.tsx'), 'utf-8')
const settingsSource = readFileSync(join(here, 'src', 'pages', 'SettingsPage.tsx'), 'utf-8')
const detailSource = readFileSync(join(here, 'src', 'components', 'DeviceStatusDetail.tsx'), 'utf-8')
const utilsSource = readFileSync(join(here, 'src', 'utils.tsx'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

const detectedStart = overviewSource.indexOf('{/* Detected agents */}')
assert.notEqual(detectedStart, -1)
const detectedEnd = overviewSource.indexOf('dashboard-refresh-surface', detectedStart)
assert.notEqual(detectedEnd, -1)
const detectedBlock = overviewSource.slice(detectedStart, detectedEnd)

const detailDetectedStart = detailSource.indexOf("{t('Detected Agents')}")
assert.notEqual(detailDetectedStart, -1)
const detailOtlpStart = detailSource.indexOf('OTLP Tracking Setup')
assert.notEqual(detailOtlpStart, -1)
const detailDetectedBlock = detailSource.slice(detailDetectedStart, detailOtlpStart)
const detailOtlpBlock = detailSource.slice(detailOtlpStart)

test('detected agents card explains where detection comes from', () => {
  assert.match(detectedBlock, /Detected from your local config and available commands\./)
  assert.match(detailDetectedBlock, /Detected from your local config and available commands\./)
})

test('detected agents use readable display labels instead of raw internal names only', () => {
  assert.match(utilsSource, /export function getAgentDisplayName/)
  assert.match(utilsSource, /claude.*Claude Code/s)
  assert.match(utilsSource, /codex.*Codex/s)
  assert.match(detailDetectedBlock, /getAgentDisplayName\(name\)/)
})

test('detected agent rows show status and path without duplicating test commands', () => {
  assert.match(detailDetectedBlock, /\{info\?\.found \? t\('Ready'\) : t\('Not found'\)\}/)
  assert.match(detailDetectedBlock, /\{t\('Detected:'\)\}/)
  assert.match(detailDetectedBlock, /info\?\.path \|\| t\('Unknown'\)/)
  assert.doesNotMatch(detailDetectedBlock, /\{t\('Test:'\)\}/)
})

test('no-agent fallback remains actionable with test commands', () => {
  assert.match(detectedBlock, /No local Agent/)
  assert.match(overviewSource, /tokenage codex exec/)
  assert.match(overviewSource, /tokenage claude/)
  assert.doesNotMatch(overviewSource, /tokenage --/)
})

test('per-device agent status renders in the settings devices detail, not the services tab', () => {
  assert.match(settingsSource, /<DeviceStatusDetail status=\{deviceReport\(device\.id\)\} \/>/)
  assert.match(settingsSource, /useDeviceStatuses/)
  assert.match(settingsSource, /expandedDeviceId/)
  assert.doesNotMatch(settingsSource, /OTLP Tracking Setup/)
  assert.doesNotMatch(settingsSource, /\{t\('Detected Agents'\)\}/)
})

test('device detail separates detection from OTLP readiness', () => {
  assert.match(detailDetectedBlock, /detected/)
  assert.doesNotMatch(detailDetectedBlock, /endpoint_matches/)
  assert.match(detailOtlpBlock, /endpoint_matches/)
  assert.match(detailOtlpBlock, /Expected endpoint/)
  assert.match(detailOtlpBlock, /Configured endpoint/)
})

test('chinese translations include detected-agent onboarding strings', () => {
  for (const key of [
    'Detected Agents',
    'Detected from your local config and available commands.',
    'Ready',
    'Unknown',
    'Detected:',
    'No local Agent',
    'No report yet. Start the tokenage client service on this device.',
  ]) {
    assert.match(zhSource, new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
  }
  assert.match(zhSource, /已检测到的Agent/)
  assert.doesNotMatch(zhSource, /已检测到的代理/)
})
