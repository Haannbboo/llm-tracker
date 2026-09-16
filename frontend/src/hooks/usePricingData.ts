import { useState, useCallback, useMemo, useEffect } from 'react'
import { t } from '../i18n/index.ts'
import { useApp } from '../contexts/AppContext'
import type { PricingEntry } from '../types.ts'

type CostPatchOp = 'set' | 'delete'
type CostPatch = { path: string[]; op: CostPatchOp; value?: number }

function cloneConfig(config: Record<string, any> | null) {
  return structuredClone(config ?? {})
}

function pricingUrlFor(provider: string): string {
  return provider === 'global'
    ? '/pricing'
    : `/pricing?provider=${encodeURIComponent(provider)}`
}

export function usePricingData() {
  const {
    configParsed,
    setConfigParsed,
    setConfigContent,
    setConfigStatus,
    setError,
    showToast,
    pricingData,
    setPricingData,
  } = useApp()

  const [selectedPricingProvider, setSelectedPricingProvider] = useState('global')
  const [pricingSearch, setPricingSearch] = useState('')
  const [costPatches, setCostPatches] = useState<CostPatch[]>([])

  useEffect(() => {
    const controller = new AbortController()

    async function fetchPricing() {
      try {
        const response = await fetch(pricingUrlFor(selectedPricingProvider), {
          signal: controller.signal,
        })
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

  const handleSavePricing = useCallback(async () => {
    if (costPatches.length === 0) return
    setConfigStatus('saving')
    try {
      const response = await fetch('/config', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patches: costPatches }),
      })
      if (!response.ok) {
        const error = await response.json()
        setError(error.detail || t('Failed to save config'))
        setConfigStatus('error')
        return
      }
      const configResp = await fetch('/config')
      if (!configResp.ok) {
        setError(t('Failed to refresh config after save'))
        setConfigStatus('error')
        return
      }
      const data = await configResp.json()
      setConfigContent(data.content)
      setConfigParsed(data.parsed)
      setCostPatches([])
      try {
        const pricingResp = await fetch(pricingUrlFor(selectedPricingProvider))
        if (pricingResp.ok) setPricingData(await pricingResp.json())
      } catch {
        /* non-critical */
      }
      setConfigStatus('saved')
      showToast(t('Configuration saved successfully'))
      setTimeout(() => setConfigStatus('idle'), 3000)
    } catch {
      setError(t('Connection error while saving config'))
      setConfigStatus('error')
    }
  }, [
    costPatches,
    selectedPricingProvider,
    setConfigContent,
    setConfigParsed,
    setConfigStatus,
    setError,
    setPricingData,
    showToast,
  ])

  return {
    selectedPricingProvider,
    setSelectedPricingProvider,
    pricingSearch,
    setPricingSearch,
    filteredPricingModels,
    costPatches,
    hasPricingEdits: costPatches.length > 0,
    handleCostChange,
    handleSavePricing,
  }
}
