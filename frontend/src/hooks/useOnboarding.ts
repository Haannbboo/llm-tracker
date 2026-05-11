import { useState, useEffect, useRef, useCallback } from 'react'
import type { UsageRow, OnboardingCopiedCommand } from '../types'
import { getVerifyTimeoutGuidance } from '../setup-guidance'
import { getSetupAgentKey } from '../utils'
import { useApp } from '../contexts/AppContext'

export function useOnboarding(opts: {
  totalTrackedEvents: number | null
  onFirstEvent: () => void
}) {
  const { localAgents, setupDiagnostics } = useApp()

  const [verifyPhase, setVerifyPhase] = useState<'idle' | 'polling' | 'success' | 'timeout'>('idle')
  const [verificationResult, setVerificationResult] = useState<UsageRow | null>(null)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollingStartRef = useRef<number>(0)
  const autoVerifyStartedRef = useRef(false)
  const [copiedOnboardingCommand, setCopiedOnboardingCommand] = useState<OnboardingCopiedCommand | null>(null)

  const stopVerificationPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }, [])

  useEffect(() => stopVerificationPolling, [stopVerificationPolling])

  const handleVerifyEvent = useCallback(() => {
    stopVerificationPolling()
    setVerifyPhase('polling')
    setVerificationResult(null)
    pollingStartRef.current = Date.now()

    const checkForEvent = async () => {
      try {
        const countRes = await fetch('/usage/count')
        if (!countRes.ok) throw new Error('Failed to check')
        const { total } = await countRes.json()

        if (total > 0) {
          stopVerificationPolling()
          setVerifyPhase('success')
          const usageRes = await fetch('/usage?limit=1')
          if (usageRes.ok) {
            const rows = await usageRes.json() as UsageRow[]
            if (rows.length > 0) {
              setVerificationResult(rows[0])
              opts.onFirstEvent()
            }
          }
          return
        }

        if (Date.now() - pollingStartRef.current >= 45000) {
          stopVerificationPolling()
          setVerifyPhase('timeout')
        }
      } catch {
        if (Date.now() - pollingStartRef.current >= 45000) {
          stopVerificationPolling()
          setVerifyPhase('timeout')
        }
      }
    }

    void checkForEvent()
    pollingRef.current = setInterval(checkForEvent, 2000)
  }, [stopVerificationPolling, opts.onFirstEvent])

  const armOnboardingVerification = useCallback((command: OnboardingCopiedCommand) => {
    setCopiedOnboardingCommand(command)
    handleVerifyEvent()
  }, [handleVerifyEvent])

  const showFirstRunOnboarding = opts.totalTrackedEvents !== null && opts.totalTrackedEvents === 0

  useEffect(() => {
    if (!showFirstRunOnboarding || autoVerifyStartedRef.current) return
    autoVerifyStartedRef.current = true
    handleVerifyEvent()
  }, [showFirstRunOnboarding, handleVerifyEvent])

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
      : 'No local Agent'
    : 'Unknown'
  const setupSummaryColor = setupDiagnostics && setupMatchingAgents > 0 ? 'var(--color-green)' : 'var(--text-muted)'
  const verifyTimeoutGuidance = getVerifyTimeoutGuidance({
    setupHealthAvailable: setupDiagnostics !== null,
    localAgentDetectionAvailable: localAgents !== null,
    localAgentCount: foundLocalAgentCount,
    setupLocalAgentTotal,
    configuredAgents: setupConfiguredAgents,
    matchingAgents: setupMatchingAgents,
  })

  const resetVerification = useCallback(() => {
    stopVerificationPolling()
    setVerifyPhase('idle')
    setVerificationResult(null)
  }, [stopVerificationPolling])

  return {
    verifyPhase, verificationResult, copiedOnboardingCommand,
    armOnboardingVerification, handleVerifyEvent, resetVerification,
    showFirstRunOnboarding,
    foundLocalAgents, foundLocalAgentCount,
    setupLocalAgentTotal, setupMatchingAgents, setupConfiguredAgents,
    setupSummaryText, setupSummaryColor, verifyTimeoutGuidance,
  }
}
