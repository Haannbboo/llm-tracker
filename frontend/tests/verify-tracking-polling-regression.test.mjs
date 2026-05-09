import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const appSource = readFileSync(join(here, 'src', 'App.tsx'), 'utf-8')
const zhSource = readFileSync(join(here, 'src', 'i18n', 'zh.ts'), 'utf-8')

const verifyStart = appSource.indexOf('const handleVerifyEvent = () => {')
const verifyEnd = appSource.indexOf('const manualCurlEquivalent = (() => {')
assert.notEqual(verifyStart, -1)
assert.notEqual(verifyEnd, -1)
const verifyHandler = appSource.slice(verifyStart, verifyEnd)

test('verify tracking uses a polling state machine instead of a one-shot check', () => {
  assert.match(appSource, /const \[verifyPhase, setVerifyPhase\] = useState<'idle' \| 'polling' \| 'success' \| 'timeout'>\('idle'\)/)
  assert.match(appSource, /const pollingRef = useRef<ReturnType<typeof setInterval> \| null>\(null\)/)
  assert.match(appSource, /const pollingStartRef = useRef<number>\(0\)/)
  assert.doesNotMatch(appSource, /const \[verifying, setVerifying\]/)
})

test('verify tracking polls immediately, every 2 seconds, and times out after 45 seconds', () => {
  assert.match(verifyHandler, /void checkForEvent\(\)/)
  assert.match(verifyHandler, /pollingRef\.current = setInterval\(checkForEvent, 2000\)/)
  assert.match(verifyHandler, /Date\.now\(\) - pollingStartRef\.current >= 45000/)
  assert.match(verifyHandler, /setVerifyPhase\('timeout'\)/)
})

test('verify tracking stops polling on duplicate click, success, timeout, and unmount', () => {
  assert.match(verifyHandler, /stopVerificationPolling\(\)\s*\n\s*setVerifyPhase\('polling'\)/)
  assert.match(verifyHandler, /if \(total > 0\) \{\s*\n\s*stopVerificationPolling\(\)/)
  assert.match(verifyHandler, /if \(Date\.now\(\) - pollingStartRef\.current >= 45000\) \{\s*\n\s*stopVerificationPolling\(\)/)
  assert.match(appSource, /useEffect\(\(\) => stopVerificationPolling, \[\]\)/)
})

test('verify tracking UI exposes polling, timeout, and success states without manual CTA', () => {
  assert.match(appSource, /verifyPhase === 'polling'\s*\? t\('Waiting for your first event\.\.\.'\)/)
  assert.match(appSource, /verifyPhase === 'timeout'\s*\? t\(verifyTimeoutGuidance\)/)
  assert.doesNotMatch(appSource, /disabled=\{verifyPhase === 'polling'\}/)
  assert.doesNotMatch(appSource, /verifyPhase === 'polling' \? `⌛ \$\{t\('Waiting\.\.\.'\)\}`/)
  assert.match(appSource, /\{t\('Tracking works\. Your first request is recorded\.'\)\}/)
})

test('verify tracking strings have Chinese translations', () => {
  assert.match(zhSource, /'Waiting\.\.\.': '等待中\.\.\.'/)
  assert.match(zhSource, /'Waiting for your first event\.\.\.': '正在等待你的第一个请求\.\.\.'/)
  assert.match(zhSource, /'No event found yet': '还没找到事件'/)
  assert.match(zhSource, /'Tracking works': '追踪已生效'/)
})
