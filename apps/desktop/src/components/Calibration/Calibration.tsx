import React from 'react'
import { useEngine } from '../../hooks/useEngine'
import './Calibration.css'

export default function Calibration() {
  const { telemetry, calibrate } = useEngine()

  const calibStatus = telemetry.calibration || {}
  const isCalibrating = calibStatus.step_name && calibStatus.step_name !== 'IDLE' && calibStatus.step_name !== 'COMPLETE'
  const stepName = calibStatus.step_name || 'IDLE'
  const isCalibrated = calibStatus.calibrated || false

  const steps = [
    { name: 'CHECK_CAMERA', title: 'Camera Check', desc: 'Verify camera feed and resolution' },
    { name: 'POSITION', title: 'Hand Positioning', desc: 'Sit at comfortable distance (50-80cm)' },
    { name: 'DETECT_HAND', title: 'Hand Detection', desc: 'Raise primary hand in front of camera' },
    { name: 'SWEEP_BOUNDS', title: 'Interaction Bounds', desc: 'Move hand to extreme corners of your range' },
    { name: 'PINCH_SAMPLES', title: 'Pinch Calibration', desc: 'Pinch index and thumb 3 times' },
    { name: 'COMPLETE', title: 'Complete', desc: 'Profile saved to %APPDATA%/AirOS' },
  ]

  const getCurrentStepIndex = () => {
    const idx = steps.findIndex(s => s.name === stepName)
    return idx >= 0 ? idx + 1 : (isCalibrated ? 6 : 1)
  }

  const activeStepIdx = getCurrentStepIndex()

  const handleStartGuided = () => {
    calibrate()
  }

  return (
    <div className="calibration-page fade-in">
      <div className="page-header">
        <div>
          <h2 className="page-title">Interactive Calibration</h2>
          <p className="page-desc">Tune active region, pinch distance threshold, and gesture sensitivity</p>
        </div>
      </div>

      <div className="calib-container">
        {/* Step Progress Tracker */}
        <div className="calib-sidebar">
          <div className="steps-tracker">
            {steps.map((s, i) => {
              const stepNum = i + 1
              const isCompleted = stepNum < activeStepIdx
              const isCurrent = stepNum === activeStepIdx
              return (
                <div key={s.name} className={`step-item ${isCompleted ? 'completed' : ''} ${isCurrent ? 'current' : ''}`}>
                  <div className="step-icon-box">
                    {isCompleted ? '✓' : stepNum}
                  </div>
                  <div className="step-details">
                    <div className="step-title">{s.title}</div>
                    <div className="step-desc">{s.desc}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Interactive Workspace */}
        <div className="calib-main">
          <div className="calib-card">
            <div className="calib-header">
              <span className="step-badge">Backend Step: {stepName}</span>
              <h3>{steps[activeStepIdx - 1]?.title || 'Guided Calibration'}</h3>
            </div>

            <div className="calib-visual-stage">
              <div className="interaction-region-overlay">
                <div className="bounds-box">
                  <span className="corner top-left" />
                  <span className="corner top-right" />
                  <span className="corner bottom-left" />
                  <span className="corner bottom-right" />
                  <div className="region-info">
                    <span>
                      Region: {((calibStatus.region_right || 0.9) - (calibStatus.region_left || 0.1)).toFixed(2)}x
                    </span>
                  </div>
                </div>
                <div className="hand-tracker-point" style={{ left: '50%', top: '45%' }}>
                  <div className="point-dot" />
                  <div className="point-ripple" />
                </div>
              </div>
            </div>

            <div className="calib-actions">
              <button className="btn btn-primary" onClick={handleStartGuided}>
                {isCalibrating ? '⊕ Restart Backend Calibration' : '⊕ Start Backend Calibration'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
