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
})
