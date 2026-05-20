import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import type { ReactNode } from 'react'
import { toggleTheme, getTheme } from '../theme'
import { useLang } from '../i18n/index.ts'
import type { PricingMap } from '../types.ts'

type AppContextType = {
  // Theme
  theme: 'light' | 'dark'
  setTheme: (t: 'light' | 'dark') => void
  toggleThemeHandler: () => void

  // Language
  lang: 'en' | 'zh'
  setLang: (l: 'en' | 'zh') => void

  // Config
  configContent: string
  setConfigContent: (c: string) => void
  configParsed: Record<string, any> | null
  setConfigParsed: (c: Record<string, any> | null) => void
  configStatus: 'idle' | 'saving' | 'saved' | 'error'
  setConfigStatus: (s: 'idle' | 'saving' | 'saved' | 'error') => void

  // Pricing
  pricingData: PricingMap | null
  setPricingData: (p: PricingMap | null) => void

  // Toast
  showToast: (message: string) => void

  // Error
  error: string | null
  setError: (e: string | null) => void

  // Refresh
  refreshTrigger: number
  requestUsageRefresh: () => void
}

const AppContext = createContext<AppContextType | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<'light' | 'dark'>(getTheme)
  const { lang, setLang } = useLang()
  const [configContent, setConfigContent] = useState('')
  const [configParsed, setConfigParsed] = useState<Record<string, any> | null>(null)
  const [configStatus, setConfigStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [pricingData, setPricingData] = useState<PricingMap | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  const [toast, setToast] = useState<{ message: string; visible: boolean }>({ message: '', visible: false })
  const showToast = useCallback((message: string) => {
    setToast({ message, visible: true })
    setTimeout(() => setToast(prev => ({ ...prev, visible: false })), 2000)
  }, [])

  const requestUsageRefresh = useCallback(() => {
    setRefreshTrigger(trigger => trigger + 1)
  }, [])

  const toggleThemeHandler = useCallback(() => {
    setTheme(toggleTheme())
  }, [])

  // Fetch config and pricing on mount
  useEffect(() => {
    const controller = new AbortController()
    async function fetchInitialData() {
      try {
        const [configResp, pricingResp] = await Promise.all([
          fetch('/config', { signal: controller.signal }),
          fetch('/pricing', { signal: controller.signal }),
        ])
        if (configResp.ok) {
          const data = await configResp.json()
          setConfigContent(data.content)
          setConfigParsed(data.parsed)
        }
        if (pricingResp.ok) {
          setPricingData(await pricingResp.json())
        }
      } catch (err) {
        console.error('Failed to load initial data:', err)
      }
    }
    void fetchInitialData()
    return () => controller.abort()
  }, [])

  return (
    <AppContext.Provider value={{
      theme, setTheme, toggleThemeHandler,
      lang, setLang,
      configContent, setConfigContent, configParsed, setConfigParsed, configStatus, setConfigStatus,
      pricingData, setPricingData,
      showToast,
      error, setError,
      refreshTrigger, requestUsageRefresh,
    }}>
      {children}
      <div className={`toast-container ${toast.visible ? 'visible' : ''}`}>
        {toast.message}
      </div>
    </AppContext.Provider>
  )
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
