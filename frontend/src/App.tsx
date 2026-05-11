import { useCallback } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import './App.css'
import { AppProvider } from './contexts/AppContext'
import { Navbar } from './components/Navbar'
import { DashboardPage } from './pages/DashboardPage'
import { LogsPage } from './pages/LogsPage'
import { SettingsPage } from './pages/SettingsPage'
import type { ActiveFilter } from './types'

function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()

  const currentView = location.pathname.startsWith('/logs')
    ? 'logs'
    : location.pathname.startsWith('/settings')
      ? 'settings'
      : 'dashboard'

  const handleNavigate = useCallback((view: 'dashboard' | 'logs' | 'settings') => {
    navigate(`/${view}`)
  }, [navigate])

  const handleNavigateToLogs = useCallback((filters?: { sessionFilter?: string; activeFilter?: ActiveFilter }) => {
    if (filters) {
      sessionStorage.setItem('llm-tracker-logs-filters', JSON.stringify(filters))
    }
    navigate('/logs')
  }, [navigate])

  return (
    <div className="app">
      <main className="main">
        <Navbar currentView={currentView} onNavigate={handleNavigate} />
        <div className="content-body">
          <Routes>
            <Route path="/dashboard" element={<DashboardPage onNavigateToLogs={handleNavigateToLogs} />} />
            <Route path="/logs" element={<LogsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <AppLayout />
      </AppProvider>
    </BrowserRouter>
  )
}

export default App
