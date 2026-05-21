import { useState, useCallback, useMemo, useEffect } from 'react'
import yaml from 'js-yaml'
import { t } from '../i18n/index.ts'
import { useApp } from '../contexts/AppContext'
import type { PricingEntry } from '../types.ts'

type CostPatchOp = 'set' | 'delete'
type CostPatch = { path: string[]; op: CostPatchOp; value?: number }

function isPlainMapping(value: unknown): value is Record<string, any> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const prototype = Object.getPrototypeOf(value)
  return prototype === Object.prototype || prototype === null
}

function cloneConfig(config: Record<string, any> | null) {
  return structuredClone(config ?? {})
}

function setPathValue(root: Record<string, any>, path: string[], value: number) {
  let target: Record<string, any> = root
  for (const key of path.slice(0, -1)) {
    if (target[key] === undefined) target[key] = {}
    if (!isPlainMapping(target[key])) throw new Error(`Cannot traverse non-mapping key '${key}'`)
    target = target[key]
  }
  target[path[path.length - 1]] = value
}

function deletePathValue(root: Record<string, any>, path: string[]) {
  let target: Record<string, any> = root
  for (const key of path.slice(0, -1)) {
    if (target[key] === undefined) return
    if (!isPlainMapping(target[key])) throw new Error(`Cannot traverse non-mapping key '${key}'`)
    target = target[key]
  }
  delete target[path[path.length - 1]]
}

function applyPatchClient(config: unknown, patches: CostPatch[]) {
  if (config !== null && config !== undefined && !isPlainMapping(config)) {
    throw new Error(t('Config root must be a YAML mapping'))
  }
  const merged = config ?? {}
  for (const patch of patches) {
    if (patch.op === 'delete') {
      deletePathValue(merged, patch.path)
    } else if (typeof patch.value === 'number') {
      setPathValue(merged, patch.path, patch.value)
    }
  }
  return merged
}

