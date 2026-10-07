import { t } from '../i18n/index.ts'
import { getAgentDisplayName, getSetupAgentKey } from '../utils'
import type { SetupDiagnostics } from '../types'

type Props = {
  status: Record<string, any> | null
}

export function DeviceStatusDetail({ status }: Props) {
  if (!status) {
    return (
      <div style={{ padding: '16px', fontSize: '13px', color: 'var(--text-muted)' }}>
        {t('No report yet. Start the tokenage client service on this device.')}
      </div>
    )
  }

  const detected = (status.detected ?? {}) as Record<
    string,
    { found?: boolean; path?: string | null }
  >
  const diagnostics = status.agents
    ? ({
        expected: status.expected,
        summary: status.summary,
        agents: status.agents,
      } as SetupDiagnostics)
    : null

  const foundLocalAgents = Object.entries(detected).filter(([, info]) => info?.found)
  const foundLocalAgentCount = foundLocalAgents.length
  const setupLocalAgentTotal = diagnostics
    ? foundLocalAgents.filter(([name]) => diagnostics.agents[getSetupAgentKey(name)]).length
    : foundLocalAgentCount
  const setupMatchingAgents = diagnostics
    ? foundLocalAgents.filter(([name]) => diagnostics.agents[getSetupAgentKey(name)]?.endpoint_matches).length
    : 0
  const setupConfiguredAgents = diagnostics
    ? foundLocalAgents.filter(([name]) => diagnostics.agents[getSetupAgentKey(name)]?.configured).length
    : 0
  const setupSummaryText = diagnostics
    ? setupLocalAgentTotal > 0
      ? `${setupMatchingAgents}/${setupLocalAgentTotal}`
      : t('No local Agent')
    : t('Unknown')

  return (
    <>
      <div className="panel" style={{ border: 'none', borderRadius: 0 }}>
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
              {Object.keys(detected).length > 0 ? Object.entries(detected).map(([name, info]) => (
                <tr key={name}>
                  <td style={{ fontWeight: 700 }}>{getAgentDisplayName(name)}</td>
                  <td>
                    <span className={`badge ${info?.found ? 'badge-success' : 'badge-error'}`}>
                      {info?.found ? t('Ready') : t('Not found')}
                    </span>
                  </td>
                  <td style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: info?.path ? 'var(--text-secondary)' : 'var(--text-muted)' }}>
                    {info?.path || t('Unknown')}
                  </td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={3} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                    {t('No local Agent')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel" style={{ border: 'none', borderRadius: 0, borderTop: '1px solid var(--border-color)' }}>
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
              {diagnostics ? Object.entries(diagnostics.agents).map(([name, agent]) => (
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
  )
}
