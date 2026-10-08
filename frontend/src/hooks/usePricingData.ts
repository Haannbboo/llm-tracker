import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import { t } from '../i18n/index.ts'
import { useApp } from '../contexts/AppContext'
import type { PricingEntry } from '../types.ts'

type CostPatchOp = 'set' | 'delete'
type CostPatch = { path: string[]; op: CostPatchOp; value?: number }

function pricingUrlFor(provider: string): string {
  return provider === 'global'
    ? '/pricing'
    : `/pricing?provider=${encodeURIComponent(provider)}`
}

/** Pricing source keys in resolution-priority order: manual first, then the
 *  sources seen in the pricing data. */
export function pricingSourceOrder(seenSources?: string[]): string[] {
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

function costPathPrefix(provider: string, model: string): string[] {
  return provider === 'global'
    ? ['models', model, 'cost']
    : ['providers', provider, 'models', model, 'cost']
}

export function usePricingData() {
  const {
    setConfigStatus,
    setError,
    showToast,
    pricingData,
    setPricingData,
  } = useApp()

  const [selectedPricingProvider, setSelectedPricingProvider] = useState('global')
  const [pricingSearch, setPricingSearch] = useState('')
  const [costPatches, setCostPatches] = useState<CostPatch[]>([])
  const [providerOptions, setProviderOptions] = useState<string[]>([])
  // Monotonic id: only the latest pricing response may update state, so a
  // slow earlier fetch (or the save refetch) can't overwrite newer data.
  const pricingSeqRef = useRef(0)

  useEffect(() => {
    const controller = new AbortController()
    const seq = ++pricingSeqRef.current

    async function fetchPricing() {
      try {
        const response = await fetch(pricingUrlFor(selectedPricingProvider), {
          signal: controller.signal,
        })
        if (response.ok && seq === pricingSeqRef.current) {
          const data = await response.json()
          setPricingData(data)
          const scopes = Object.values(data)
            .map((entry) => (entry as PricingEntry).scope)
            .filter((scope): scope is string => typeof scope === 'string' && scope !== 'global')
          if (scopes.length > 0) {
            setProviderOptions((prev) => Array.from(new Set([...prev, ...scopes])).sort())
          }
        }
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
    // Manual overrides first, then sources in resolution priority order.
    const order = pricingSourceOrder(models.map((m) => m.source))
    const rank = (source: string) => {
      const i = order.indexOf(source)
      return i === -1 ? order.length : i
    }
    models.sort((a, b) => rank(a.source) - rank(b.source) || a.name.localeCompare(b.name))
    return models
  }, [pricingData, pricingSearch])

  const handleCostChange = useCallback((model: string, field: string, val: string) => {
    const numValue = val === '' ? undefined : Number(val)
    if (numValue !== undefined && !Number.isFinite(numValue)) return
    const op: CostPatchOp = val === '' ? 'delete' : 'set'
    const path = costPathPrefix(selectedPricingProvider, model).concat(field)
    const nextPatch: CostPatch = numValue === undefined ? { path, op } : { path, op, value: numValue }
    setCostPatches((patches) => {
      const existingIndex = patches.findIndex(patch => patch.path.join('\0') === path.join('\0'))
      if (existingIndex === -1) return [...patches, nextPatch]
      const next = [...patches]
      next[existingIndex] = nextPatch
      return next
    })
  }, [selectedPricingProvider])

  /** Cost fields currently in effect for a model: a manual override resolved
   *  from the pricing data, with unsaved edits applied on top. */
  const activeCost = useCallback((model: { name: string } & PricingEntry) => {
    const active: Record<string, number> = {}
    // A provider view also lists global entries; only this scope's overrides are editable here.
    if (model.source === 'yaml' && model.scope === selectedPricingProvider) {
      active.input = model.input
      active.output = model.output
      active.cacheRead = model.cache_read
      if (typeof model.cache_write === 'number') active.cacheWrite = model.cache_write
    }
    const prefix = costPathPrefix(selectedPricingProvider, model.name)
    const prefixKey = prefix.join('\0')
    for (const patch of costPatches) {
      if (patch.path.length !== prefix.length + 1) continue
      if (patch.path.slice(0, prefix.length).join('\0') !== prefixKey) continue
      const field = patch.path[prefix.length]
      if (patch.op === 'delete') delete active[field]
      else if (patch.value !== undefined) active[field] = patch.value
    }
    return active
  }, [costPatches, selectedPricingProvider])

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
      setCostPatches([])
      try {
        const seq = ++pricingSeqRef.current
        const pricingResp = await fetch(pricingUrlFor(selectedPricingProvider))
        if (pricingResp.ok && seq === pricingSeqRef.current) {
          setPricingData(await pricingResp.json())
        }
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
    setConfigStatus,
    setError,
    setPricingData,
    showToast,
  ])

  return {
    selectedPricingProvider,
    setSelectedPricingProvider,
    providerOptions,
    pricingSearch,
    setPricingSearch,
    filteredPricingModels,
    costPatches,
    hasPricingEdits: costPatches.length > 0,
    activeCost,
    handleCostChange,
    handleSavePricing,
  }
}
