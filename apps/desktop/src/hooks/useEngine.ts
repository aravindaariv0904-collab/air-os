import { useState, useEffect, useCallback } from 'react'

export interface Telemetry {
  type: string
  timestamp: number
  state: string
  gesture: string
  confidence: number
  hands: number
  fps: { current: number; avg: number; min: number; dropped: number }
  latency: { capture_ms: number; inference_ms: number; gesture_ms: number; total_ms: number }
  system: { cpu_percent: number; ram_mb: number }
  enabled: boolean
  profile?: string
  foreground_app?: string
}

export interface EngineStatus {
  state: 'stopped' | 'starting' | 'running' | 'paused' | 'error'
  connected: boolean
  error?: string
}

export interface GestureProfile {
  id: string
  name: string
  active: boolean
  app_matchers: string[]
  gesture_overrides: Record<string, unknown>
}

const INITIAL_TELEMETRY: Telemetry = {
  type: 'telemetry',
  timestamp: 0,
  state: 'IDLE',
  gesture: 'NONE',
  confidence: 0,
  hands: 0,
  fps: { current: 0, avg: 0, min: 0, dropped: 0 },
  latency: { capture_ms: 0, inference_ms: 0, gesture_ms: 0, total_ms: 0 },
  system: { cpu_percent: 0, ram_mb: 0 },
  enabled: false,
}

export function useEngine() {
  const [telemetry, setTelemetry] = useState<Telemetry>(INITIAL_TELEMETRY)
  const [status, setStatus] = useState<EngineStatus>({
    state: 'stopped',
    connected: false,
  })
  const [profiles, setProfiles] = useState<GestureProfile[]>([])

  useEffect(() => {
    if (!window.airos) return

    const cleanupTelemetry = window.airos.onTelemetry((data: Telemetry) => {
      setTelemetry(data)
    })

    const cleanupState = window.airos.onEngineState((data: { state: string }) => {
      setStatus(prev => ({ ...prev, state: data.state as EngineStatus['state'] }))
    })

    const cleanupError = window.airos.onEngineError((data: { message: string }) => {
      setStatus(prev => ({ ...prev, state: 'error', error: data.message }))
    })

    const cleanupConnected = window.airos.onIPCConnected(() => {
      setStatus(prev => ({ ...prev, connected: true }))
      window.airos?.profileList()
    })

    const cleanupProfileList = window.airos.onProfileList((data: { profiles?: GestureProfile[] }) => {
      if (data?.profiles) setProfiles(data.profiles)
    })

    return () => {
      cleanupTelemetry?.()
      cleanupState?.()
      cleanupError?.()
      cleanupConnected?.()
      cleanupProfileList?.()
    }
  }, [])

  const start = useCallback(() => window.airos?.startEngine(), [])
  const stop = useCallback(() => window.airos?.stopEngine(), [])
  const pause = useCallback(() => window.airos?.pauseEngine(), [])
  const resume = useCallback(() => window.airos?.resumeEngine(), [])
  const calibrate = useCallback(() => window.airos?.calibrateEngine(), [])
  const setProfile = useCallback((id: string) => window.airos?.profileSet(id), [])

  return { telemetry, status, profiles, start, stop, pause, resume, calibrate, setProfile }
}

// Type declarations for window.airos
declare global {
  interface Window {
    airos?: {
      startEngine: () => void
      stopEngine: () => void
      pauseEngine: () => void
      resumeEngine: () => void
      calibrateEngine: () => void
      profileList: () => void
      profileSet: (id: string) => void
      minimize: () => void
      maximize: () => void
      close: () => void
      onTelemetry: (cb: (data: Telemetry) => void) => (() => void) | undefined
      onEngineState: (cb: (data: { state: string }) => void) => (() => void) | undefined
      onEngineError: (cb: (data: { message: string }) => void) => (() => void) | undefined
      onIPCConnected: (cb: () => void) => (() => void) | undefined
      onProfileList: (cb: (data: { profiles?: GestureProfile[] }) => void) => (() => void) | undefined
    }
  }
}
