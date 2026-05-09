import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')

const copyButtonComponentStart = appSource.indexOf('function CopyButton(')
const appComponentStart = appSource.indexOf('function App()')

test('onboarding and connectivity copy controls use one shared CopyButton component', () => {
  assert.notEqual(copyButtonComponentStart, -1, 'App.tsx should define a shared CopyButton component')
  assert.notEqual(appComponentStart, -1, 'App.tsx should define App component after shared helpers')

  const copyButtonComponent = appSource.slice(copyButtonComponentStart, appComponentStart)
  const appComponent = appSource.slice(appComponentStart)

  assert.match(copyButtonComponent, /navigator\.clipboard\.writeText\(text\)/)
  assert.match(copyButtonComponent, /setCopied\(true\)/)
  assert.match(copyButtonComponent, /setTimeout\(\(\) => setCopied\(false\),/)

  assert.equal((appComponent.match(/<CopyButton\b/g) || []).length, 3)
  assert.doesNotMatch(appComponent, /navigator\.clipboard\.writeText/)
  assert.doesNotMatch(appComponent, /btn\.textContent/)
  assert.doesNotMatch(appComponent, /classList\.add\('btn-copy-clicked'\)/)
})