export function useSettingsData() {
  const { configContent, setConfigContent, configParsed, setConfigParsed, configStatus: _configStatus, setConfigStatus, setError, pricingData, setPricingData } = useApp()

  const [selectedPricingProvider, setSelectedPricingProvider] = useState('global')
  const [pricingSearch, setPricingSearch] = useState('')
  const [costPatches, setCostPatches] = useState<CostPatch[]>([])
  const [originalConfigContent, setOriginalConfigContent] = useState<string | null>(null)

  useEffect(() => {
    if (originalConfigContent === null && configParsed !== null) {
      setOriginalConfigContent(configContent)
    }
  }, [configContent, configParsed, originalConfigContent])

  useEffect(() => {
    const pricingUrl = selectedPricingProvider === 'global' ? '/pricing' : `/pricing?provider=${encodeURIComponent(selectedPricingProvider)}`
    const controller = new AbortController()

    async function fetchPricing() {
      try {
        const response = await fetch(pricingUrl, { signal: controller.signal })
        if (response.ok) setPricingData(await response.json())
      } catch (err) {
        if (!(err instanceof DOMException && err.name === 'AbortError')) {
          console.error('Failed to load pricing:', err)
        }
      }
    }

    void fetchPricing()
    return () => controller.abort()
  }, [selectedPricingProvider, setPricingData])

  const filteredPricingModels = useMemo(() => {
    if (!pricingData) return []
    const search = pricingSearch.toLowerCase()
    const models: Array<{ name: string } & PricingEntry> = []
    for (const [name, data] of Object.entries(pricingData)) {
      if (search && !name.toLowerCase().includes(search)) continue
      models.push({ name, ...data })
    }
    models.sort((a, b) => {
      if (a.source !== b.source) return a.source === 'yaml' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    return models
  }, [pricingData, pricingSearch])

  // Connectivity test state
  const [testBaseUrl, setTestBaseUrl] = useState('')
  const [testApiKey, setTestApiKey] = useState('')
  const [testFormat, setTestFormat] = useState('openai')
  const [testModel, setTestModel] = useState('')
  const [testMessage, setTestMessage] = useState('What is 2 + 3?')
  const [testResult, setTestResult] = useState<Record<string, any> | null>(null)
  const [isTesting, setIsTesting] = useState(false)

  const handleSaveConfig = useCallback(async () => {
    setConfigStatus('saving')
    try {
      const yamlChanged = originalConfigContent !== null && configContent !== originalConfigContent
      const hasCostPatches = costPatches.length > 0
      let response: Response

      if (yamlChanged && hasCostPatches) {
        let parsedConfig: unknown
        try {
          parsedConfig = yaml.load(configContent)
        } catch (err) {
          const detail = err instanceof Error ? err.message : t('Failed to save config')
          setError(detail.startsWith('Invalid YAML') ? detail : `Invalid YAML: ${detail}`)
          setConfigStatus('error')
          return
        }
        let mergedConfig: Record<string, any>
        try {
          mergedConfig = applyPatchClient(parsedConfig, costPatches)
        } catch (err) {
          setError(err instanceof Error ? err.message : t('Failed to save config'))
          setConfigStatus('error')
          return
        }
        response = await fetch('/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: yaml.dump(mergedConfig, { indent: 2, noRefs: true }) })
        })
      } else if (hasCostPatches) {
        response = await fetch('/config', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patches: costPatches })
        })
      } else {
        response = await fetch('/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: configContent })
        })
      }

      if (response.ok) {
        const configResp = await fetch('/config')
        if (!configResp.ok) {
          setError(t('Failed to refresh config after save'))
          setConfigStatus('error')
          return
        }
        const data = await configResp.json()
        const freshContent = data.content
        setConfigContent(freshContent)
        setConfigParsed(data.parsed)
        setOriginalConfigContent(freshContent)
        setCostPatches([])
        setConfigStatus('saved')
        setTimeout(() => setConfigStatus('idle'), 3000)
        // Re-fetch pricing to update source tags after save
        try {
          const pricingUrl = selectedPricingProvider === 'global' ? '/pricing' : `/pricing?provider=${encodeURIComponent(selectedPricingProvider)}`
          const pricingResp = await fetch(pricingUrl)
          if (pricingResp.ok) setPricingData(await pricingResp.json())
        } catch { /* non-critical */ }
      } else {
        const error = await response.json()
        setError(error.detail || t('Failed to save config'))
        setConfigStatus('error')
      }
    } catch {
      setError(t('Connection error while saving config'))
      setConfigStatus('error')
    }
  }, [configContent, costPatches, originalConfigContent, selectedPricingProvider, setConfigContent, setConfigParsed, setConfigStatus, setError, setPricingData])

  const handleRunTest = useCallback(async () => {
    setIsTesting(true)
    setTestResult(null)
    try {
      const response = await fetch('/test-connectivity', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: testBaseUrl,
          api_key: testApiKey,
          format: testFormat,
          model: testModel || null,
          message: testMessage || null
        })
      })
      const text = await response.text()
      try {
        setTestResult(JSON.parse(text))
      } catch {
        setTestResult({ status_code: response.status, body: text, url: '' })
      }
    } catch (err) {
      setTestResult({ error: err instanceof Error ? err.message : t('Test failed') })
    } finally {
      setIsTesting(false)
    }
  }, [testBaseUrl, testApiKey, testFormat, testModel, testMessage])

  const handleCostChange = useCallback((model: string, field: string, val: string) => {
    const numValue = val === '' ? undefined : Number(val)
    if (numValue !== undefined && !Number.isFinite(numValue)) return
    const op: CostPatchOp = val === '' ? 'delete' : 'set'
    const path = selectedPricingProvider === 'global'
      ? ['models', model, 'cost', field]
      : ['providers', selectedPricingProvider, 'models', model, 'cost', field]
    const newParsed = cloneConfig(configParsed)

    if (selectedPricingProvider === 'global') {
      if (!newParsed.models) newParsed.models = {}
      if (!newParsed.models[model]) newParsed.models[model] = {}
      if (!newParsed.models[model].cost) newParsed.models[model].cost = {}

      if (numValue === undefined) {
        delete newParsed.models[model].cost[field]
      } else {
        newParsed.models[model].cost[field] = numValue
      }
    } else {
      if (!newParsed.providers) newParsed.providers = {}
      if (!newParsed.providers[selectedPricingProvider]) newParsed.providers[selectedPricingProvider] = {}
      if (!newParsed.providers[selectedPricingProvider].models) newParsed.providers[selectedPricingProvider].models = {}
      if (!newParsed.providers[selectedPricingProvider].models[model]) newParsed.providers[selectedPricingProvider].models[model] = {}
      if (!newParsed.providers[selectedPricingProvider].models[model].cost) newParsed.providers[selectedPricingProvider].models[model].cost = {}

      if (numValue === undefined) {
        delete newParsed.providers[selectedPricingProvider].models[model].cost[field]
      } else {
        newParsed.providers[selectedPricingProvider].models[model].cost[field] = numValue
      }
    }

    const nextPatch: CostPatch = numValue === undefined ? { path, op } : { path, op, value: numValue }
    setCostPatches((patches) => {
      const existingIndex = patches.findIndex(patch => patch.path.join('\0') === path.join('\0'))
      if (existingIndex === -1) return [...patches, nextPatch]
      const next = [...patches]
      next[existingIndex] = nextPatch
      return next
    })
    setConfigParsed(newParsed)
  }, [configParsed, selectedPricingProvider, setConfigParsed])

  const manualCurlEquivalent = (() => {
    let base = testBaseUrl.replace(/\/$/, '')
    if (!base.includes('/v1')) base = base + '/v1'
    const endpoint = testFormat === 'openai' ? '/chat/completions' : testFormat === 'anthropic' ? '/messages' : '/responses'
    const fullUrl = base.endsWith(endpoint) ? base : base + endpoint
    return `curl ${fullUrl} \\\n  -H "${testFormat === 'anthropic' ? 'x-api-key' : 'Authorization: Bearer'}: ${testApiKey || 'YOUR_KEY'}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"model": "${testModel || 'gpt-5.4'}", "messages": [{"role": "user", "content": "${(testMessage || 'What is 2 + 3?').replace(/"/g, '\\"')}"}], "max_tokens": 10}'`
  })()

  return {
    selectedPricingProvider, setSelectedPricingProvider,
    pricingSearch, setPricingSearch, filteredPricingModels,
    testBaseUrl, setTestBaseUrl, testApiKey, setTestApiKey,
    testFormat, setTestFormat, testModel, setTestModel,
    testMessage, setTestMessage, testResult, isTesting,
    handleSaveConfig, handleRunTest, handleCostChange,
    costPatches, originalConfigContent,
    manualCurlEquivalent,
  }
}
