import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import type { ReactNode } from 'react'
import { toggleTheme, getTheme } from '../theme'
import { useLang } from '../i18n/index.ts'
import { getSavedTimezone, saveTimezone } from '../utils'
import type { ActiveFilter, AuthUser, DateRangeOption, EvaluatorOption, EvaluatorType, PricingMap } from '../types.ts'

export type AuthState = {
  status: 'loading' | 'ready'
  enabled: boolean
  user: AuthUser | null
}

type AppContextType = {
  theme: 'light' | 'dark'
  setTheme: (t: 'light' | 'dark') => void
  toggleThemeHandler: () => void

  lang: 'en' | 'zh'
  setLang: (l: 'en' | 'zh') => void

  auth: AuthState
  signOut: () => Promise<void>

  configContent: string
  setConfigContent: (c: string) => void
  configParsed: Record<string, any> | null
  setConfigParsed: (c: Record<string, any> | null) => void
  evaluationEvaluator: EvaluatorType
  setEvaluationEvaluator: (e: EvaluatorType) => void
  evaluationEvaluators: EvaluatorOption[]
  setEvaluationEvaluators: (e: EvaluatorOption[]) => void
  configStatus: 'idle' | 'saving' | 'saved' | 'error'
  setConfigStatus: (s: 'idle' | 'saving' | 'saved' | 'error') => void

  pricingData: PricingMap | null
  setPricingData: (p: PricingMap | null) => void

  showToast: (message: string) => void

  error: string | null
  setError: (e: string | null) => void

  refreshTrigger: number
  requestUsageRefresh: () => void

  activeFilter: ActiveFilter
  setActiveFilter: (f: ActiveFilter) => void
  activeSource: string | null
  setActiveSource: (s: string | null) => void
  dateRange: DateRangeOption
  setDateRange: (d: DateRangeOption) => void
  customSince: string
  setCustomSince: (s: string) => void
  customUntil: string
  setCustomUntil: (s: string) => void

  timezone: string
  setTimezone: (tz: string) => void
}

const AppContext = createContext<AppContextType | null>(null)

export function isApiPath(pathname: string): boolean {
  return (
    pathname === '/auth' ||
    pathname.startsWith('/auth/') ||
    pathname === '/usage' ||
    pathname.startsWith('/usage/') ||
    pathname === '/sessions' ||
    pathname.startsWith('/sessions/') ||
    pathname === '/model-effectiveness' ||
    pathname === '/config' ||
    pathname.startsWith('/config/') ||
    pathname === '/pricing' ||
    pathname.startsWith('/pricing/') ||
    pathname.startsWith('/local/') ||
    pathname === '/test-connectivity' ||
    pathname === '/version'
  )
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<'light' | 'dark'>(getTheme)
  const { lang, setLang } = useLang()
  const [auth, setAuth] = useState<AuthState>({ status: 'loading', enabled: false, user: null })
  const [configContent, setConfigContent] = useState('')
  const [configParsed, setConfigParsed] = useState<Record<string, any> | null>(null)
  const [evaluationEvaluator, setEvaluationEvaluator] = useState<EvaluatorType>('codex')
  const [evaluationEvaluators, setEvaluationEvaluators] = useState<EvaluatorOption[]>([])
  const [configStatus, setConfigStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [pricingData, setPricingData] = useState<PricingMap | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  const [activeFilter, setActiveFilter] = useState<ActiveFilter>(null)
  const [activeSource, setActiveSource] = useState<string | null>(null)
  const [dateRange, setDateRange] = useState<DateRangeOption>('24h')
  const [customSince, setCustomSince] = useState('')
  const [customUntil, setCustomUntil] = useState('')
  const [timezone, setTimezoneState] = useState<string>(getSavedTimezone)
  const setTimezone = useCallback((tz: string) => { setTimezoneState(tz); saveTimezone(tz) }, [])

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

  const markLoggedOut = useCallback(() => {
    setAuth(current => {
      if (!current.enabled) return current
      if (current.user === null && current.status === 'ready') return current
      return { status: 'ready', enabled: true, user: null }
    })
  }, [])

  const signOut = useCallback(async () => {
    try {
      await fetch('/auth/logout', { method: 'POST' })
    } catch {}
    window.location.reload()
  }, [])

  // Resolve the session on mount. With auth enabled and no session the app
  // renders the LoginGate instead of the dashboard.
  useEffect(() => {
    const controller = new AbortController()
    async function fetchAuth() {
      try {
        const response = await fetch('/auth/me', { signal: controller.signal })
        if (response.ok) {
          const data = await response.json()
          setAuth({
            status: 'ready',
            enabled: data.auth_enabled === true,
            user: data.user ?? null,
          })
          return
        }
        if (response.status === 401) {
          // A 401 from /auth/me can only happen when auth is enabled
          // server-side (auth disabled returns 200 auth_enabled: false),
          // so this is the unauthenticated login-gate state.
          setAuth({ status: 'ready', enabled: true, user: null })
          return
        }
        // Any other failure (500, ...): fail closed rather than rendering
        // the dashboard with an unresolved auth state. /auth/me only fails
        // when auth is enabled (auth-disabled returns 200 with no DB access),
        // so treat "can't tell" the same as "logged out."
        setAuth({ status: 'ready', enabled: true, user: null })
      } catch (err) {
        if (controller.signal.aborted) return
        console.error('Failed to resolve session:', err)
        setAuth({ status: 'ready', enabled: true, user: null })
      }
    }
    void fetchAuth()
    return () => controller.abort()
  }, [])

  // While auth is enabled, any 401 from the API means the session died
  // (revoked cookie, expired token); drop back to the login gate.
  useEffect(() => {
    if (!auth.enabled) return
    const originalFetch = window.fetch.bind(window)
    window.fetch = async (input, init) => {
      const response = await originalFetch(input, init)
      if (response.status === 401) {
        const raw = typeof input === 'string'
          ? input
          : input instanceof Request
            ? input.url
            : input.href
        const url = new URL(raw, window.location.origin)
        if (isApiPath(url.pathname)) markLoggedOut()
      }
      return response
    }
    return () => { window.fetch = originalFetch }
  }, [auth.enabled, markLoggedOut])

  // Fetch config on mount. Settings owns pricing fetches because pricing scope
  // depends on the selected provider.
  useEffect(() => {
    const controller = new AbortController()
    async function fetchInitialData() {
      try {
        const configResp = await fetch('/config', { signal: controller.signal })
        if (configResp.ok) {
          const data = await configResp.json()
          setConfigContent(data.content)
          setConfigParsed(data.parsed)
          const runtimeEvaluator = data.runtime?.evaluation?.evaluator
          setEvaluationEvaluator(typeof runtimeEvaluator === 'string' ? runtimeEvaluator as EvaluatorType : 'codex')
          if (Array.isArray(data.runtime?.evaluation?.evaluators)) {
            setEvaluationEvaluators(data.runtime.evaluation.evaluators)
          }
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
      auth, signOut,
      configContent, setConfigContent, configParsed, setConfigParsed, configStatus, setConfigStatus,
      evaluationEvaluator, setEvaluationEvaluator, evaluationEvaluators, setEvaluationEvaluators,
      pricingData, setPricingData,
      showToast,
      error, setError,
      refreshTrigger, requestUsageRefresh,
      activeFilter, setActiveFilter, activeSource, setActiveSource,
      dateRange, setDateRange, customSince, setCustomSince, customUntil, setCustomUntil,
      timezone, setTimezone,
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
