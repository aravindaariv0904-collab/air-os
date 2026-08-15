import React, { useState, useEffect } from 'react'
import { useEngine } from '../../hooks/useEngine'
import './Settings.css'

export default function Settings() {
  const { settings, updateSettings } = useEngine()

  const cursor = settings?.cursor || {}
  const gestures = settings?.gestures || {}
  const system = settings?.system || {}

  const [sensitivity, setSensitivity] = useState(cursor.sensitivity || 1.0)
  const [smoothing, setSmoothing] = useState(cursor.smoothing_min_cutoff || 1.2)
  const [deadZone, setDeadZone] = useState(cursor.dead_zone || 0.008)
  const [scrollSpeed, setScrollSpeed] = useState(gestures.scroll_speed || 3)
  const [pinchThreshold, setPinchThreshold] = useState(gestures.pinch_threshold || 0.30)
  const [startMinimized, setStartMinimized] = useState(system.start_minimized || false)
  const [startOnBoot, setStartOnBoot] = useState(system.start_engine_on_launch || true)
  const [debugOverlay, setDebugOverlay] = useState(system.debug_logging || false)

  useEffect(() => {
    if (settings) {
      if (settings.cursor) {
        setSensitivity(settings.cursor.sensitivity || 1.0)
        setSmoothing(settings.cursor.smoothing_min_cutoff || 1.2)
        setDeadZone(settings.cursor.dead_zone || 0.008)
      }
      if (settings.gestures) {
        setScrollSpeed(settings.gestures.scroll_speed || 3)
        setPinchThreshold(settings.gestures.pinch_threshold || 0.30)
      }
      if (settings.system) {
        setStartMinimized(settings.system.start_minimized || false)
        setStartOnBoot(settings.system.start_engine_on_launch || true)
        setDebugOverlay(settings.system.debug_logging || false)
      }
    }
  }, [settings])

  const handleSensitivityChange = (val: number) => {
    setSensitivity(val)
    updateSettings({ cursor: { sensitivity: val } })
  }

  const handleSmoothingChange = (val: number) => {
    setSmoothing(val)
    updateSettings({ cursor: { smoothing_min_cutoff: val } })
  }

  const handleDeadZoneChange = (val: number) => {
    setDeadZone(val)
    updateSettings({ cursor: { dead_zone: val } })
  }

  const handleScrollSpeedChange = (val: number) => {
    setScrollSpeed(val)
    updateSettings({ gestures: { scroll_speed: val } })
  }

  const handlePinchThresholdChange = (val: number) => {
    setPinchThreshold(val)
    updateSettings({ gestures: { pinch_threshold: val } })
  }

  const handleStartMinimizedToggle = (val: boolean) => {
    setStartMinimized(val)
    updateSettings({ system: { start_minimized: val } })
  }

  const handleStartOnBootToggle = (val: boolean) => {
    setStartOnBoot(val)
    updateSettings({ system: { start_engine_on_launch: val } })
  }

  const handleDebugToggle = (val: boolean) => {
    setDebugOverlay(val)
    updateSettings({ system: { debug_logging: val } })
  }

  return (
    <div className="settings-page fade-in">
      <div className="page-header">
        <div>
          <h2 className="page-title">Settings & Preferences</h2>
          <p className="page-desc">Fine-tune motion dynamics, input filters, and system persistence</p>
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
            onChange={handleSensitivityChange}
          />
          <SettingSlider
            id="setting-smoothing"
            label="OneEuro Filter Cutoff"
            desc="Lower cutoff = smoother low-speed tracking; higher = less lag"
            min={0.5} max={3.0} step={0.1}
            value={smoothing}
            onChange={handleSmoothingChange}
          />
          <SettingSlider
            id="setting-dead-zone"
            label="Tremor Dead Zone"
            desc="Suppress micro-tremor when hand is still"
            min={0.0} max={0.02} step={0.001}
            value={deadZone}
            onChange={handleDeadZoneChange}
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
            onChange={handleScrollSpeedChange}
          />
          <SettingSlider
            id="setting-pinch-threshold"
            label="Pinch Hysteresis Threshold"
            desc="Normalized index-to-thumb tip pinch trigger distance"
            min={0.15} max={0.45} step={0.01}
            value={pinchThreshold}
            onChange={handlePinchThresholdChange}
          />
        </div>

        <div className="settings-card">
          <h3 className="section-heading">⚙️ Application & Startup</h3>
          <SettingToggle
            id="setting-start-minimized"
            label="Start minimized to Windows System Tray"
            value={startMinimized}
            onChange={handleStartMinimizedToggle}
          />
          <SettingToggle
            id="setting-start-boot"
            label="Launch AirOS engine automatically at startup"
            value={startOnBoot}
            onChange={handleStartOnBootToggle}
          />
          <SettingToggle
            id="setting-debug"
            label="Enable real-time latency & tracking debug logs"
            value={debugOverlay}
            onChange={handleDebugToggle}
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
