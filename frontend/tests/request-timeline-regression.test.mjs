import { test, describe } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = join(__dirname, '..')
const timeline = readFileSync(join(root, 'src/components/RequestTimeline.tsx'), 'utf8')
const logsPage = readFileSync(join(root, 'src/pages/LogsPage.tsx'), 'utf8')
const css = readFileSync(join(root, 'src/index.css'), 'utf8')

describe('RequestTimeline per-tool color coding', () => {
  test('each tool becomes its own segment colored by tool name', () => {
    // Tool segments are keyed per tool and colored via the shared tool palette.
    assert.match(timeline, /key: `tool:\$\{tc\.tool_use_id\}`/)
    assert.match(timeline, /color: getToolColor\(tc\.tool_name\)\.bg/)
  })

  test('no single fixed-color block for all tools', () => {
    // Regression: the old bar lumped every tool into one green block.
    assert.doesNotMatch(timeline, /background: 'var\(--color-green\)'/)
  })

  test('does not fabricate a total when no timing exists', () => {
    // Regression: a `, 1` floor in the total made rows with no latency/ttft/tools
    // render a bogus 1ms "Output generation" bar.
    assert.doesNotMatch(timeline, /Math\.max\(latency, toolMaxEnd, ttft, 1\)/)
  })

  test('renders a dedicated row with constrained max-width (does not occupy full width)', () => {
    assert.match(timeline, /className="request-timeline"/)
    assert.match(css, /\.request-timeline\s*\{[\s\S]*grid-column:\s*1\s*\/\s*-1/)
    assert.match(css, /\.request-timeline\s*\{[\s\S]*max-width:\s*540px/)
  })

  test('displays sequential TUs one per line and parallel TUs stacked', () => {
    // Sequential TUs: single tool per cluster gets individual row
    assert.match(timeline, /cluster\.length === 1/)
    assert.match(timeline, /type:\s*'tool'/)
    // Parallel TUs: overlapping tools are grouped and stacked
    assert.match(timeline, /type:\s*'parallel_group'/)
    assert.match(timeline, /request-timeline-bar-stacked/)
    assert.match(timeline, /isParallel/)
  })

  test('includes TTFT, Output generation, and total end-to-end latency', () => {
    assert.match(timeline, /id:\s*'ttft'/)
    assert.match(timeline, /id:\s*'generation'/)
    assert.match(timeline, /label:\s*t\('Output generation'\)/)
    assert.match(timeline, /className="request-timeline-total"/)
    assert.match(timeline, /formatLatency\(displayTotal\)/)
    // Total reports end-to-end latency when known (session builds prefer latency
    // over the drawn axis, which tools can overrun).
    assert.match(timeline, /const displayTotal = latency > 0 \? latency : totalMs/)
  })

  test('generation is the complement of tool-occupied time, not the span', () => {
    // Regression: `totalMs - toolMaxEnd` treated the wall-clock gap between
    // tools as tool time, collapsing generation to ~0 for agentic clients whose
    // tools run between requests.
    assert.doesNotMatch(timeline, /const genDuration = Math\.max\(0, totalMs - genStart\)/)
    assert.match(timeline, /const toolBusyMs = mergedToolBusy\.reduce/)
    assert.match(timeline, /const genDuration = Math\.max\(0, totalMs - genStart - toolBusyMs\)/)
    // Generation is drawn as one or more segments filling the gaps between tools.
    assert.match(timeline, /const genSegments: TimelineSegment\[\]/)
  })

  test('supports extra components for future extensibility', () => {
    assert.match(timeline, /extraComponents\?: TimelineCustomComponent\[\]/)
  })
})

describe('LogsPage uses RequestTimeline', () => {
  test('expanded row renders the component with latency, ttft, and tool calls', () => {
    assert.match(logsPage, /import \{ RequestTimeline \} from '\.\.\/components\/RequestTimeline'/)
    assert.match(logsPage, /<RequestTimeline[\s\S]*latencyMs=\{row\.latency_ms\}[\s\S]*ttftMs=\{row\.ttft_ms\}[\s\S]*toolCalls=\{expandedToolCalls\}/)
  })
})
