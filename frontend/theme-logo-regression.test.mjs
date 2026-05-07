import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import { dirname, resolve } from 'node:path'
import ts from 'typescript'
import vm from 'node:vm'

const require = createRequire(import.meta.url)
const root = dirname(new URL(import.meta.url).pathname)
const moduleCache = new Map()

function loadSourceModule(filePath) {
  const absolutePath = resolve(root, filePath)
  const cached = moduleCache.get(absolutePath)
  if (cached) return cached.exports

  const source = readFileSync(absolutePath, 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      esModuleInterop: true,
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2023,
    },
    fileName: absolutePath,
  })

  const module = { exports: {} }
  moduleCache.set(absolutePath, module)

  const localRequire = (specifier) => {
    if (specifier === './theme') return loadSourceModule('src/theme.ts')
    if (specifier === 'react/jsx-runtime') return require(specifier)
    return require(specifier)
  }

  vm.runInNewContext(outputText, {
    exports: module.exports,
    module,
    require: localRequire,
    document: globalThis.document,
    localStorage: globalThis.localStorage,
    window: globalThis.window,
  }, { filename: absolutePath })

  return module.exports
}

globalThis.document = { documentElement: { dataset: { theme: 'light' } } }
globalThis.localStorage = { getItem: () => null, setItem: () => {} }
globalThis.window = { matchMedia: () => ({ matches: false }) }

test('model icons choose the light and dark assets from the current theme', () => {
  const { getModelIcon } = loadSourceModule('src/utils.tsx')

  document.documentElement.dataset.theme = 'light'
  assert.equal(getModelIcon('gpt-5.4').props.src, '/models/chatgpt.svg')

  document.documentElement.dataset.theme = 'dark'
  assert.equal(getModelIcon('gpt-5.4').props.src, '/models/chatgpt-dark.png')
})

test('provider icons choose the light and dark SVG assets from the current theme', () => {
  const { getProviderIcon } = loadSourceModule('src/utils.tsx')

  document.documentElement.dataset.theme = 'light'
  assert.equal(getProviderIcon('openrouter').props.src, '/models/openrouter.svg')

  document.documentElement.dataset.theme = 'dark'
  assert.equal(getProviderIcon('openrouter').props.src, '/models/openrouter-dark.svg')
  assert.equal(getProviderIcon('openai').props.src, '/models/chatgpt-dark.png')
})

test('gpt model badge text stays readable on the dark mode badge background', () => {
  const {
    getModelBadgeBackgroundColor,
    getModelTextColor,
  } = loadSourceModule('src/model-badge.ts')

  assert.equal(getModelBadgeBackgroundColor('gpt-5.4', 'dark'), '#dcdcdc90')
  assert.equal(getModelTextColor('gpt-5.4', 'dark'), '#0f172a')
})

test('codex source badge text stays readable on the dark mode badge background', () => {
  const {
    getSourceBadgeBg,
    getSourceBadgeText,
  } = loadSourceModule('src/utils.tsx')

  document.documentElement.dataset.theme = 'dark'
  assert.equal(getSourceBadgeBg('codex'), '#dcdcdc90')
  assert.equal(getSourceBadgeText('codex'), '#0f172a')
})
