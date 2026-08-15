/**
 * AirOS — Electron Preload Script
 * Safely exposes IPC methods to the renderer process via contextBridge.
 */

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('airos', {
  // Engine control
  startEngine: () => ipcRenderer.send('engine-start'),
  stopEngine: () => ipcRenderer.send('engine-stop'),
  pauseEngine: () => ipcRenderer.send('engine-pause'),
  resumeEngine: () => ipcRenderer.send('engine-resume'),
  calibrateEngine: () => ipcRenderer.send('engine-calibrate'),

  // Profiles
  profileList: () => ipcRenderer.send('engine-profile-list'),
  profileSet: (id) => ipcRenderer.send('engine-profile-set', id),

  // Settings
  settingsGet: () => ipcRenderer.send('engine-settings-get'),
  settingsUpdate: (settings) => ipcRenderer.send('engine-settings-update', settings),

  // Voice assistant
  voiceStart: () => ipcRenderer.send('engine-voice-start'),
  voiceStop: () => ipcRenderer.send('engine-voice-stop'),
  voiceStatus: () => ipcRenderer.send('engine-voice-status'),
  voiceCommand: (text) => ipcRenderer.send('engine-voice-command', text),

  // Desktop actions
  actionExecute: (skill, params) => ipcRenderer.send('engine-action-execute', { skill, params }),
  screenshotCapture: (target) => ipcRenderer.send('engine-screenshot', target),

  // Window control  
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),

  // Event listeners
  onTelemetry: (cb) => {
    ipcRenderer.on('telemetry', (_, data) => cb(data))
    return () => ipcRenderer.removeAllListeners('telemetry')
  },
  onEngineState: (cb) => {
    ipcRenderer.on('engine-state', (_, data) => cb(data))
    return () => ipcRenderer.removeAllListeners('engine-state')
  },
  onEngineError: (cb) => {
    ipcRenderer.on('engine-error', (_, data) => cb(data))
    return () => ipcRenderer.removeAllListeners('engine-error')
  },
  onIPCConnected: (cb) => {
    ipcRenderer.on('ipc-connected', (_, data) => cb(data))
    return () => ipcRenderer.removeAllListeners('ipc-connected')
  },
  onProfileList: (cb) => {
    ipcRenderer.on('profile-list', (_, data) => cb(data))
    return () => ipcRenderer.removeAllListeners('profile-list')
  },
  onSettings: (cb) => {
    ipcRenderer.on('settings-data', (_, data) => cb(data))
    return () => ipcRenderer.removeAllListeners('settings-data')
  },
  onVoiceStatus: (cb) => {
    ipcRenderer.on('voice-status', (_, data) => cb(data))
    return () => ipcRenderer.removeAllListeners('voice-status')
  },
  onActionResult: (cb) => {
    ipcRenderer.on('action-result', (_, data) => cb(data))
    return () => ipcRenderer.removeAllListeners('action-result')
  },
})
