import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appContextSource = readFileSync(join(here, 'src', 'contexts', 'AppContext.tsx'), 'utf-8')
const hookSource = readFileSync(join(here, 'src', 'hooks', 'useSettingsData.ts'), 'utf-8')
const settingsSource = readFileSync(join(here, 'src', 'pages', 'SettingsPage.tsx'), 'utf-8')

test('app context initial load does not write pricing data', () => {
  assert.doesNotMatch(appContextSource, /fetch\('\/pricing'/)
  assert.doesNotMatch(appContextSource, /setPricingData\(await pricingResp\.json\(\)\)/)
})

test('settings pricing fetches provider-specific pricing when scope changes', () => {
  assert.match(hookSource, /useEffect/)
  assert.match(hookSource, /selectedPricingProvider === 'global'\s*\?\s*'\/pricing'\s*:\s*`\/pricing\?provider=\$\{encodeURIComponent\(selectedPricingProvider\)\}`/)
  assert.match(hookSource, /fetch\(pricingUrl/)
  assert.match(hookSource, /\[selectedPricingProvider, setPricingData\]/)
})

test('settings pricing keeps slash-bearing model ids visible', () => {
  assert.doesNotMatch(hookSource, /name\.includes\('\/'\)/)
})

test('settings pricing refetch after save preserves the selected provider scope', () => {
  assert.match(hookSource, /const pricingUrl = selectedPricingProvider === 'global'/)
  assert.match(hookSource, /const pricingResp = await fetch\(pricingUrl\)/)
  assert.match(hookSource, /selectedPricingProvider/)
  assert.match(hookSource, /setPricingData/)
})

test('provider pricing view shows multiplier and effective prices with base prices visible', () => {
  assert.match(settingsSource, /model\.multiplier/)
  assert.match(settingsSource, /model\.effective_input/)
  assert.match(settingsSource, /model\.effective_output/)
  assert.match(settingsSource, /model\.effective_cache_read/)
  assert.match(settingsSource, /model\.effective_cache_write/)
  assert.match(settingsSource, /selectedPricingProvider !== 'global'/)
  assert.match(settingsSource, /Base:/)
})

test('provider pricing view shows and edits cache write pricing', () => {
  assert.match(settingsSource, /Cache Write \(per 1M\)/)
  assert.match(settingsSource, /inputProps\('cacheWrite'/)
  assert.match(settingsSource, /model\.cache_write/)
})

test('provider pricing view uses resolved prices for missing yaml-field placeholders', () => {
  assert.match(settingsSource, /const price = modelPrice\(field\)/)
  assert.match(settingsSource, /price !== undefined && price !== null \? String\(price\) : "—"/)
  assert.doesNotMatch(settingsSource, /String\(activeCost\[field\]\) : "0\.000"/)
})

test('pricing empty state spans all pricing columns', () => {
  assert.match(settingsSource, /colSpan=\{6\}/)
})
