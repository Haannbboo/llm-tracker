import { getTheme, type Theme } from './theme'

export function getModelColor(model: string): string {
  const m = model.toLowerCase()
  if (m.startsWith('tencent/') || m.startsWith('hy3')) return '#0052D9'
  if (m.includes('gpt-5') || m.includes('gpt-4')) return '#dcdcdc'
  if (m.includes('claude')) return '#cc7c5e'
  if (m.includes('gemini')) return '#528af2'
  if (m.includes('minimax')) return '#ec6b53'
  if (m.includes('mimo-')) return '#dcc496'
  if (m.includes('openrouter')) return '#6366f1'
  return '#f1f5f9'
}

export function getModelTextColor(model: string, theme: Theme = getTheme()): string {
  const dark = theme === 'dark'
  const m = model.toLowerCase()
  if (m.startsWith('tencent/') || m.startsWith('hy3')) return dark ? '#d0dff5' : '#003a8c'
  if (m.includes('gpt-5') || m.includes('gpt-4')) return dark ? '#0f172a' : '#475569'
  if (m.includes('mimo-')) return dark ? '#dcc496' : '#6b4f2a'
  if (m.includes('openrouter')) return dark ? '#a5b4fc' : '#6366f1'
  return getModelColor(model)
}

export function getModelBadgeBackgroundColor(model: string, theme: Theme = getTheme()): string {
  const dark = theme === 'dark'
  const m = model.toLowerCase()
  if (m.startsWith('tencent/') || m.startsWith('hy3')) return dark ? '#0052D980' : '#0052D926'
  const base = getModelColor(model)
  if (m.includes('gpt-5') || m.includes('gpt-4')) return dark ? `${base}90` : `${base}80`
  if (m.includes('mimo-')) return dark ? `${base}90` : `${base}80`
  if (m.includes('openrouter')) return dark ? `${base}40` : `${base}26`
  return dark ? `${base}40` : `${base}26`
}
