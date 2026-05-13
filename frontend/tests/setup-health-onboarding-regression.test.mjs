import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')
const appContextSource = readFileSync(join(here, 'src', 'contexts', 'AppContext.tsx'), 'utf-8')
const dashboardSource = readFileSync(join(here, 'src', 'pages', 'DashboardPage.tsx'), 'utf-8')
const settingsSource = readFileSync(join(here, 'src', 'pages', 'SettingsPage.tsx'), 'utf-8')
const useOnboardingSource = readFileSync(join(here, 'src', 'hooks', 'useOnboarding.ts'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

const settingsBlock = settingsSource

const healthStart = dashboardSource.indexOf('{/* Setup health + Detected agents */}')
assert.notEqual(healthStart, -1)
const healthEnd = dashboardSource.indexOf('{/* Detected agents */}', healthStart)
assert.notEqual(healthEnd, -1)
const onboardingHealthBlock = dashboardSource.slice(healthStart, healthEnd)

test('app fetches local setup diagnostics from backend', () => {
  assert.match(appContextSource, /SetupDiagnostics/)
  assert.match(appContextSource, /const \[setupDiagnostics, setSetupDiagnostics\] = useState<SetupDiagnostics \| null>/)
  assert.match(appContextSource, /fetch\('\/local\/setup-health'\)/)
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
  assert.match(onboardingHealthBlock, /setupSummaryText/)
  assert.match(useOnboardingSource, /foundLocalAgentCount/)
  assert.match(useOnboardingSource, /setupLocalAgentTotal/)
  assert.match(useOnboardingSource, /'No local Agent'/)
  assert.doesNotMatch(dashboardSource, /summary\.total_agents \?\? 3/)
  assert.doesNotMatch(onboardingHealthBlock, /Fix setup/)
  assert.doesNotMatch(onboardingHealthBlock, /setupCommand/)
  assert.doesNotMatch(onboardingHealthBlock, /Copy bootstrap command/)
  assert.doesNotMatch(onboardingHealthBlock, /Copy expected endpoint/)
  assert.doesNotMatch(onboardingHealthBlock, /setView\('settings'\)/)
  assert.doesNotMatch(onboardingHealthBlock, /Agents detected/)
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
