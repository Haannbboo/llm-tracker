import { useState, useCallback } from 'react'
import yaml from 'js-yaml'
import { t } from '../i18n/index.ts'
import { useApp } from '../contexts/AppContext'

export function useSettingsData() {
  const { configContent, setConfigContent, configParsed, setConfigParsed, configStatus: _configStatus, setConfigStatus, setError } = useApp()

  const [selectedPricingProvider, setSelectedPricingProvider] = useState('global')

  // Connectivity test state
  const [testBaseUrl, setTestBaseUrl] = useState('')
  const [testApiKey, setTestApiKey] = useState('')
  const [testFormat, setTestFormat] = useState('openai')
  const [testModel, setTestModel] = useState('')
  const [testMessage, setTestMessage] = useState('What is 2 + 3?')
  const [testResult, setTestResult] = useState<Record<string, any> | null>(null)
  const [isTesting, setIsTesting] = useState(false)

  const handleSaveConfig = useCallback(async () => {
    setConfigStatus('saving')
    try {
      const response = await fetch('/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: configContent })
      })
      if (response.ok) {
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
  }, [configContent, setConfigStatus, setError])

  const handleRunTest = useCallback(async () => {
    setIsTesting(true)
    setTestResult(null)
    try {
      const response = await fetch('/test-connectivity', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: testBaseUrl,
          api_key: testApiKey,
          format: testFormat,
          model: testModel || null,
          message: testMessage || null
        })
      })
      const text = await response.text()
      try {
        setTestResult(JSON.parse(text))
      } catch {
        setTestResult({ status_code: response.status, body: text, url: '' })
      }
    } catch (err) {
      setTestResult({ error: err instanceof Error ? err.message : t('Test failed') })
    } finally {
      setIsTesting(false)
    }
  }, [testBaseUrl, testApiKey, testFormat, testModel, testMessage])

  const handleCostChange = useCallback((model: string, field: string, val: string) => {
    const numValue = val === '' ? undefined : parseFloat(val);
    const newParsed = { ...configParsed };

    if (selectedPricingProvider === 'global') {
      if (!newParsed.models) newParsed.models = {};
      if (!newParsed.models[model]) newParsed.models[model] = {};
      if (!newParsed.models[model].cost) newParsed.models[model].cost = {};

      if (numValue === undefined) {
        delete newParsed.models[model].cost[field];
      } else {
        newParsed.models[model].cost[field] = numValue;
      }
    } else {
      if (!newParsed.providers) newParsed.providers = {};
      if (!newParsed.providers[selectedPricingProvider]) newParsed.providers[selectedPricingProvider] = {};
      if (!newParsed.providers[selectedPricingProvider].models) newParsed.providers[selectedPricingProvider].models = {};
      if (!newParsed.providers[selectedPricingProvider].models[model]) newParsed.providers[selectedPricingProvider].models[model] = {};
      if (!newParsed.providers[selectedPricingProvider].models[model].cost) newParsed.providers[selectedPricingProvider].models[model].cost = {};

      if (numValue === undefined) {
        delete newParsed.providers[selectedPricingProvider].models[model].cost[field];
      } else {
        newParsed.providers[selectedPricingProvider].models[model].cost[field] = numValue;
      }
    }

    setConfigParsed(newParsed);
    setConfigContent(yaml.dump(newParsed, { indent: 2, noRefs: true }));
  }, [configParsed, selectedPricingProvider, setConfigParsed, setConfigContent])

  const manualCurlEquivalent = (() => {
    let base = testBaseUrl.replace(/\/$/, '')
    if (!base.includes('/v1')) base = base + '/v1'
    const endpoint = testFormat === 'openai' ? '/chat/completions' : testFormat === 'anthropic' ? '/messages' : '/responses'
    const fullUrl = base.endsWith(endpoint) ? base : base + endpoint
    return `curl ${fullUrl} \\\n  -H "${testFormat === 'anthropic' ? 'x-api-key' : 'Authorization: Bearer'}: ${testApiKey || 'YOUR_KEY'}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"model": "${testModel || 'gpt-5.4'}", "messages": [{"role": "user", "content": "${(testMessage || 'What is 2 + 3?').replace(/"/g, '\\"')}"}], "max_tokens": 10}'`
  })()

  return {
    selectedPricingProvider, setSelectedPricingProvider,
    testBaseUrl, setTestBaseUrl, testApiKey, setTestApiKey,
    testFormat, setTestFormat, testModel, setTestModel,
    testMessage, setTestMessage, testResult, isTesting,
    handleSaveConfig, handleRunTest, handleCostChange,
    manualCurlEquivalent,
  }
}
