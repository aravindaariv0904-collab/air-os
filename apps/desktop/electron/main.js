/**
 * AirOS — Electron Main Process
 * Launches the Python engine, creates the BrowserWindow, and manages system tray.
 */

const { app, BrowserWindow, Tray, Menu, ipcMain, shell, nativeImage } = require('electron')
const path = require('path')
const { spawn, execSync } = require('child_process')
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
let ws = null // WebSocket to Python engine
let engineState = 'stopped' // 'stopped' | 'starting' | 'running' | 'paused' | 'error'

function getEngineExecution() {
  // 1. Packaged production executable in extraResources
  const packagedExe = path.join(process.resourcesPath, 'AirOSEngine', 'AirOSEngine.exe')
  if (fs.existsSync(packagedExe)) {
    return { command: packagedExe, args: [], cwd: path.dirname(packagedExe) }
  }

  // 2. Standalone compiled engine in project dist/
  const distExe = path.join(PROJECT_ROOT, 'dist', 'AirOSEngine', 'AirOSEngine.exe')
  if (fs.existsSync(distExe)) {
    return { command: distExe, args: [], cwd: path.dirname(distExe) }
  }

  // 3. Fallback to venv for development
  return { command: PYTHON_EXE, args: [ENGINE_SCRIPT], cwd: PROJECT_ROOT }
}

function startEngine() {
  if (engineProcess) return

  const execConfig = getEngineExecution()

  if (!fs.existsSync(execConfig.command)) {
    console.error('AirOS Engine executable/python not found:', execConfig.command)
    sendToRenderer('engine-error', { message: 'AirOS Engine not found.' })
    return
  }

  engineState = 'starting'
  console.log('Starting AirOS engine:', execConfig.command)

  fs.mkdirSync(LOGS_DIR, { recursive: true })
  const logFile = fs.createWriteStream(path.join(LOGS_DIR, 'electron-engine.log'), { flags: 'a' })

  engineProcess = spawn(execConfig.command, execConfig.args, {
    cwd: execConfig.cwd,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env },
  })

  engineProcess.stdout.on('data', (data) => {
    const msg = data.toString()
    logFile.write(msg)
    if (msg.includes('pipeline started') || msg.includes('RESUMED')) {
      engineState = 'running'
      connectWebSocket()
      updateTrayMenu()
      sendToRenderer('engine-state', { state: engineState })
    }
  })

  engineProcess.stderr.on('data', (data) => {
    logFile.write(data.toString())
  })

  engineProcess.on('exit', (code) => {
    console.log(`Engine exited with code ${code}`)
    engineProcess = null
    engineState = 'stopped'
    if (ws) { ws.close(); ws = null }
    updateTrayMenu()
    sendToRenderer('engine-state', { state: engineState })
  })

  engineProcess.on('error', (err) => {
    console.error('Engine process error:', err)
    engineState = 'error'
    sendToRenderer('engine-error', { message: err.message })
  })
}

function stopEngine() {
  if (engineProcess) {
    engineProcess.kill('SIGTERM')
    engineProcess = null
  }
  if (ws) { ws.close(); ws = null }
  engineState = 'stopped'
  updateTrayMenu()
  sendToRenderer('engine-state', { state: engineState })
}

function sendEngineCommand(command) {
  if (ws && ws.readyState === 1 /* OPEN */) {
    ws.send(JSON.stringify({ type: 'control', command }))
  }
}

// ─── WebSocket Connection to Python Engine ───────────────────────────────────

function connectWebSocket() {
  const WebSocket = require('ws')
  
  const connect = () => {
    if (ws) return
    ws = new WebSocket(`ws://localhost:${IPC_PORT}`)
    
    ws.on('open', () => {
      console.log('Connected to AirOS engine WebSocket')
      sendToRenderer('ipc-connected', {})
    })
    
    ws.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString())
        if (msg.type === 'telemetry') {
          sendToRenderer('telemetry', msg)
        } else if (msg.type === 'profile_list') {
          sendToRenderer('profile-list', msg)
        }
      } catch (e) {}
    })
    
    ws.on('close', () => {
      ws = null
      sendToRenderer('ipc-disconnected', {})
      // Reconnect after 2s if engine still running
      if (engineProcess) {
        setTimeout(connect, 2000)
      }
    })
    
    ws.on('error', (err) => {
      ws = null
      if (engineProcess) {
        setTimeout(connect, 3000)
      }
    })
  }
  
  // Wait a second for engine to start WebSocket server
  setTimeout(connect, 1000)
}

// ─── Window Management ───────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 750,
    minWidth: 900,
    minHeight: 600,
    frame: false,        // Custom title bar
    transparent: false,
    backgroundColor: '#0f1117',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    icon: path.join(__dirname, '..', 'public', 'icon.png'),
    show: false,
  })

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    // mainWindow.webContents.openDevTools()
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

// ─── System Tray ─────────────────────────────────────────────────────────────

function createTray() {
  // Use a simple PNG icon (create placeholder if not exists)
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

// ─── IPC Handlers (Renderer → Main) ─────────────────────────────────────────

ipcMain.on('engine-start', () => startEngine())
ipcMain.on('engine-stop', () => stopEngine())
ipcMain.on('engine-pause', () => sendEngineCommand('pause'))
ipcMain.on('engine-resume', () => sendEngineCommand('resume'))
ipcMain.on('engine-calibrate', () => sendEngineCommand('calibrate'))
ipcMain.on('engine-profile-list', () => sendEngineCommand('profile_list'))
ipcMain.on('engine-profile-set', (event, id) => {
  if (ws && ws.readyState === 1) {
    ws.send(JSON.stringify({ type: 'control', command: 'profile_set', data: { id } }))
  }
})
ipcMain.on('window-minimize', () => mainWindow?.minimize())
ipcMain.on('window-maximize', () => {
  if (mainWindow?.isMaximized()) mainWindow.unmaximize()
  else mainWindow?.maximize()
})
ipcMain.on('window-close', () => mainWindow?.hide())

function sendToRenderer(channel, data) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, data)
  }
}

// ─── App Lifecycle ───────────────────────────────────────────────────────────

app.whenReady().then(() => {
  createWindow()
  createTray()
  // Auto-start engine in development
  if (isDev) {
    setTimeout(startEngine, 1500)
  }
})

app.on('window-all-closed', () => {
  // Don't quit — keep running in tray
})

app.on('activate', () => {
  if (!mainWindow) createWindow()
})

app.on('before-quit', () => {
  stopEngine()
  tray?.destroy()
})
