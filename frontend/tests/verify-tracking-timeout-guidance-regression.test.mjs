import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { pathToFileURL, fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')
const guidanceModulePath = join(here, 'src', 'setup-guidance.ts')

async function loadGuidanceModule() {
  if (!existsSync(guidanceModulePath)) {
    assert.fail('verify timeout guidance module is missing')
  }
  return import(pathToFileURL(guidanceModulePath))
}

test('verify timeout guidance classifies setup health states without repair actions', async () => {
  const { getVerifyTimeoutGuidance } = await loadGuidanceModule()

  const generic = 'No event found yet'
  const noLocalAgent = 'No local Agent detected. Run or install an agent, then try Verify Tracking again.'
  const otlpNotConfigured = 'OTLP is not configured for detected agents. Check Settings OTLP Tracking Setup.'
  const endpointMismatch = 'OTLP endpoint mismatch detected. Check Settings OTLP Tracking Setup.'

  const base = {
    setupHealthAvailable: true,
    localAgentDetectionAvailable: true,
    localAgentCount: 2,
    setupLocalAgentTotal: 2,
    configuredAgents: 2,
    matchingAgents: 2,
  }

  assert.equal(getVerifyTimeoutGuidance({ ...base, setupHealthAvailable: false }), generic)
  assert.equal(getVerifyTimeoutGuidance({ ...base, localAgentDetectionAvailable: false }), generic)
  assert.equal(getVerifyTimeoutGuidance({ ...base, localAgentCount: 0, setupLocalAgentTotal: 0, configuredAgents: 0, matchingAgents: 0 }), noLocalAgent)
  assert.equal(getVerifyTimeoutGuidance({ ...base, configuredAgents: 0, matchingAgents: 0 }), otlpNotConfigured)
  assert.equal(getVerifyTimeoutGuidance({ ...base, configuredAgents: 2, matchingAgents: 1 }), endpointMismatch)
  assert.equal(getVerifyTimeoutGuidance({ ...base, setupLocalAgentTotal: 3, configuredAgents: 2, matchingAgents: 2 }), endpointMismatch)
  assert.equal(getVerifyTimeoutGuidance(base), generic)
})

test('verify tracking timeout UI uses setup-aware guidance while avoiding fake repair UX', () => {
  assert.match(appSource, /getVerifyTimeoutGuidance/)
  assert.match(appSource, /const verifyTimeoutGuidance = getVerifyTimeoutGuidance/)
  assert.match(appSource, /verifyPhase === 'timeout'\s*\?\s*t\(verifyTimeoutGuidance\)/)
  assert.doesNotMatch(appSource, /verifyPhase === 'timeout'\s*\?\s*t\('No event found yet'\)/)
  assert.doesNotMatch(appSource, /Fix setup/)
  assert.doesNotMatch(appSource, /setupCommand/)
  assert.doesNotMatch(appSource, /Copy bootstrap command/)
})

test('chinese translations include setup-aware verify timeout guidance', () => {
  for (const key of [
    'No local Agent detected. Run or install an agent, then try Verify Tracking again.',
    'OTLP is not configured for detected agents. Check Settings OTLP Tracking Setup.',
    'OTLP endpoint mismatch detected. Check Settings OTLP Tracking Setup.',
  ]) {
    assert.match(zhSource, new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
  }
})
