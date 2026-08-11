import React, { useState, useEffect, useRef } from 'react'
import { useEngine } from '../../hooks/useEngine'
import './Dashboard.css'

const GESTURE_GUIDE = [
  { emoji: '☝️', label: 'Index Finger', action: 'Move cursor' },
  { emoji: '🤏', label: 'Pinch', action: 'Left click' },
  { emoji: '🤏→', label: 'Pinch + Move', action: 'Drag' },
  { emoji: '↑', label: 'Hand Up', action: 'Scroll up' },
  { emoji: '↓', label: 'Hand Down', action: 'Scroll down' },
  { emoji: '←', label: 'Swipe Left', action: 'Navigate back' },
  { emoji: '→', label: 'Swipe Right', action: 'Navigate forward' },
  { emoji: '🖐️', label: 'Open Palm', action: 'Pause AirOS' },
  { emoji: '👐', label: 'Two Hands', action: 'Keyboard mode' },
]

function MetricBar({ label, value, max, unit, color }: {
  label: string; value: number; max: number; unit: string; color: string
}) {
  const pct = Math.min(100, (value / max) * 100)
  return (
    <div className="metric-bar-row">
      <div className="metric-bar-header">
        <span className="metric-bar-label">{label}</span>
        <span className="metric-bar-value mono-number" style={{ color }}>
          {value.toFixed(1)}{unit}
        </span>
      </div>
      <div className="progress-bar">
        <div
          className="progress-bar-fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  )
}

function LatencyGauge({ ms }: { ms: number }) {
  const color = ms < 60 ? 'var(--accent-green)' : ms < 100 ? 'var(--accent-amber)' : 'var(--accent-red)'
  return (
    <div className="latency-gauge">
      <div className="latency-value" style={{ color }}>
        {ms.toFixed(1)}
      </div>
      <div className="latency-unit">ms</div>
      <div className="latency-label">Latency</div>
    </div>
  )
}

function FPSGauge({ fps }: { fps: number }) {
  const color = fps >= 28 ? 'var(--accent-green)' : fps >= 20 ? 'var(--accent-amber)' : 'var(--accent-red)'
  return (
    <div className="latency-gauge">
      <div className="latency-value" style={{ color }}>
        {fps.toFixed(0)}
      </div>
      <div className="latency-unit">fps</div>
      <div className="latency-label">Camera</div>
    </div>
  )
}

function HandIndicator({ count }: { count: number }) {
  return (
    <div className="hand-indicator">
      {[0, 1].map(i => (
        <div key={i} className={`hand-dot ${i < count ? 'active' : ''}`}>
          🖐
        </div>
      ))}
    </div>
  )
}

function GestureDisplay({ gesture, confidence }: { gesture: string; confidence: number }) {
  const entry = GESTURE_GUIDE.find(g =>
    gesture.toLowerCase().includes(g.label.toLowerCase().split(' ')[0].toLowerCase())
  )
  const emoji = entry?.emoji ?? '—'
  const confPct = Math.round(confidence * 100)

  return (
    <div className="gesture-display">
      <div className="gesture-emoji">{emoji}</div>
      <div className="gesture-info">
        <div className="gesture-name">{gesture.replace(/_/g, ' ')}</div>
        {confidence > 0 && (
          <div className="gesture-confidence">
            <div className="progress-bar" style={{ width: '120px' }}>
              <div
                className="progress-bar-fill"
                style={{
                  width: `${confPct}%`,
                  background: confPct > 80 ? 'var(--accent-green)' : 'var(--accent-amber)'
                }}
              />
            </div>
            <span className="mono-number" style={{ fontSize: '11px' }}>{confPct}%</span>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { telemetry, status, start, stop, pause, resume, calibrate } = useEngine()
  const [fpsHistory, setFpsHistory] = useState<number[]>(Array(60).fill(0))
  const animRef = useRef<number>()

  useEffect(() => {
    if (telemetry.fps.current > 0) {
      setFpsHistory(prev => [...prev.slice(1), telemetry.fps.current])
    }
  }, [telemetry.fps.current])

  const engineRunning = status.state === 'running' || status.state === 'paused'
  const isPaused = status.state === 'paused' || telemetry.state === 'PAUSED'

  const stateColor = {
    running: 'var(--accent-green)',
    paused: 'var(--accent-amber)',
    error: 'var(--accent-red)',
    stopped: 'var(--text-muted)',
    starting: 'var(--accent-blue)',
  }[status.state] || 'var(--text-muted)'

  return (
    <div className="dashboard fade-in">

      {/* ── Hero Status ─────────────────────────────────────── */}
      <div className="dashboard-hero">
        <div className="hero-left">
          <div className="hero-logo">
            <div className="logo-icon">
              <svg viewBox="0 0 32 32" fill="none" width="28" height="28">
                <circle cx="16" cy="16" r="14" stroke="url(#grad)" strokeWidth="2"/>
                <path d="M16 8v8M16 16l5 5" stroke="#63b3ed" strokeWidth="2" strokeLinecap="round"/>
                <circle cx="16" cy="16" r="3" fill="#63b3ed"/>
                <defs>
                  <linearGradient id="grad" x1="0" y1="0" x2="32" y2="32">
                    <stop offset="0%" stopColor="#63b3ed"/>
                    <stop offset="100%" stopColor="#b794f4"/>
                  </linearGradient>
                </defs>
              </svg>
            </div>
            <div>
              <h1 className="hero-title">AirOS</h1>
              <p className="hero-subtitle">Touchless Computing</p>
            </div>
          </div>

          <div className={`status-pill ${status.state}`}>
            {status.state.toUpperCase()}
          </div>
        </div>

        <div className="hero-right">
          <HandIndicator count={telemetry.hands} />
          <div className="hero-gauges">
            <FPSGauge fps={telemetry.fps.avg} />
            <LatencyGauge ms={telemetry.latency.total_ms} />
          </div>
        </div>
      </div>

      {/* ── Mode + Gesture ──────────────────────────────────── */}
      <div className="mode-row">
        <div className="metric-card mode-card">
          <div className="section-title">Mode</div>
          <div className="mode-value" style={{ color: stateColor }}>
            {telemetry.state}
          </div>
        </div>
        <div className="metric-card gesture-card">
          <div className="section-title">Gesture</div>
          <GestureDisplay
            gesture={telemetry.gesture === 'NONE' ? '— none —' : telemetry.gesture}
            confidence={telemetry.confidence}
          />
        </div>
        <div className="metric-card">
          <div className="section-title">Connection</div>
          <div className="connection-status">
            <div className={`conn-dot ${status.connected ? 'connected' : 'disconnected'}`} />
            <span className="conn-label">
              {status.connected ? 'Engine connected' : 'Waiting for engine...'}
            </span>
          </div>
          {status.error && (
            <div className="error-message">{status.error}</div>
          )}
        </div>
        <div className="metric-card context-card">
          <div className="section-title">Context</div>
          <div className="context-row">
            <span className="context-label">Profile</span>
            <span className="context-value">
              <span className={`profile-chip profile-${(telemetry.profile || 'default').toLowerCase()}`}>
                {(telemetry.profile || 'default').replace(/_/g, ' ')}
              </span>
            </span>
          </div>
          <div className="context-row">
            <span className="context-label">App</span>
            <span className="context-value app-name">
              {telemetry.foreground_app ? telemetry.foreground_app : '—'}
            </span>
          </div>
        </div>
      </div>

      {/* ── Performance ─────────────────────────────────────── */}
      <div className="perf-section">
        <div className="section-title">Performance</div>
        <div className="perf-grid">
          <div className="metric-card">
            <div className="perf-row">
              <div className="perf-item">
                <span className="perf-label">FPS avg</span>
                <span className="mono-number">{telemetry.fps.avg.toFixed(1)}</span>
              </div>
              <div className="perf-item">
                <span className="perf-label">FPS min</span>
                <span className="mono-number" style={{ color: telemetry.fps.min < 20 ? 'var(--accent-red)' : 'var(--accent-cyan)' }}>
                  {telemetry.fps.min.toFixed(1)}
                </span>
              </div>
              <div className="perf-item">
                <span className="perf-label">Dropped</span>
                <span className="mono-number" style={{ color: telemetry.fps.dropped > 10 ? 'var(--accent-amber)' : 'var(--accent-cyan)' }}>
                  {telemetry.fps.dropped}
                </span>
              </div>
            </div>
          </div>

          <div className="metric-card">
            <MetricBar
              label="Capture"
              value={telemetry.latency.capture_ms}
              max={33}
              unit="ms"
              color="var(--accent-blue)"
            />
            <MetricBar
              label="Inference"
              value={telemetry.latency.inference_ms}
              max={50}
              unit="ms"
              color="var(--accent-purple)"
            />
            <MetricBar
              label="Gesture"
              value={telemetry.latency.gesture_ms}
              max={10}
              unit="ms"
              color="var(--accent-cyan)"
            />
          </div>

          <div className="metric-card">
            <MetricBar
              label="CPU"
              value={telemetry.system.cpu_percent}
              max={100}
              unit="%"
              color="var(--accent-green)"
            />
            <MetricBar
              label="RAM"
              value={telemetry.system.ram_mb}
              max={500}
              unit="MB"
              color="var(--accent-amber)"
            />
            <div className="perf-item" style={{ marginTop: 8 }}>
              <span className="perf-label">Total latency</span>
              <span className="mono-number" style={{
                color: telemetry.latency.total_ms < 60 ? 'var(--accent-green)' :
                       telemetry.latency.total_ms < 100 ? 'var(--accent-amber)' : 'var(--accent-red)'
              }}>
                {telemetry.latency.total_ms.toFixed(1)}ms
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ── FPS Sparkline ───────────────────────────────────── */}
      <div className="sparkline-section metric-card">
        <div className="section-title">FPS History</div>
        <svg className="sparkline" viewBox="0 0 300 40" preserveAspectRatio="none">
          <polyline
            points={fpsHistory.map((v, i) =>
              `${(i / (fpsHistory.length - 1)) * 300},${40 - Math.min(40, (v / 60) * 40)}`
            ).join(' ')}
            fill="none"
            stroke="url(#sparkGrad)"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
          <defs>
            <linearGradient id="sparkGrad" x1="0" y1="0" x2="300" y2="0" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#4299e1" stopOpacity="0.4"/>
              <stop offset="100%" stopColor="#63b3ed"/>
            </linearGradient>
          </defs>
        </svg>
        <div className="sparkline-labels">
          <span>60s ago</span>
          <span>Target: 30 fps</span>
          <span>now</span>
        </div>
      </div>

      {/* ── Controls ────────────────────────────────────────── */}
      <div className="controls-section">
        {!engineRunning ? (
          <button
            id="btn-start-engine"
            className="btn btn-primary btn-large"
            onClick={start}
            disabled={status.state === 'starting'}
          >
            {status.state === 'starting' ? '⟳ Starting...' : '▶  START AIR OS'}
          </button>
        ) : (
          <div className="control-group">
            {isPaused ? (
              <button id="btn-resume" className="btn btn-primary" onClick={resume}>
                ▶ Resume
              </button>
            ) : (
              <button id="btn-pause" className="btn btn-ghost" onClick={pause}>
                ⏸ Pause
              </button>
            )}
            <button id="btn-calibrate" className="btn btn-ghost" onClick={calibrate}>
              ⊕ Calibrate
            </button>
            <button id="btn-stop" className="btn btn-danger" onClick={stop}>
              ■ TURN OFF AIR OS
            </button>
          </div>
        )}
        <div className="shortcut-hint">Safety shortcut: Ctrl+Alt+A to stop immediately</div>
      </div>

      {/* ── Gesture Guide ───────────────────────────────────── */}
      <div className="gesture-guide-section">
        <div className="section-title">Gesture Reference</div>
        <div className="gesture-guide-grid">
          {GESTURE_GUIDE.map(g => (
            <div key={g.label} className={`gesture-guide-item ${
              telemetry.gesture.toLowerCase().includes(g.label.toLowerCase().split(' ')[0].toLowerCase())
                ? 'highlighted' : ''
            }`}>
              <span className="guide-emoji">{g.emoji}</span>
              <div className="guide-text">
                <span className="guide-label">{g.label}</span>
                <span className="guide-action">{g.action}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}
