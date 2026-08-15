import React, { useState } from 'react'
import { useEngine } from '../../hooks/useEngine'
import './Calibration.css'

export default function Calibration() {
  const { telemetry, calibrate } = useEngine()
  const [activeStep, setActiveStep] = useState(1)

  const steps = [
    { step: 1, title: 'Camera Check', desc: 'Verify camera feed and resolution', icon: '📷' },
    { step: 2, title: 'Hand Positioning', desc: 'Sit at comfortable distance (50-80cm)', icon: '🧍' },
    { step: 3, title: 'Hand Detection', desc: 'Raise primary hand in front of camera', icon: '✋' },
    { step: 4, title: 'Interaction Bounds', desc: 'Move hand to extreme corners of your range', icon: '📐' },
    { step: 5, title: 'Pinch Calibration', desc: 'Pinch index and thumb 3 times', icon: '🤏' },
    { step: 6, title: 'Complete', desc: 'Profile saved to %APPDATA%/AirOS', icon: '✅' },
  ]

  const handleStartGuided = () => {
    calibrate()
    setActiveStep(2)
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
            {steps.map(s => {
              const isCompleted = s.step < activeStep
              const isCurrent = s.step === activeStep
              return (
                <div key={s.step} className={`step-item ${isCompleted ? 'completed' : ''} ${isCurrent ? 'current' : ''}`}>
                  <div className="step-icon-box">
                    {isCompleted ? '✓' : s.step}
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
              <span className="step-badge">Step {activeStep} of {steps.length}</span>
              <h3>{steps[activeStep - 1].title}</h3>
            </div>

            <div className="calib-visual-stage">
              <div className="interaction-region-overlay">
                <div className="bounds-box">
                  <span className="corner top-left" />
                  <span className="corner top-right" />
                  <span className="corner bottom-left" />
                  <span className="corner bottom-right" />
                  <div className="region-info">
                    <span>Region: {((telemetry as any)?.calibration?.region_right - (telemetry as any)?.calibration?.region_left || 0.8).toFixed(2)}x</span>
                  </div>
                </div>
                <div className="hand-tracker-point" style={{ left: '50%', top: '45%' }}>
                  <div className="point-dot" />
                  <div className="point-ripple" />
                </div>
              </div>
            </div>

            <div className="calib-actions">
              {activeStep > 1 && (
                <button className="btn btn-ghost" onClick={() => setActiveStep(prev => Math.max(1, prev - 1))}>
                  ← Back
                </button>
              )}
              {activeStep < steps.length ? (
                <button className="btn btn-primary" onClick={() => {
                  if (activeStep === 1) handleStartGuided()
                  else setActiveStep(prev => prev + 1)
                }}>
                  {activeStep === 1 ? 'Start Guided Calibration' : 'Next Step →'}
                </button>
              ) : (
                <button className="btn btn-primary" onClick={() => setActiveStep(1)}>
                  Finish & Save Profile
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
