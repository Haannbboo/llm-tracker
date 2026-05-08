export type VerifyTimeoutGuidanceInput = {
  setupHealthAvailable: boolean
  localAgentDetectionAvailable: boolean
  localAgentCount: number
  setupLocalAgentTotal: number
  configuredAgents: number
  matchingAgents: number
}

const GENERIC_TIMEOUT_GUIDANCE = 'No event found yet'
const NO_LOCAL_AGENT_GUIDANCE = 'No local Agent detected. Run or install an agent, then try Verify Tracking again.'
const OTLP_NOT_CONFIGURED_GUIDANCE = 'OTLP is not configured for detected agents. Check Settings OTLP Tracking Setup.'
const ENDPOINT_MISMATCH_GUIDANCE = 'OTLP endpoint mismatch detected. Check Settings OTLP Tracking Setup.'

export function getVerifyTimeoutGuidance({
  setupHealthAvailable,
  localAgentDetectionAvailable,
  localAgentCount,
  setupLocalAgentTotal,
  configuredAgents,
  matchingAgents,
}: VerifyTimeoutGuidanceInput): string {
  if (!setupHealthAvailable || !localAgentDetectionAvailable) {
    return GENERIC_TIMEOUT_GUIDANCE
  }

  const detectedAgentTotal = Math.max(localAgentCount, setupLocalAgentTotal)
  if (detectedAgentTotal === 0) {
    return NO_LOCAL_AGENT_GUIDANCE
  }

  if (configuredAgents === 0) {
    return OTLP_NOT_CONFIGURED_GUIDANCE
  }

  if (matchingAgents < Math.max(configuredAgents, detectedAgentTotal)) {
    return ENDPOINT_MISMATCH_GUIDANCE
  }

  return GENERIC_TIMEOUT_GUIDANCE
}
