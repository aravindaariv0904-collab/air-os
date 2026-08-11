import { useState } from 'react'
import Dashboard from './components/Dashboard/Dashboard'
import { useEngine } from './hooks/useEngine'
import './App.css'

type Page = 'dashboard' | 'gestures' | 'calibration' | 'settings'

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')

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
          {page === 'gestures' && <GesturePage />}
          {page === 'calibration' && <CalibrationPage />}
          {page === 'settings' && <SettingsPage />}
        </main>
      </div>
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

function GesturePage() {
  const { profiles, setProfile, telemetry } = useEngine()
  const gestures = [
    { emoji: '☝️', name: 'Index Pointer', desc: 'Move cursor — point with index finger', action: 'cursor_move', enabled: true },
    { emoji: '🤏', name: 'Pinch Click', desc: 'Touch index to thumb → left click', action: 'left_click', enabled: true },
    { emoji: '🤏', name: 'Pinch Drag', desc: 'Hold pinch and move → drag', action: 'drag', enabled: true },
    { emoji: '↑', name: 'Scroll Up', desc: 'Move hand up → scroll up', action: 'scroll_up', enabled: true },
    { emoji: '↓', name: 'Scroll Down', desc: 'Move hand down → scroll down', action: 'scroll_down', enabled: true },
    { emoji: '←', name: 'Swipe Left', desc: 'Fast left swipe → navigate back', action: 'navigate_back', enabled: true },
    { emoji: '→', name: 'Swipe Right', desc: 'Fast right swipe → navigate forward', action: 'navigate_forward', enabled: true },
    { emoji: '🖐️', name: 'Open Palm', desc: 'Hold palm open → pause AirOS', action: 'pause', enabled: true },
    { emoji: '👐', name: 'Two Hands', desc: 'Both hands up → keyboard mode', action: 'enter_keyboard', enabled: true },
  ]

  const activeProfile = telemetry.profile || 'default'

  return (
    <div className="page-content fade-in">
      <div className="page-header">
        <h2 className="page-title">Gesture Library</h2>
        <p className="page-desc">All active gestures and their assigned actions</p>
      </div>

      {/* ── App Profiles ───────────────────────────────────── */}
      {profiles.length > 1 && (
        <div className="profile-section">
          <h3 className="settings-section-title">Active Profile</h3>
          <p className="profile-hint">
            Profiles auto-activate based on the foreground app. You can also switch manually.
          </p>
          <div className="profile-tabs">
            {profiles.map(p => (
              <button
                key={p.id}
                id={`profile-tab-${p.id}`}
                className={`profile-tab ${p.id === activeProfile ? 'active' : ''}`}
                onClick={() => setProfile(p.id)}
                title={p.app_matchers?.join(', ') || 'Default profile'}
              >
                <span className="profile-tab-name">{p.name}</span>
                {p.app_matchers && p.app_matchers.length > 0 && (
                  <span className="profile-tab-apps">{p.app_matchers.join(', ')}</span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="gesture-list">
        {gestures.map(g => (
          <div key={g.name} className="gesture-list-item">
            <span className="gesture-list-emoji">{g.emoji}</span>
            <div className="gesture-list-info">
              <div className="gesture-list-name">{g.name}</div>
              <div className="gesture-list-desc">{g.desc}</div>
            </div>
            <div className="gesture-list-action">
              <span className="action-chip">{g.action}</span>
            </div>
            <div className={`toggle ${g.enabled ? 'on' : 'off'}`}>
              <div className="toggle-thumb" />
            </div>
          </div>
        ))}
      </div>
      <div className="page-note">
        Custom gesture recording is available via the Gesture Studio CLI
        (python scripts/gesture_studio_cli.py record "Name").
      </div>
    </div>
  )
}

function CalibrationPage() {
  return (
    <div className="page-content fade-in">
      <div className="page-header">
        <h2 className="page-title">Calibration</h2>
        <p className="page-desc">Tune AirOS to your physical setup and hand size</p>
      </div>
      <div className="calib-steps">
        {[
          { step: 1, title: 'Camera Check', desc: 'Verify camera is detected and working', done: true },
          { step: 2, title: 'Hand Detection', desc: 'Ensure hand is reliably tracked', done: false },
          { step: 3, title: 'Interaction Region', desc: 'Define your comfortable movement range', done: false },
          { step: 4, title: 'Pinch Threshold', desc: 'Calibrate pinch sensitivity to your hand', done: false },
          { step: 5, title: 'Cursor Sensitivity', desc: 'Set cursor speed and smoothing', done: false },
        ].map(s => (
          <div key={s.step} className={`calib-step ${s.done ? 'done' : ''}`}>
            <div className="calib-step-num">{s.done ? '✓' : s.step}</div>
            <div className="calib-step-info">
              <div className="calib-step-title">{s.title}</div>
              <div className="calib-step-desc">{s.desc}</div>
            </div>
          </div>
        ))}
      </div>
      <button
        id="btn-start-calibration"
        className="btn btn-primary"
        onClick={() => window.airos?.calibrateEngine()}
        style={{ marginTop: 24 }}
      >
        ⊕ Start Calibration
      </button>
    </div>
  )
}

function SettingsPage() {
  return (
    <div className="page-content fade-in">
      <div className="page-header">
        <h2 className="page-title">Settings</h2>
        <p className="page-desc">Configure AirOS behavior and performance</p>
      </div>
      <div className="settings-section">
        <h3 className="settings-section-title">Cursor</h3>
        <SettingSlider id="setting-sensitivity" label="Sensitivity" min={0.5} max={2.0} step={0.1} defaultValue={1.0} />
        <SettingSlider id="setting-smoothing" label="Smoothing" min={0.5} max={3.0} step={0.1} defaultValue={1.2} />
        <SettingSlider id="setting-dead-zone" label="Dead Zone" min={0} max={0.03} step={0.001} defaultValue={0.008} />
      </div>
      <div className="settings-section">
        <h3 className="settings-section-title">Gestures</h3>
        <SettingSlider id="setting-scroll-speed" label="Scroll Speed" min={1} max={10} step={1} defaultValue={3} />
        <SettingSlider id="setting-pinch-threshold" label="Pinch Sensitivity" min={0.15} max={0.45} step={0.01} defaultValue={0.30} />
      </div>
      <div className="settings-section">
        <h3 className="settings-section-title">System</h3>
        <SettingToggle id="setting-start-minimized" label="Start minimized to tray" defaultValue={false} />
        <SettingToggle id="setting-start-engine" label="Start engine on launch" defaultValue={true} />
        <SettingToggle id="setting-debug-overlay" label="Show debug overlay" defaultValue={false} />
      </div>
    </div>
  )
}

function SettingSlider({ id, label, min, max, step, defaultValue }: {
  id: string; label: string; min: number; max: number; step: number; defaultValue: number
}) {
  const [value, setValue] = useState(defaultValue)
  return (
    <div className="setting-row">
      <label className="setting-label" htmlFor={id}>{label}</label>
      <div className="setting-control">
        <input
          id={id}
          type="range"
          min={min} max={max} step={step}
          value={value}
          onChange={e => setValue(parseFloat(e.target.value))}
          className="slider"
        />
        <span className="setting-value mono-number">{value.toFixed(2)}</span>
      </div>
    </div>
  )
}

function SettingToggle({ id, label, defaultValue }: {
  id: string; label: string; defaultValue: boolean
}) {
  const [value, setValue] = useState(defaultValue)
  return (
    <div className="setting-row">
      <label className="setting-label" htmlFor={id}>{label}</label>
      <button
        id={id}
        className={`toggle ${value ? 'on' : 'off'}`}
        onClick={() => setValue(v => !v)}
        role="switch"
        aria-checked={value}
      >
        <div className="toggle-thumb" />
      </button>
    </div>
  )
}
