import { getTheme } from './theme'

export function getModelColor(model: string): string {
  const m = model.toLowerCase()
  if (m.includes('gpt-5') || m.includes('gpt-4')) return '#dcdcdc'
  if (m.includes('claude')) return '#cc7c5e'
  if (m.includes('gemini')) return '#528af2'
  if (m.includes('minimax')) return '#ec6b53'
  if (m.includes('mimo-')) return '#dcc496'
  return '#f1f5f9'
}

export function getModelTextColor(model: string): string {
  const dark = getTheme() === 'dark'
  const m = model.toLowerCase()
  if (m.includes('gpt-5') || m.includes('gpt-4')) return dark ? '#94a3b8' : '#475569'
  if (m.includes('mimo-')) return dark ? '#dcc496' : '#6b4f2a'
  return getModelColor(model)
}

export function getModelBadgeBackgroundColor(model: string): string {
  const dark = getTheme() === 'dark'
  const m = model.toLowerCase()
  const base = getModelColor(model)
  if (m.includes('gpt-5') || m.includes('gpt-4')) return dark ? `${base}90` : `${base}80`
  if (m.includes('mimo-')) return dark ? `${base}90` : `${base}80`
  return dark ? `${base}40` : `${base}26`
}
