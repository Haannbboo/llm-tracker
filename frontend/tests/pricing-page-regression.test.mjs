import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appContextSource = readFileSync(join(here, 'src', 'contexts', 'AppContext.tsx'), 'utf-8')
const hookSource = readFileSync(join(here, 'src', 'hooks', 'usePricingData.ts'), 'utf-8')
const pageSource = readFileSync(join(here, 'src', 'pages', 'PricingPage.tsx'), 'utf-8')

test('app context initial load does not write pricing data', () => {
  assert.doesNotMatch(appContextSource, /fetch\('\/pricing'/)
  assert.doesNotMatch(appContextSource, /setPricingData\(await pricingResp\.json\(\)\)/)
})

test('pricing page fetches provider-specific pricing when scope changes', () => {
  assert.match(hookSource, /useEffect/)
  assert.match(hookSource, /provider === 'global'/)
  assert.match(hookSource, /\/pricing\?provider=\$\{encodeURIComponent\(provider\)\}/)
  assert.match(hookSource, /fetch\(pricingUrlFor\(selectedPricingProvider\)/)
  assert.match(hookSource, /\[selectedPricingProvider, setPricingData\]/)
})

test('pricing page keeps slash-bearing model ids visible', () => {
  assert.doesNotMatch(hookSource, /name\.includes\('\/'\)/)
})

test('pricing refetch after save preserves the selected provider scope', () => {
  assert.match(hookSource, /fetch\(pricingUrlFor\(selectedPricingProvider\)\)/)
  assert.match(hookSource, /setPricingData/)
})

test('provider pricing view shows multiplier and effective prices with base prices visible', () => {
  assert.match(pageSource, /typeof m\.multiplier === 'number'/)
  assert.match(pageSource, /model\.effective_input/)
  assert.match(pageSource, /model\.effective_output/)
  assert.match(pageSource, /model\.effective_cache_read/)
  assert.match(pageSource, /model\.effective_cache_write/)
  assert.match(pageSource, /selectedPricingProvider !== 'global'/)
  assert.match(pageSource, /Base:/)
})

test('provider pricing view shows and edits cache write pricing', () => {
  assert.match(pageSource, /Cache Write \(per 1M\)/)
  assert.match(pageSource, /inputProps\(model, 'cacheWrite'\)/)
  assert.match(pageSource, /model\.cache_write/)
})

test('provider pricing view uses resolved prices for missing yaml-field placeholders', () => {
  assert.match(pageSource, /const price = modelPrice\(model, field\)/)
  assert.match(pageSource, /price !== undefined && price !== null \? String\(price\) : '—'/)
  assert.doesNotMatch(pageSource, /String\(activeCost\[field\]\) : "0\.000"/)
})

test('pricing page renders tiers and time-of-day windows', () => {
  assert.match(pageSource, /Token tiers/)
  assert.match(pageSource, /Time-of-day rates/)
  assert.match(pageSource, /model\.time_rates/)
})

test('pricing empty state spans all pricing columns', () => {
  assert.match(pageSource, /colSpan=\{7\}/)
})
