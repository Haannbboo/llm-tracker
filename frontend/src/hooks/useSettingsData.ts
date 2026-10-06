import { useCallback } from 'react'
import yaml from 'js-yaml'
import { t } from '../i18n/index.ts'
import { useApp } from '../contexts/AppContext'
import type { EvaluatorType } from '../types.ts'

function isPlainMapping(value: unknown): value is Record<string, any> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const prototype = Object.getPrototypeOf(value)
  return prototype === Object.prototype || prototype === null
}

function cloneConfig(config: Record<string, any> | null) {
  return structuredClone(config ?? {})
}

export function useSettingsData() {
  const {
    configContent,
    setConfigContent,
    configParsed,
    setConfigParsed,
    evaluationEvaluator,
    setEvaluationEvaluator,
    evaluationEvaluators,
    setEvaluationEvaluators,
    showToast,
    setConfigStatus,
    setError,
  } = useApp()

  const handleSaveConfig = useCallback(async () => {
    setConfigStatus('saving')
    try {
      const response = await fetch('/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: configContent }),
      })

      if (response.ok) {
        const configResp = await fetch('/config')
        if (!configResp.ok) {
          setError(t('Failed to refresh config after save'))
          setConfigStatus('error')
          return
        }
        const data = await configResp.json()
        setConfigContent(data.content)
        setConfigParsed(data.parsed)
        setEvaluationEvaluator(data.runtime?.evaluation?.evaluator === 'claude' ? 'claude' : 'codex')
        setConfigStatus('saved')
        setTimeout(() => setConfigStatus('idle'), 3000)
      } else {
        const error = await response.json()
        setError(error.detail || t('Failed to save config'))
        setConfigStatus('error')
      }
    } catch {
      setError(t('Connection error while saving config'))
      setConfigStatus('error')
    }
  }, [configContent, setConfigContent, setConfigParsed, setConfigStatus, setError, setEvaluationEvaluator])

  const handleEvaluationEvaluatorChange = useCallback(async (nextEvaluator: EvaluatorType) => {
    const option = evaluationEvaluators.find((item) => item.id === nextEvaluator)
    if (option && !option.available) {
      setError(t('Evaluator unavailable'))
      return
    }

    const previousEvaluator = evaluationEvaluator
    const previousContent = configContent
    const previousParsed = configParsed
    const nextConfig = cloneConfig(configParsed)
    if (!nextConfig.evaluation) nextConfig.evaluation = {}
    if (!isPlainMapping(nextConfig.evaluation)) {
      setError(t('Config root must be a YAML mapping'))
      return
    }
    nextConfig.evaluation.evaluator = nextEvaluator
    const nextContent = yaml.dump(nextConfig, { indent: 2, noRefs: true })

    setEvaluationEvaluator(nextEvaluator)
    setConfigParsed(nextConfig)
    setConfigContent(nextContent)
    setConfigStatus('saving')
    try {
      const response = await fetch('/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: nextContent }),
      })
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || t('Failed to save config'))
      }

      const configResp = await fetch('/config')
      if (!configResp.ok) throw new Error(t('Failed to refresh config after save'))
      const data = await configResp.json()
      setConfigContent(data.content)
      setConfigParsed(data.parsed)
      setEvaluationEvaluator(data.runtime?.evaluation?.evaluator === 'claude' ? 'claude' : 'codex')
      if (Array.isArray(data.runtime?.evaluation?.evaluators)) {
        setEvaluationEvaluators(data.runtime.evaluation.evaluators)
      }
      setConfigStatus('saved')
      showToast(t('Configuration saved successfully'))
      setTimeout(() => setConfigStatus('idle'), 3000)
    } catch (err) {
      setEvaluationEvaluator(previousEvaluator)
      setConfigContent(previousContent)
      setConfigParsed(previousParsed)
      setConfigStatus('error')
      setError(err instanceof Error ? err.message : t('Failed to save config'))
    }
  }, [
    configContent,
    configParsed,
    evaluationEvaluator,
    evaluationEvaluators,
    setConfigContent,
    setConfigParsed,
    setConfigStatus,
    setError,
    setEvaluationEvaluator,
    setEvaluationEvaluators,
    showToast,
  ])

  return {
    handleSaveConfig, handleEvaluationEvaluatorChange,
    evaluationEvaluator, evaluationEvaluators,
  }
}
