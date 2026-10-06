import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { PricingPage } from './PricingPage'
import { useApp } from '../contexts/AppContext'
import { useSettingsData } from '../hooks/useSettingsData'
import { useDevices } from '../hooks/useDevices'
import { t } from '../i18n/index.ts'
import { getAgentDisplayName, formatTime } from '../utils'
import { TimezoneSelector } from '../components/TimezoneSelector'
import { useDashboardAgents } from '../hooks/useDashboardAgents'
import { useVersion } from '../hooks/useVersion'

const DEVICE_KIND_LABELS: Record<string, string> = {
  client: 'Machine',
  cli: 'CLI',
  ingest: 'Ingest',
}

export function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const section = searchParams.get('section')
  const activeSection = section && ['pricing', 'services', 'devices'].includes(section) ? section : 'services'
  const {
    auth, showToast, signOut,
  } = useApp()
  const { localAgents, setupDiagnostics } = useDashboardAgents()
  const versionData = useVersion()
  const authDevicesActive = activeSection === 'devices'
  const { devices, refresh: refreshDevices } = useDevices(authDevicesActive && auth.enabled)
  const [revokingDeviceId, setRevokingDeviceId] = useState<string | null>(null)

  const handleRevokeDevice = async (deviceId: string) => {
    if (revokingDeviceId !== null) return
    setRevokingDeviceId(deviceId)
    try {
      const response = await fetch(`/auth/devices/${deviceId}/revoke`, { method: 'POST' })
      if (response.ok) {
        showToast(t('Device revoked'))
        refreshDevices()
      } else {
        showToast(t('Failed to revoke device'))
      }
    } catch {
      showToast(t('Failed to revoke device'))
    } finally {
      setRevokingDeviceId(null)
    }
  }

  const {
    handleEvaluationEvaluatorChange,
    evaluationEvaluator, evaluationEvaluators,
  } = useSettingsData()

  // Setup summary computations (from App.tsx lines 821-838)
  const getSetupAgentKey = (name: string) => {
    const normalized = name.toLowerCase()
    if (normalized.includes('vectorengine') || normalized.includes('claude')) return 'claude'
    if (normalized.includes('codesonline') || normalized.includes('codex')) return 'codex'
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
            { id: 'pricing', label: t('Pricing') },
            { id: 'services', label: t('Services') },
            ...(auth.enabled && auth.user ? [{ id: 'devices', label: t('Devices') }] : []),
          ].map((section) => (
            <button
              key={section.id}
              type="button"
              className={`tab-toggle-btn ${activeSection === section.id ? 'active' : ''}`}
              onClick={() => setSearchParams({ section: section.id })}
            >
              {section.label}
            </button>
          ))}
        </div>
      </div>

      {activeSection === 'pricing' && <PricingPage />}

      {activeSection === 'services' && (
        <>
          <div className="panel evaluation-default-selector">
            <div className="panel-tabs">
              <div className="tab active">{t('Evaluator')}</div>
            </div>
            <div className="panel-body" style={{ padding: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)' }}>{t('Global default')}</div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>{t('Used for future automatic evaluator jobs.')}</div>
              </div>
              <select
                className="input-plain"
                value={evaluationEvaluator}
                onChange={(event) => handleEvaluationEvaluatorChange(event.target.value as any)}
              >
                {evaluationEvaluators.map((evaluator) => (
                  <option key={evaluator.id} value={evaluator.id} disabled={!evaluator.available}>
                    {evaluator.label}{evaluator.available ? '' : ` (${t('Not found')})`}
                  </option>
                ))}
                {evaluationEvaluators.length === 0 && (
                  <>
                    <option value="codex">Codex</option>
                    <option value="claude">Claude Code</option>
                  </>
                )}
              </select>
            </div>
          </div>

          <TimezoneSelector />

          {/* Service Version */}
          <div className="panel">
            <div className="panel-tabs">
              <div className="tab active"><span>🏷️</span> {t('Service Version')}</div>
            </div>
            <div className="panel-body" style={{ padding: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{t('Version')}:</span>
                <span style={{
                  fontSize: '16px',
                  fontWeight: 700,
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text-primary)',
                  padding: '4px 12px',
                  background: 'var(--tab-toggle-bg)',
                  borderRadius: '6px',
                }}>
                  {versionData?.version ?? '—'}
                </span>
              </div>
            </div>
          </div>

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

      {activeSection === 'devices' && (
        <div className="panel">
            <div className="panel-tabs" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="tab active"><span>💻</span> {t('Devices')}</div>
              {auth.user && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="user-avatar">
                    {(auth.user.name || auth.user.email).charAt(0).toUpperCase()}
                  </span>
                  <span className="user-email" title={auth.user.email}>
                    {auth.user.name || auth.user.email}
                  </span>
                  <button className="btn-danger" onClick={() => void signOut()}>
                    {t('Sign out')}
                  </button>
                </div>
              )}
            </div>
            <div className="panel-body" style={{ padding: '0' }}>
              <div style={{ padding: '16px', borderBottom: '1px solid var(--border-color)', fontSize: '13px', color: 'var(--text-secondary)' }}>
                {t('Installed machines and browser sessions. Revoking a machine stops tracking immediately.')}
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('Device')}</th>
                    <th>{t('Kind')}</th>
                    <th>{t('Installed version')}</th>
                    <th>{t('Created')}</th>
                    <th>{t('Last used')}</th>
                    <th>{t('Status')}</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {devices && devices.length > 0 ? devices.map((device) => (
                    <tr key={device.id}>
                      <td style={{ fontWeight: 700 }}>
                        {device.device_name ?? '—'}
                        {device.current && (
                          <span className="badge badge-success" style={{ marginLeft: '8px' }}>
                            {t('Current device')}
                          </span>
                        )}
                      </td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {t(DEVICE_KIND_LABELS[device.kind] ?? device.kind)}
                      </td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }} title={device.client_commit ?? undefined}>
                        {device.client_version ?? '—'}
                        {device.client_commit && ` (${device.client_commit.slice(0, 7)})`}
                      </td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{formatTime(device.created_at)}</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {device.last_used_at != null ? formatTime(device.last_used_at) : '—'}
                      </td>
                      <td>
                        <span className={`badge ${device.kind === 'client' || device.current ? 'badge-success' : 'badge-neutral'}`}>
                          {device.kind === 'client' ? t('Authorized') : device.current ? t('Active') : t('Idle')}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          type="button"
                          className="btn-danger"
                          disabled={revokingDeviceId !== null}
                          onClick={() => void handleRevokeDevice(device.id)}
                        >
                          {revokingDeviceId === device.id ? `${t('Revoke')}…` : t('Revoke')}
                        </button>
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={7} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                        {devices ? t('No devices found.') : t('Loading...')}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
      )}
    </div>
  )
}
