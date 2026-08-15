import React, { useState, useEffect } from 'react'
import { useEngine } from '../../hooks/useEngine'
import './Settings.css'

export default function Settings() {
  const { settings, updateSettings } = useEngine()

  const cursor = settings?.cursor || {}
  const gestures = settings?.gestures || {}
  const system = settings?.system || {}
  const eyes = settings?.eyes || {}
  const voice = settings?.voice || {}

  const [sensitivity, setSensitivity] = useState(cursor.sensitivity || 1.0)
  const [smoothing, setSmoothing] = useState(cursor.smoothing_min_cutoff || 1.2)
  const [deadZone, setDeadZone] = useState(cursor.dead_zone || 0.008)
  const [scrollSpeed, setScrollSpeed] = useState(gestures.scroll_speed || 3)
  const [pinchThreshold, setPinchThreshold] = useState(gestures.pinch_threshold || 0.30)
  const [startMinimized, setStartMinimized] = useState(system.start_minimized || false)
  const [startOnBoot, setStartOnBoot] = useState(system.start_engine_on_launch || true)
  const [debugOverlay, setDebugOverlay] = useState(system.debug_logging || false)
  const [eyesEnabled, setEyesEnabled] = useState(eyes.enabled !== false)
  const [tripleBlinkAction, setTripleBlinkAction] = useState(eyes.triple_blink_action || 'screenshot')
  const [earThreshold, setEarThreshold] = useState(eyes.ear_threshold || 0.21)
  const [voiceEnabled, setVoiceEnabled] = useState(voice.enabled || false)
  const [wakeWord, setWakeWord] = useState(voice.wake_word || 'jarvis')
  const [ttsEnabled, setTtsEnabled] = useState(voice.tts_enabled !== false)
  const [voiceTimeout, setVoiceTimeout] = useState(voice.command_timeout_ms || 7000)

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
      if (settings.eyes) {
        setEyesEnabled(settings.eyes.enabled !== false)
        setTripleBlinkAction(settings.eyes.triple_blink_action || 'screenshot')
        setEarThreshold(settings.eyes.ear_threshold || 0.21)
      }
      if (settings.voice) {
        setVoiceEnabled(settings.voice.enabled || false)
        setWakeWord(settings.voice.wake_word || 'jarvis')
        setTtsEnabled(settings.voice.tts_enabled !== false)
        setVoiceTimeout(settings.voice.command_timeout_ms || 7000)
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

  const handleEyesEnabledToggle = (val: boolean) => {
    setEyesEnabled(val)
    updateSettings({ eyes: { enabled: val } })
  }

  const handleTripleBlinkAction = (val: string) => {
    setTripleBlinkAction(val)
    updateSettings({ eyes: { triple_blink_action: val } })
  }

  const handleEarThreshold = (val: number) => {
    setEarThreshold(val)
    updateSettings({ eyes: { ear_threshold: val } })
  }

  const handleVoiceEnabledToggle = (val: boolean) => {
    setVoiceEnabled(val)
    updateSettings({ voice: { enabled: val } })
  }

  const handleWakeWord = (val: string) => {
    setWakeWord(val)
    updateSettings({ voice: { wake_word: val } })
  }

  const handleTtsToggle = (val: boolean) => {
    setTtsEnabled(val)
    updateSettings({ voice: { tts_enabled: val } })
  }

  const handleVoiceTimeout = (val: number) => {
    setVoiceTimeout(val)
    updateSettings({ voice: { command_timeout_ms: val } })
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

        <div className="settings-card">
          <h3 className="section-heading">👁️ Eyes & Blink Gestures</h3>
          <SettingToggle
            id="setting-eyes-enabled"
            label="Enable eye-tracking (triple-blink commands)"
            value={eyesEnabled}
            onChange={handleEyesEnabledToggle}
          />
          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label" htmlFor="setting-blink-action">Triple-Blink Action</label>
              <span className="setting-desc">Deliberate triple blink performs this action</span>
            </div>
            <select
              id="setting-blink-action"
              className="setting-select"
              value={tripleBlinkAction}
              onChange={e => handleTripleBlinkAction(e.target.value)}
            >
              <option value="screenshot">Screenshot (active monitor)</option>
              <option value="volume_mute">Mute volume</option>
              <option value="volume_unmute">Unmute volume</option>
              <option value="minimize">Minimize window</option>
              <option value="maximize">Maximize window</option>
              <option value="close_window">Close window</option>
              <option value="pause">Pause gestures</option>
              <option value="resume">Resume gestures</option>
            </select>
          </div>
          <SettingSlider
            id="setting-ear-threshold"
            label="Eye-Closed Threshold (EAR)"
            desc="Lower = eyes must be more closed to count as a blink"
            min={0.10} max={0.35} step={0.01}
            value={earThreshold}
            onChange={handleEarThreshold}
          />
        </div>

        <div className="settings-card">
          <h3 className="section-heading">🎙️ Voice Assistant (offline)</h3>
          <SettingToggle
            id="setting-voice-enabled"
            label="Enable local voice assistant"
            value={voiceEnabled}
            onChange={handleVoiceEnabledToggle}
          />
          <div className="setting-row">
            <div className="setting-info">
              <label className="setting-label" htmlFor="setting-wake-word">Wake Word</label>
              <span className="setting-desc">Say this word, then your command</span>
            </div>
            <input
              id="setting-wake-word"
              className="setting-text"
              type="text"
              value={wakeWord}
              onChange={e => handleWakeWord(e.target.value)}
            />
          </div>
          <SettingToggle
            id="setting-tts"
            label="Voice responses (text-to-speech)"
            value={ttsEnabled}
            onChange={handleTtsToggle}
          />
          <SettingSlider
            id="setting-voice-timeout"
            label="Command Capture Timeout"
            desc="Max time to listen for a command after the wake word"
            min={2000} max={15000} step={500}
            value={voiceTimeout}
            onChange={handleVoiceTimeout}
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
