/**
 * AirOS — Electron Main Process
 * Launches the Python engine, creates the BrowserWindow, and manages system tray.
 * Hardened for security: context isolation, sandboxing, CSP, navigation limits.
 */

const { app, BrowserWindow, Tray, Menu, ipcMain, shell, nativeImage, session } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const fs = require('fs')

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged
const PROJECT_ROOT = path.resolve(__dirname, '..', '..', '..') // air-os/
const PYTHON_EXE = path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe')
const ENGINE_SCRIPT = path.join(PROJECT_ROOT, 'run_engine.py')
const LOGS_DIR = path.join(PROJECT_ROOT, 'logs')
const IPC_PORT = 7890

let mainWindow = null
let tray = null
let engineProcess = null
let ws = null
let engineState = 'stopped'

function getEngineExecution() {
  const packagedExe = path.join(process.resourcesPath, 'AirOSEngine', 'AirOSEngine.exe')
  if (fs.existsSync(packagedExe)) {
    return { command: packagedExe, args: [], cwd: path.dirname(packagedExe) }
  }

  const distExe = path.join(PROJECT_ROOT, 'dist', 'AirOSEngine', 'AirOSEngine.exe')
  if (fs.existsSync(distExe)) {
    return { command: distExe, args: [], cwd: path.dirname(distExe) }
  }

  return { command: PYTHON_EXE, args: [ENGINE_SCRIPT], cwd: PROJECT_ROOT }
}

function startEngine() {
  if (engineProcess) return

  const execConfig = getEngineExecution()

  if (!fs.existsSync(execConfig.command)) {
    console.error('AirOS Engine executable not found:', execConfig.command)
    sendToRenderer('engine-error', { message: 'AirOS Engine executable not found.' })
    return
  }

  engineState = 'starting'
  console.log('Starting AirOS engine:', execConfig.command)
  updateTrayMenu()
  sendToRenderer('engine-state', { state: engineState })

  fs.mkdirSync(LOGS_DIR, { recursive: true })
  const logFile = fs.createWriteStream(path.join(LOGS_DIR, 'electron-engine.log'), { flags: 'a' })

  engineProcess = spawn(execConfig.command, execConfig.args, {
    cwd: execConfig.cwd,
    stdio: ['pipe', 'pipe', 'pipe'],
  })

  engineProcess.stdout.on('data', (chunk) => {
    logFile.write(chunk)
  })

  engineProcess.stderr.on('data', (chunk) => {
    logFile.write(chunk)
  })

  engineProcess.on('exit', (code) => {
    console.log(`Engine process exited with code ${code}`)
    engineProcess = null
    if (ws) {
      ws.close()
      ws = null
    }
    engineState = 'stopped'
    updateTrayMenu()
    sendToRenderer('engine-state', { state: engineState })
  })

  connectWebSocket()
}

function stopEngine() {
  if (engineProcess) {
    console.log('Stopping AirOS engine process...')
    sendEngineCommand('stop')
    setTimeout(() => {
      if (engineProcess) {
        try { engineProcess.kill('SIGTERM') } catch (e) {}
      }
    }, 1500)
  }
  if (ws) {
    ws.close()
    ws = null
  }
  engineState = 'stopped'
  updateTrayMenu()
  sendToRenderer('engine-state', { state: engineState })
}

function sendEngineCommand(command, extraData = {}) {
  if (ws && ws.readyState === 1 /* OPEN */) {
    ws.send(JSON.stringify({
      type: 'control',
      version: '1.0',
      payload: { command, ...extraData }
    }))
  }
}

