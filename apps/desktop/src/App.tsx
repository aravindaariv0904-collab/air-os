import { useState } from 'react'
import Dashboard from './components/Dashboard/Dashboard'
import GestureStudio from './components/GestureStudio/GestureStudio'
import Calibration from './components/Calibration/Calibration'
import Settings from './components/Settings/Settings'
import KeyboardOverlay from './components/KeyboardOverlay/KeyboardOverlay'
import { useEngine } from './hooks/useEngine'
import './App.css'

type Page = 'dashboard' | 'gestures' | 'calibration' | 'settings'

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const { telemetry } = useEngine()

  return (
    <div className="app-shell">
      {/* ── Custom Title Bar ──────────────────────────────── */}
      <div className="title-bar">
        <div className="title-bar-left">
          <span className="title-bar-logo">⬤</span>
          <span className="title-bar-name">AirOS Control Center</span>
        </div>
        <div className="title-bar-drag" style={{ flex: 1, WebkitAppRegion: 'drag' } as any} />
        <div className="title-bar-controls">
          <button
            className="titlebar-btn minimize"
            onClick={() => window.airos?.minimize()}
            aria-label="Minimize"
          >—</button>
          <button
            className="titlebar-btn maximize"
            onClick={() => window.airos?.maximize()}
            aria-label="Maximize"
          >⤢</button>
          <button
            className="titlebar-btn close"
            onClick={() => window.airos?.close()}
            aria-label="Close"
          >✕</button>
        </div>
      </div>

      {/* ── Sidebar Navigation ────────────────────────────── */}
      <div className="app-body">
        <nav className="sidebar">
          <div className="sidebar-logo">
            <svg viewBox="0 0 32 32" fill="none" width="32" height="32">
              <circle cx="16" cy="16" r="14" stroke="url(#sideGrad)" strokeWidth="1.5"/>
              <path d="M16 9v7M16 16l4 4" stroke="#63b3ed" strokeWidth="2" strokeLinecap="round"/>
              <circle cx="16" cy="16" r="2.5" fill="#63b3ed"/>
              <defs>
                <linearGradient id="sideGrad" x1="0" y1="0" x2="32" y2="32">
                  <stop offset="0%" stopColor="#63b3ed"/>
                  <stop offset="100%" stopColor="#b794f4"/>
                </linearGradient>
              </defs>
            </svg>
          </div>

          <NavItem id="nav-dashboard" icon="◉" label="Dashboard" active={page === 'dashboard'} onClick={() => setPage('dashboard')} />
          <NavItem id="nav-gestures" icon="✋" label="Gestures" active={page === 'gestures'} onClick={() => setPage('gestures')} />
          <NavItem id="nav-calibration" icon="⊕" label="Calibrate" active={page === 'calibration'} onClick={() => setPage('calibration')} />
          <NavItem id="nav-settings" icon="⚙" label="Settings" active={page === 'settings'} onClick={() => setPage('settings')} />

          <div className="sidebar-footer">
            <div className="version-tag">v0.1.0</div>
          </div>
        </nav>

        {/* ── Main Content ──────────────────────────────────── */}
        <main className="main-content">
          {page === 'dashboard' && <Dashboard />}
          {page === 'gestures' && <GestureStudio />}
          {page === 'calibration' && <Calibration />}
          {page === 'settings' && <Settings />}
        </main>
      </div>

      {/* ── Virtual Keyboard Overlay ──────────────────────── */}
      <KeyboardOverlay keyboardState={telemetry.keyboard_state} />
    </div>
  )
}

function NavItem({ id, icon, label, active, onClick }: {
  id: string; icon: string; label: string; active: boolean; onClick: () => void
}) {
  return (
    <button id={id} className={`nav-item ${active ? 'active' : ''}`} onClick={onClick}>
      <span className="nav-icon">{icon}</span>
      <span className="nav-label">{label}</span>
    </button>
  )
}
