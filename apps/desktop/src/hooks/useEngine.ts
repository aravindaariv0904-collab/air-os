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
  eye?: {
    face_present?: boolean
    ear?: number
    blink_count?: number
    triple_blink_count?: number
    last_event?: string
  }
  voice?: any
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

export interface VoiceStatus {
  state?: string
  enabled?: boolean
  wake_word?: string
  last_transcript?: string
  wake_count?: number
  tts_available?: boolean
  mic_available?: boolean
  error?: string
}

export interface ActionResult {
  ok?: boolean
  skill?: string
  message?: string
  verified?: boolean
  ambiguous?: boolean
  detail?: Record<string, unknown>
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
  const [voice, setVoice] = useState<VoiceStatus>({})
  const [lastAction, setLastAction] = useState<ActionResult | null>(null)

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
        window.airos?.settingsGet()
        window.airos?.voiceStatus()
      })

      const cleanupProfileList = window.airos.onProfileList((data: { profiles?: GestureProfile[] }) => {
        if (data?.profiles) setProfiles(data.profiles)
      })

      const cleanupSettings = window.airos.onSettings((data: { settings?: any }) => {
        if (data?.settings) setSettings(data.settings)
      })

      const cleanupVoice = window.airos.onVoiceStatus((data: any) => {
        const status = data?.status || data?.data || data
        if (status) setVoice(status)
      })

      const cleanupAction = window.airos.onActionResult((data: any) => {
        const result = data?.data || data
        if (result) setLastAction(result)
      })

      return () => {
        cleanupTelemetry?.()
        cleanupState?.()
        cleanupError?.()
        cleanupConnected?.()
        cleanupProfileList?.()
        cleanupSettings?.()
        cleanupVoice?.()
        cleanupAction?.()
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
            socket?.send(JSON.stringify({ type: 'control', command: 'voice_status' }))
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
              } else if (data.type === 'voice_status') {
                const status = payload?.status || payload?.data || payload
                if (status) setVoice(status)
              } else if (data.type === 'action_result') {
                const result = payload?.data || payload
                if (result) setLastAction(result)
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

  const voiceStart = useCallback(() => {
    if (window.airos) window.airos.voiceStart()
    else sendCommand('voice_start')
  }, [sendCommand])
  const voiceStop = useCallback(() => {
    if (window.airos) window.airos.voiceStop()
    else sendCommand('voice_stop')
  }, [sendCommand])
  const voiceStatus = useCallback(() => {
    if (window.airos) window.airos.voiceStatus()
    else sendCommand('voice_status')
  }, [sendCommand])
  const voiceCommand = useCallback((text: string) => {
    if (window.airos) window.airos.voiceCommand(text)
    else sendCommand('voice_text_command', { text })
  }, [sendCommand])
  const executeAction = useCallback((skill: string, params: Record<string, any> = {}) => {
    if (window.airos) window.airos.actionExecute(skill, params)
    else sendCommand('action_execute', { skill, params })
  }, [sendCommand])
  const takeScreenshot = useCallback((target: string = 'active') => {
    if (window.airos) window.airos.screenshotCapture(target)
    else sendCommand('screenshot_capture', { target })
  }, [sendCommand])

  return {
    telemetry,
    status,
    profiles,
    templates,
    settings,
    voice,
    lastAction,
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
    voiceStart,
    voiceStop,
    voiceStatus,
    voiceCommand,
    executeAction,
    takeScreenshot,
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
      settingsGet: () => void
      settingsUpdate: (settings: any) => void
      voiceStart: () => void
      voiceStop: () => void
      voiceStatus: () => void
      voiceCommand: (text: string) => void
      actionExecute: (skill: string, params: Record<string, any>) => void
      screenshotCapture: (target: string) => void
      minimize: () => void
      maximize: () => void
      close: () => void
      onTelemetry: (cb: (data: Telemetry) => void) => (() => void) | undefined
      onEngineState: (cb: (data: { state: string }) => void) => (() => void) | undefined
      onEngineError: (cb: (data: { message: string }) => void) => (() => void) | undefined
      onIPCConnected: (cb: () => void) => (() => void) | undefined
      onProfileList: (cb: (data: { profiles?: GestureProfile[] }) => void) => (() => void) | undefined
      onSettings: (cb: (data: { settings?: any }) => void) => (() => void) | undefined
      onVoiceStatus: (cb: (data: any) => void) => (() => void) | undefined
      onActionResult: (cb: (data: any) => void) => (() => void) | undefined
    }
  }
}
