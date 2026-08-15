import React, { useState } from 'react'
import { useEngine } from '../../hooks/useEngine'
import './GestureStudio.css'

interface CustomGesture {
  id: string
  name: string
  action: string
  samples: number
  quality: number
  date: string
}

export default function GestureStudio() {
  const { telemetry } = useEngine()
  const [recording, setRecording] = useState(false)
  const [gestureName, setGestureName] = useState('')
  const [selectedAction, setSelectedAction] = useState('left_click')
  const [customGestures, setCustomGestures] = useState<CustomGesture[]>([
    { id: 'g1', name: 'Peace Sign', action: 'win_minimize', samples: 10, quality: 98, date: '2026-08-11' },
    { id: 'g2', name: 'Thumbs Up', action: 'media_play_pause', samples: 10, quality: 95, date: '2026-08-11' }
  ])

  const actionOptions = [
    { label: 'Left Click', value: 'left_click' },
    { label: 'Right Click', value: 'right_click' },
    { label: 'Double Click', value: 'double_click' },
    { label: 'Scroll Up', value: 'scroll_up' },
    { label: 'Scroll Down', value: 'scroll_down' },
    { label: 'Navigate Back', value: 'navigate_back' },
    { label: 'Navigate Forward', value: 'navigate_forward' },
    { label: 'Minimize Windows', value: 'win_minimize' },
    { label: 'Play / Pause Media', value: 'media_play_pause' },
    { label: 'Volume Up', value: 'volume_up' },
    { label: 'Volume Down', value: 'volume_down' },
  ]

  const handleStartRecording = () => {
    if (!gestureName.trim()) return
    setRecording(true)
    // Simulate multi-pass recording process (10 samples)
    setTimeout(() => {
      setRecording(false)
      const newG: CustomGesture = {
        id: `g_${Date.now()}`,
        name: gestureName.trim(),
        action: selectedAction,
        samples: 10,
        quality: 96,
        date: new Date().toISOString().split('T')[0]
      }
      setCustomGestures(prev => [...prev, newG])
      setGestureName('')
    }, 3000)
  }

  const handleDelete = (id: string) => {
    setCustomGestures(prev => prev.filter(g => g.id !== id))
  }

  return (
    <div className="gesture-studio fade-in">
      <div className="page-header">
        <div>
          <h2 className="page-title">Gesture Studio</h2>
          <p className="page-desc">Record, train, and map personalized custom hand gestures</p>
        </div>
        <div className="studio-badge">DTW Landmark Matcher v1.0</div>
      </div>

      <div className="studio-grid">
        {/* Recording Panel */}
        <div className="studio-card record-card">
          <div className="card-header">
            <span className="card-icon">🎥</span>
            <h3>Record Custom Gesture</h3>
          </div>

          <div className="form-group">
            <label className="form-label">Gesture Name</label>
            <input
              type="text"
              className="studio-input"
              placeholder="e.g., Circle Wave, Fist Pump"
              value={gestureName}
              onChange={e => setGestureName(e.target.value)}
              disabled={recording}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Triggered Action</label>
            <select
              className="studio-select"
              value={selectedAction}
              onChange={e => setSelectedAction(e.target.value)}
              disabled={recording}
            >
              {actionOptions.map(opt => (
                <option key={opt.value} value={opt.value}>
                  {opt.label} ({opt.value})
                </option>
              ))}
            </select>
          </div>

          <div className="recording-preview">
            <div className={`preview-box ${recording ? 'recording' : ''}`}>
              {recording ? (
                <div className="recording-animation">
                  <div className="pulse-ring" />
                  <span className="rec-text">Recording 10 Landmarks Samples...</span>
                  <span className="rec-subtext">Perform gesture naturally in front of camera</span>
                </div>
              ) : (
                <div className="idle-preview">
                  <span className="idle-icon">✋</span>
                  <span>Hand Tracking: {telemetry.hands > 0 ? 'ACTIVE' : 'READY'}</span>
                </div>
              )}
            </div>
          </div>

          <button
            className={`btn btn-large ${recording ? 'btn-danger' : 'btn-primary'}`}
            onClick={handleStartRecording}
            disabled={!gestureName.trim() || recording}
          >
            {recording ? 'Recording in progress...' : '⏺ Start 3s Recording'}
          </button>
        </div>

        {/* Saved Custom Gestures */}
        <div className="studio-card list-card">
          <div className="card-header">
            <span className="card-icon">⚡</span>
            <h3>Custom Gesture Templates ({customGestures.length})</h3>
          </div>

          <div className="custom-gestures-list">
            {customGestures.length === 0 ? (
              <div className="empty-state">
                <span>No custom gestures recorded yet.</span>
                <span>Use the recording panel to create your first custom gesture.</span>
              </div>
            ) : (
              customGestures.map(g => (
                <div key={g.id} className="custom-gesture-item">
                  <div className="g-item-left">
                    <div className="g-item-name">{g.name}</div>
                    <div className="g-item-meta">
                      <span className="meta-tag">{g.samples} samples</span>
                      <span className="meta-tag quality">{g.quality}% match score</span>
                      <span className="meta-date">{g.date}</span>
                    </div>
                  </div>

                  <div className="g-item-right">
                    <span className="action-chip">{g.action}</span>
                    <button
                      className="btn-icon-danger"
                      onClick={() => handleDelete(g.id)}
                      title="Delete gesture"
                    >
                      🗑
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
