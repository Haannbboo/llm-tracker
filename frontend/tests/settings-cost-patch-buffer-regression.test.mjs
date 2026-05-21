import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const hookSource = readFileSync(join(here, 'src', 'hooks', 'useSettingsData.ts'), 'utf-8')

function extractCallback(name) {
  const startToken = `const ${name} = useCallback(`
  const start = hookSource.indexOf(startToken)
  assert.notEqual(start, -1, `${name} callback should exist`)

  const nextCallback = hookSource.indexOf('\n  const handle', start + startToken.length)
  return hookSource.slice(start, nextCallback === -1 ? hookSource.length : nextCallback)
}

const saveConfigSource = extractCallback('handleSaveConfig')
const costChangeSource = extractCallback('handleCostChange')

test('settings cost edits keep keystroke path out of YAML serialization', () => {
  assert.doesNotMatch(costChangeSource, /yaml\.dump\(/)
  assert.doesNotMatch(costChangeSource, /setConfigContent\(/)
  assert.match(costChangeSource, /setCostPatches\(/)
  assert.match(costChangeSource, /setConfigParsed\(newParsed\)/)
})

test('settings cost edit patch buffer records set and delete operations by scope', () => {
  assert.match(hookSource, /type CostPatchOp = 'set' \| 'delete'/)
  assert.match(hookSource, /type CostPatch = \{ path: string\[\]; op: CostPatchOp; value\?: number \}/)
  assert.match(costChangeSource, /const op: CostPatchOp = val === '' \? 'delete' : 'set'/)
  assert.match(costChangeSource, /Number\(val\)/)
  assert.match(costChangeSource, /Number\.isFinite\(numValue\)/)
  assert.match(costChangeSource, /\['models', model, 'cost', field\]/)
  assert.match(costChangeSource, /\['providers', selectedPricingProvider, 'models', model, 'cost', field\]/)
})

test('patches-only save routes to PATCH config endpoint', () => {
  assert.match(saveConfigSource, /method: 'PATCH'/)
  assert.match(saveConfigSource, /body: JSON\.stringify\(\{ patches: costPatches \}\)/)
})

test('yaml-only save keeps existing PUT config behavior', () => {
  assert.match(saveConfigSource, /method: 'PUT'/)
  assert.match(saveConfigSource, /body: JSON\.stringify\(\{ content: configContent \}\)/)
})

test('both-changed save merges patches into YAML content before PUT', () => {
  assert.match(hookSource, /function applyPatchClient\(/)
  assert.match(hookSource, /function isPlainMapping\(/)
  assert.match(hookSource, /Object\.getPrototypeOf\(value\)/)
  assert.match(hookSource, /Cannot traverse non-mapping key/)
  assert.match(hookSource, /useState<string \| null>\(null\)/)
  assert.match(saveConfigSource, /const yamlChanged = originalConfigContent !== null && configContent !== originalConfigContent/)
  assert.match(hookSource, /if \(originalConfigContent === null && configParsed !== null\)/)
  assert.match(saveConfigSource, /parsedConfig = yaml\.load\(configContent\)/)
  assert.match(hookSource, /Config root must be a YAML mapping/)
  assert.match(saveConfigSource, /mergedConfig = applyPatchClient\(parsedConfig, costPatches\)/)
  assert.match(saveConfigSource, /content: yaml\.dump\(mergedConfig/)
})

test('both-changed invalid YAML reports YAML validation error before save request', () => {
  assert.match(saveConfigSource, /catch \(err\)/)
  assert.match(saveConfigSource, /Invalid YAML/)
  assert.match(saveConfigSource, /setConfigStatus\('error'\)/)
  assert.match(saveConfigSource, /return/)
})

test('successful save clears patch buffer and refreshes config and scoped pricing', () => {
  assert.match(saveConfigSource, /const configResp = await fetch\('\/config'\)/)
  assert.match(saveConfigSource, /setOriginalConfigContent\(freshContent\)/)
  assert.match(saveConfigSource, /setCostPatches\(\[\]\)/)
  assert.match(saveConfigSource, /Failed to refresh config after save/)
  assert.match(saveConfigSource, /setConfigStatus\('error'\)/)

  const configRefreshIndex = saveConfigSource.indexOf('if (!configResp.ok)')
  const baselineIndex = saveConfigSource.indexOf('setOriginalConfigContent(freshContent)')
  const clearIndex = saveConfigSource.indexOf('setCostPatches([])')
  assert.ok(configRefreshIndex < baselineIndex, 'baseline should advance only after config refresh succeeds')
  assert.ok(configRefreshIndex < clearIndex, 'patch buffer should clear only after config refresh succeeds')

  assert.match(hookSource, /costPatches, originalConfigContent,/)
  assert.match(saveConfigSource, /selectedPricingProvider === 'global'\s*\?\s*'\/pricing'\s*:\s*`\/pricing\?provider=\$\{encodeURIComponent\(selectedPricingProvider\)\}`/)
})
