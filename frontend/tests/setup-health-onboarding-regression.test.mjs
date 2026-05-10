import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

const settingsStart = appSource.indexOf("{view === 'settings' && (")
assert.notEqual(settingsStart, -1)
const settingsBlock = appSource.slice(settingsStart)

const healthStart = appSource.indexOf('{/* Setup health + Detected agents */}')
assert.notEqual(healthStart, -1)
const healthEnd = appSource.indexOf('{/* Detected agents */}', healthStart)
assert.notEqual(healthEnd, -1)
const onboardingHealthBlock = appSource.slice(healthStart, healthEnd)

test('app fetches local setup diagnostics from backend', () => {
  assert.match(appSource, /SetupDiagnostics/)
  assert.match(appSource, /useState<SetupDiagnostics \| null>/)
  assert.match(appSource, /fetch\('\/local\/setup-health'\)/)
})

test('settings page includes OTLP diagnostics panel before raw YAML editor without pretending bootstrap can fix everything', () => {
  const diagnosticsIndex = settingsBlock.indexOf('OTLP Tracking Setup')
  const configIndex = settingsBlock.indexOf('Configuration (YAML)')
  assert.ok(diagnosticsIndex !== -1, 'settings should show OTLP Tracking Setup')
  assert.ok(configIndex !== -1, 'settings should still show Configuration (YAML)')
  assert.ok(diagnosticsIndex < configIndex, 'diagnostics should be above raw YAML editor')
  assert.match(settingsBlock, /Expected endpoint/)
  assert.match(settingsBlock, /Configured endpoint/)
  assert.match(settingsBlock, /Wrong endpoint/)
  assert.doesNotMatch(settingsBlock, /Fix setup/)
  assert.doesNotMatch(settingsBlock, /setupCommand/)
  assert.doesNotMatch(settingsBlock, /Copy bootstrap command/)
  assert.doesNotMatch(settingsBlock, /Copy expected endpoint/)
})

test('onboarding setup health shows passive status only and does not offer unreliable setup repair', () => {
  assert.match(onboardingHealthBlock, /OTLP configured/)
  assert.match(onboardingHealthBlock, /setupDiagnostics/)
  assert.match(appSource, /foundLocalAgentCount/)
  assert.match(appSource, /setupLocalAgentTotal/)
  assert.match(appSource, /t\('No local Agent'\)/)
  assert.doesNotMatch(appSource, /summary\.total_agents \?\? 3/)
  assert.doesNotMatch(onboardingHealthBlock, /Fix setup/)
  assert.doesNotMatch(onboardingHealthBlock, /setupCommand/)
  assert.doesNotMatch(onboardingHealthBlock, /Copy bootstrap command/)
  assert.doesNotMatch(onboardingHealthBlock, /Copy expected endpoint/)
  assert.doesNotMatch(onboardingHealthBlock, /setView\('settings'\)/)
  assert.doesNotMatch(onboardingHealthBlock, /Agents detected/)
  assert.doesNotMatch(onboardingHealthBlock, /configContent \? t\('Loaded'\) : t\('Unknown'\)/)
})

test('chinese translations include OTLP diagnostics strings', () => {
  for (const key of [
    'OTLP Tracking Setup',
    'OTLP configured',
    'Expected endpoint',
    'Configured endpoint',
    'Missing config',
    'Wrong endpoint',
    'No local OTLP config found yet. Run bootstrap, then run a test command above. This page checks automatically.',
    'No local Agent',
  ]) {
    assert.match(zhSource, new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
  }
})