function connectWebSocket() {
  const WebSocket = require('ws')

  const connect = () => {
    if (ws || !engineProcess) return
    ws = new WebSocket(`ws://127.0.0.1:${IPC_PORT}`)

    ws.on('open', () => {
      console.log('Connected to AirOS engine WebSocket')
      engineState = 'running'
      updateTrayMenu()
      sendToRenderer('engine-state', { state: engineState })
      sendToRenderer('ipc-connected', {})
    })

    ws.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString())
        const payload = msg.payload || msg
        if (msg.type === 'telemetry') {
          sendToRenderer('telemetry', payload)
        } else if (msg.type === 'profile_list') {
          sendToRenderer('profile-list', payload)
        } else if (msg.type === 'settings_data') {
          sendToRenderer('settings-data', payload)
        } else if (msg.type === 'engine_state') {
          engineState = payload.state || engineState
          updateTrayMenu()
          sendToRenderer('engine-state', { state: engineState })
        } else if (msg.type === 'voice_status') {
          sendToRenderer('voice-status', payload)
        } else if (msg.type === 'action_result') {
          sendToRenderer('action-result', payload)
        }
      } catch (e) {}
    })

    ws.on('close', () => {
      ws = null
      sendToRenderer('ipc-disconnected', {})
      if (engineProcess) {
        setTimeout(connect, 2000)
      }
    })

    ws.on('error', () => {
      ws = null
      if (engineProcess) {
        setTimeout(connect, 2000)
      }
    })
  }

  setTimeout(connect, 1000)
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 750,
    minWidth: 900,
    minHeight: 600,
    frame: false,
    transparent: false,
    backgroundColor: '#0f1117',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
    icon: path.join(__dirname, '..', 'public', 'icon.png'),
    show: false,
  })

  // Set CSP headers
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [
          "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self' ws://127.0.0.1:7890 ws://localhost:7890; img-src 'self' data:;"
        ]
      }
    })
  })

  // Prevent unexpected navigation or popups
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  mainWindow.webContents.on('will-navigate', (e) => {
    e.preventDefault()
  })

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.on('close', (e) => {
    if (tray) {
      e.preventDefault()
      mainWindow.hide()
    }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

function createTray() {
  const iconPath = path.join(__dirname, '..', 'public', 'icon16.png')
  let icon
  try {
    icon = nativeImage.createFromPath(iconPath)
  } catch {
    icon = nativeImage.createEmpty()
  }

  tray = new Tray(icon)
  tray.setToolTip('AirOS — Touchless Control')
  tray.on('double-click', showWindow)
  updateTrayMenu()
}

function updateTrayMenu() {
  if (!tray) return
  const menu = Menu.buildFromTemplate([
    { label: 'AirOS Dashboard', click: showWindow },
    { type: 'separator' },
    {
      label: 'Start AirOS',
      enabled: engineState === 'stopped' || engineState === 'error',
      click: () => { startEngine(); showWindow() }
    },
    {
      label: 'Pause',
      enabled: engineState === 'running',
      click: () => sendEngineCommand('pause')
    },
    {
      label: 'Resume',
      enabled: engineState === 'paused',
      click: () => sendEngineCommand('resume')
    },
    {
      label: 'Stop AirOS',
      enabled: engineState !== 'stopped',
      click: stopEngine
    },
    { type: 'separator' },
    { label: 'Exit', click: () => { stopEngine(); app.quit() } },
  ])
  tray.setContextMenu(menu)
  tray.setToolTip(`AirOS — ${engineState.toUpperCase()}`)
}

function showWindow() {
  if (!mainWindow) {
    createWindow()
  } else {
    mainWindow.show()
    mainWindow.focus()
  }
}

// IPC Handlers with sender validation
function validateSender(event) {
  return mainWindow && event.sender === mainWindow.webContents
}

ipcMain.on('engine-start', (event) => { if (validateSender(event)) startEngine() })
ipcMain.on('engine-stop', (event) => { if (validateSender(event)) stopEngine() })
ipcMain.on('engine-pause', (event) => { if (validateSender(event)) sendEngineCommand('pause') })
ipcMain.on('engine-resume', (event) => { if (validateSender(event)) sendEngineCommand('resume') })
ipcMain.on('engine-calibrate', (event) => { if (validateSender(event)) sendEngineCommand('calibrate') })
ipcMain.on('engine-profile-list', (event) => { if (validateSender(event)) sendEngineCommand('profile_list') })
ipcMain.on('engine-profile-set', (event, id) => {
  if (validateSender(event)) sendEngineCommand('profile_set', { id })
})
ipcMain.on('engine-settings-get', (event) => { if (validateSender(event)) sendEngineCommand('settings_get') })
ipcMain.on('engine-settings-update', (event, settings) => {
  if (validateSender(event)) sendEngineCommand('settings_update', { settings })
})
ipcMain.on('engine-voice-start', (event) => { if (validateSender(event)) sendEngineCommand('voice_start') })
ipcMain.on('engine-voice-stop', (event) => { if (validateSender(event)) sendEngineCommand('voice_stop') })
ipcMain.on('engine-voice-status', (event) => { if (validateSender(event)) sendEngineCommand('voice_status') })
ipcMain.on('engine-voice-command', (event, text) => {
  if (validateSender(event)) sendEngineCommand('voice_text_command', { text })
})
ipcMain.on('engine-action-execute', (event, data) => {
  if (validateSender(event)) sendEngineCommand('action_execute', { skill: data?.skill, params: data?.params })
})
ipcMain.on('engine-screenshot', (event, target) => {
  if (validateSender(event)) sendEngineCommand('screenshot_capture', { target: target || 'active' })
})
ipcMain.on('window-minimize', (event) => { if (validateSender(event)) mainWindow?.minimize() })
ipcMain.on('window-maximize', (event) => {
  if (validateSender(event)) {
    if (mainWindow?.isMaximized()) mainWindow.unmaximize()
    else mainWindow?.maximize()
  }
})
ipcMain.on('window-close', (event) => { if (validateSender(event)) mainWindow?.hide() })

function sendToRenderer(channel, data) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, data)
  }
}

app.whenReady().then(() => {
  createWindow()
  createTray()
  if (isDev) {
    setTimeout(startEngine, 1500)
  }
})

app.on('window-all-closed', () => {})

app.on('activate', () => {
  if (!mainWindow) createWindow()
})

app.on('before-quit', () => {
  stopEngine()
  tray?.destroy()
})
