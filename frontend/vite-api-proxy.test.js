import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import {
  resolveProxyRequestUrl,
  shouldProxyApiRequest,
} from './vite-api-proxy.js'

test('shouldProxyApiRequest matches config, usage and session routes', () => {
  assert.equal(shouldProxyApiRequest('/config'), true)
  assert.equal(shouldProxyApiRequest('/usage'), true)
  assert.equal(shouldProxyApiRequest('/usage/count?since=1'), true)
  assert.equal(shouldProxyApiRequest('/sessions'), true)
  assert.equal(shouldProxyApiRequest('/sessions/summary'), true)
  assert.equal(shouldProxyApiRequest('/sessions/123/evaluation'), true)
  assert.equal(shouldProxyApiRequest('/model-effectiveness?group_by=model'), true)
  assert.equal(shouldProxyApiRequest('/poll/job-123'), true)
  assert.equal(shouldProxyApiRequest('/evaluation-jobs/active'), true)
  assert.equal(shouldProxyApiRequest('/assets/index.js'), false)
})

test('resolveProxyRequestUrl re-reads tracker config for each request', () => {
  const root = mkdtempSync(join(tmpdir(), 'llm-tracker-vite-api-proxy-'))
  const configPath = join(root, 'config.yaml')

  try {
    writeFileSync(
      configPath,
      ['server:', '  host: 127.0.0.1', '  api_port: 4004', ''].join('\n'),
      'utf-8',
    )
    assert.equal(
      resolveProxyRequestUrl('/usage/count', {
        env: {},
        trackerConfigPath: configPath,
      }),
      'http://127.0.0.1:4004/usage/count',
    )

    writeFileSync(
      configPath,
      ['server:', '  host: 127.0.0.1', '  api_port: 4011', ''].join('\n'),
      'utf-8',
    )
    assert.equal(
      resolveProxyRequestUrl('/usage/count', {
        env: {},
        trackerConfigPath: configPath,
      }),
      'http://127.0.0.1:4011/usage/count',
    )
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test('resolveProxyRequestUrl ignores an incoming absolute frontend origin', () => {
  assert.equal(
    resolveProxyRequestUrl('http://localhost:5173/config?x=1', {
      env: {
        LLM_TRACKER_API_URL: 'http://127.0.0.1:4004',
      },
    }),
    'http://127.0.0.1:4004/config?x=1',
  )
})
