import { t } from '../i18n/index.ts'
import { useApp } from '../contexts/AppContext'

type View = 'dashboard' | 'logs' | 'settings'

export function Navbar({ currentView, onNavigate }: { currentView: View; onNavigate: (v: View) => void }) {
  const { theme, toggleThemeHandler, lang, setLang } = useApp()

  return (
    <header className="top-navbar">
      <pre className="navbar-ascii" style={{ fontFamily: 'monospace', fontSize: 'clamp(2px, 0.275vw, 5px)', lineHeight: '1.1', margin: 0, whiteSpace: 'pre', letterSpacing: '0.5px' }}>
{" ___       ___       _____ ______           _________  ________  ________  ________  ___  __    _______   ________     \n"}
{"|\\  \\     |\\  \\     |\\   _ \\  _   \\        |\\___   ___\\\\   __  \\|\\   __  \\|\\   ____\\|\\  \\|\\  \\ |\\  ___ \\ |\\   __  \\    \n"}
{"\\ \\  \\    \\ \\  \\    \\ \\  \\\\\\__\\ \\  \\       |\\___ \\  \\_\\ \\  \\|\\  \\ \\  \\|\\  \\ \\  \\___|\\ \\  \\/  /|\\ \\   __/|\\ \\  \\|\\  \\   \n"}
{" \\ \\  \\    \\ \\  \\    \\ \\  \\\\|__| \\  \\           \\ \\  \\ \\ \\   _  _\\ \\   __  \\ \\  \\    \\ \\   ___  \\ \\  \\_|/_\\ \\   _  _\\  \n"}
{"  \\ \\  \\____\\ \\  \\____\\ \\  \\    \\ \\  \\           \\ \\  \\ \\ \\  \\\\  \\\\ \\  \\ \\  \\ \\  \\____\\ \\  \\\\ \\  \\ \\  \\_|\\ \\ \\  \\\\  \\| \n"}
{"   \\ \\_______\\ \\_______\\ \\__\\    \\ \\__\\           \\ \\__\\ \\ \\__\\\\ _\\\\ \\__\\ \\__\\ \\_______\\ \\__\\\\ \\__\\ \\_______\\ \\__\\\\ _\\ \n"}
{"    \\|_______|\\|_______|\\|__|     \\|__|            \\|__|  \\|__|\\|__|\\|__|\\|__|\\|_______|\\|__| \\|__|\\|_______|\\|__|\\|__|"}
</pre>
      <nav className="navbar-nav">
        <button className={`nav-item ${currentView === 'dashboard' ? 'active' : ''}`} onClick={() => onNavigate('dashboard')}>
          📊 {t('Dashboard')}
        </button>
        <button className={`nav-item ${currentView === 'logs' ? 'active' : ''}`} onClick={() => onNavigate('logs')}>
          📜 {t('Request Logs')}
        </button>
        <button className={`nav-item ${currentView === 'settings' ? 'active' : ''}`} onClick={() => onNavigate('settings')}>
          ⚙️ {t('Settings')}
        </button>
      </nav>
      <button
        className="nav-item"
        style={{ marginLeft: 'auto', fontSize: '18px' }}
        onClick={toggleThemeHandler}
        title={theme === 'dark' ? t('Switch to light mode') : t('Switch to dark mode')}
      >
        {theme === 'dark' ? '☀️' : '🌙'}
      </button>
      <button
        className="nav-item"
        style={{ fontSize: '13px', fontWeight: 700, minWidth: '36px', textAlign: 'center' }}
        onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
        title={lang === 'zh' ? '切换到中文' : 'Switch to English'}
      >
        {lang === 'zh' ? '中' : 'EN'}
      </button>
    </header>
  )
}
