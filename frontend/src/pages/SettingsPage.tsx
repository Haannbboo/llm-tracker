import { useState } from 'react'
import { useApp } from '../contexts/AppContext'
import { useSettingsData } from '../hooks/useSettingsData'
import { CopyButton } from '../components/CopyButton'
import { t } from '../i18n/index.ts'
import { FIXED_PROVIDER_COLORS, getProviderColor, getModelIcon, getAgentDisplayName } from '../utils'

type Props = {
  providerColors?: Record<string, string>
}

export function SettingsPage({ providerColors }: Props) {
  const [activeSection, setActiveSection] = useState<'tracker' | 'services' | 'connectivity'>('tracker')
  const colors = providerColors ?? FIXED_PROVIDER_COLORS
  const {
    configParsed, configContent, setConfigContent,
    configStatus, error,
    localAgents, setupDiagnostics,
  } = useApp()

  const {
    selectedPricingProvider, setSelectedPricingProvider,
    testBaseUrl, setTestBaseUrl, testApiKey, setTestApiKey,
    testFormat, setTestFormat, testModel, setTestModel,
    testMessage, setTestMessage, testResult, isTesting,
    handleSaveConfig, handleRunTest, handleCostChange,
    manualCurlEquivalent,
  } = useSettingsData()

  // Setup summary computations (from App.tsx lines 821-838)
  const getSetupAgentKey = (name: string) => {
    const normalized = name.toLowerCase()
    if (normalized.includes('vectorengine') || normalized.includes('claude')) return 'claude'
    if (normalized.includes('codesonline') || normalized.includes('codex')) return 'codex'
    if (normalized.includes('gemini')) return 'gemini'
    return normalized
  }

  const foundLocalAgents = localAgents
    ? Object.entries(localAgents).filter(([, info]) => info.found)
    : []
  const foundLocalAgentCount = foundLocalAgents.length
  const setupLocalAgentTotal = setupDiagnostics
    ? foundLocalAgents.filter(([name]) => setupDiagnostics.agents[getSetupAgentKey(name)]).length
    : foundLocalAgentCount
  const setupMatchingAgents = setupDiagnostics
    ? foundLocalAgents.filter(([name]) => setupDiagnostics.agents[getSetupAgentKey(name)]?.endpoint_matches).length
    : 0
  const setupConfiguredAgents = setupDiagnostics
    ? foundLocalAgents.filter(([name]) => setupDiagnostics.agents[getSetupAgentKey(name)]?.configured).length
    : 0
  const setupSummaryText = setupDiagnostics
    ? setupLocalAgentTotal > 0
      ? `${setupMatchingAgents}/${setupLocalAgentTotal}`
      : t('No local Agent')
    : t('Unknown')

  return (
    <div className="settings-page" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div className="panel" style={{ overflow: 'hidden' }}>
        <div
          style={{
            display: 'flex',
            gap: '4px',
            padding: '8px',
            background: 'var(--tab-toggle-bg)',
            borderRadius: '12px',
            flexWrap: 'wrap',
          }}
        >
          {[
            { id: 'tracker', label: t('LLM-Tracker Settings') },
            { id: 'services', label: t('Services') },
            { id: 'connectivity', label: t('Connectivity Test') },
          ].map((section) => (
            <button
              key={section.id}
              type="button"
              className={`tab-toggle-btn ${activeSection === section.id ? 'active' : ''}`}
              onClick={() => setActiveSection(section.id as 'tracker' | 'services' | 'connectivity')}
            >
              {section.label}
            </button>
          ))}
        </div>
      </div>

      {activeSection === 'services' && (
        <>
          {/* Detected Agents */}
          <div className="panel">
            <div className="panel-tabs">
              <div className="tab active"><span>🧭</span> {t('Detected Agents')}</div>
            </div>
            <div className="panel-body" style={{ padding: '0' }}>
              <div style={{ padding: '16px', borderBottom: '1px solid var(--border-color)', fontSize: '13px', color: 'var(--text-secondary)' }}>
                {t('Detected from your local config and available commands.')}
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('Agent')}</th>
                    <th>{t('Status')}</th>
                    <th>{t('Detected:')}</th>
                  </tr>
                </thead>
                <tbody>
                  {localAgents && Object.keys(localAgents).length > 0 ? Object.entries(localAgents).map(([name, info]) => (
                    <tr key={name}>
                      <td style={{ fontWeight: 700 }}>{getAgentDisplayName(name)}</td>
                      <td>
                        <span className={`badge ${info.found ? 'badge-success' : 'badge-error'}`}>
                          {info.found ? t('Ready') : t('Not found')}
                        </span>
                      </td>
                      <td style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: info.path ? 'var(--text-secondary)' : 'var(--text-muted)' }}>
                        {info.path || t('Unknown')}
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={3} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                        {localAgents ? t('No local Agent') : t('Unknown')}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel">
            <div className="panel-tabs">
              <div className="tab active"><span>📡</span> {t('OTLP Tracking Setup')}</div>
            </div>
            <div className="panel-body" style={{ padding: '0' }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('Agent')}</th>
                    <th>{t('Status')}</th>
                    <th>{t('Expected endpoint')}</th>
                    <th>{t('Configured endpoint')}</th>
                  </tr>
                </thead>
                <tbody>
                  {setupDiagnostics ? Object.entries(setupDiagnostics.agents).map(([name, agent]) => (
                    <tr key={name}>
                      <td style={{ fontWeight: 700 }}>{getAgentDisplayName(name)}</td>
                      <td>
                        <span className={`badge ${agent.endpoint_matches ? 'badge-success' : 'badge-error'}`}>
                          {agent.status === 'ready' ? t('Ready') : agent.status === 'wrong_endpoint' ? t('Wrong endpoint') : t('Missing config')}
                        </span>
                      </td>
                      <td style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{agent.expected_endpoint}</td>
                      <td style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: agent.endpoint_matches ? 'var(--color-green)' : 'var(--color-red)' }}>
                        {agent.configured_endpoint ?? '—'}
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={4} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                        {t('Unknown')}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              <div style={{ padding: '16px', borderTop: '1px solid var(--border-color)', fontSize: '13px', color: 'var(--text-secondary)' }}>
                {t('OTLP configured')}: <strong>{setupSummaryText}</strong> · {t('Configured')}: <strong>{setupConfiguredAgents}/{setupLocalAgentTotal}</strong>
              </div>
            </div>
          </div>
        </>
      )}

      {activeSection === 'tracker' && (
        <>
          <div className="panel">
            <div className="panel-tabs">
              <div className="tab active"><span>🔌</span> {t('Active Providers')}</div>
            </div>
            <div className="panel-body" style={{ padding: '0' }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('Provider')}</th>
                    <th>{t('Base URL')}</th>
                    <th>{t('Models')}</th>
                  </tr>
                </thead>
                <tbody>
                  {configParsed?.providers ? Object.entries(configParsed.providers as Record<string, unknown>).map(([name, conf]) => {
                    const c = conf as { models?: unknown[] | Record<string, unknown>, base_url?: string };
                    const models = Array.isArray(c.models)
                      ? c.models
                      : (c.models ? Object.keys(c.models) : []);
                    const color = getProviderColor(name, colors);
                    return (
                      <tr key={name}>
                        <td style={{ padding: '8px' }}>
                          <div style={{
                            padding: '4px 10px',
                            borderRadius: '6px',
                            backgroundColor: color + '22',
                            color: color,
                            fontWeight: 500,
                            border: `1px solid ${color}44`,
                            display: 'inline-block',
                            fontSize: '12px'
                          }}>
                            {name}
                          </div>
                        </td>
                        <td style={{ fontSize: '12px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{c.base_url}</td>
                        <td>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                            {(models as string[]).map((m: string) => {
                              const mConf = !Array.isArray(c.models) ? (c.models?.[m] as { cost?: unknown }) : undefined;
                              const hasOverride = mConf?.cost !== undefined;
                              return (
                                <span key={m} style={{
                                  fontSize: '10px',
                                  padding: '2px 6px',
                                  background: hasOverride ? 'var(--icon-yellow-bg)' : 'var(--tab-toggle-bg)',
                                  borderRadius: '4px',
                                  color: hasOverride ? 'var(--color-yellow)' : 'var(--text-secondary)',
                                  border: hasOverride ? `1px solid var(--color-yellow)` : '1px solid var(--border-color)',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '4px'
                                }}>
                                  {m}
                                  {hasOverride && <span title={t('Cost Override')} style={{ fontSize: '10px' }}>💰</span>}
                                </span>
                              );
                            })}
                          </div>
                        </td>
                      </tr>
                    );
                  }) : (
                    <tr>
                      <td colSpan={3} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                        {t('No providers configured in config.yaml.')}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

      <div className="panel">
        <div className="panel-tabs" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="tab active"><span>💎</span> {t('Model Pricing')}</div>
          <div style={{ paddingRight: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
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
                outline: 'none'
              }}
            >
              <option value="global">{t('Global Default')}</option>
              {configParsed?.providers && Object.keys(configParsed.providers).map(p => (
                <option key={p} value={p}>{t('Provider:')} {p}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="panel-body" style={{ padding: '0' }}>
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: '220px' }}>{t('Model')}</th>
                <th>{t('Input (per 1M)')}</th>
                <th>{t('Output (per 1M)')}</th>
                <th>{t('Cache Read (per 1M)')}</th>
                <th>{t('Cache Write (per 1M)')}</th>
              </tr>
            </thead>
            <tbody>
              {configParsed?.models ? Object.keys(configParsed.models).map((name) => {
                const globalCost = configParsed.models[name]?.cost || {};
                const providerCost = selectedPricingProvider !== 'global'
                  ? (configParsed.providers?.[selectedPricingProvider]?.models?.[name]?.cost || {})
                  : null;

                const isOverridden = providerCost !== null && Object.keys(providerCost).length > 0;
                const activeCost = providerCost !== null ? providerCost : globalCost;

                const inputProps = (field: string) => ({
                  type: "number",
                  step: "0.001",
                  value: activeCost[field] !== undefined ? activeCost[field] : "",
                  placeholder: selectedPricingProvider !== 'global' ? (globalCost[field] ?? "—") : "0.000",
                  onChange: (e: React.ChangeEvent<HTMLInputElement>) => handleCostChange(name, field, e.target.value),
                  style: {
                    width: '100%',
                    padding: '6px 8px',
                    borderRadius: '4px',
                    border: '1px solid transparent',
                    background: activeCost[field] === undefined && selectedPricingProvider !== 'global' ? 'transparent' : 'var(--input-bg)',
                    borderBottom: '1px solid var(--border-color)',
                    fontSize: '13px',
                    color: activeCost[field] === undefined && selectedPricingProvider !== 'global' ? 'var(--text-muted)' : 'var(--text-primary)',
                    outline: 'none',
                    textAlign: 'left' as const
                  }
                });

                return (
                  <tr key={name} style={{ background: isOverridden ? 'var(--icon-yellow-bg)' : 'transparent' }}>
                    <td style={{ fontWeight: 700 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {getModelIcon(name)}
                        {name}
                        {isOverridden && <span title={t('Provider Override')} style={{ fontSize: '10px' }}>💰</span>}
                      </div>
                    </td>
                    <td><input {...inputProps('input')} /></td>
                    <td><input {...inputProps('output')} /></td>
                    <td><input {...inputProps('cacheRead')} /></td>
                    <td><input {...inputProps('cacheWrite')} /></td>
                  </tr>
                );
              }) : (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                    {t('No global models configured in config.yaml.')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="panel-tabs">
          <div className="tab active"><span>📝</span> {t('Configuration (YAML)')}</div>
        </div>
        <div className="panel-body">
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }} dangerouslySetInnerHTML={{ __html: t('Directly edit your <code>config.yaml</code>. Providers and routing are defined here.') }} />

          <div style={{ position: 'relative', background: '#1e293b', borderRadius: '8px', overflow: 'hidden', border: '1px solid #334155' }}>
            <div style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '40px',
              bottom: 0,
              background: '#0f172a',
              borderRight: '1px solid #334155',
              display: 'flex',
              flexDirection: 'column',
              paddingTop: '16px',
              alignItems: 'center',
              color: '#475569',
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
              userSelect: 'none'
            }}>
              {Array.from({ length: 20 }, (_, i) => <div key={i} style={{ height: '20.8px' }}>{i + 1}</div>)}
            </div>
            <textarea
              value={configContent}
              onChange={(e) => setConfigContent(e.target.value)}
              style={{
                width: '100%',
                height: '420px',
                padding: '16px 16px 16px 56px',
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
                border: 'none',
                outline: 'none',
                lineHeight: '1.6',
                background: 'transparent',
                color: '#e2e8f0',
                resize: 'vertical',
                whiteSpace: 'pre',
                overflowX: 'auto'
              }}
              spellCheck={false}
            />
          </div>

          {error && (
            <div style={{
              marginTop: '16px',
              padding: '12px',
              background: 'var(--badge-error-bg)',
              color: 'var(--badge-error-text)',
              borderRadius: '8px',
              fontSize: '13px',
              fontWeight: 500
            }}>
              ⚠️ {error}
            </div>
          )}

          <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end', gap: '12px', alignItems: 'center' }}>
            {configStatus === 'saved' && (
              <span style={{ color: 'var(--color-green)', fontSize: '13px', fontWeight: 600 }}>
                ✓ {t('Configuration saved successfully')}
              </span>
            )}
            <button
              disabled={configStatus === 'saving'}
              onClick={handleSaveConfig}
              style={{
                padding: '10px 24px',
                background: 'var(--color-blue)',
                color: 'white',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: 700,
                opacity: configStatus === 'saving' ? 0.7 : 1,
                cursor: configStatus === 'saving' ? 'not-allowed' : 'pointer',
                boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
              }}
            >
              {configStatus === 'saving' ? t('Saving...') : t('Save Configuration')}
            </button>
          </div>
        </div>
      </div>
        </>
      )}

      {activeSection === 'connectivity' && (
        <div className="panel">
        <div className="panel-tabs">
          <div className="tab active"><span>🔌</span> {t('Upstream Connectivity Test')}</div>
        </div>
        <div className="panel-content" style={{ padding: '24px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div className="filter-group">
                <div className="filter-label">{t('Base URL')}</div>
                <input
                  type="text"
                  className="input-plain"
                  placeholder="https://api.openai.com/v1"
                  value={testBaseUrl}
                  onChange={(e) => setTestBaseUrl(e.target.value)}
                  style={{ width: '100%' }}
                />
                <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '4px' }}>
                  {t('The upstream API root URL, e.g. https://api.openai.com/v1')}
                </div>
              </div>

              <div className="filter-group">
                <div className="filter-label">{t('API Key')}</div>
                <input
                  type="password"
                  className="input-plain"
                  placeholder="sk-..."
                  value={testApiKey}
                  onChange={(e) => setTestApiKey(e.target.value)}
                  style={{ width: '100%' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div className="filter-group">
                  <div className="filter-label">{t('Format')}</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {[
                      { id: 'openai', label: t('OpenAI'), sub: t('Chat Completion') },
                      { id: 'anthropic', label: t('Anthropic'), sub: t('Claude') },
                      { id: 'responses', label: t('Codex'), sub: t('Responses') },
                    ].map((f) => (
                      <button
                        key={f.id}
                        type="button"
                        className={`format-chip${testFormat === f.id ? ' format-chip-active' : ''}`}
                        onClick={() => setTestFormat(f.id)}
                      >
                        <span style={{ fontWeight: 700, fontSize: '12px' }}>{f.label}</span>
                        <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{f.sub}</span>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="filter-group">
                  <div className="filter-label">{t('Model')}</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
                    {[
                      { id: 'gpt-5.5', label: 'GPT-5.5', sub: 'OpenAI' },
                      { id: 'gpt-5.4', label: 'GPT-5.4', sub: 'OpenAI' },
                      { id: 'claude-opus-4-7', label: 'Claude Opus 4.7', sub: 'Anthropic' },
                      { id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6', sub: 'Anthropic' },
                    ].map((m) => (
                      <button
                        key={m.id}
                        type="button"
                        className={`model-chip${testModel === m.id ? ' model-chip-active' : ''}`}
                        onClick={() => setTestModel(testModel === m.id ? '' : m.id)}
                      >
                        <span style={{ fontWeight: 700, fontSize: '12px' }}>{m.label}</span>
                        <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{m.sub}</span>
                      </button>
                    ))}
                  </div>
                  <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{t('Custom:')}</span>
                    <input
                      type="text"
                      className="input-plain"
                      placeholder="model-id"
                      value={!['gpt-5.5','gpt-5.4','claude-opus-4-7','claude-sonnet-4-6'].includes(testModel) ? testModel : ''}
                      onChange={(e) => setTestModel(e.target.value)}
                      style={{ flex: 1 }}
                    />
                  </div>
                </div>
                <div className="filter-group" style={{ marginTop: '12px', gridColumn: '1 / -1' }}>
                  <div className="filter-label">{t('Message')}</div>
                  <textarea
                    className="input-plain"
                    rows={2}
                    value={testMessage}
                    onChange={(e) => setTestMessage(e.target.value)}
                    style={{ width: '100%', resize: 'vertical', fontFamily: 'var(--font-mono)', fontSize: '12px' }}
                  />
                </div>
              </div>

              <button
                className="btn-primary"
                onClick={handleRunTest}
                disabled={isTesting || !testBaseUrl || !testApiKey}
                style={{ marginTop: '8px' }}
              >
                {isTesting ? `⌛ ${t('Testing...')}` : `🚀 ${t('Run Connectivity Test')}`}
              </button>

              <div style={{ marginTop: '16px', padding: '16px', background: 'var(--surface-hover)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>{t('Manual curl equivalent')}</div>
                  <CopyButton
                    className="btn-copy"
                    text={manualCurlEquivalent}
                    idleLabel={`📋 ${t('Copy')}`}
                    copiedLabel={`✓ ${t('Copied')}`}
                    timeoutMs={800}
                  />
                </div>
                <pre style={{ margin: 0, fontSize: '11px', whiteSpace: 'pre-wrap', wordBreak: 'break-all', color: 'var(--text-secondary)' }}>
                  {manualCurlEquivalent}
                </pre>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div className="filter-label">{t('Test Result')}</div>
              {!testResult ? (
                <div style={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--text-muted)',
                  border: '2px dashed var(--border-color)',
                  borderRadius: '12px',
                  minHeight: '300px'
                }}>
                  <span style={{ fontSize: '32px', marginBottom: '12px' }}>⚡</span>
                  <span>{t('Results will appear here after testing')}</span>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div className="widget" style={{ padding: '16px', background: testResult.error || testResult.status_code >= 400 ? 'var(--icon-pink-bg)' : 'var(--icon-green-bg)' }}>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{t('Status Code')}</div>
                      <div style={{ fontSize: '24px', fontWeight: 800, color: testResult.error || testResult.status_code >= 400 ? '#e11d48' : '#16a34a' }}>
                        {testResult.error ? t('Error') : testResult.status_code}
                      </div>
                    </div>
                    <div className="widget" style={{ padding: '16px' }}>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{t('Latency')}</div>
                      <div style={{ fontSize: '24px', fontWeight: 800 }}>{testResult.latency_ms}ms</div>
                    </div>
                  </div>

                  {typeof testResult.body === 'string' && testResult.body.trim().startsWith('<') ? (
                    <div className="widget" style={{ padding: '16px', background: 'var(--icon-yellow-bg)' }}>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>{t('Response')}</div>
                      <div style={{ fontSize: '12px', color: '#b45309', fontWeight: 600, marginBottom: '8px' }}>
                        {t('Upstream returned HTML -- check that base_url points to an API endpoint')}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: '200px', overflow: 'auto' }}>
                        {testResult.body.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 1000)}
                      </div>
                    </div>
                  ) : (
                    <div className="widget" style={{ padding: '16px' }}>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '8px' }}>{t('Response Body')}</div>
                      <pre style={{
                        margin: 0,
                        fontSize: '12px',
                        fontFamily: 'var(--font-mono)',
                        lineHeight: '1.5',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-all',
                        color: 'var(--text-primary)',
                        maxHeight: '400px',
                        overflow: 'auto'
                      }}>
                        {typeof testResult.body === 'object' ? JSON.stringify(testResult.body, null, 2) : testResult.body || testResult.error}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
        </div>
      )}
    </div>
  )
}
