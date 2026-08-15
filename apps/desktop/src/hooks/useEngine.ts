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
  const wsRef = useState<WebSocket | null>(null)

  // Direct WebSocket connection for Web Browser mode
  useEffect(() => {
    if (window.airos) {
      // Electron mode
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
    } else {
      // Standalone Web Browser mode — connect directly to WebSocket server
      let socket: WebSocket | null = null
      let reconnectTimer: any = null

      const connectWS = () => {
        try {
          socket = new WebSocket('ws://localhost:7890')

          socket.onopen = () => {
            setStatus({ state: 'running', connected: true })
            socket?.send(JSON.stringify({ type: 'control', command: 'profile_list' }))
          }

          socket.onmessage = (event) => {
            try {
              const data = JSON.parse(event.data)
              if (data.type === 'telemetry') {
                setTelemetry(data)
                if (data.state) {
                  setStatus(prev => ({
                    ...prev,
                    state: data.state.toLowerCase() === 'paused' ? 'paused' : 'running'
                  }))
                }
              } else if (data.type === 'profile_list') {
                if (data.profiles) setProfiles(data.profiles)
              }
            } catch (e) {
              console.error('IPC parse error:', e)
            }
          }

          socket.onclose = () => {
            setStatus({ state: 'stopped', connected: false })
            reconnectTimer = setTimeout(connectWS, 2000)
          }

          socket.onerror = () => {
            socket?.close()
          }
        } catch (e) {
          reconnectTimer = setTimeout(connectWS, 3000)
        }
      }

      connectWS()

      return () => {
        if (reconnectTimer) clearTimeout(reconnectTimer)
        if (socket) socket.close()
      }
    }
  }, [])

  const sendCommand = useCallback((command: string, extraData: Record<string, any> = {}) => {
    if (window.airos) {
      if (command === 'start') window.airos.startEngine()
      else if (command === 'stop') window.airos.stopEngine()
      else if (command === 'pause') window.airos.pauseEngine()
      else if (command === 'resume') window.airos.resumeEngine()
      else if (command === 'calibrate') window.airos.calibrateEngine()
      else if (command === 'profile_set') window.airos.profileSet(extraData.id)
    } else {
      try {
        const ws = new WebSocket('ws://localhost:7890')
        ws.onopen = () => {
          ws.send(JSON.stringify({ type: 'control', command, ...extraData }))
          setTimeout(() => ws.close(), 500)
        }
      } catch (e) {
        console.error('Failed to send command over WS:', e)
      }
    }
  }, [])

  const start = useCallback(() => sendCommand('start'), [sendCommand])
  const stop = useCallback(() => sendCommand('stop'), [sendCommand])
  const pause = useCallback(() => sendCommand('pause'), [sendCommand])
  const resume = useCallback(() => sendCommand('resume'), [sendCommand])
  const calibrate = useCallback(() => sendCommand('calibrate'), [sendCommand])
  const setProfile = useCallback((id: string) => sendCommand('profile_set', { id }), [sendCommand])

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
