import { Fragment, useMemo, useState, type ChangeEvent } from 'react'
import { t } from '../i18n/index.ts'
import { useApp } from '../contexts/AppContext'
import { formatNumber, getModelIcon } from '../utils'
import { usePricingData } from '../hooks/usePricingData'
import type { PricingEntry } from '../types'

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const SOURCE_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  yaml: { bg: 'var(--icon-yellow-bg)', color: '#b8860b', label: 'YAML' },
  litellm: { bg: 'rgba(59, 130, 246, 0.15)', color: '#3b82f6', label: 'LiteLLM' },
  openrouter: { bg: 'rgba(147, 51, 234, 0.15)', color: '#9333ea', label: 'OpenRouter' },
}

function sourceStyle(source: string) {
  return SOURCE_STYLES[source] ?? { bg: 'var(--surface-hover)', color: 'var(--text-muted)', label: source }
}

function formatMinutes(minute: number): string {
  const m = minute % (24 * 60)
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}

function formatWindow(start: number, end: number): string {
  const endLabel = end === 0 && start !== 0 ? '24:00' : formatMinutes(end)
  return `${formatMinutes(start)}–${endLabel}`
}

function formatDays(days: number[] | null): string {
  if (!days) return t('Every day')
  return days.map((day) => DAY_LABELS[day] ?? String(day)).join(', ')
}

type Model = { name: string } & PricingEntry

