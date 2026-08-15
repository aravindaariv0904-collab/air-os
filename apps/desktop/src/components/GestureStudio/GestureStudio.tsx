import React, { useState } from 'react'
import { useEngine } from '../../hooks/useEngine'
import './GestureStudio.css'

export default function GestureStudio() {
  const { telemetry, templates, recordGestureStart, recordGestureFinish, deleteGesture } = useEngine()
  const [recording, setRecording] = useState(false)
  const [gestureName, setGestureName] = useState('')
  const [selectedAction, setSelectedAction] = useState('left_click')

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

  const handleToggleRecording = () => {
    if (!recording) {
      if (!gestureName.trim()) return
      setRecording(true)
      recordGestureStart()
    } else {
      setRecording(false)
      recordGestureFinish(gestureName.trim())
      setGestureName('')
    }
  }

  const handleDelete = (id: string) => {
    deleteGesture(id)
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
                  <span className="rec-text">Capturing Real Hand Landmark Samples...</span>
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
            onClick={handleToggleRecording}
            disabled={!recording && !gestureName.trim()}
          >
            {recording ? '⏹ Finish & Save Recording' : '⏺ Start Real Landmark Recording'}
          </button>
        </div>

        {/* Saved Custom Gestures */}
        <div className="studio-card list-card">
          <div className="card-header">
            <span className="card-icon">⚡</span>
            <h3>Custom Gesture Templates ({templates ? templates.length : 0})</h3>
          </div>

          <div className="custom-gestures-list">
            {!templates || templates.length === 0 ? (
              <div className="empty-state">
                <span>No custom gestures recorded yet.</span>
                <span>Use the recording panel to capture real hand landmarks.</span>
              </div>
            ) : (
              templates.map((g: any) => (
                <div key={g.id || g.name} className="custom-gesture-item">
                  <div className="g-item-left">
                    <div className="g-item-name">{g.name}</div>
                    <div className="g-item-meta">
                      <span className="meta-tag">{g.num_samples || 90} frames</span>
                      <span className="meta-tag quality">{g.threshold ? (1.0 - g.threshold).toFixed(2) : '0.85'} threshold</span>
                    </div>
                  </div>

                  <div className="g-item-right">
                    <span className="action-chip">{g.action || 'left_click'}</span>
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
