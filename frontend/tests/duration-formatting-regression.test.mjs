import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const dashboard = readFileSync(join(root, 'src/pages/DashboardPage.tsx'), 'utf8')
const utils = readFileSync(join(root, 'src/utils.tsx'), 'utf8')

describe('Duration formatting', () => {
  test('formatDuration supports opt-in seconds rounding precision', () => {
    assert.match(utils, /type DurationFormatOptions = \{/)
    assert.match(utils, /secondsFractionDigits\?: number/)
    assert.match(utils, /toFixed\(options\.secondsFractionDigits\)/)
  })

  test('sessions average duration uses two decimal places for seconds', () => {
    assert.match(
      dashboard,
      /formatDuration\(sessionsSummary\.avg_duration_s, \{ secondsFractionDigits: 2 \}\)/,
    )
    assert.match(dashboard, /formatDuration\(session\.duration_s\)/)
  })
})
