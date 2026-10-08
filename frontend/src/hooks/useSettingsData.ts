import { useCallback } from 'react'
import { t } from '../i18n/index.ts'
import { useApp } from '../contexts/AppContext'
import type { EvaluatorType } from '../types.ts'

export function useSettingsData() {
  const {
    evaluationEvaluator,
    setEvaluationEvaluator,
    evaluationEvaluators,
    showToast,
    setConfigStatus,
    setError,
  } = useApp()

  const handleEvaluationEvaluatorChange = useCallback(async (nextEvaluator: EvaluatorType) => {
    const option = evaluationEvaluators.find((item) => item.id === nextEvaluator)
    if (option && !option.available) {
      setError(t('Evaluator unavailable'))
      return
    }

    const previousEvaluator = evaluationEvaluator
    setEvaluationEvaluator(nextEvaluator)
    setConfigStatus('saving')
    try {
      const response = await fetch('/config/evaluation', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ evaluator: nextEvaluator }),
      })
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || t('Failed to save config'))
      }
      setConfigStatus('saved')
      showToast(t('Configuration saved successfully'))
      setTimeout(() => setConfigStatus('idle'), 3000)
    } catch (err) {
      setEvaluationEvaluator(previousEvaluator)
      setConfigStatus('error')
      setError(err instanceof Error ? err.message : t('Failed to save config'))
    }
  }, [
    evaluationEvaluator,
    evaluationEvaluators,
    setEvaluationEvaluator,
    setConfigStatus,
    setError,
    showToast,
  ])

  return {
    handleEvaluationEvaluatorChange,
    evaluationEvaluator, evaluationEvaluators,
  }
}
