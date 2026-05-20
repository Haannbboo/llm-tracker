import { getTheme, type Theme } from './theme'

export function getModelColor(model: string): string {
  const m = model.toLowerCase()
  if (m.startsWith('tencent/') || m.startsWith('hy3')) return '#0052D9'
  if (m.includes('gpt-5') || m.includes('gpt-4')) return '#dcdcdc'
  if (m.includes('claude')) return '#cc7c5e'
  if (m.includes('gemini')) return '#528af2'
  if (m.includes('minimax')) return '#ec6b53'
  if (m.includes('mimo-')) return '#dcc496'
  if (m.includes('inclusionai')) return '#6366f1'
  if (m.includes('poolside')) return '#f97316'
  if (m.includes('deepseek')) return '#4d7cff'
  if (m.includes('openrouter')) return '#6366f1'
  if (m.startsWith('z-ai/') || m.includes('glm')) return '#1F63EC'
  return '#f1f5f9'
}

export function getModelTextColor(model: string, theme: Theme = getTheme()): string {
  const dark = theme === 'dark'
  const m = model.toLowerCase()
  if (m.startsWith('tencent/') || m.startsWith('hy3')) return dark ? '#d0dff5' : '#003a8c'
  if (m.includes('gpt-5') || m.includes('gpt-4')) return dark ? '#0f172a' : '#475569'
  if (m.includes('claude')) return dark ? '#e8a878' : '#975a3d'
  if (m.includes('gemini')) return dark ? '#a5b4fc' : '#1e40af'
  if (m.includes('minimax')) return dark ? '#fca5a5' : '#b91c1c'
  if (m.includes('mimo-')) return dark ? '#dcc496' : '#6b4f2a'
  if (m.includes('inclusionai')) return dark ? '#a5b4fc' : '#6366f1'
  if (m.includes('poolside')) return dark ? '#fdba74' : '#c2410c'
  if (m.includes('deepseek')) return dark ? '#93b4ff' : '#1d4ed8'
  if (m.includes('openrouter')) return dark ? '#a5b4fc' : '#6366f1'
  if (m.startsWith('z-ai/') || m.includes('glm')) return dark ? '#7daaf5' : '#1F63EC'
  return dark ? '#f1f5f9' : '#1e293b'
}

export function getModelBadgeBackgroundColor(model: string, theme: Theme = getTheme()): string {
  const dark = theme === 'dark'
  const m = model.toLowerCase()
  if (m.startsWith('tencent/') || m.startsWith('hy3')) return dark ? '#0052D980' : '#0052D926'
  if (m.includes('gpt-5') || m.includes('gpt-4')) {
    const base = '#dcdcdc'
    return dark ? `${base}90` : `${base}80`
  }
  if (m.includes('claude')) return dark ? '#cc7c5e60' : '#cc7c5e80'
  if (m.includes('gemini')) return dark ? '#528af260' : '#528af280'
  if (m.includes('minimax')) return dark ? '#ec6b5360' : '#ec6b5380'
  if (m.includes('mimo-')) {
    const base = '#dcc496'
    return dark ? `${base}90` : `${base}80`
  }
  if (m.includes('inclusionai')) return dark ? '#6366f140' : '#6366f126'
  if (m.includes('poolside')) return dark ? '#f9731640' : '#f9731626'
  if (m.includes('deepseek')) return dark ? '#4d7cff40' : '#4d7cff26'
  if (m.includes('openrouter')) return dark ? '#6366f140' : '#6366f126'
  if (m.startsWith('z-ai/') || m.includes('glm')) return dark ? '#1F63EC40' : '#1F63EC26'
  return dark ? '#64748b40' : '#64748b26'
}
