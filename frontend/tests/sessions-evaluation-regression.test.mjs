import { test, describe } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = join(__dirname, '..')

const types = readFileSync(join(root, 'src/types.ts'), 'utf8')
const dashboard = readFileSync(join(root, 'src/pages/DashboardPage.tsx'), 'utf8')
const detail = readFileSync(join(root, 'src/components/SessionDetailPanel.tsx'), 'utf8')
const css = readFileSync(join(root, 'src/App.css'), 'utf8')
const zh = readFileSync(join(root, 'src/i18n/zh.ts'), 'utf8')

describe('Session evaluation types', () => {
  test('SessionOutcome type is defined', () => {
    assert.match(types, /export type SessionOutcome/)
    assert.match(types, /'solved'/)
    assert.match(types, /'partial'/)
    assert.match(types, /'failed'/)
    assert.match(types, /'stuck'/)
    assert.match(types, /'no_op'/)
    assert.match(types, /'unknown'/)
  })

  test('SessionEvaluation type is defined', () => {
    assert.match(types, /export type SessionEvaluation/)
    assert.match(types, /outcome: SessionOutcome/)
    assert.match(types, /source: SessionEvaluationSource/)
    assert.match(types, /evaluated_at: string \| null/)
  })

  test('SessionSummary includes evaluation field', () => {
    assert.match(types, /evaluation: SessionEvaluation \| null/)
  })
})

describe('Session evaluation UI', () => {
  test('sessions table has outcome column header', () => {
    assert.match(dashboard, /Outcome/)
  })

  test('sessions table renders outcome badge', () => {
    assert.match(dashboard, /session-outcome-badge/)
  })

  test('getOutcomeBadge helper exists', () => {
    assert.match(dashboard, /getOutcomeBadge/)
  })

  test('session detail has evaluation section', () => {
    assert.match(detail, /session-eval-section/)
  })

  test('session detail has evaluation buttons', () => {
    assert.match(detail, /session-eval-btn/)
  })

  test('session detail has Mark Solved button', () => {
    assert.match(detail, /Mark Solved|Solved/)
  })

  test('session detail has Mark Failed button', () => {
    assert.match(detail, /Mark Failed|Failed/)
  })

  test('session detail calls evaluation API', () => {
    assert.match(detail, /\/sessions\//)
    assert.match(detail, /evaluation/)
    assert.match(detail, /PUT|DELETE/)
  })

  test('session detail notifies parent on evaluation update', () => {
    assert.match(detail, /onEvaluationUpdate/)
    assert.match(detail, /onEvaluationUpdate\(newEval\)/)
    assert.match(dashboard, /handleEvaluationUpdate/)
    assert.match(dashboard, /setSessions/)
  })

  test('session detail notifies parent after evaluation persistence succeeds', () => {
    assert.match(detail, /onEvaluationPersisted/)
    assert.match(detail, /if \(!response\.ok\) throw new Error/)
    assert.match(detail, /onEvaluationPersisted\?\.\(\)/)
    assert.match(dashboard, /onEvaluationPersisted=\{refreshModelEffectiveness\}/)
  })
})

describe('Session evaluation CSS', () => {
  test('outcome badge styles exist', () => {
    assert.match(css, /\.session-outcome-badge/)
    assert.match(css, /\.session-outcome-solved/)
    assert.match(css, /\.session-outcome-failed/)
  })

  test('evaluation button styles exist', () => {
    assert.match(css, /\.session-eval-btn/)
    assert.match(css, /\.session-eval-buttons/)
    assert.match(css, /\.session-eval-section/)
  })
})

describe('Session evaluation i18n', () => {
  test('evaluation translations exist', () => {
    assert.match(zh, /'Solved'/)
    assert.match(zh, /'Failed'/)
    assert.match(zh, /'Mark Solved'/)
    assert.match(zh, /'Evaluation'/)
  })
})
