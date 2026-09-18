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

/** Pricing source keys in resolution-priority order (manual first, then the
 *  enabled `pricing.sources` from config). When config is unavailable (e.g.
 *  `/config` is unreachable), falls back to the sources seen in the data. */
export function pricingSourceOrder(
  config: Record<string, any> | null,
  seenSources?: string[],
): string[] {
  const specs = config?.pricing?.sources
  if (Array.isArray(specs) && specs.some((s) => s && typeof s === 'object')) {
    const names = specs
      .filter((s: any) => s && typeof s === 'object' && s.enabled !== false)
      .map((s: any) => String(s.name || s.type || ''))
      .filter((name: string) => name === 'litellm' || name === 'openrouter')
    return [...new Set(['yaml', ...names])]
  }
  const seen = new Set(seenSources ?? [])
  const order = ['yaml']
  for (const name of ['openrouter', 'litellm']) {
    if (seen.size === 0 || seen.has(name)) order.push(name)
  }
  for (const name of [...seen].sort()) {
    if (!order.includes(name)) order.push(name)
  }
  return order
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
    // Manual overrides first, then sources in config priority order.
    const order = pricingSourceOrder(configParsed, models.map((m) => m.source))
    const rank = (source: string) => {
      const i = order.indexOf(source)
      return i === -1 ? order.length : i
    }
    models.sort((a, b) => rank(a.source) - rank(b.source) || a.name.localeCompare(b.name))
    return models
  }, [pricingData, pricingSearch, configParsed])

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
