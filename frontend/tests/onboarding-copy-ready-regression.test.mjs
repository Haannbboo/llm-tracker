import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

const copyButtonComponentStart = appSource.indexOf('function CopyButton(')
const appComponentStart = appSource.indexOf('function App()')
assert.notEqual(copyButtonComponentStart, -1)
assert.notEqual(appComponentStart, -1)
const copyButtonComponent = appSource.slice(copyButtonComponentStart, appComponentStart)

const onboardingCommandsStart = appSource.indexOf('{/* Step 2: Run a test command */}')
assert.notEqual(onboardingCommandsStart, -1)
const bootstrapStepStart = appSource.indexOf('{/* Step 1: Bootstrap */}')
assert.notEqual(bootstrapStepStart, -1)
const bootstrapStepBlock = appSource.slice(bootstrapStepStart, onboardingCommandsStart)
const verifyStart = appSource.indexOf('{/* Step 3: Wait for event */}', onboardingCommandsStart)
assert.notEqual(verifyStart, -1)
const onboardingCommandsBlock = appSource.slice(onboardingCommandsStart, verifyStart)

const detectedAgentsStart = appSource.indexOf('{/* Detected agents */}', verifyStart)
assert.notEqual(detectedAgentsStart, -1)
const verifyBlock = appSource.slice(verifyStart, detectedAgentsStart)

const manualCurlCopyStart = appSource.indexOf('text={manualCurlEquivalent}')
assert.notEqual(manualCurlCopyStart, -1)
const manualCurlCopyEnd = appSource.indexOf('/>', manualCurlCopyStart)
assert.notEqual(manualCurlCopyEnd, -1)
const manualCurlCopyBlock = appSource.slice(manualCurlCopyStart, manualCurlCopyEnd)

test('shared copy button supports success-only copy callbacks', () => {
  assert.match(copyButtonComponent, /onCopied\?: \(\) => void/)
  assert.match(copyButtonComponent, /navigator\.clipboard\.writeText\(text\)\s*\n\s*\.then\(\(\) => \{/)

  const writeIndex = copyButtonComponent.indexOf('navigator.clipboard.writeText(text)')
  const copiedIndex = copyButtonComponent.indexOf('setCopied(true)', writeIndex)
  const callbackIndex = copyButtonComponent.indexOf('onCopied?.()', writeIndex)

  assert.ok(writeIndex !== -1, 'copy button should write the requested text to clipboard')
  assert.ok(copiedIndex > writeIndex, 'copy UI should only flip after writeText succeeds')
  assert.ok(callbackIndex > copiedIndex, 'success callback should run after copied state is set')
})

test('bootstrap copy does not arm the event verification step', () => {
  assert.match(bootstrapStepBlock, /text="llm-tracker bootstrap"/)
  assert.doesNotMatch(bootstrapStepBlock, /setCopiedOnboardingCommand/)
  assert.doesNotMatch(bootstrapStepBlock, /source: 'Bootstrap'/)
  assert.doesNotMatch(bootstrapStepBlock, /Agent command copied/)
})

test('onboarding command copy starts verification polling automatically', () => {
  assert.match(appSource, /type OnboardingCopiedCommand = \{\s*source: string\s*command: string\s*\}/)
  assert.match(appSource, /const \[copiedOnboardingCommand, setCopiedOnboardingCommand\] = useState<OnboardingCopiedCommand \| null>\(null\)/)
  assert.match(onboardingCommandsBlock, /onCopied=\{\(\) => armOnboardingVerification\(\{ source, command: cmd \}\)\}/)

  assert.match(appSource, /const armOnboardingVerification = \(command: OnboardingCopiedCommand\) => \{[\s\S]*setCopiedOnboardingCommand\(command\)[\s\S]*handleVerifyEvent\(\)/)
  assert.match(onboardingCommandsBlock, /armOnboardingVerification/)
})

test('first-run dashboard auto-starts verification polling on open', () => {
  assert.match(appSource, /const autoVerifyStartedRef = useRef\(false\)/)
  assert.match(appSource, /useEffect\(\(\) => \{[\s\S]*showFirstRunOnboarding[\s\S]*handleVerifyEvent\(\)[\s\S]*\}, \[showFirstRunOnboarding\]\)/)
})

test('verify panel shows compact auto-check hints without manual first-run CTA', () => {
  assert.match(verifyBlock, /copiedOnboardingCommand/)
  assert.match(verifyBlock, /Agent command copied\. Run it in your terminal — checking automatically\./)
  assert.match(verifyBlock, /This page is checking automatically\. Run a command above to generate your first event\./)
  assert.match(verifyBlock, /aria-live="polite"/)
  assert.doesNotMatch(verifyBlock, /Fix setup/)
  assert.doesNotMatch(verifyBlock, /Copy bootstrap command/)
  assert.doesNotMatch(verifyBlock, /onClick=\{handleVerifyEvent\}/)
  assert.doesNotMatch(verifyBlock, />\s*\{t\('Check for Event'\)\}\s*</)
})

test('connectivity test copy does not trigger onboarding ready state', () => {
  assert.doesNotMatch(manualCurlCopyBlock, /onCopied/)
  assert.doesNotMatch(manualCurlCopyBlock, /setCopiedOnboardingCommand/)
  assert.doesNotMatch(manualCurlCopyBlock, /Agent command copied/)
})

test('auto-check hints have natural Chinese translations', () => {
  assert.match(
    zhSource,
    /'This page is checking automatically\. Run a command above to generate your first event\.': '页面正在自动检查。运行上面的命令来生成第一个事件。'/
  )
  assert.match(
    zhSource,
    /'Agent command copied\. Run it in your terminal — checking automatically\.': 'Agent 命令已复制。请在终端运行它，页面会自动检查。'/
  )
})
