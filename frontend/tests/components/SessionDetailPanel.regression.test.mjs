import { test, describe } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = join(__dirname, '../..')
const detail = readFileSync(join(root, 'src/components/SessionDetailPanel.tsx'), 'utf8')
const css = readFileSync(join(root, 'src/App.css'), 'utf8')

describe('SessionDetailPanel Set as default button', () => {
  test('component has Set as default button inside evaluator picker', () => {
    // Button should be inside session-evaluator-picker div
    assert.match(detail, /session-evaluator-picker[\s\S]*Set as default/)
  })

  test('component has Set as default button with correct class', () => {
    assert.match(detail, /session-eval-btn-set-default/)
  })

  test('component calls PATCH /config/evaluation when Set as default is clicked', () => {
    assert.match(detail, /method:\s*['"]PATCH['"]/)
    assert.match(detail, /\/config\/evaluation/)
  })

  test('button is disabled when selectedEvaluatorType equals globalEvaluatorType', () => {
    assert.match(detail, /selectedEvaluatorType\s*===\s*globalEvaluatorType/)
  })

  test('CSS includes session-eval-btn-set-default styles', () => {
    assert.match(css, /\.session-eval-btn-set-default/)
  })
})