export function PricingPage() {
  const { configParsed } = useApp()
  const {
    selectedPricingProvider,
    setSelectedPricingProvider,
    pricingSearch,
    setPricingSearch,
    filteredPricingModels,
    hasPricingEdits,
    handleCostChange,
    handleSavePricing,
  } = usePricingData()

  const [sourceFilter, setSourceFilter] = useState<'all' | 'yaml' | 'litellm' | 'openrouter'>('all')
  const [expanded, setExpanded] = useState<string | null>(null)

  const models = useMemo(
    () => (sourceFilter === 'all'
      ? filteredPricingModels
      : filteredPricingModels.filter((m) => m.source === sourceFilter)),
    [filteredPricingModels, sourceFilter],
  )

  const counts = useMemo(() => {
    const bySource: Record<string, number> = { yaml: 0, litellm: 0, openrouter: 0 }
    for (const m of filteredPricingModels) bySource[m.source] = (bySource[m.source] ?? 0) + 1
    return {
      total: filteredPricingModels.length,
      yaml: bySource.yaml ?? 0,
      litellm: bySource.litellm ?? 0,
      openrouter: bySource.openrouter ?? 0,
    }
  }, [filteredPricingModels])

  const pricingMultiplier = selectedPricingProvider === 'global'
    ? 1
    : filteredPricingModels.find((m) => typeof m.multiplier === 'number')?.multiplier
      ?? Number(configParsed?.providers?.[selectedPricingProvider]?.price_multiplier ?? 1)

  const formatPrice = (v: number | null | undefined) => (typeof v === 'number' ? v.toFixed(3) : '—')

  const activeCost = (name: string) => {
    const providerCost = selectedPricingProvider !== 'global'
      ? configParsed?.providers?.[selectedPricingProvider]?.models?.[name]?.cost
      : null
    if (providerCost && Object.keys(providerCost).length > 0) return providerCost
    return configParsed?.models?.[name]?.cost || {}
  }

  const modelPrice = (model: Model, field: string) => {
    if (field === 'cacheRead') return model.cache_read
    if (field === 'cacheWrite') return model.cache_write
    return model[field as keyof PricingEntry] as number | null | undefined
  }

  const inputProps = (model: Model, field: string) => {
    const price = modelPrice(model, field)
    const active = activeCost(model.name)
    return {
      type: 'number' as const,
      step: '0.001',
      value: active[field] !== undefined ? active[field] : '',
      placeholder: active[field] !== undefined
        ? String(active[field])
        : price !== undefined && price !== null ? String(price) : '—',
      onChange: (e: ChangeEvent<HTMLInputElement>) => handleCostChange(model.name, field, e.target.value),
      style: {
        width: '100%',
        padding: '6px 8px',
        borderRadius: '4px',
        border: '1px solid transparent',
        borderBottom: '1px solid var(--border-color)',
        background: active[field] !== undefined ? 'var(--input-bg)' : 'transparent',
        fontSize: '13px',
        color: active[field] !== undefined ? 'var(--text-primary)' : 'var(--text-muted)',
        outline: 'none',
        textAlign: 'left' as const,
      },
    }
  }

  const providerPriceDetail = (base: number | null | undefined, effective: number | null | undefined) => (
    selectedPricingProvider !== 'global' && effective !== undefined ? (
      <div style={{ marginTop: '4px', fontSize: '11px', color: 'var(--text-muted)', lineHeight: 1.4 }}>
        <div style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>{t('Effective:')} {formatPrice(effective)}</div>
        <div>{t('Base:')} {formatPrice(base)}</div>
      </div>
    ) : null
  )

  const statCard = (label: string, value: string | number, accent?: string) => (
    <div style={{
      flex: '1 1 140px',
      minWidth: '140px',
      padding: '12px 14px',
      borderRadius: '10px',
      background: 'var(--surface-hover)',
      border: '1px solid var(--border-color)',
    }}>
      <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.4px', color: 'var(--text-muted)' }}>{label}</div>
      <div style={{ marginTop: '4px', fontSize: '20px', fontWeight: 700, color: accent ?? 'var(--text-primary)' }}>{value}</div>
    </div>
  )

  return (
    <div className="settings-page" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div className="panel">
        <div className="panel-tabs" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <div className="tab active"><span>💎</span> {t('Model Pricing')}</div>
          <div style={{ paddingRight: '16px', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-muted)', textTransform: 'uppercase' }}>{t('Scope:')}</span>
            <select
              value={selectedPricingProvider}
              onChange={(e) => setSelectedPricingProvider(e.target.value)}
              style={{
                padding: '4px 12px',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                fontSize: '13px',
                fontWeight: 600,
                background: 'var(--surface-hover)',
                outline: 'none',
              }}
            >
              <option value="global">{t('Global Default')}</option>
              {configParsed?.providers && Object.keys(configParsed.providers).map((p) => (
                <option key={p} value={p}>{t('Provider:')} {p}</option>
              ))}
            </select>
            {selectedPricingProvider !== 'global' && (
              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600 }}>
                {t('Multiplier:')} {pricingMultiplier.toFixed(3)}x
              </span>
            )}
            <button
              type="button"
              className="nav-item"
              disabled={!hasPricingEdits}
              onClick={handleSavePricing}
              style={{
                fontSize: '12px',
                fontWeight: 600,
                padding: '6px 14px',
                borderRadius: '6px',
                opacity: hasPricingEdits ? 1 : 0.5,
                cursor: hasPricingEdits ? 'pointer' : 'not-allowed',
              }}
            >
              {t('Save Pricing')}
            </button>
          </div>
        </div>
        <div className="panel-body" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            {t('Precedence: YAML overrides win; otherwise the configured price sources are checked in order (earlier wins), then a containing-name fallback.')}
          </div>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            {statCard(t('Models'), counts.total)}
            {statCard(t('YAML'), counts.yaml, '#b8860b')}
            {statCard('LiteLLM', counts.litellm, '#3b82f6')}
            {statCard('OpenRouter', counts.openrouter, '#9333ea')}
          </div>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              type="text"
              placeholder={t('Search models...')}
              value={pricingSearch}
              onChange={(e) => setPricingSearch(e.target.value)}
              style={{
                flex: '1 1 240px',
                padding: '6px 12px',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                fontSize: '13px',
                background: 'var(--input-bg)',
                color: 'var(--text-primary)',
                outline: 'none',
              }}
            />
            <div style={{ display: 'flex', gap: '4px' }}>
              {(['all', 'yaml', 'litellm', 'openrouter'] as const).map((source) => (
                <button
                  key={source}
                  type="button"
                  className={`tab-toggle-btn ${sourceFilter === source ? 'active' : ''}`}
                  onClick={() => setSourceFilter(source)}
                  style={{ fontSize: '12px', padding: '5px 10px' }}
                >
                  {source === 'all' ? t('All') : sourceStyle(source).label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-body" style={{ padding: '0', maxHeight: '640px', overflowY: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: '220px' }}>{t('Model')}</th>
                <th style={{ width: '90px' }}>{t('Source')}</th>
                <th>{t('Input (per 1M)')}</th>
                <th>{t('Output (per 1M)')}</th>
                <th>{t('Cache Read (per 1M)')}</th>
                <th>{t('Cache Write (per 1M)')}</th>
                <th style={{ width: '80px' }}>{t('Details')}</th>
              </tr>
            </thead>
            <tbody>
              {models.length > 0 ? models.map((model) => {
                const style = sourceStyle(model.source)
                const hasTiers = (model.tiers?.length ?? 0) > 0
                const hasWindows = (model.time_rates?.length ?? 0) > 0
                const showDetails = expanded === model.name
                return (
                  <Fragment key={model.name}>
                    <tr>
                      <td style={{ fontWeight: 600 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          {getModelIcon(model.name)}
                          <span>{model.name}</span>
                        </div>
                      </td>
                      <td>
                        <span
                          title={`${t('Scope:')} ${model.scope}`}
                          style={{
                            fontSize: '10px',
                            fontWeight: 600,
                            padding: '2px 6px',
                            borderRadius: '4px',
                            background: style.bg,
                            color: style.color,
                          }}
                        >
                          {style.label}
                        </span>
                      </td>
                      <td>
                        <input {...inputProps(model, 'input')} />
                        {providerPriceDetail(model.input, model.effective_input)}
                      </td>
                      <td>
                        <input {...inputProps(model, 'output')} />
                        {providerPriceDetail(model.output, model.effective_output)}
                      </td>
                      <td>
                        <input {...inputProps(model, 'cacheRead')} />
                        {providerPriceDetail(model.cache_read, model.effective_cache_read)}
                      </td>
                      <td>
                        <input {...inputProps(model, 'cacheWrite')} />
                        {providerPriceDetail(model.cache_write, model.effective_cache_write)}
                      </td>
                      <td>
                        {(hasTiers || hasWindows) && (
                          <button
                            type="button"
                            className="nav-item"
                            onClick={() => setExpanded(showDetails ? null : model.name)}
                            style={{ fontSize: '12px', padding: '4px 8px' }}
                          >
                            {showDetails ? '−' : '+'}
                          </button>
                        )}
                      </td>
                    </tr>
                    {showDetails && (hasTiers || hasWindows) && (
                      <tr>
                        <td colSpan={7} style={{ background: 'var(--surface-hover)', padding: '12px 16px' }}>
                          {hasTiers && (
                            <div style={{ marginBottom: hasWindows ? '12px' : 0 }}>
                              <div style={{ fontSize: '12px', fontWeight: 700, marginBottom: '6px' }}>{t('Token tiers')}</div>
                              <table className="table">
                                <thead>
                                  <tr>
                                    <th>{t('Range (tokens)')}</th>
                                    <th>{t('Input')}</th>
                                    <th>{t('Output')}</th>
                                    <th>{t('Cache Read')}</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {model.tiers?.map((tier, index) => (
                                    <tr key={index}>
                                      <td>{tier.max_tokens === null ? `${formatNumber(tier.min_tokens)}+` : `${formatNumber(tier.min_tokens)}–${formatNumber(tier.max_tokens)}`}</td>
                                      <td>{formatPrice(tier.input)}</td>
                                      <td>{formatPrice(tier.output)}</td>
                                      <td>{formatPrice(tier.cache_read)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                          {hasWindows && (
                            <div>
                              <div style={{ fontSize: '12px', fontWeight: 700, marginBottom: '6px' }}>{t('Time-of-day rates')}</div>
                              <table className="table">
                                <thead>
                                  <tr>
                                    <th>{t('Window (UTC)')}</th>
                                    <th>{t('Days')}</th>
                                    <th>{t('Input')}</th>
                                    <th>{t('Output')}</th>
                                    <th>{t('Cache Read')}</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {model.time_rates?.map((window, index) => (
                                    <tr key={index}>
                                      <td>{formatWindow(window.start_minute, window.end_minute)}</td>
                                      <td>{formatDays(window.days)}</td>
                                      <td>{formatPrice(window.input)}</td>
                                      <td>{formatPrice(window.output)}</td>
                                      <td>{formatPrice(window.cache_read)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              }) : (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                    {pricingSearch ? t('No models match your search.') : t('No pricing data available.')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {filteredPricingModels.length > 0 && (
          <div style={{ padding: '8px 16px', fontSize: '11px', color: 'var(--text-muted)', borderTop: '1px solid var(--border-color)' }}>
            {t('Showing')} {filteredPricingModels.length} {t('models')} ({counts.yaml} {t('YAML')}, {counts.litellm + counts.openrouter} {t('auto')})
          </div>
        )}
      </div>
    </div>
  )
}
