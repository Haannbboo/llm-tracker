import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const settingsHook = readFileSync(join(here, 'src', 'hooks', 'useSettingsData.ts'), 'utf-8')
const pricingHook = readFileSync(join(here, 'src', 'hooks', 'usePricingData.ts'), 'utf-8')

function extractCallback(source, name) {
  const startToken = `const ${name} = useCallback(`
  const start = source.indexOf(startToken)
  assert.notEqual(start, -1, `${name} callback should exist`)

  const nextCallback = source.indexOf('\n  const handle', start + startToken.length)
  return source.slice(start, nextCallback === -1 ? source.length : nextCallback)
}

const costChangeSource = extractCallback(pricingHook, 'handleCostChange')
const savePricingSource = extractCallback(pricingHook, 'handleSavePricing')
const saveConfigSource = extractCallback(settingsHook, 'handleSaveConfig')

test('settings YAML save is a plain PUT and no longer carries cost patches', () => {
  assert.match(saveConfigSource, /method: 'PUT'/)
  assert.match(saveConfigSource, /body: JSON\.stringify\(\{ content: configContent \}\)/)
  assert.doesNotMatch(settingsHook, /costPatches/)
})

test('pricing cost edits keep keystroke path out of YAML serialization', () => {
  assert.doesNotMatch(costChangeSource, /yaml\.dump\(/)
  assert.doesNotMatch(costChangeSource, /setConfigContent\(/)
  assert.match(costChangeSource, /setCostPatches\(/)
  assert.match(costChangeSource, /setConfigParsed\(newParsed\)/)
})

test('pricing cost edit patch buffer records set and delete operations by scope', () => {
  assert.match(pricingHook, /type CostPatchOp = 'set' \| 'delete'/)
  assert.match(pricingHook, /type CostPatch = \{ path: string\[\]; op: CostPatchOp; value\?: number \}/)
  assert.match(costChangeSource, /const op: CostPatchOp = val === '' \? 'delete' : 'set'/)
  assert.match(costChangeSource, /Number\(val\)/)
  assert.match(costChangeSource, /Number\.isFinite\(numValue\)/)
  assert.match(costChangeSource, /\['models', model, 'cost', field\]/)
  assert.match(costChangeSource, /\['providers', selectedPricingProvider, 'models', model, 'cost', field\]/)
})

test('pricing save routes to PATCH config endpoint', () => {
  assert.match(savePricingSource, /method: 'PATCH'/)
  assert.match(savePricingSource, /body: JSON\.stringify\(\{ patches: costPatches \}\)/)
})

test('pricing save clears the buffer only after config refresh and refetches pricing', () => {
  assert.match(savePricingSource, /const configResp = await fetch\('\/config'\)/)
  assert.match(savePricingSource, /Failed to refresh config after save/)

  const configRefreshIndex = savePricingSource.indexOf('if (!configResp.ok)')
  const clearIndex = savePricingSource.indexOf('setCostPatches([])')
  assert.ok(configRefreshIndex !== -1 && clearIndex !== -1)
  assert.ok(configRefreshIndex < clearIndex, 'patch buffer should clear only after config refresh succeeds')

  assert.match(savePricingSource, /fetch\(pricingUrlFor\(selectedPricingProvider\)\)/)
  assert.match(savePricingSource, /setPricingData\(await pricingResp\.json\(\)\)/)
})
