import React from 'react'
import './KeyboardOverlay.css'

interface KeyLayoutItem {
  label: string
  x: number
  y: number
  w: number
  h: number
  action: string
}

interface KeyboardState {
  active: boolean
  hovered_key: string | null
  shift_active: boolean
  typed_text: string
  layout: KeyLayoutItem[]
}

interface Props {
  keyboardState?: KeyboardState
  onClose?: () => void
}

export default function KeyboardOverlay({ keyboardState, onClose }: Props) {
  if (!keyboardState || !keyboardState.active) return null

  return (
    <div className="keyboard-overlay-backdrop fade-in">
      <div className="keyboard-overlay-container">
        {/* Preview Header */}
        <div className="keyboard-header">
          <div className="keyboard-title">
            <span>👐 Virtual Keyboard (Air-Tap Active)</span>
          </div>
          <div className="typed-preview-box">
            <span className="typed-text">{keyboardState.typed_text || 'Point & Air-tap keys below...'}</span>
            <span className="cursor-blink">|</span>
          </div>
        </div>

        {/* Keyboard Canvas / Keys Grid */}
        <div className="keyboard-canvas">
          {keyboardState.layout.map((key) => {
            const isHovered = keyboardState.hovered_key === key.label
            const isShift = key.action === 'shift' && keyboardState.shift_active

            return (
              <div
                key={key.label}
                className={`key-cap ${isHovered ? 'hovered' : ''} ${isShift ? 'shift-active' : ''}`}
                style={{
                  left: `${key.x * 100}%`,
                  top: `${(key.y - 0.55) * (1 / 0.43) * 100}%`,
                  width: `${key.w * 100}%`,
                  height: `${key.h * (1 / 0.43) * 100}%`,
                }}
              >
                <span className="key-label">{key.label}</span>
              </div>
            )
          })}
        </div>

        <div className="keyboard-footer">
          <span className="keyboard-hint">Deliberate short downward air-tap motion triggers key</span>
          {onClose && (
            <button className="btn btn-ghost btn-sm" onClick={onClose}>
              Close Keyboard (Esc)
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
