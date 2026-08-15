import React, { useState } from 'react'
import './Settings.css'

export default function Settings() {
  const [sensitivity, setSensitivity] = useState(1.0)
  const [smoothing, setSmoothing] = useState(1.2)
  const [deadZone, setDeadZone] = useState(0.008)
  const [scrollSpeed, setScrollSpeed] = useState(3)
  const [pinchThreshold, setPinchThreshold] = useState(0.30)
  const [startMinimized, setStartMinimized] = useState(false)
  const [startOnBoot, setStartOnBoot] = useState(true)
  const [debugOverlay, setDebugOverlay] = useState(false)

  return (
    <div className="settings-page fade-in">
      <div className="page-header">
        <div>
          <h2 className="page-title">Settings & Preferences</h2>
          <p className="page-desc">Fine-tune motion dynamics, input filters, and system startup behavior</p>
        </div>
      </div>

      <div className="settings-grid">
        <div className="settings-card">
          <h3 className="section-heading">🎯 Cursor Engine Dynamics</h3>
          <SettingSlider
            id="setting-sensitivity"
            label="Gain Sensitivity"
            desc="Cursor speed gain relative to hand motion center"
            min={0.5} max={2.5} step={0.1}
            value={sensitivity}
            onChange={setSensitivity}
          />
          <SettingSlider
            id="setting-smoothing"
            label="OneEuro Filter Cutoff"
            desc="Lower cutoff = smoother low-speed tracking; higher = less lag"
            min={0.5} max={3.0} step={0.1}
            value={smoothing}
            onChange={setSmoothing}
          />
          <SettingSlider
            id="setting-dead-zone"
            label="Tremor Dead Zone"
            desc="Suppress micro-tremor when hand is still"
            min={0.0} max={0.02} step={0.001}
            value={deadZone}
            onChange={setDeadZone}
          />
        </div>

        <div className="settings-card">
          <h3 className="section-heading">✋ Gesture Thresholds</h3>
          <SettingSlider
            id="setting-scroll-speed"
            label="Scroll Wheel Speed"
            desc="Lines per scroll notch gesture update"
            min={1} max={10} step={1}
            value={scrollSpeed}
            onChange={setScrollSpeed}
          />
          <SettingSlider
            id="setting-pinch-threshold"
            label="Pinch Hysteresis Threshold"
            desc="Normalized index-to-thumb tip pinch trigger distance"
            min={0.15} max={0.45} step={0.01}
            value={pinchThreshold}
            onChange={setPinchThreshold}
          />
        </div>

        <div className="settings-card">
          <h3 className="section-heading">⚙️ Application & Startup</h3>
          <SettingToggle
            id="setting-start-minimized"
            label="Start minimized to Windows System Tray"
            value={startMinimized}
            onChange={setStartMinimized}
          />
          <SettingToggle
            id="setting-start-boot"
            label="Launch AirOS engine automatically at startup"
            value={startOnBoot}
            onChange={setStartOnBoot}
          />
          <SettingToggle
            id="setting-debug"
            label="Enable real-time latency & tracking debug logs"
            value={debugOverlay}
            onChange={setDebugOverlay}
          />
        </div>
      </div>
    </div>
  )
}

function SettingSlider({ id, label, desc, min, max, step, value, onChange }: {
  id: string; label: string; desc: string; min: number; max: number; step: number; value: number; onChange: (v: number) => void
}) {
  return (
    <div className="setting-row">
      <div className="setting-info">
        <label className="setting-label" htmlFor={id}>{label}</label>
        <span className="setting-desc">{desc}</span>
      </div>
      <div className="setting-control">
        <input
          id={id}
          type="range"
          min={min} max={max} step={step}
          value={value}
          onChange={e => onChange(parseFloat(e.target.value))}
          className="slider"
        />
        <span className="setting-value mono-number">{value.toFixed(2)}</span>
      </div>
    </div>
  )
}

function SettingToggle({ id, label, value, onChange }: {
  id: string; label: string; value: boolean; onChange: (v: boolean) => void
}) {
  return (
    <div className="setting-row">
      <label className="setting-label" htmlFor={id}>{label}</label>
      <button
        id={id}
        className={`toggle ${value ? 'on' : 'off'}`}
        onClick={() => onChange(!value)}
        role="switch"
        aria-checked={value}
      >
        <div className="toggle-thumb" />
      </button>
    </div>
  )
}
