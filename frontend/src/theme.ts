export type Theme = 'light' | 'dark'

export function getTheme(): Theme {
  return (document.documentElement.dataset.theme as Theme) || 'light'
}

export function toggleTheme(): Theme {
  const next = getTheme() === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = next
  localStorage.setItem('theme', next)
  return next
}

export function initTheme(): void {
  const stored = localStorage.getItem('theme') as Theme | null
  if (stored) {
    document.documentElement.dataset.theme = stored
  } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
    document.documentElement.dataset.theme = 'dark'
  }
}
