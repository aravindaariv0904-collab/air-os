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
  keyboard_state?: any
  calibration?: any
}

export interface EngineStatus {
  state: 'stopped' | 'starting' | 'ready' | 'running' | 'paused' | 'error'
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
  const [templates, setTemplates] = useState<any[]>([])
  const [settings, setSettings] = useState<any>(null)

  // Direct WebSocket connection for Web Browser mode or Electron mode
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
          socket = new WebSocket('ws://127.0.0.1:7890')

          socket.onopen = () => {
            setStatus({ state: 'running', connected: true })
            socket?.send(JSON.stringify({ type: 'control', command: 'profile_list' }))
            socket?.send(JSON.stringify({ type: 'control', command: 'gesture_list' }))
            socket?.send(JSON.stringify({ type: 'control', command: 'settings_get' }))
          }

          socket.onmessage = (event) => {
            try {
              const data = JSON.parse(event.data)
              const payload = data.payload || data
              if (data.type === 'telemetry') {
                setTelemetry(payload)
                if (payload.state) {
                  setStatus(prev => ({
                    ...prev,
                    state: payload.state.toLowerCase() === 'paused' ? 'paused' : 'running'
                  }))
                }
              } else if (data.type === 'profile_list') {
                if (payload.profiles) setProfiles(payload.profiles)
              } else if (data.type === 'gesture_list') {
                if (payload.templates) setTemplates(payload.templates)
              } else if (data.type === 'settings_data') {
                if (payload.settings) setSettings(payload.settings)
              } else if (data.type === 'engine_state') {
                if (payload.state) {
                  setStatus(prev => ({ ...prev, state: payload.state.toLowerCase() as EngineStatus['state'] }))
                }
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
        const ws = new WebSocket('ws://127.0.0.1:7890')
        ws.onopen = () => {
          ws.send(JSON.stringify({ type: 'control', command, payload: { command, ...extraData } }))
          setTimeout(() => ws.close(), 300)
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
  const updateSettings = useCallback((newSettings: any) => sendCommand('settings_update', { settings: newSettings }), [sendCommand])
  const recordGestureStart = useCallback(() => sendCommand('gesture_start_recording'), [sendCommand])
  const recordGestureFinish = useCallback((name: string) => sendCommand('gesture_finish_recording', { name }), [sendCommand])
  const deleteGesture = useCallback((id: string) => sendCommand('gesture_delete', { id }), [sendCommand])

  return {
    telemetry,
    status,
    profiles,
    templates,
    settings,
    start,
    stop,
    pause,
    resume,
    calibrate,
    setProfile,
    updateSettings,
    recordGestureStart,
    recordGestureFinish,
    deleteGesture,
  }
}

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
