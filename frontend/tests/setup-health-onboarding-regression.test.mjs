import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const overviewSource = readFileSync(join(here, 'src', 'pages', 'OverviewTab.tsx'), 'utf-8')
const detailSource = readFileSync(join(here, 'src', 'components', 'DeviceStatusDetail.tsx'), 'utf-8')
const useDashboardAgentsSource = readFileSync(join(here, 'src', 'hooks', 'useDashboardAgents.ts'), 'utf-8')
const useDeviceStatusesSource = readFileSync(join(here, 'src', 'hooks', 'useDeviceStatuses.ts'), 'utf-8')
const useOnboardingSource = readFileSync(join(here, 'src', 'hooks', 'useOnboarding.ts'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

const healthStart = overviewSource.indexOf('{/* Setup health + Detected agents */}')
assert.notEqual(healthStart, -1)
const healthEnd = overviewSource.indexOf('{/* Detected agents */}', healthStart)
assert.notEqual(healthEnd, -1)
const onboardingHealthBlock = overviewSource.slice(healthStart, healthEnd)

test('dashboard and settings fetch device status reports from the backend', () => {
  assert.match(useDashboardAgentsSource, /fetch\('\/devices\/status'/)
  assert.match(useDeviceStatusesSource, /fetch\('\/devices\/status'/)
})

test('device detail shows OTLP diagnostics without pretending bootstrap can fix everything', () => {
  const diagnosticsIndex = detailSource.indexOf('OTLP Tracking Setup')
  assert.ok(diagnosticsIndex !== -1, 'device detail should show OTLP Tracking Setup')
  assert.match(detailSource, /Expected endpoint/)
  assert.match(detailSource, /Configured endpoint/)
  assert.match(detailSource, /Wrong endpoint/)
  assert.doesNotMatch(detailSource, /Fix setup/)
  assert.doesNotMatch(detailSource, /setupCommand/)
  assert.doesNotMatch(detailSource, /Copy bootstrap command/)
  assert.doesNotMatch(detailSource, /Copy expected endpoint/)
})

test('onboarding setup health shows passive status only and does not offer unreliable setup repair', () => {
  assert.match(onboardingHealthBlock, /OTLP configured/)
  assert.match(onboardingHealthBlock, /setupSummaryText/)
  assert.match(useOnboardingSource, /foundLocalAgentCount/)
  assert.match(useOnboardingSource, /setupLocalAgentTotal/)
  assert.match(useOnboardingSource, /'No local Agent'/)
  assert.doesNotMatch(overviewSource, /summary\.total_agents \?\? 3/)
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
