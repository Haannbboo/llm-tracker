import assert from 'node:assert/strict'
import { shouldProxyApiRequest } from '../vite-api-proxy.js'

const proxiedRoutes = [
  '/config',
  '/usage',
  '/usage/count',
  '/usage/logs?limit=1',
  '/test-connectivity',
  '/local/agents',
  '/local/setup-health',
  '/model-effectiveness?group_by=model',
  '/poll/job-123',
  '/evaluation-jobs/active',
]

for (const route of proxiedRoutes) {
  assert.equal(
    shouldProxyApiRequest(route),
    true,
    `${route} should be proxied to the llm-tracker API`,
  )
}

const frontendRoutes = ['/', '/assets/index.js', '/favicon.ico', '/local/not-agents']

for (const route of frontendRoutes) {
  assert.equal(
    shouldProxyApiRequest(route),
    false,
    `${route} should remain handled by Vite/frontend`,
  )
}

console.log('vite api proxy route coverage regression passed')
