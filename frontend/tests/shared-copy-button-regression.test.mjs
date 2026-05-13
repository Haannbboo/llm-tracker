import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const copyButtonSource = readFileSync(join(here, 'src', 'components', 'CopyButton.tsx'), 'utf-8')
const dashboardSource = readFileSync(join(here, 'src', 'pages', 'DashboardPage.tsx'), 'utf-8')
const settingsSource = readFileSync(join(here, 'src', 'pages', 'SettingsPage.tsx'), 'utf-8')
const logsSource = readFileSync(join(here, 'src', 'pages', 'LogsPage.tsx'), 'utf-8')

test('onboarding and connectivity copy controls use one shared CopyButton component', () => {
  assert.match(copyButtonSource, /function CopyButton\(/)
  assert.match(copyButtonSource, /navigator\.clipboard\.writeText\(text\)/)
  assert.match(copyButtonSource, /setCopied\(true\)/)
  assert.match(copyButtonSource, /setTimeout\(\(\) => setCopied\(false\),/)

  assert.match(dashboardSource, /import \{[\s\S]*CopyButton[\s\S]*\} from '\.\.\/components\/CopyButton'/)
  assert.match(settingsSource, /import \{[\s\S]*CopyButton[\s\S]*\} from '\.\.\/components\/CopyButton'/)
  assert.match(logsSource, /import \{[\s\S]*ClickToCopy[\s\S]*\} from '\.\.\/components\/CopyButton'/)

  assert.match(dashboardSource, /<CopyButton\b/)
  assert.match(settingsSource, /<CopyButton\b/)
})
